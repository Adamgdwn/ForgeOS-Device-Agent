#!/usr/bin/env python3
"""Bounded workstation demonstrator. No network, credentials or tablet access.

The Python launcher and optional aplay sink are development tools. The runtime
under test is the pair of native C executables. Every owned process is reaped.
"""
from __future__ import annotations

import argparse
import array
import math
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "output" / "native"


def compose(path: Path, seconds: int = 12) -> None:
    """Write an original quiet arpeggio; this proves PCM, not YouTube Music."""
    notes = (220.0, 261.625565, 329.627557, 391.995436,
             293.664768, 261.625565, 195.997718, 164.813778)
    with wave.open(str(path), "wb") as wav:
        wav.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        for second in range(seconds):
            samples = array.array("h")
            for index in range(48000):
                t = second + index / 48000
                step = int(t / .5)
                phase = t % .5
                attack = min(1.0, phase / .015)
                envelope = attack * math.exp(-phase * 7)
                frequency = notes[step % len(notes)]
                value = int(3800 * envelope * math.sin(2 * math.pi * frequency * t))
                samples.extend((value, value))
            if sys.byteorder != "little":
                samples.byteswap()
            wav.writeframesraw(samples.tobytes())


def request(path: Path, command: str = "GET") -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(.5)
        client.connect(str(path))
        client.sendall((command + "\n").encode("ascii"))
        response = bytearray()
        while b"\n" not in response:
            chunk = client.recv(256 - len(response))
            if not chunk or len(response) + len(chunk) > 255:
                raise RuntimeError("Incomplete or oversized engine response")
            response.extend(chunk)
    fields = response.decode("ascii").strip().split()
    if len(fields) != 8 or fields[0] not in ("OK", "STALE"):
        raise RuntimeError("Engine rejected command: " + response.decode("ascii"))
    keys = ("revision", "playing", "volume", "position_frames", "frames_written", "underruns", "fault")
    return {"result": fields[0], **dict(zip(keys, map(int, fields[1:])))}


def stop(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=120, help="Session deadline, 1..1800 seconds")
    parser.add_argument("--audio", action="store_true", help="Send the original test piece to workstation audio using aplay")
    parser.add_argument("--snapshot", type=Path, help="Render one PNG-independent PPM snapshot, without opening a window")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 1800:
        parser.error("--seconds must be between 1 and 1800")
    if args.audio and not shutil.which("aplay"):
        parser.error("--audio requires the host ALSA aplay tool")
    if not args.snapshot and not os.environ.get("DISPLAY"):
        parser.error("Interactive host mode needs DISPLAY; use --snapshot for a static render")
    subprocess.run(["make", "-C", str(Path(__file__).parent), "host"], check=True, timeout=30)
    player = engine = panel = None
    reader = None
    interrupted = False

    def interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    with tempfile.TemporaryDirectory(prefix="forge-demo-") as directory:
        work = Path(directory)
        wav = work / "first-light.wav"
        endpoint = work / "engine.sock"
        output = work / ("audio.fifo" if args.audio else "observed.pcm")
        compose(wav)
        try:
            if args.audio:
                os.mkfifo(output, 0o600)
                # Hold a reader only across startup, then hand ownership to aplay.
                reader = os.open(output, os.O_RDONLY | os.O_NONBLOCK)
                player = subprocess.Popen(["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-r", "48000", "-c", "2", "--buffer-time=60000", "--period-time=20000", str(output)])
            engine = subprocess.Popen([str(BUILD / "forge-engine"), "--socket", str(endpoint), "--wav", str(wav), "--output", str(output), "--loop"])
            ready = time.monotonic() + 3
            while time.monotonic() < ready:
                if engine.poll() is not None:
                    raise RuntimeError("Engine exited during startup")
                try:
                    request(endpoint)
                    break
                except (OSError, RuntimeError):
                    time.sleep(.02)
            else:
                raise RuntimeError("Engine did not become ready")
            if reader is not None:
                os.close(reader)
                reader = None
            args_panel = [str(BUILD / "forge-panel-x11"), "--socket", str(endpoint)]
            args_panel += ["--snapshot", str(args.snapshot.resolve())] if args.snapshot else ["--x11"]
            panel = subprocess.Popen(args_panel)
            print("Original native runtime. Local test audio only; YouTube Music and home systems are not connected.", flush=True)
            print("Tap Play, Home, Music, Reset or volume. Keyboard: Space, H, M, Q. Closing the demo ends its owned processes.", flush=True)
            print("Audio destination: " + ("workstation sound output" if args.audio else "temporary PCM capture (silent)"), flush=True)
            deadline = time.monotonic() + args.seconds
            while not interrupted and time.monotonic() < deadline and panel.poll() is None:
                if engine.poll() is not None or (player is not None and player.poll() is not None):
                    raise RuntimeError("Audio process exited")
                time.sleep(.05)
            if panel.poll() not in (None, 0):
                raise RuntimeError("Panel exited unsuccessfully")
            return 0
        finally:
            stop(panel)
            stop(engine)
            stop(player)
            if reader is not None:
                os.close(reader)


if __name__ == "__main__":
    raise SystemExit(main())
