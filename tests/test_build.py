from __future__ import annotations

import os
import shutil
import stat
import subprocess
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.package import verify_archive

_REPO = Path(__file__).parents[1]
_BUILD_FILES = (
    "Makefile",
    ".node-version",
    "mise.toml",
    "scripts/generate-frontend.sh",
    "scripts/generate-kaitai.sh",
    "scripts/package.py",
)
_CONTRACT_FILES = (
    "const.py",
    "effect_catalogue.py",
    "effect_contracts.py",
    "effect_deployments.py",
    "effect_domain.py",
    "effect_identity.py",
    "effect_migration.py",
    "effect_preview.py",
    "effect_scene_defaults.py",
    "effect_scenes.py",
    "effect_storage.py",
    "effect_template_defaults.py",
    "effect_websocket_payloads.py",
    "scenes.py",
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _executable(path: Path, content: str) -> None:
    _write(path, content)
    path.chmod(0o755)


@pytest.fixture
def build_repo(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    root = tmp_path / "repo"
    for relative in _BUILD_FILES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_REPO / relative, destination)

    _write(root / "scripts/kaitai-runtime-roots.txt", "sample\n")
    _write(root / "scripts/kaitai-runtime-outputs.txt", "__init__.py\nsample.py\n")
    _write(root / "tools/ble/kaitai/sample.ksy", "meta:\n  id: sample\n")
    _write(root / "tools/ble/kaitai/shared.ksy", "meta:\n  id: shared\n")

    integration = root / "custom_components/ha_govee_led_ble"
    _write(integration / "__init__.py", 'DOMAIN = "ha_govee_led_ble"\n')
    _write(integration / "manifest.json", '{"domain":"ha_govee_led_ble","version":"1.0.0"}\n')
    _write(integration / "py.typed", "")
    _write(integration / "scene_catalogues/H617A.json", '{"scenes":[]}\n')
    _write(integration / "frontend/editor-loader.js", "export const loader = true;\n")
    _write(integration / "frontend/editor.js", "export const fallback = true;\n")
    _write(integration / "__pycache__/ignored.pyc", "cache")
    _write(integration / ".cache/ignored", "cache")
    for filename in _CONTRACT_FILES:
        _write(integration / filename, "\n")

    _write(root / "frontend/src/panel.ts", 'export const panel = "fixture";\n')
    _write(root / "frontend/src/contracts.ts", "export const API_VERSION = 1;\n")
    _write(root / "frontend/package.json", '{"name":"fixture","private":true}\n')
    _write(root / "frontend/package-lock.json", '{"name":"fixture","lockfileVersion":3}\n')
    _write(root / "frontend/tsconfig.json", "{}\n")
    _write(root / "frontend/vite.config.ts", "export default {};\n")
    _write(root / "frontend/vite.dev.config.ts", "export default {};\n")
    _write(root / "frontend/vitest.config.ts", "export default {};\n")
    _write(root / "frontend/tests/fixtures/backend-contracts.json", "{}\n")
    _write(root / "tools/generate_frontend_contract_fixtures.py", "\n")

    bin_dir = root / "test-bin"
    _executable(
        bin_dir / "node",
        """#!/usr/bin/env bash
set -euo pipefail
printf 'v24.19.0\\n'
""",
    )
    _executable(
        bin_dir / "kaitai-struct-compiler",
        """#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

if "--version" in sys.argv:
    print("kaitai-struct-compiler 0.11")
    raise SystemExit

output = Path(sys.argv[sys.argv.index("--outdir") + 1])
output.mkdir(parents=True, exist_ok=True)
inputs = [Path(value) for value in sys.argv if value.endswith(".ksy")]
digest = hashlib.sha256(b"".join(path.read_bytes() for path in inputs)).hexdigest()
for path in inputs:
    (output / f"{path.stem}.py").write_text(f'BUILD = "{digest}"\\n', encoding="utf-8")
""",
    )
    _executable(
        bin_dir / "npm",
        """#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

root = Path.cwd()
if "--version" in sys.argv:
    print("11.17.0")
    raise SystemExit
if "ci" in sys.argv:
    destination = root / "frontend/node_modules/.package-lock.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "frontend/package-lock.json", destination)
    raise SystemExit
if "build" not in sys.argv:
    raise SystemExit(f"unsupported npm invocation: {sys.argv[1:]}")
output = Path(os.environ["FRONTEND_OUT_DIR"])
output.mkdir(parents=True, exist_ok=True)
source = b"".join(path.read_bytes() for path in sorted((root / "frontend/src").glob("*.ts")))
digest = hashlib.sha256(source).hexdigest()[:8]
(output / "effect-studio-bootstrap.js").write_text(f'export const build = "{digest}";\\n', encoding="utf-8")
(output / "manifest.json").write_text(
    json.dumps(
        {"bootstrap": "effect-studio-bootstrap.js", "chunks": []},
        indent=2,
    ) + "\\n",
    encoding="utf-8",
)
""",
    )
    _executable(
        bin_dir / "uv",
        """#!/usr/bin/env bash
set -euo pipefail
exit 0
""",
    )

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return root, env


def _make(root: Path, env: dict[str, str], *targets: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/make", "--no-print-directory", *targets],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    return result


def _generated_files(root: Path) -> list[Path]:
    integration = root / "custom_components/ha_govee_led_ble"
    frontend = integration / "frontend"
    return [
        integration / "generated_protocol/__init__.py",
        integration / "generated_protocol/sample.py",
        frontend / "effect-studio-bootstrap.js",
        frontend / "manifest.json",
    ]


def _make_fails(root: Path, env: dict[str, str], *targets: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603
        ["/usr/bin/make", "--no-print-directory", *targets],
        cwd=root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0, f"{result.stdout}\n{result.stderr}"
    return result


def test_build_is_incremental_and_rebuilds_missing_outputs(build_repo: tuple[Path, dict[str, str]]) -> None:
    root, env = build_repo
    _make(root, env, "build")
    generated = _generated_files(root)
    mtimes = {path.relative_to(root): path.stat().st_mtime_ns for path in generated}

    _make(root, env, "build")
    assert {path.relative_to(root): path.stat().st_mtime_ns for path in generated} == mtimes

    protocol = root / "custom_components/ha_govee_led_ble/generated_protocol/sample.py"
    protocol_content = protocol.read_bytes()
    protocol.unlink()
    _make(root, env, "protocol")
    assert protocol.read_bytes() == protocol_content

    frontend = root / "custom_components/ha_govee_led_ble/frontend"
    bootstrap = frontend / "effect-studio-bootstrap.js"
    bootstrap_content = bootstrap.read_bytes()
    bootstrap.unlink()
    _make(root, env, "frontend")
    assert bootstrap.read_bytes() == bootstrap_content

    protocol_source = root / "tools/ble/kaitai/sample.ksy"
    protocol_source.write_text("meta:\n  id: sample\nseq: []\n", encoding="utf-8")
    _make(root, env, "protocol")
    assert protocol.read_bytes() != protocol_content

    manifest = frontend / "manifest.json"
    manifest_mtime = manifest.stat().st_mtime_ns
    frontend_source = root / "frontend/src/panel.ts"
    frontend_source.write_text('export const panel = "source-stale";\n', encoding="utf-8")
    _make(root, env, "frontend")
    assert bootstrap.read_bytes() != bootstrap_content
    assert manifest.stat().st_mtime_ns > manifest_mtime


def test_verification_rejects_modified_and_extra_outputs(build_repo: tuple[Path, dict[str, str]]) -> None:
    root, env = build_repo
    _make(root, env, "build")
    protocol = root / "custom_components/ha_govee_led_ble/generated_protocol/sample.py"
    frontend = root / "custom_components/ha_govee_led_ble/frontend"
    bootstrap = frontend / "effect-studio-bootstrap.js"

    protocol_content = protocol.read_bytes()
    protocol.write_text("modified\n", encoding="utf-8")
    _make_fails(root, env, "verify-protocol")
    _make_fails(root, env, "package")
    assert protocol.read_text(encoding="utf-8") == "modified\n"
    assert not (root / "dist/ha_govee_led_ble.zip").exists()
    protocol.write_bytes(protocol_content)

    extra_protocol = protocol.with_name("extra.py")
    extra_protocol.write_text("extra\n", encoding="utf-8")
    _make_fails(root, env, "verify-protocol")
    extra_protocol.unlink()

    bootstrap_content = bootstrap.read_bytes()
    bootstrap.write_text("modified\n", encoding="utf-8")
    _make_fails(root, env, "verify-frontend")
    assert bootstrap.read_text(encoding="utf-8") == "modified\n"
    assert not (root / "dist/ha_govee_led_ble.zip").exists()
    bootstrap.write_bytes(bootstrap_content)

    extra_frontend = frontend / "effect-studio-extra.js"
    extra_frontend.write_text("extra\n", encoding="utf-8")
    _make_fails(root, env, "verify-frontend")
    extra_frontend.unlink()


def test_package_has_stable_runtime_layout_and_metadata(build_repo: tuple[Path, dict[str, str]]) -> None:
    root, env = build_repo
    _make(root, env, "package")
    archive_path = root / "dist/ha_govee_led_ble.zip"
    checksum_path = root / "dist/ha_govee_led_ble.zip.sha256"
    first_archive = archive_path.read_bytes()
    first_checksum = checksum_path.read_text(encoding="ascii")

    _make(root, env, "package")
    assert archive_path.read_bytes() == first_archive
    assert checksum_path.read_text(encoding="ascii") == first_checksum
    assert first_checksum == f"{sha256(first_archive).hexdigest()}  ha_govee_led_ble.zip\n"

    with ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        assert names == sorted(names)
        assert "__init__.py" in names
        assert "manifest.json" in names
        assert "py.typed" in names
        assert "generated_protocol/sample.py" in names
        assert "scene_catalogues/H617A.json" in names
        assert "frontend/editor-loader.js" in names
        assert "frontend/editor.js" in names
        assert "frontend/effect-studio-bootstrap.js" in names
        assert not any(name.startswith(("custom_components/", "scripts/", "tools/", "frontend/src/")) for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") or name.startswith(".") for name in names)
        for info in infos:
            mode = info.external_attr >> 16
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.create_system == 3
            assert stat.S_IFMT(mode) == stat.S_IFREG
            assert stat.S_IMODE(mode) == 0o644
            assert info.extra == b""
            assert info.comment == b""
    verify_archive(root / "custom_components/ha_govee_led_ble", archive_path)


def test_package_verification_rejects_source_drift(build_repo: tuple[Path, dict[str, str]]) -> None:
    root, env = build_repo
    _make(root, env, "package")
    source = root / "custom_components/ha_govee_led_ble"
    archive = root / "dist/ha_govee_led_ble.zip"

    (source / "manifest.json").write_text('{"domain":"changed"}\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="content differs"):
        verify_archive(source, archive)


def test_clean_rebuilds_generated_outputs(build_repo: tuple[Path, dict[str, str]]) -> None:
    root, env = build_repo
    _make(root, env, "package")
    generated = _generated_files(root)
    baseline = {path.relative_to(root): path.read_bytes() for path in generated}

    _make(root, env, "clean")

    assert not (root / ".build").exists()
    assert not (root / "dist").exists()
    assert not any(path.exists() for path in generated)

    _make(root, env, "build", "verify-generated")
    assert {path.relative_to(root): path.read_bytes() for path in generated} == baseline
