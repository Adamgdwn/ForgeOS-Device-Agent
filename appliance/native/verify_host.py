#!/usr/bin/env python3
"""Exercise real native windows against real PCM output under an owned X server.

No audio hardware, tablet, network service or private account is accessed.
Runs in under 60 seconds; all child processes are owned and stopped in finally.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import time

from demo import BUILD, compose, request, stop


def until(predicate, message, seconds=2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = predicate()
            if value:
                return value
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            pass
        time.sleep(.02)
    raise AssertionError(message)


def process_memory(pid):
    result = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:", "Threads:")):
            key, value = line.split(":", 1)
            result[key] = value.strip()
    return result


def run(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    os.chmod(output, 0o700)
    endpoint = output / "engine.sock"
    if len(str(endpoint).encode()) >= 108:
        raise ValueError("Use a short absolute output path for the Unix socket")
    wav = output / "first-light.wav"
    pcm = output / "observed.pcm"
    capture = output / "current.ppm"
    compose(wav)
    server = engine = panel = None
    checks = []
    artifacts = []
    report = {"captured_at": datetime.now(timezone.utc).isoformat(), "stage": "OBSERVED_HOST_PROTOTYPE_INTERACTION", "audio_sink": "regular PCM capture file, not a physical speaker", "tablet_access": False, "youtube_music_connected": False, "home_control_connected": False}
    try:
        server = subprocess.Popen(["Xvfb", "-displayfd", "1", "-screen", "0", "900x1400x24", "-nolisten", "tcp"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if not select.select([server.stdout], [], [], 3)[0]:
            raise RuntimeError("Xvfb did not return a display number")
        display = server.stdout.readline().strip()
        if not display.isdigit():
            raise RuntimeError("Invalid Xvfb display number")
        env = {**os.environ, "DISPLAY": ":" + display}

        def xdo(*args):
            return subprocess.check_output(["xdotool", *map(str, args)], env=env, text=True, timeout=3).strip()

        def open_panel():
            process = subprocess.Popen([str(BUILD / "forge-panel-x11"), "--socket", str(endpoint), "--x11", "--capture", str(capture)], env=env)
            try:
                window = until(lambda: xdo("search", "--onlyvisible", "--pid", process.pid, "--name", "Forge"), "No native panel window")
            except BaseException:
                stop(process)
                raise
            return process, window.splitlines()[0]

        def click(x, y):
            xdo("mousemove", "--window", window, x, y)
            xdo("click", "1")

        def screenshot(name):
            previous = capture.stat().st_mtime_ns if capture.exists() else None
            xdo("key", "--window", window, "s")
            until(lambda: capture.exists() and capture.stat().st_mtime_ns != previous and capture.stat().st_size >= 800 * 1280 * 3, "Capture not written")
            destination = output / (name + ".ppm")
            shutil.copyfile(capture, destination)
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-threads", "1", "-i", str(destination), "-frames:v", "1", "-threads", "1", str(output / (name + ".png"))], check=True, timeout=5)
            artifacts.append(name + ".png")

        engine = subprocess.Popen([str(BUILD / "forge-engine"), "--socket", str(endpoint), "--wav", str(wav), "--output", str(pcm), "--loop"])
        until(lambda: request(endpoint), "Engine startup failed")
        assert request(endpoint)["playing"] == 0
        checks.append("starts paused")
        panel, window = open_panel()
        click(400, 882)
        until(lambda: request(endpoint)["playing"] == 1, "Touch Play did not start PCM")
        until(lambda: pcm.stat().st_size > 7680, "No real PCM output")
        first = request(endpoint)
        screenshot("music-playing")
        click(600, 1180)
        until(lambda: request(endpoint)["frames_written"] > first["frames_written"] + 4800, "Home navigation interrupted audio")
        screenshot("home-playing")
        checks.append("native Play click produces PCM; Home navigation preserves playback")
        before = request(endpoint)
        memory_before = {"engine": process_memory(engine.pid), "panel_x11": process_memory(panel.pid)}
        panel.kill()
        panel.wait(timeout=2)
        after = until(lambda: (s if (s := request(endpoint))["frames_written"] >= before["frames_written"] + 12000 and s["playing"] else None), "Audio did not survive UI SIGKILL")
        checks.append("audio advances at least 12000 frames after UI SIGKILL")
        panel, window = open_panel()
        old_revision = request(endpoint)["revision"]
        click(400, 882)
        paused = until(lambda: (s if not (s := request(endpoint))["playing"] else None), "Reopened panel could not pause")
        stale = request(endpoint, f"DO {old_revision} PLAY")
        assert stale["result"] == "STALE" and stale["playing"] == 0
        time.sleep(.12)
        assert request(endpoint)["frames_written"] == paused["frames_written"]
        checks.append("reopened UI pauses; delayed PLAY is rejected and PCM stops")
        screenshot("music-paused")
        stop(panel)
        panel = None
        panel, window = open_panel()
        time.sleep(.25)
        assert request(endpoint)["playing"] == 0
        checks.append("reopening UI preserves intentional pause")
        click(240, 1034)
        until(lambda: request(endpoint)["volume"] == 25, "Volume click not delivered")
        click(160, 882)
        until(lambda: request(endpoint)["position_frames"] == 0 and not request(endpoint)["playing"], "Reset did not rewind and pause")
        checks.append("volume is controlled by touch; Reset rewinds and pauses")
        report.update(checks=checks, status="PASS", memory=memory_before, ui_crash_frame_delta=after["frames_written"]-before["frames_written"], final_state=request(endpoint), artifacts=artifacts)
    finally:
        stop(panel)
        stop(engine)
        stop(server)
        report["owned_processes_remaining"] = [p.pid for p in (panel, engine, server) if p is not None and p.poll() is None]
        report["socket_removed"] = not endpoint.exists()
        (output / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    assert not report["owned_processes_remaining"] and report["socket_removed"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New absolute directory, short path required")
    arguments = parser.parse_args()
    subprocess.run(["make", "-C", str(Path(__file__).parent), "host"], check=True, timeout=30)
    print(json.dumps(run(arguments.output.resolve()), indent=2))
