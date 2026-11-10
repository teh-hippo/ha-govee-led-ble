from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
from homeassistant.util.yaml import load_yaml

_REPO = Path(__file__).parents[1]
_SOURCE_SHA = "a" * 40


def _step_script(workflow_name: str, step_name: str) -> str:
    workflow = load_yaml(_REPO / ".github/workflows" / workflow_name)
    assert isinstance(workflow, dict)
    return next(
        str(step["run"])
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
        if step.get("name", step.get("id")) == step_name
    )


def _run(script: str, root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - repository workflow exercised against local command stubs
        ["/usr/bin/bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.parametrize(
    ("version", "accepted"),
    [("1.2.3", False), ("1.2.3-rc.4.branch", False), ("1.2.3-pr-145.4", True), ("1.2.3-pr-146.4", False)],
)
def test_pr_candidate_cannot_publish_stable(tmp_path: Path, version: str, accepted: bool) -> None:
    (tmp_path / "selected-pr.json").write_text(
        json.dumps(
            {
                "number": 145,
                "headRefName": "feature",
                "baseRefName": "master",
                "isCrossRepository": False,
                "state": "OPEN",
            }
        )
    )
    (tmp_path / "hacs.json").write_text('{"zip_release": true, "filename": "ha_govee_led_ble.zip"}')
    output = tmp_path / "output"
    env = {
        **os.environ,
        "INPUT_SHA": _SOURCE_SHA,
        "INPUT_VERSION": version,
        "INPUT_NOTES": "Candidate for testing.",
        "BRANCH": "feature",
        "GITHUB_OUTPUT": str(output),
    }

    result = _run(_step_script("prerelease.yml", "defaults"), tmp_path, env)

    assert (result.returncode == 0) is accepted, result.stderr
    if accepted:
        assert f"version={version}\n" in output.read_text()
        assert "package_version=1.2.3-rc.4.pr-145\n" in output.read_text()
    else:
        assert output.read_text() == ""
        assert "publish stable through the Release workflow" in result.stderr


@pytest.mark.parametrize("new_commit", [False, True])
def test_pr_candidate_revision_reuses_exact_sha_or_advances(tmp_path: Path, new_commit: bool) -> None:
    (tmp_path / "selected-pr.json").write_text(
        json.dumps(
            {
                "number": 145,
                "headRefName": "feature",
                "baseRefName": "master",
                "isCrossRepository": False,
                "state": "OPEN",
            }
        )
    )
    (tmp_path / "hacs.json").write_text('{"zip_release": true, "filename": "ha_govee_led_ble.zip"}')
    manifest = tmp_path / "custom_components/ha_govee_led_ble/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version": "1.2.2"}')
    setup = _run(
        "git init -b feature; git config user.name Fixture; git config user.email fixture@example.invalid; "
        "git config tag.gpgsign false; git config core.hooksPath /dev/null; "
        "git -c commit.gpgsign=false commit --allow-empty -m 'fix: preview'; "
        "git tag v1.2.3-pr-145.1; git tag v1.2.3-pr-146.99",
        tmp_path,
        dict(os.environ),
    )
    assert setup.returncode == 0, setup.stderr
    if new_commit:
        result = _run(
            "git -c commit.gpgsign=false commit --allow-empty -m 'fix: next preview'", tmp_path, dict(os.environ)
        )
        assert result.returncode == 0, result.stderr
    output = tmp_path / "output"
    env = {
        **os.environ,
        "INPUT_SHA": "",
        "INPUT_VERSION": "",
        "INPUT_NOTES": "",
        "BRANCH": "feature",
        "GITHUB_OUTPUT": str(output),
    }

    result = _run(_step_script("prerelease.yml", "defaults"), tmp_path, env)

    assert result.returncode == 0, result.stderr
    assert f"version=1.2.3-pr-145.{2 if new_commit else 1}\n" in output.read_text()


def test_master_release_excludes_only_local_pr_preview_tags(tmp_path: Path) -> None:
    setup = _run(
        "git init -b master; git config user.name Fixture; git config user.email fixture@example.invalid; "
        "git config tag.gpgsign false; git config core.hooksPath /dev/null; "
        "git -c commit.gpgsign=false commit --allow-empty -m 'fix: preview'; "
        "git tag v1.2.2; git tag v1.2.3-rc.1; git tag v1.2.3-pr-145.1",
        tmp_path,
        dict(os.environ),
    )
    assert setup.returncode == 0, setup.stderr

    result = _run(
        _step_script("release.yml", "Exclude PR previews from master release history"), tmp_path, dict(os.environ)
    )

    assert result.returncode == 0, result.stderr
    tags = _run("git tag --list", tmp_path, dict(os.environ))
    assert set(tags.stdout.splitlines()) == {"v1.2.2", "v1.2.3-rc.1"}


