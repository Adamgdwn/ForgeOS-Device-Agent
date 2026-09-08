"""Host-only lifecycle checks for the Exynos3475 direct display UAPI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "appliance" / "native" / "samsung_display.h"


@pytest.fixture(scope="module")
def display_boundary_runner(tmp_path_factory: pytest.TempPathFactory) -> Path:
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for display boundary test")
    output = tmp_path_factory.mktemp("samsung-display") / "boundary"
    harness = r'''
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static int fake_open(const char *path, int flags, ...);
static int fake_ioctl(int fd, unsigned long request, ...);
static void *fake_mmap(void *address, size_t length, int protection, int flags, int fd, off_t offset);
static int fake_munmap(void *address, size_t length);
static int fake_close(int fd);
static int fake_fcntl(int fd, int command, ...);
static int fake_poll(struct pollfd *fds, nfds_t count, int timeout);
#define open fake_open
#define ioctl fake_ioctl
#define mmap fake_mmap
#define munmap fake_munmap
#define close fake_close
#define fcntl fake_fcntl
#define poll fake_poll
#include "__HEADER__"
#undef poll
#undef fcntl
#undef close
#undef munmap
#undef mmap
#undef ioctl
#undef open

enum { ALLOCATE_RELEASE, REUSE_FENCE, FAILURE_PATHS };
static int mode, opens, allocs, shares, frees, maps, unmaps, polls, submit_calls;
static int fail_share_at, submit_fence = 70, poll_result = 1;
static int closed[64], closed_count;
static unsigned char pages[2][64];

static void reset(void) {
    mode = opens = allocs = shares = frees = maps = unmaps = polls = submit_calls = 0;
    fail_share_at = 0; submit_fence = 70; poll_result = 1; closed_count = 0;
    memset(closed, 0, sizeof(closed));
}
static int was_closed(int fd) {
    for (int i = 0; i < closed_count; ++i) if (closed[i] == fd) return 1;
    return 0;
}
static int fake_open(const char *path, int flags, ...) {
    (void)path; (void)flags; ++opens; return 10;
}
static int fake_fcntl(int fd, int command, ...) { (void)fd; (void)command; return 0; }
static int fake_close(int fd) { closed[closed_count++] = fd; return 0; }
static void *fake_mmap(void *address, size_t length, int protection, int flags, int fd, off_t offset) {
    (void)address; (void)length; (void)protection; (void)flags; (void)offset;
    ++maps; return pages[fd - 20];
}
static int fake_munmap(void *address, size_t length) { (void)address; (void)length; ++unmaps; return 0; }
static int fake_poll(struct pollfd *fds, nfds_t count, int timeout) {
    (void)count; (void)timeout; ++polls;
    if (poll_result > 0) fds[0].revents = POLLIN;
    return poll_result;
}
static int fake_ioctl(int fd, unsigned long request, ...) {
    va_list ap; va_start(ap, request);
    if (request == FORGE_ION_ALLOC) {
        ForgeIonAlloc *a = va_arg(ap, ForgeIonAlloc *); ++allocs; a->handle = 100 + allocs;
    } else if (request == FORGE_ION_SHARE) {
        ForgeIonFd *shared = va_arg(ap, ForgeIonFd *); ++shares;
        if (fail_share_at == shares) { errno = ENOMEM; va_end(ap); return -1; }
        shared->fd = 19 + shares;
    } else if (request == FORGE_ION_FREE) {
        (void)va_arg(ap, int32_t *); ++frees;
    } else if (request == FORGE_WIN_CONFIG) {
        ForgeWindows *config = va_arg(ap, ForgeWindows *); ++submit_calls;
        if (mode == FAILURE_PATHS && submit_calls == 2) { errno = EIO; va_end(ap); return -1; }
        config->fence = submit_fence++;
    }
    (void)fd; va_end(ap); return 0;
}
static int allocation_and_release(void) {
    SamsungDisplay display; reset();
    if (samsung_allocate(&display, sizeof pages[0]) == 0 || errno != ENOTSUP || opens || allocs || shares || maps) return 1;
    samsung_init(&display); display.size = sizeof pages[0]; display.ion = 10;
    display.buffer[0] = 20; display.buffer[1] = 21;
    display.memory[0] = pages[0]; display.memory[1] = pages[1];
    display.handle[0] = 101; display.handle[1] = 102;
    samsung_release(&display);
    if (frees != 2 || unmaps != 2 || !was_closed(10) || !was_closed(20) || !was_closed(21)) return 2;
    return 0;
}
static int release_fence_reuse(void) {
    SamsungDisplay display; reset(); samsung_init(&display);
    display.size = sizeof pages[0]; display.ion = 10; display.buffer[0] = 20; display.buffer[1] = 21;
    display.memory[0] = pages[0]; display.memory[1] = pages[1]; display.handle[0] = 101; display.handle[1] = 102;
    if (samsung_submit(&display, 30, 1) || display.next != 1 || display.fence[0] != 70 || polls) return 1;
    if (samsung_submit(&display, 30, 1) || display.next != 0 || display.fence[1] != 71 || polls) return 2;
    if (samsung_begin(&display) != pages[0] || polls != 1 || display.fence[0] != -1 || !was_closed(70)) return 3;
    if (samsung_begin(&display) != pages[0] || polls != 1) return 4;
    samsung_release(&display);
    if (!was_closed(71) || frees != 2 || unmaps != 2) return 5;
    return 0;
}
static int failures_fail_closed_and_cleanup(void) {
    SamsungDisplay display; reset(); samsung_init(&display); display.buffer[0] = 20; display.memory[0] = pages[0];
    submit_fence = -1;
    if (samsung_submit(&display, 30, 1) == 0 || errno != EPROTO || display.next != 0 || display.fence[0] != -1) return 1;
    submit_fence = 70; submit_calls = 0; mode = FAILURE_PATHS;
    if (samsung_submit(&display, 30, 1) || display.next != 1 || display.fence[0] != 70) return 2;
    if (samsung_submit(&display, 30, 1) == 0 || display.next != 1 || display.fence[1] != -1) return 3;
    poll_result = 0;
    display.next = 0;
    if (samsung_begin(&display) != NULL || errno != ETIMEDOUT || display.fence[0] != -1 || !was_closed(70)) return 4;
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 2) return 64;
    if (!strcmp(argv[1], "allocation")) return allocation_and_release();
    if (!strcmp(argv[1], "reuse")) return release_fence_reuse();
    if (!strcmp(argv[1], "failure")) return failures_fail_closed_and_cleanup();
    return 64;
}
'''.replace("__HEADER__", str(HEADER))
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-x", "c", "-", "-o", str(output)],
        input=harness,
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize("scenario", ["allocation", "reuse", "failure"])
def test_samsung_display_owns_double_buffer_fences_and_cleanup(
    display_boundary_runner: Path, scenario: str
) -> None:
    result = subprocess.run([str(display_boundary_runner), scenario], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
