import pathlib
import subprocess


ROOT = pathlib.Path(__file__).parents[1]
SOURCE = ROOT / "appliance/native/music_bridge.c"


def test_music_bridge_builds_and_rejects_invalid_cli(tmp_path):
    binary = tmp_path / "music_bridge"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-D_POSIX_C_SOURCE=200809L", str(SOURCE), "-o", str(binary)], check=True)
    bad = subprocess.run([str(binary), "--socket", "relative", "--cdp-port", "9224", "--seconds", "1"], text=True, capture_output=True)
    assert bad.returncode == 2


def test_music_bridge_refuses_socket_collision(tmp_path):
    binary = tmp_path / "music_bridge"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-D_POSIX_C_SOURCE=200809L", str(SOURCE), "-o", str(binary)], check=True)
    socket = tmp_path / "bridge.sock"
    socket.write_text("not ours")
    run = subprocess.run([str(binary), "--socket", str(socket), "--cdp-port", "9224", "--seconds", "1"], text=True, capture_output=True)
    assert run.returncode == 1
    assert socket.read_text() == "not ours"
