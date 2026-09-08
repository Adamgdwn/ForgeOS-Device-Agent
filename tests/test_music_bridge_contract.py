"""Exercise the real native bridge over HTTP, masked WebSocket, and Unix IO."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time

import pytest

ROOT = Path(__file__).parents[1]


def exact(sock, n):
    out = b""
    while len(out) < n:
        data = sock.recv(n - len(out))
        if not data:
            raise EOFError
        out += data
    return out


def read_frame(sock):
    first, second = exact(sock, 2)
    assert second & 128, "client frames, including pong, must be masked"
    n = second & 127
    if n == 126:
        n = struct.unpack("!H", exact(sock, 2))[0]
    assert n < 16000
    mask = exact(sock, 4)
    data = exact(sock, n)
    return first & 15, bytes(c ^ mask[i % 4] for i, c in enumerate(data))


def frame(data, opcode=1, final=True):
    if isinstance(data, str):
        data = data.encode()
    head = bytes([(128 if final else 0) | opcode])
    return head + (bytes([len(data)]) if len(data) < 126 else b"\x7e" + struct.pack("!H", len(data))) + data


class Browser(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.playing = False
        self.volume = 35
        self.title = 'First "Track"'
        self.artist = "Test Artist"
        self.output = "THIS TABLET"
        self.status = "READY"
        self.video_id = "current0000"
        self.actions = []
        self.mode = "good"
        self.errors = []
        self.pongs = 0
        self.pages = None
        self.action_reply_gate = None
        self.apply_delay = 0
        self.activations = 0


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        s = self.request
        s.settimeout(2)
        try:
            request = b""
            while not request.endswith(b"\r\n\r\n"):
                request += exact(s, 1)
                assert len(request) < 2048
            path = request.split(b" ", 2)[1]
            if path == b"/json/list":
                pages = self.server.pages or [{"type": "page", "url": "https://music.youtube.com/watch?v=test", "webSocketDebuggerUrl": f"ws://127.0.0.1:{self.server.server_address[1]}/devtools/page/test"}]
                body = json.dumps(pages).encode()
                # Deliberately separate headers and body to exercise framing.
                s.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n")
                time.sleep(.005)
                s.sendall(body)
                return
            assert path == b"/devtools/page/test"
            headers = dict(line.split(b": ", 1) for line in request.split(b"\r\n")[1:] if b": " in line)
            key = headers[b"Sec-WebSocket-Key"]
            accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            s.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
            opcode, payload = read_frame(s)
            assert opcode == 1
            query = json.loads(payload)
            if query["method"] == "Page.bringToFront":
                self.server.activations += 1
                s.sendall(frame(json.dumps({"id": query["id"], "result": {}})))
                return
            assert query["params"]["awaitPromise"] is True
            expression = query["params"]["expression"]
            assert "location.origin" in expression
            if self.server.mode == "stall":
                time.sleep(1.3)
                return
            if self.server.mode == "oversize":
                s.sendall(b"\x81\x7e\xff\xff")
                return
            if self.server.mode == "malformed":
                s.sendall(frame('{"id":1,"result":'))
                return
            if "p.playVideo()" in expression:
                if self.server.apply_delay:
                    threading.Timer(self.server.apply_delay, setattr, args=(self.server,"playing",True)).start()
                else:
                    self.server.playing = True
                self.server.actions.append("PLAY")
                value = "ok"
            elif "p.pauseVideo()" in expression:
                self.server.playing = False
                self.server.actions.append("REWIND" if "p.seekTo(0,true)" in expression else "PAUSE")
                value = "ok"
            elif "p.setVolume(" in expression:
                self.server.volume = int(expression.split("p.setVolume(")[1].split(")")[0])
                self.server.actions.append("VOLUME")
                value = "ok"
            elif "next.resolveCommand(" in expression:
                if self.server.mode != "next_noop":
                    self.server.title = "Next Track"
                    self.server.video_id = "nextsong000"
                self.server.actions.append("NEXT")
                value = "nextsong000"
            else:
                value = f"{int(self.server.playing)}\t96000\t{self.server.volume}\t{self.server.title}\t{self.server.artist}\t{self.server.output}\t{self.server.status}\t{self.server.video_id}"
            if self.server.mode == "lose_action_reply" and value == "ok":
                return
            if value == "ok" and self.server.action_reply_gate is not None:
                assert self.server.action_reply_gate.wait(2), "test did not release action reply"
            # Event + ping + fragmented reply exercise actual message parsing.
            s.sendall(frame(json.dumps({"method": "Runtime.consoleAPICalled", "params": {}})))
            s.sendall(frame(b"proof", opcode=9))
            opcode, pong = read_frame(s)
            assert (opcode, pong) == (10, b"proof")
            self.server.pongs += 1
            answer = json.dumps({"id": query["id"], "result": {"result": {"type": "string", "value": value}}}).encode()
            mid = len(answer) // 2
            s.sendall(frame(answer[:mid], final=False) + frame(answer[mid:], opcode=0))
        except (EOFError, ConnectionError, TimeoutError):
            pass
        except BaseException as error:
            self.server.errors.append(repr(error))


@pytest.fixture(scope="module")
def binary(tmp_path_factory):
    path = tmp_path_factory.mktemp("music-bin") / "bridge"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pthread", str(ROOT / "appliance/native/music_bridge.c"), "-o", str(path)], check=True)
    return path


@pytest.fixture
def running(binary):
    browser = Browser()
    thread = threading.Thread(target=browser.serve_forever, daemon=True)
    thread.start()
    with tempfile.TemporaryDirectory(prefix="forge-cdp-") as directory:
        path = str(Path(directory) / "session.sock")
        process = subprocess.Popen([str(binary), "--socket", path, "--cdp-port", str(browser.server_address[1]), "--seconds", "60"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            wait_for(lambda: os.path.exists(path))
            yield browser, path, process
        finally:
            process.terminate()
            process.communicate(timeout=5)
            assert not os.path.exists(path)
            browser.shutdown()
            browser.server_close()
            thread.join(timeout=2)
            assert not browser.errors


def request(path, command="GET", timeout=2):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(path)
        s.sendall(command.encode() + b"\n")
        data = b""
        while not data.endswith(b"\n"):
            chunk = s.recv(512)
            assert chunk, "bridge closed before reply"
            data += chunk
        return data.decode()


def wait_for(predicate, seconds=4):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.025)
    raise AssertionError("condition did not become true")


def connected(path):
    state = request(path)
    return state if state.split("\t")[0].split()[-1] == "0" else None


def test_real_wire_controls_metadata_and_stale(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    assert state.endswith('\tFirst "Track"\tTest Artist\tTHIS TABLET\tREADY\n')
    rev = state.split()[1]
    played = request(path, f"DO {rev} PLAY")
    assert played.split()[2] == "1"
    assert request(path, f"DO {rev} PAUSE").startswith("STALE ")
    assert browser.actions == ["PLAY"]
    rev = played.split()[1]
    paused = request(path, f"DO {rev} PAUSE")
    assert paused.split()[2] == "0"
    volume = request(path, f"DO {paused.split()[1]} VOLUME 22")
    assert volume.split()[3] == "22"
    assert browser.actions == ["PLAY", "PAUSE", "VOLUME"]
    assert browser.pongs >= 7
    assert request(path, f"DO {volume.split()[1]} VOLUME 20 junk").startswith("ERR ")


def test_cached_get_stays_fast_during_stall_and_never_replays(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.mode = "stall"
    time.sleep(.6)
    start = time.monotonic()
    request(path, timeout=.2)
    assert time.monotonic() - start < .2
    wait_for(lambda: request(path).split("\t")[0].split()[-1] == "1")
    assert request(path, f"DO {state.split()[1]} PLAY").startswith(("STALE ", "ERR "))
    browser.mode = "good"
    wait_for(lambda: connected(path))
    assert browser.actions == []


@pytest.mark.parametrize("mode", ["malformed", "oversize"])
def test_invalid_browser_messages_become_offline(running, mode):
    browser, path, _ = running
    wait_for(lambda: connected(path))
    browser.mode = mode
    wait_for(lambda: request(path).split("\t")[0].split()[-1] == "1")
    assert browser.actions == []


def test_rejects_malicious_origin_before_opening_its_websocket(running):
    browser, path, _ = running
    port = browser.server_address[1]
    browser.pages = [
        {"type": "page", "url": "https://music.youtube.com.evil.invalid/", "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/evil"},
        {"type": "page", "url": "https://music.youtube.com/", "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/test"},
    ]
    assert wait_for(lambda: connected(path)).endswith("\tTest Artist\tTHIS TABLET\tREADY\n")


def test_refuses_ambiguous_eligible_ytm_pages(running):
    browser, path, _ = running
    port = browser.server_address[1]
    browser.pages = [
        {"type": "page", "url": "https://music.youtube.com/watch?v=one", "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/test"},
        {"type": "page", "url": "https://music.youtube.com/watch?v=two", "webSocketDebuggerUrl": f"ws://127.0.0.1:{port}/devtools/page/other"},
    ]
    assert wait_for(lambda: request(path).split("\t")[0].split()[-1] == "1")


def test_lost_mutation_reply_is_reported_and_never_replayed(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.mode = "lose_action_reply"
    failed = request(path, f"DO {state.split()[1]} PLAY")
    assert failed.startswith("FAILED ")
    assert failed.split()[2] == "0", "the last confirmed state remains usable after a lost action reply"
    assert failed.endswith('\tFirst "Track"\tTest Artist\tTHIS TABLET\tREADY\n')
    assert browser.actions == ["PLAY"]
    browser.mode = "good"
    wait_for(lambda: connected(path))
    time.sleep(.6)
    assert browser.actions == ["PLAY"]


def test_stream_limit_blocks_play_and_next_without_dispatch(running):
    browser, path, _ = running
    browser.status = "STREAM_LIMIT"
    state = wait_for(lambda: value if (value := connected(path)) and value.endswith("\tSTREAM_LIMIT\n") else None)
    assert request(path, f"DO {state.split()[1]} PLAY").startswith("FAILED ")
    state = request(path)
    assert request(path, f"DO {state.split()[1]} NEXT").startswith("FAILED ")
    assert browser.actions == []


def test_next_requires_the_resolved_video_identity_to_advance(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.mode = "next_noop"
    failed = request(path, f"DO {state.split()[1]} NEXT", timeout=15.5)
    assert failed.startswith("FAILED ")
    assert failed.endswith('\tFirst "Track"\tTest Artist\tTHIS TABLET\tREADY\n')
    assert browser.actions == ["NEXT"]
    browser.mode = "good"
    state = request(path)
    advanced = request(path, f"DO {state.split()[1]} NEXT")
    assert advanced.startswith("OK ")
    assert advanced.endswith("\tNext Track\tTest Artist\tTHIS TABLET\tREADY\n")


def test_focuses_music_once_without_stealing_focus_on_later_read_failures(running):
    browser, path, _ = running
    wait_for(lambda: connected(path))
    assert browser.activations == 1
    browser.mode = "malformed"
    wait_for(lambda: request(path).split("\t")[0].split()[-1] == "1")
    browser.mode = "good"
    wait_for(lambda: connected(path))
    assert browser.activations == 1


def test_pending_client_disconnect_releases_the_single_mutation_slot(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.action_reply_gate = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(path)
        client.sendall(f"DO {state.split()[1]} PLAY\n".encode())
        # Establish a pending action before disconnecting. Closing immediately
        # after send races the server's POLLHUP and can cancel an unread request.
        wait_for(lambda: browser.actions == ["PLAY"])
    browser.action_reply_gate.set()
    def pause_when_free():
        state = connected(path)
        if not state:
            return None
        reply = request(path, f"DO {state.split()[1]} PAUSE")
        return reply if reply.startswith("OK ") else None

    assert wait_for(pause_when_free)
    assert browser.actions == ["PLAY", "PAUSE"]


def test_pending_confirmation_does_not_block_cached_get(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.action_reply_gate = threading.Event()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(path)
        client.sendall(f"DO {state.split()[1]} PLAY\n".encode())
        wait_for(lambda: browser.actions == ["PLAY"])
        start = time.monotonic()
        cached = request(path, timeout=.2)
        assert time.monotonic() - start < .2
        assert cached.startswith("OK ") and cached.split()[2] == "0"
        browser.action_reply_gate.set()
        reply = b""
        while not reply.endswith(b"\n"):
            reply += client.recv(512)
    assert reply.decode().startswith("OK ")


def test_shutdown_does_not_unlink_a_replacement_socket(binary):
    with tempfile.TemporaryDirectory(prefix="forge-replace-") as directory:
        path = str(Path(directory) / "session.sock")
        process = subprocess.Popen([str(binary), "--socket", path, "--cdp-port", "9", "--seconds", "60"])
        replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            wait_for(lambda: os.path.exists(path))
            os.unlink(path)
            replacement.bind(path)
            inode = os.lstat(path).st_ino
            process.terminate()
            process.wait(timeout=5)
            assert os.path.exists(path)
            assert os.lstat(path).st_ino == inode
        finally:
            replacement.close()
            if os.path.exists(path):
                os.unlink(path)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)


def test_play_observes_delayed_effect_without_replaying_action(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.apply_delay = .7
    started = time.monotonic()
    reply = request(path, f"DO {state.split()[1]} PLAY")
    assert reply.startswith("OK ") and reply.split()[2] == "1"
    assert time.monotonic() - started >= .65
    assert browser.actions == ["PLAY"]


def test_slow_song_start_is_confirmed_without_replaying(running):
    browser, path, _ = running
    state = wait_for(lambda: connected(path))
    browser.apply_delay = 5.6
    reply = request(path, f"DO {state.split()[1]} PLAY", timeout=8)
    assert reply.startswith("OK ") and reply.split()[2] == "1"
    assert browser.actions == ["PLAY"]
