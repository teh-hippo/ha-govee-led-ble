import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from tests.hci_capture import POWER_ON, STATUS, notify, pcap, two_unnamed_connections, write

_REPO = Path(__file__).parents[1]
_SCRIPT = _REPO / "tools" / "ble" / "govee-capture.sh"
_PCAP_FIXTURE = _REPO / "tests" / "fixtures" / "govee_hci.pcap"
_PCAPNG_FIXTURE = _REPO / "tests" / "fixtures" / "govee_hci.pcapng"
_EMPTY_PCAPNG_FIXTURE = _REPO / "tests" / "fixtures" / "govee_hci_empty.pcapng"


def _capture_env(tmp_path: Path, pymobiledevice3: str = "/bin/false") -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GOVEE_CAPTURE_DIR": str(tmp_path / "captures"),
            "PYMOBILEDEVICE3": pymobiledevice3,
            "PREFLIGHT_SECONDS": "4",
        }
    )
    return env


def _stub_logger(tmp_path: Path, *, writes: bytes) -> str:
    """A stand-in for ``pymobiledevice3 btlogger capture`` that we control.

    It is invoked exactly as the real CLI is, so the argument handling, backgrounding and
    PID tracking under test are the real code paths; only the phone is replaced.
    """
    stub = tmp_path / "stub-pymobiledevice3"
    payload = tmp_path / "payload.bin"
    payload.write_bytes(writes)
    stub.write_text(
        "#!/bin/bash\n"
        # The version probe asks for help first; answer it the way 10.2.3 does, with no
        # `capture` subcommand, so the bare invocation is what gets exercised.
        'if [[ " $* " == *" --help "* ]]; then echo "Usage: pymobiledevice3 btlogger [OPTIONS] {out}"; exit 0; fi\n'
        'out="${@: -1}"\n'  # the output path is the last argument, as in the real CLI
        f'cat "{payload}" > "$out"\n'
        "exec sleep 60\n"
    )
    stub.chmod(0o755)
    return str(stub)


def _assert_logger_stopped(state: Path, pid: int, result: subprocess.CompletedProcess[bytes]) -> None:
    assert result.returncode == 0, result.stderr.decode()
    assert not state.exists()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    raise AssertionError(f"logger pid {pid} survived capture stop")


def _stop(tmp_path: Path, stub: str) -> None:
    state = tmp_path / "captures" / ".current"
    if not state.exists():
        return
    pid = int(state.read_text().split()[0])
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "stop"],
        check=False,
        capture_output=True,
        env=_capture_env(tmp_path, stub),
    )
    _assert_logger_stopped(state, pid, result)


def test_mark_records_timestamped_batch_action(tmp_path: Path):
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / ".current").write_text(f"123 batch-run 2026-07-13T15:00:00+10:00 {'a' * 64}\n")

    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "mark", "Bloom", "Dynamic"],
        check=True,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    timestamp, label = (captures / "batch-run.actions.tsv").read_text().rstrip().split("\t", 1)
    assert datetime.fromisoformat(timestamp)
    assert label == "Bloom Dynamic"
    assert result.stdout.strip() == "marked 'Bloom Dynamic'"


def test_marks_carry_an_offset_so_they_can_be_compared_to_a_capture(tmp_path: Path):
    """A naive mark cannot be compared to a pcapng record without guessing a zone.

    analyse_capture slices at these marks. The old container dated its records in device
    wall clock, so a naive mark happened to line up; pcapng dates them truly, and it no
    longer does. The offset written here is what keeps that comparison an instant comparison.
    """
    captures = tmp_path / "captures"
    captures.mkdir()
    (captures / ".current").write_text("123 batch-run 2026-07-13T15:00:00+10:00 -\n")

    subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "mark", "Scene"],
        check=True,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    timestamp = (captures / "batch-run.actions.tsv").read_text().split("\t", 1)[0]
    assert datetime.fromisoformat(timestamp).tzinfo is not None


def test_mark_requires_active_capture(tmp_path: Path):
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "mark", "Bloom Dynamic"],
        check=False,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    assert result.returncode == 1
    assert result.stdout.strip() == "no capture running"


def test_start_rejects_invalid_prediction_hash(tmp_path: Path):
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "start", "batch-run", "not-a-hash"],
        check=False,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path),
    )

    assert result.returncode == 1
    assert "prediction SHA-256" in result.stderr


