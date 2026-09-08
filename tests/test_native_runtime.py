"""Black-box verification of the native local PCM player protocol.

The test compiles the daemon itself and drives it only through its UNIX socket
and output file.  It deliberately does not import or call the C implementation.
"""

from __future__ import annotations

import os
import re
import signal
import socket
import struct
import subprocess
import time
import wave
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "appliance" / "native"
STATUS = re.compile(
    r"^(OK|STALE) (\d+) (0|1) (\d{1,3}) (\d+) (\d+) (\d+) ([A-Z0-9_]+)$"
)


def _write_wav(path: Path, *, seconds: int = 12, frames: int | None = None,
               channels: int = 2, rate: int = 48_000, width: int = 2,
               amplitude: int = 12_000) -> None:
    """Create a deterministic PCM fixture using only the standard library."""
    with wave.open(str(path), "wb") as fixture:
        fixture.setnchannels(channels)
        fixture.setsampwidth(width)
        fixture.setframerate(rate)
        if width == 2:
            sample = struct.pack("<h", amplitude)
        else:
            sample = b"\0" * width
        frame_count = rate * seconds if frames is None else frames
        fixture.writeframes(sample * channels * frame_count)


def _status(line: str, expected: str | None = "OK") -> dict[str, int | str]:
    match = STATUS.fullmatch(line.strip())
    assert match, f"invalid status response: {line!r}"
    kind, revision, playing, volume, position, written, underruns, fault = match.groups()
    if expected is not None:
        assert kind == expected, line
    return {
        "kind": kind,
        "revision": int(revision),
        "playing": int(playing),
        "volume": int(volume),
        "position": int(position),
        "written": int(written),
        "underruns": int(underruns),
        "fault": fault,
    }


class NativeDaemon:
    def __init__(self, binary: Path, work: Path, wav: Path, output: Path, *, loop: bool = False):
        self.binary = binary
        self.work = work
        self.wav = wav
        self.output = output
        self.socket_path = work / "player.sock"
        command = [str(binary), "--socket", str(self.socket_path), "--wav", str(wav), "--output", str(output)]
        if loop:
            command.append("--loop")
        self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._wait_for_socket()

    def _wait_for_socket(self) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.socket_path.exists():
                return
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate(timeout=1)
                pytest.fail(f"daemon exited before socket creation ({self.process.returncode}): {stdout} {stderr}")
            time.sleep(0.02)
        self.close()
        pytest.fail("daemon did not create its control socket within 3 seconds")

    def command(self, text: str, *, timeout: float = 1.5) -> str:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(self.socket_path))
            client.sendall(text.encode("ascii"))
            received = b""
            while not received.endswith(b"\n"):
                chunk = client.recv(512)
                assert chunk, "daemon closed connection without a response"
                received += chunk
        return received.decode("ascii")

    def open_idle_client(self) -> socket.socket:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(1)
        client.connect(str(self.socket_path))
        return client

    def wait_for(self, predicate, *, timeout: float = 3.0, message: str) -> dict[str, int | str]:
        deadline = time.monotonic() + timeout
        latest: dict[str, int | str] | None = None
        while time.monotonic() < deadline:
            latest = _status(self.command("GET\n"))
            if predicate(latest):
                return latest
            time.sleep(0.03)
        pytest.fail(f"{message}; last status={latest}")

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
                pytest.fail("daemon ignored SIGTERM")
        if self.socket_path.exists():
            pytest.fail("daemon left its UNIX socket behind after shutdown")


