"""Host checks for the recovery script's owned music-socket cleanup.

The function is extracted from the device script, not reimplemented here.  Real
UNIX sockets exercise the file-type guard; a PATH-injected ``stat`` supplies
UID 65000 because a normal host test user cannot create a socket with Android's
service UID.  This proves control flow, not Android kernel ownership metadata.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile

import pytest


REPO = Path(__file__).resolve().parents[1]
RECOVER = REPO / "appliance/device/forge-recover.sh"


@pytest.fixture
def short_tmp() -> Path:
    # AF_UNIX limits pathname bytes, so pytest's descriptive per-test path is
    # too long once the device-shaped hierarchy is appended.
    with tempfile.TemporaryDirectory(prefix="forge-") as directory:
        yield Path(directory)


def _cleanup_function() -> str:
    source = RECOVER.read_text()
    match = re.search(r"(?ms)^cleanup_music_socket\(\) \{.*?^\}\n(?=cleanup_music_socket \|\|)", source)
    assert match, "recovery script no longer contains an extractable cleanup_music_socket"
    return match.group(0)


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    install = tmp_path / "install"
    control = install / "linux-root/var/lib/forge/control"
    control.mkdir(parents=True)
    return install, control / "music.sock"


def _unix_socket(path: Path) -> socket.socket:
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path))
    return listener


def _run_cleanup(tmp_path: Path, install: Path, uid: int = 65000) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    stat = fake_bin / "stat"
    stat.write_text("#!/bin/sh\nprintf '%s\\n' \"$FORGE_TEST_SOCKET_UID\"\n")
    stat.chmod(0o755)
    env = os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "FORGE_TEST_SOCKET_UID": str(uid)}
    return subprocess.run(
        ["/bin/bash", "-ceu", _cleanup_function() + "\ncleanup_music_socket\n"],
        env=env | {"install": str(install)}, text=True, capture_output=True, timeout=10,
    )


def test_cleanup_removes_missing_or_injected_owned_real_socket(short_tmp: Path) -> None:
    install, music_socket = _layout(short_tmp)
    assert _run_cleanup(short_tmp, install).returncode == 0
    listener = _unix_socket(music_socket)
    try:
        result = _run_cleanup(short_tmp, install, uid=65000)
        assert result.returncode == 0, result.stderr
        assert not music_socket.exists()
    finally:
        listener.close()


@pytest.mark.parametrize("kind", ["regular", "symlink", "wrong-owner"])
def test_cleanup_rejects_unowned_socket_objects_without_removal(short_tmp: Path, kind: str) -> None:
    install, music_socket = _layout(short_tmp)
    listener: socket.socket | None = None
    target: Path | None = None
    if kind == "regular":
        music_socket.write_text("preserve")
    elif kind == "symlink":
        target = short_tmp / "outside.sock"
        listener = _unix_socket(target)
        music_socket.symlink_to(target)
    else:
        listener = _unix_socket(music_socket)
    try:
        result = _run_cleanup(short_tmp, install, uid=65001 if kind == "wrong-owner" else 65000)
        assert result.returncode != 0
        assert music_socket.is_symlink() if kind == "symlink" else music_socket.exists()
        if kind == "regular":
            assert music_socket.read_text() == "preserve"
        if target is not None:
            assert target.exists()
    finally:
        if listener is not None:
            listener.close()


@pytest.mark.parametrize("ancestor", ["var", "lib", "forge", "control"])
def test_cleanup_rejects_symlinked_ancestor_without_touching_target(short_tmp: Path, ancestor: str) -> None:
    install, music_socket = _layout(short_tmp)
    root = install / "linux-root"
    paths = {
        "var": root / "var",
        "lib": root / "var/lib",
        "forge": root / "var/lib/forge",
        "control": root / "var/lib/forge/control",
    }
    replacement = short_tmp / f"outside-{ancestor}"
    suffixes = {
        "var": "lib/forge/control/music.sock",
        "lib": "forge/control/music.sock",
        "forge": "control/music.sock",
        "control": "music.sock",
    }
    target = replacement / suffixes[ancestor]
    target.parent.mkdir(parents=True)
    listener = _unix_socket(target)
    path = paths[ancestor]
    # This removes only the temporary fixture hierarchy below the replaced path.
    shutil.rmtree(path)
    path.symlink_to(replacement, target_is_directory=True)
    try:
        result = _run_cleanup(short_tmp, install)
        assert result.returncode != 0
        assert target.exists(), "a rejected ancestor link must not reach its target"
    finally:
        listener.close()