def test_start_refuses_a_capture_carrying_no_frames(tmp_path: Path):
    """The failure that cost a session on 2026-07-30, made loud.

    A missing Bluetooth logging profile leaves btlogger connecting cleanly and recording
    nothing. Note what that leaves on disk: not an empty file, but a well-formed pcapng of
    zero packets, because the writer emits its section and interface blocks up front. So
    checking that a file exists, or that it parses, or that it has a header, all pass. Only
    counting frames separates a dead stream from a quiet one.
    """
    stub = _stub_logger(tmp_path, writes=_EMPTY_PCAPNG_FIXTURE.read_bytes())
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "start", "empty-run"],
        check=False,
        capture_output=True,
        text=True,
        env=_capture_env(tmp_path, stub),
    )

    assert result.returncode == 1
    assert "no HCI frames" in result.stderr
    assert "BluetoothLogging.mobileconfig" in result.stderr
    assert "D8A1D847-C161-4D0A-9426-FB9C3E48297D" in result.stderr
    assert not (tmp_path / "captures" / ".current").exists()
    # The file the preflight rejected was a valid capture, not a broken one.
    assert (tmp_path / "captures" / "empty-run.pcapng").stat().st_size > 0


def test_start_uses_the_capture_subcommand_when_the_installed_cli_has_one(tmp_path: Path):
    """The invocation differs by version, and getting it wrong is not a soft failure.

    pymobiledevice3 10.2.3 takes ``btlogger [OPTIONS] {out}``; upstream moved it under a
    ``capture`` subcommand. Passing ``capture`` to 10.2.3 makes it the OUTPUT PATH, so the
    tool writes a file called ``capture`` and exits, which is what happened on 2026-07-30
    against the form both our note and the lab documentation recorded.
    """
    stub = tmp_path / "stub-pymobiledevice3"
    payload = tmp_path / "payload.bin"
    payload.write_bytes(_PCAPNG_FIXTURE.read_bytes())
    argv_log = tmp_path / "argv.log"
    stub.write_text(
        "#!/bin/bash\n"
        'if [[ " $* " == *" --help "* ]]; then printf "Commands:\\n  capture  Capture HCI\\n"; exit 0; fi\n'
        f'echo "$@" > "{argv_log}"\n'
        'out="${@: -1}"\n'
        f'cat "{payload}" > "$out"\n'
        "exec sleep 60\n"
    )
    stub.chmod(0o755)
    try:
        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(_SCRIPT), "start", "versioned-run"],
            check=False,
            capture_output=True,
            text=True,
            env=_capture_env(tmp_path, str(stub)),
        )
        assert result.returncode == 0, result.stderr
        assert argv_log.read_text().split()[:2] == ["btlogger", "capture"]
    finally:
        _stop(tmp_path, str(stub))


def test_start_accepts_a_capture_that_is_carrying_frames(tmp_path: Path):
    """Positive control for the check above: it has to be able to pass, or it proves nothing."""
    stub = _stub_logger(tmp_path, writes=_PCAPNG_FIXTURE.read_bytes())
    try:
        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(_SCRIPT), "start", "live-run"],
            check=False,
            capture_output=True,
            text=True,
            env=_capture_env(tmp_path, stub),
        )

        assert result.returncode == 0, result.stderr
        assert "recording 'live-run'" in result.stdout
        assert (tmp_path / "captures" / ".current").read_text().split()[1] == "live-run"
    finally:
        _stop(tmp_path, stub)


def test_wsl_capture_uses_native_idevicebtlogger_pcap(tmp_path: Path):
    """Windows pymobiledevice3 has only ever made zero-byte captures.

    The app path transfers USB ownership to WSL, where the known-good native logger writes
    classic pcap. This checks the real command shape and container choice without a phone.
    """
    logger = tmp_path / "idevicebtlogger"
    argv_log = tmp_path / "argv.log"
    logger.write_text(
        f'#!/bin/bash\nprintf "%s\\n" "$*" > "{argv_log}"\ncat "{_PCAP_FIXTURE}" > "${{@: -1}}"\nexec sleep 60\n'
    )
    logger.chmod(0o755)
    env = _capture_env(tmp_path)
    env.update(
        {
            "GOVEE_CAPTURE_BACKEND": "idevicebtlogger",
            "IDEVICEBTLOGGER": str(logger),
            "PHONE_UDID": "00008140-AAAABBBBCCCCDDDD",
        }
    )

    try:
        result = subprocess.run(  # noqa: S603
            ["/bin/bash", str(_SCRIPT), "start", "wsl-run"],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "captures" / "wsl-run.pcap").is_file()
        assert argv_log.read_text().split()[:5] == [
            "-u",
            "00008140-AAAABBBBCCCCDDDD",
            "-f",
            "pcap",
            "-x",
        ]
    finally:
        state = tmp_path / "captures" / ".current"
        if state.exists():
            pid = int(state.read_text().split()[0])
            stopped = subprocess.run(  # noqa: S603
                ["/bin/bash", str(_SCRIPT), "stop"],
                check=False,
                capture_output=True,
                env=env,
            )
            _assert_logger_stopped(state, pid, stopped)