@pytest.fixture(scope="module")
def native_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the shipped daemon with a normal host C compiler, once per run."""
    sources = [NATIVE / "core.c", NATIVE / "engine.c"]
    missing = [str(source.relative_to(ROOT)) for source in sources if not source.is_file()]
    assert not missing, f"native runtime sources missing: {', '.join(missing)}"
    binary = tmp_path_factory.mktemp("native-build") / "forgeos-native-engine"
    result = subprocess.run(
        ["cc", "-D_POSIX_C_SOURCE=200809L", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", *map(str, sources), "-o", str(binary)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, f"native daemon compilation failed:\n{result.stdout}\n{result.stderr}"
    return binary


@pytest.fixture
def pcm_wav(tmp_path: Path) -> Path:
    path = tmp_path / "stereo-48k.pcm.wav"
    _write_wav(path)
    return path


def _daemon(native_binary: Path, tmp_path: Path, wav_path: Path, *, fifo: bool = False) -> NativeDaemon:
    output = tmp_path / ("audio.fifo" if fifo else "audio.pcm")
    if fifo:
        os.mkfifo(output)
    return NativeDaemon(native_binary, tmp_path, wav_path, output)


def test_pcm_progresses_and_state_transitions_are_revision_guarded(native_binary: Path, tmp_path: Path, pcm_wav: Path) -> None:
    daemon = _daemon(native_binary, tmp_path, pcm_wav)
    try:
        initial = _status(daemon.command("GET\n"))
        assert initial["playing"] == 0
        assert initial["position"] == initial["written"] == 0

        playing = _status(daemon.command(f"DO {initial['revision']} PLAY\n"))
        assert playing["playing"] == 1
        advanced = daemon.wait_for(
            lambda state: int(state["position"]) > 1_000 and int(state["written"]) > 1_000,
            message="playback counters did not advance without a UI client",
        )
        assert daemon.output.stat().st_size >= int(advanced["written"]) * 4
        assert daemon.output.stat().st_size % 4 == 0

        paused = _status(daemon.command(f"DO {advanced['revision']} PAUSE\n"))
        assert paused["playing"] == 0
        stale = _status(daemon.command(f"DO {initial['revision']} PLAY\n"), expected="STALE")
        assert stale["revision"] == paused["revision"]
        assert stale["playing"] == 0, "a delayed PLAY undid the newer PAUSE"
    finally:
        daemon.close()


def test_volume_scaling_and_rewind_preserves_pause(native_binary: Path, tmp_path: Path, pcm_wav: Path) -> None:
    daemon = _daemon(native_binary, tmp_path, pcm_wav)
    try:
        state = _status(daemon.command("GET\n"))
        state = _status(daemon.command(f"DO {state['revision']} PLAY\n"))
        state = daemon.wait_for(lambda item: int(item["written"]) > 5_000, message="baseline PCM was not written")
        state = _status(daemon.command(f"DO {state['revision']} PAUSE\n"))
        boundary = daemon.output.stat().st_size
        state = _status(daemon.command(f"DO {state['revision']} VOLUME 25\n"))
        rewind = _status(daemon.command(f"DO {state['revision']} REWIND\n"))
        assert rewind["playing"] == 0 and rewind["position"] == 0
        replaying = _status(daemon.command(f"DO {rewind['revision']} PLAY\n"))
        daemon.wait_for(
            lambda item: daemon.output.stat().st_size >= boundary + 16_000,
            message="rewound PCM was not written",
        )
        _status(daemon.command(f"DO {replaying['revision']} PAUSE\n"))
        raw = daemon.output.read_bytes()
        baseline = struct.unpack("<h", raw[4_000:4_002])[0]
        scaled = struct.unpack("<h", raw[boundary + 8_000:boundary + 8_002])[0]
        assert abs(scaled) < abs(baseline) * 0.35
        assert abs(scaled) > abs(baseline) * 0.15
    finally:
        daemon.close()


@pytest.mark.parametrize("kind", ["truncated", "mono"])
def test_rejects_invalid_wav_before_exposing_control_socket(native_binary: Path, tmp_path: Path, kind: str) -> None:
    wav_path = tmp_path / f"{kind}.wav"
    if kind == "truncated":
        wav_path.write_bytes(b"RIFF\xff\xff\xff\xffWAVEfmt ")
    else:
        _write_wav(wav_path, channels=1)
    output = tmp_path / "invalid-output.pcm"
    socket_path = tmp_path / "invalid.sock"
    process = subprocess.run(
        [str(native_binary), "--socket", str(socket_path), "--wav", str(wav_path), "--output", str(output)],
        text=True,
        capture_output=True,
        timeout=3,
    )
    assert process.returncode != 0
    assert not socket_path.exists(), "invalid WAV started a controllable daemon"


@pytest.mark.parametrize("kind", ["declared-size", "partial-chunk", "empty-pcm"])
def test_rejects_wav_container_boundary_and_empty_pcm(
    native_binary: Path, tmp_path: Path, kind: str,
) -> None:
    """A valid-looking container must not bypass the PCM parser's bounds."""
    wav_path = tmp_path / f"{kind}.wav"
    _write_wav(wav_path, frames=0 if kind == "empty-pcm" else None)
    contents = bytearray(wav_path.read_bytes())
    if kind == "declared-size":
        contents[4:8] = struct.pack("<I", len(contents) - 16)
    elif kind == "partial-chunk":
        contents.extend(b"JUNK\x01")
        contents[4:8] = struct.pack("<I", len(contents) - 8)
    wav_path.write_bytes(contents)

    socket_path = tmp_path / "invalid.sock"
    output = tmp_path / "invalid-output.pcm"
    process = subprocess.run(
        [str(native_binary), "--socket", str(socket_path), "--wav", str(wav_path), "--output", str(output)],
        text=True,
        capture_output=True,
        timeout=3,
    )
    assert process.returncode != 0
    assert not socket_path.exists(), "invalid WAV started a controllable daemon"
    assert not output.exists(), "invalid WAV created a PCM artifact"


def test_idle_client_cannot_block_control_or_pcm(native_binary: Path, tmp_path: Path, pcm_wav: Path) -> None:
    daemon = _daemon(native_binary, tmp_path, pcm_wav)
    idle: socket.socket | None = None
    try:
        state = _status(daemon.command("GET\n"))
        _status(daemon.command(f"DO {state['revision']} PLAY\n"))
        idle = daemon.open_idle_client()
        began = time.monotonic()
        responsive = _status(daemon.command("GET\n", timeout=0.08))
        assert time.monotonic() - began <= 0.08
        assert responsive["playing"] == 1
        daemon.wait_for(
            lambda item: int(item["written"]) > 1_000 and daemon.output.stat().st_size > 4_000,
            message="idle client blocked independently commanded playback",
        )
    finally:
        if idle is not None:
            idle.close()
        daemon.close()