@pytest.mark.parametrize(
    ("remote_sha", "conclusion", "accepted"),
    [
        (_SOURCE_SHA, "success", True),
        ("b" * 40, "success", False),
        (_SOURCE_SHA, "failure", False),
        (_SOURCE_SHA, "", False),
    ],
)
def test_master_release_requires_current_validated_commit(
    tmp_path: Path, remote_sha: str, conclusion: str, accepted: bool
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        'if [[ "$1" == ls-remote ]]; then\n'
        '  printf "%s\\trefs/heads/master\\n" "$REMOTE_SHA"\n'
        'elif [[ "$*" == "checkout -B master $SOURCE_SHA" ]]; then\n'
        '  touch "$CHECKED_OUT"\n'
        "else\n  exit 1\nfi\n"
    )
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        '[[ "$*" == *"--branch master --commit $SOURCE_SHA"* ]]\n'
        'printf "%s\\n" "$VALIDATE_CONCLUSION"\n'
    )
    git.chmod(0o755)
    gh.chmod(0o755)
    checked_out = tmp_path / "checked-out"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "SOURCE_SHA": _SOURCE_SHA,
        "REMOTE_SHA": remote_sha,
        "VALIDATE_CONCLUSION": conclusion,
        "GITHUB_REPOSITORY": "example/release-fixture",
        "CHECKED_OUT": str(checked_out),
    }

    result = _run(_step_script("release.yml", "Require current, validated master"), tmp_path, env)

    assert (result.returncode == 0) is accepted, result.stdout + result.stderr
    assert checked_out.exists() is accepted


@pytest.mark.parametrize(("event", "candidate"), [("workflow_run", True), ("workflow_dispatch", False)])
def test_automatic_master_publication_cannot_publish_stable(tmp_path: Path, event: str, candidate: bool) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uvx = bin_dir / "uvx"
    uvx.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$ARGUMENTS"\n')
    uvx.chmod(0o755)
    arguments = tmp_path / "arguments"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RELEASE_EVENT": event,
        "ARGUMENTS": str(arguments),
    }

    result = _run(_step_script("release.yml", "Python Semantic Release"), tmp_path, env)

    assert result.returncode == 0, result.stderr
    args = arguments.read_text().splitlines()
    assert ("--as-prerelease" in args) is candidate
    assert "--no-vcs-release" in args


def _publisher_env(tmp_path: Path, tag_state: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(
        """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
with Path(os.environ["CALLS"]).open("a") as calls:
    calls.write(json.dumps(args) + "\\n")
state = Path(os.environ["TAG_STATE"])
if args[0] == "api":
    if "--method" in args:
        state.write_text("same")
    elif "/git/tags/" in args[1]:
        print(json.dumps({"object": {"type": "commit", "sha": os.environ["TARGET_SHA"]}}))
    else:
        value = state.read_text()
        if value in ("missing", "forbidden"):
            print("HTTP 404" if value == "missing" else "HTTP 403", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({"object": {
            "type": "tag" if value == "annotated" else "commit",
            "sha": "b" * 40 if value == "different" else os.environ["TARGET_SHA"],
        }}))
else:
    attempted = Path(os.environ["ATTEMPTED"])
    if os.environ.get("FAIL_ONCE") == "true" and not attempted.exists():
        attempted.touch()
        print("Simulated upload failure", file=sys.stderr)
        sys.exit(1)
"""
    )
    gh.chmod(0o755)
    (tmp_path / "tag-state").write_text(tag_state)
    (tmp_path / "notes.md").write_text("Approved release notes.")
    (tmp_path / "package.zip").write_bytes(b"verified fixture")
    return {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS": str(tmp_path / "calls"),
        "TAG_STATE": str(tmp_path / "tag-state"),
        "ATTEMPTED": str(tmp_path / "attempted"),
        "TARGET_SHA": _SOURCE_SHA,
        "GITHUB_REPOSITORY": "example/release-fixture",
        "PUBLISH_SCRIPT": str(_REPO / "scripts/publish-release.sh"),
        "IS_PRERELEASE": "true",
    }


_PUBLISH = 'bash "$PUBLISH_SCRIPT" v1.2.3-pr-145.1 "$TARGET_SHA" "$IS_PRERELEASE" notes.md package.zip'


@pytest.mark.parametrize(
    ("tag_state", "accepted"),
    [("missing", True), ("same", True), ("annotated", True), ("different", False), ("forbidden", False)],
)
def test_publication_never_retargets_existing_tag(tmp_path: Path, tag_state: str, accepted: bool) -> None:
    env = _publisher_env(tmp_path, tag_state)

    result = _run(_PUBLISH, tmp_path, env)

    assert (result.returncode == 0) is accepted, result.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert any(call[:2] == ["release", "create"] for call in calls) is accepted
    assert any("--method" in call for call in calls) is (tag_state == "missing")


def test_publication_retry_resumes_after_tag_creation(tmp_path: Path) -> None:
    env = {**_publisher_env(tmp_path, "missing"), "FAIL_ONCE": "true"}

    first = _run(_PUBLISH, tmp_path, env)
    retry = _run(_PUBLISH, tmp_path, env)

    assert first.returncode != 0
    assert retry.returncode == 0, retry.stderr
    calls = [json.loads(line) for line in (tmp_path / "calls").read_text().splitlines()]
    assert sum("--method" in call for call in calls) == 1
    assert sum(call[:2] == ["release", "create"] for call in calls) == 2


@pytest.mark.parametrize("prerelease", ["true", "false"])
def test_only_stable_publication_sets_latest(tmp_path: Path, prerelease: str) -> None:
    env = {**_publisher_env(tmp_path, "same"), "IS_PRERELEASE": prerelease}

    result = _run(_PUBLISH, tmp_path, env)

    assert result.returncode == 0, result.stderr
    args = json.loads((tmp_path / "calls").read_text().splitlines()[-1])
    assert f"--prerelease={prerelease}" in args
    assert f"--latest={'false' if prerelease == 'true' else 'true'}" in args
    assert args[:2] == ["release", "create"]
    assert "--verify-tag" in args
