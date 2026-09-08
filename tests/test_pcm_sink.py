"""No-hardware boundary tests for the direct ALSA PCM bring-up utility."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SINK = ROOT / "appliance" / "native" / "pcm_sink.c"


@pytest.fixture(scope="module")
def sink_boundary_runner(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for PCM sink boundary test")
    output = tmp_path_factory.mktemp("pcm-sink") / "boundary"
    harness = r'''
#include <errno.h>
#include <poll.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>

static int fake_poll(struct pollfd *fds, nfds_t nfds, int timeout);
static int fake_ioctl(int fd, unsigned long request, ...);
#define poll fake_poll
#define ioctl fake_ioctl
#define main pcm_sink_program_main
#include "__SINK__"
#undef main
#undef ioctl
#undef poll

enum { PARTIAL, EAGAIN_ONCE, UNDERRUN_ONCE };
static int scenario, writes, prepares;

static int fake_poll(struct pollfd *fds, nfds_t nfds, int timeout) {
    (void)nfds; (void)timeout;
    fds[0].revents = fds[0].events;
    return 1;
}

static int fake_ioctl(int fd, unsigned long request, ...) {
    va_list ap;
    (void)fd;
    va_start(ap, request);
    if (request == SNDRV_PCM_IOCTL_WRITEI_FRAMES) {
        struct snd_xferi *xfer = va_arg(ap, struct snd_xferi *);
        ++writes;
        if (scenario == EAGAIN_ONCE && writes == 1) {
            errno = EAGAIN;
            va_end(ap);
            return -1;
        }
        if (scenario == UNDERRUN_ONCE && writes == 1) {
            xfer->result = -EPIPE;
            va_end(ap);
            return 0;
        }
        xfer->result = (scenario == PARTIAL && writes == 1) ? 2 : (snd_pcm_sframes_t)xfer->frames;
        va_end(ap);
        return 0;
    }
    if (request == SNDRV_PCM_IOCTL_PREPARE) ++prepares;
    va_end(ap);
    return 0;
}

int main(int argc, char **argv) {
    uint8_t data[5 * BYTES_PER_FRAME] = {0};
    uint64_t written = 0;
    unsigned int recoveries = 0;
    if (argc != 2) return 64;
    scenario = atoi(argv[1]);
    interrupted = 0;
    if (write_frames(9, data, 5, &recoveries, &written) != 0) return 2;
    if (written != 5) return 3;
    if (scenario == UNDERRUN_ONCE && (recoveries != 1 || prepares != 1)) return 4;
    return 0;
}
'''.replace("__SINK__", str(SINK))
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-D_POSIX_C_SOURCE=200809L", "-x", "c", "-", "-o", str(output)],
        input=harness,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize("scenario", [0, 1, 2], ids=["partial-write", "eagain", "underrun"])
def test_pcm_sink_retries_transient_output_and_counts_recovery(
    sink_boundary_runner: Path, scenario: int
) -> None:
    result = subprocess.run([str(sink_boundary_runner), str(scenario)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_pcm_sink_builds_armv7_static_binary() -> None:
    script = ROOT / "appliance" / "native" / "build-pcm-sink-armv7.sh"
    result = subprocess.run(["timeout", "--signal=TERM", "--kill-after=5s", "120s", str(script)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    binary = ROOT / "output" / "native-arm" / "forge-pcm-sink"
    description = subprocess.run(["file", str(binary)], capture_output=True, text=True, check=True).stdout
    assert "ARM" in description and "statically linked" in description


def test_pcm_sink_idle_fifo_uses_pcm_clock_without_input_period_wait(tmp_path: Path) -> None:
    """An empty idle-silence FIFO must fill the exact ALSA-clock budget."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for PCM sink idle boundary test")
    output = tmp_path / "idle-boundary"
    harness = r'''
#include <errno.h>
#include <poll.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>

static int fake_open(const char *path, int flags, ...);
static int fake_fstat(int fd, struct stat *info);
static int fake_poll(struct pollfd *fds, nfds_t nfds, int timeout);
static int fake_ioctl(int fd, unsigned long request, ...);
static int fake_fcntl(int fd, int command, ...);
static int fake_close(int fd);
#define open fake_open
#define fstat fake_fstat
#define poll fake_poll
#define ioctl fake_ioctl
#define fcntl fake_fcntl
#define close fake_close
#define main pcm_sink_program_main
#include "__SINK__"
#undef main
#undef close
#undef fcntl
#undef ioctl
#undef poll
#undef fstat
#undef open

static int input_polls, output_polls, writes, drains;
static uint64_t frames;
static int fake_open(const char *path, int flags, ...) {
    (void)path; (void)flags;
    static int calls; return calls++ ? 41 : 40;
}
static int fake_fstat(int fd, struct stat *info) {
    (void)fd; memset(info, 0, sizeof(*info)); info->st_mode = S_IFIFO; return 0;
}
static int fake_poll(struct pollfd *fds, nfds_t nfds, int timeout) {
    (void)nfds;
    if (fds[0].fd == 40) { ++input_polls; if (timeout != 0) return -1; return 0; }
    ++output_polls; fds[0].revents = POLLOUT; return 1;
}
static int fake_ioctl(int fd, unsigned long request, ...) {
    va_list ap; (void)fd; va_start(ap, request);
    if (request == SNDRV_PCM_IOCTL_WRITEI_FRAMES) {
        struct snd_xferi *xfer = va_arg(ap, struct snd_xferi *);
        ++writes; frames += xfer->frames; xfer->result = (snd_pcm_sframes_t)xfer->frames;
    } else if (request == SNDRV_PCM_IOCTL_DRAIN) ++drains;
    va_end(ap); return 0;
}
static int fake_fcntl(int fd, int command, ...) { (void)fd; (void)command; return 0; }
static int fake_close(int fd) { (void)fd; return 0; }
int main(void) {
    char *argv[] = {"sink", "--input", "idle.fifo", "--seconds", "1", "--idle-silence", NULL};
    if (pcm_sink_program_main(6, argv) != 0) return 1;
    return input_polls != 50 || output_polls != 50 || writes != 50 || frames != 48000 || drains != 1;
}
'''.replace("__SINK__", str(SINK))
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-D_POSIX_C_SOURCE=200809L", "-x", "c", "-", "-o", str(output)],
        input=harness,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(output)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