def test_fifo_backpressure_is_bounded_and_shutdown_cleans_socket(native_binary: Path, tmp_path: Path, pcm_wav: Path) -> None:
    output = tmp_path / "audio.fifo"
    os.mkfifo(output)
    # Keep one reader open before daemon startup, then deliberately never drain
    # it.  This separates a legitimate FIFO writer open from write backpressure.
    reader = os.open(output, os.O_RDONLY | os.O_NONBLOCK)
    daemon = NativeDaemon(native_binary, tmp_path, pcm_wav, output)
    try:
        state = _status(daemon.command("GET\n"))
        _status(daemon.command(f"DO {state['revision']} PLAY\n"))
        time.sleep(0.5)
        state = _status(daemon.command("GET\n", timeout=1.0))
        assert int(state["written"]) <= 48_000 * 5, "backpressure allowed unbounded PCM production"
    finally:
        os.close(reader)
        daemon.close()


def test_short_loop_refills_pcm_and_eight_idle_clients_expire(
    native_binary: Path, tmp_path: Path,
) -> None:
    """Looping must continue across EOF while bounded clients cannot exhaust control."""
    wav_path = tmp_path / "three-frames.wav"
    _write_wav(wav_path, frames=3)
    output = tmp_path / "audio.pcm"
    daemon = NativeDaemon(native_binary, tmp_path, wav_path, output, loop=True)
    idle_clients: list[socket.socket] = []
    try:
        state = _status(daemon.command("GET\n"))
        _status(daemon.command(f"DO {state['revision']} PLAY\n"))
        idle_clients = [daemon.open_idle_client() for _ in range(8)]
        time.sleep(0.35)
        assert output.stat().st_size >= 960 * 4, (
            "short loop did not refill a complete PCM tick while clients were idle"
        )
        assert output.read_bytes()[: 960 * 4] == struct.pack("<h", 12_000) * (960 * 2)

        # The exact deadline is an implementation detail; bounded clients must
        # release capacity and allow a later independent request to complete.
        assert int(_status(daemon.command("GET\n", timeout=1.0))["fault"]) == 0
    finally:
        for client in idle_clients:
            client.close()
        daemon.close()


def test_output_fault_rejects_play_until_engine_restart(
    native_binary: Path, tmp_path: Path, pcm_wav: Path,
) -> None:
    output = tmp_path / "audio.fifo"
    os.mkfifo(output)
    reader = os.open(output, os.O_RDONLY | os.O_NONBLOCK)
    daemon = NativeDaemon(native_binary, tmp_path, pcm_wav, output)
    try:
        state = _status(daemon.command("GET\n"))
        _status(daemon.command(f"DO {state['revision']} PLAY\n"))
        os.close(reader)
        reader = -1
        faulted = daemon.wait_for(
            lambda item: int(item["fault"]) == 1,
            message="lost FIFO reader did not enter the documented audio-fault state",
        )
        assert faulted["playing"] == 0
        assert daemon.command(f"DO {faulted['revision']} PLAY\n").startswith("ERR")
    finally:
        if reader >= 0:
            os.close(reader)
        daemon.close()


@pytest.mark.parametrize("target", ["socket", "output"])
def test_refuses_preexisting_exclusive_paths(native_binary: Path, tmp_path: Path, pcm_wav: Path, target: str) -> None:
    socket_path = tmp_path / "taken.sock"
    output = tmp_path / "taken.pcm"
    held_socket: socket.socket | None = None
    if target == "socket":
        held_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        held_socket.bind(str(socket_path))
    else:
        output.write_bytes(b"must-survive")
    try:
        result = subprocess.run(
            [str(native_binary), "--socket", str(socket_path), "--wav", str(pcm_wav), "--output", str(output)],
            text=True,
            capture_output=True,
            timeout=3,
        )
        assert result.returncode != 0
        if target == "socket":
            assert socket_path.exists(), "daemon removed a socket it did not own"
            assert not output.exists(), "socket collision leaked a newly created output file"
        else:
            assert output.read_bytes() == b"must-survive"
    finally:
        if held_socket is not None:
            held_socket.close()


def test_protocol_rejects_invalid_command_and_second_command(native_binary: Path, tmp_path: Path, pcm_wav: Path) -> None:
    daemon = _daemon(native_binary, tmp_path, pcm_wav)
    try:
        assert daemon.command("DO nope PLAY\n").startswith("ERR")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(daemon.socket_path))
            client.sendall(b"GET\nGET\n")
            response = client.recv(512).decode("ascii")
            assert response.count("\n") == 1
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(1)
            client.connect(str(daemon.socket_path))
            client.sendall(b"X" * 257 + b"\n")
            assert client.recv(512).decode("ascii").startswith("ERR")
    finally:
        daemon.close()