# The peer the committed pcapng fixture was built around, and one that is not in it.
_FIXTURE_PEER = "D0:35:34:AA:BB:CC"
_ABSENT_PEER = "D5:36:36:DD:EE:FF"


def _record_session(
    tmp_path: Path,
    name: str,
    *,
    expected_peer: str | None,
    capture: bytes | None = None,
    model: str = "H617A",
) -> subprocess.CompletedProcess[str]:
    """Start a capture over the committed fixture and stop it, returning stop's result."""
    stub = _stub_logger(tmp_path, writes=capture if capture is not None else _PCAPNG_FIXTURE.read_bytes())
    env = _capture_env(tmp_path, stub)
    env["GOVEE_MODEL"] = model
    if expected_peer is not None:
        env["GOVEE_EXPECTED_PEER"] = expected_peer
    started = subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "start", name],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert started.returncode == 0, started.stderr
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(_SCRIPT), "stop"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_a_session_for_a_light_that_never_appeared_is_a_failed_run(tmp_path: Path):
    """The quiet failure app-sniff sessions are prone to, made loud.

    The phone can be recording perfectly while the vendor app never reaches the light, or
    reaches it on a connection opened before recording started. Either way the decode comes
    out clean and holds nothing from the device the session was for, which reads as "it sent
    nothing" rather than "we did not capture it". Binding the capture to the address it is
    supposed to be of turns that into an error while the rig is still up to redo it.
    """
    result = _record_session(tmp_path, "wrong-light", expected_peer=_ABSENT_PEER)

    # 3 rather than 1, so down.sh can separate this from "no capture running", which it
    # has always tolerated on the path that hands the BLE link back.
    assert result.returncode == 3
    assert "not usable as evidence" in result.stderr
    assert "no captured source" in result.stderr


def test_a_session_that_did_capture_its_light_passes_and_records_the_binding(tmp_path: Path):
    """Positive control: the check above can pass, and says which peer it was checked against."""
    result = _record_session(tmp_path, "right-light", expected_peer=_FIXTURE_PEER)

    assert result.returncode == 0, result.stderr
    meta = json.loads((tmp_path / "captures" / "right-light.meta.json").read_text())
    assert meta["expected_peer"] == _FIXTURE_PEER
    assert meta["model"] == "H617A"
    assert f"filtered to source {_FIXTURE_PEER}" in result.stdout


def test_a_capture_with_no_expected_peer_still_decodes(tmp_path: Path):
    """Direct-mode and ad-hoc captures never set one, and must not start failing."""
    result = _record_session(tmp_path, "unbound", expected_peer=None)

    assert result.returncode == 0, result.stderr
    meta = json.loads((tmp_path / "captures" / "unbound.meta.json").read_text())
    assert meta["expected_peer"] is None


def test_a_session_that_recorded_two_bluetooth_connections_is_a_failed_run(tmp_path: Path):
    """The quiet failure that got through on 2026-08-05, made loud.

    The phone stays paired with everything in the house, so a capture can hold a second
    device's connection alongside the light's. Both connections here predate the recording
    and neither carries an address, which is the normal state of an app-sniff session and
    was exactly why the old address-keyed count reported one source and stopped clean. An
    unbound stop tolerates unnamed frames, because ad-hoc and direct-mode captures are full
    of them, but it must not tolerate two devices being read as one.
    """
    result = _record_session(tmp_path, "two-devices", expected_peer=None, capture=two_unnamed_connections())

    # 3, matching the other "this capture proves nothing" exit, so down.sh keeps telling it
    # apart from "there was no capture running".
    assert result.returncode == 3
    assert "not usable as evidence about one device" in result.stderr
    assert "holds 2 Govee sources" in result.stderr


def test_an_unbound_session_still_stops_clean_when_it_holds_one_unnamed_connection(tmp_path: Path):
    """Positive control: unnamed frames alone are not a failure, or the check above proves nothing.

    An unbound stop passes --allow-unattributed for this reason. Frames on a connection
    opened before recording started are the normal state of the sessions that never bind a
    peer, and failing them would only teach the operator to ignore the exit status.
    """
    capture = pcap([write(0x004E, POWER_ON), notify(0x004E, STATUS)])
    result = _record_session(tmp_path, "one-unnamed", expected_peer=None, capture=capture)

    assert result.returncode == 0, result.stderr
    assert "?conn-0x4e" in result.stdout
