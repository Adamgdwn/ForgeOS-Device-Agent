"""Host-boundary tests for retained evdev touch-state seeding."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "appliance" / "native" / "touch_state.h"


@pytest.fixture(scope="module")
def touch_state_boundary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the production header against an ioctl-shaped deterministic fake."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for touch-state boundary test")

    directory = tmp_path_factory.mktemp("touch-state")
    harness = directory / "touch-state-boundary.c"
    harness.write_text(
        f'''\
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

enum scenario {{ MT, LEGACY, AXIS_FAILURE, CLAMP, BAD_SLOT }};
static enum scenario selected;
static int calls;

#define ioctl forge_fake_ioctl
#include "{HEADER}"
#undef ioctl

int forge_fake_ioctl(int fd, unsigned long request, ...) {{
    va_list arguments;
    void *output;
    (void)fd;
    calls++;
    va_start(arguments, request);
    output = va_arg(arguments, void *);
    va_end(arguments);

    if (request == EVIOCGMTSLOTS(sizeof(int[2]))) {{
        int *slots = output;
        if (selected == LEGACY || selected == AXIS_FAILURE) {{
            errno = ENOTTY;
            return -1;
        }}
        slots[1] = slots[0] == ABS_MT_POSITION_X
            ? (selected == CLAMP ? -50 : 1601)
            : (selected == CLAMP ? 9999 : 4738);
        return 0;
    }}
    if (request == EVIOCGABS(ABS_X) || request == EVIOCGABS(ABS_Y)) {{
        struct input_absinfo *axis = output;
        if (selected == AXIS_FAILURE) {{
            errno = EIO;
            return -1;
        }}
        memset(axis, 0, sizeof(*axis));
        axis->value = request == EVIOCGABS(ABS_X) ? 801 : 2369;
        return 0;
    }}
    if (request == EVIOCGABS(ABS_MT_SLOT)) {{
        struct input_absinfo *slot = output;
        if (selected == BAD_SLOT) {{
            slot->minimum = 0;
            slot->maximum = 2;
            slot->value = 3;
        }} else {{
            slot->minimum = 0;
            slot->maximum = 7;
            slot->value = 4;
        }}
        return 0;
    }}
    errno = EINVAL;
    return -1;
}}

static int run(enum scenario mode, int minx, int maxx, int miny, int maxy,
               int width, int height, int wanted_x, int wanted_y,
               int wanted_slot, int wanted_errno, int wanted_calls) {{
    int x = -1, y = -1, slot = -1;
    int result;
    selected = mode;
    calls = 0;
    errno = 0;
    result = forge_touch_seed(9, minx, maxx, miny, maxy, width, height,
                              &x, &y, &slot);
    if (wanted_errno) return result == -1 && errno == wanted_errno && calls == wanted_calls ? 0 : 1;
    return result == 0 && x == wanted_x && y == wanted_y && slot == wanted_slot && calls == wanted_calls ? 0 : 1;
}}

int main(int argc, char **argv) {{
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "mt"))
        return run(MT, 0, 1601, 0, 4738, 800, 480, 799, 479, 4, 0, 3);
    if (!strcmp(argv[1], "legacy"))
        return run(LEGACY, 0, 1602, 0, 4738, 802, 480, 400, 239, 4, 0, 5);
    if (!strcmp(argv[1], "axis-failure"))
        return run(AXIS_FAILURE, 0, 1601, 0, 4738, 800, 480, 0, 0, 0, EIO, 2);
    if (!strcmp(argv[1], "clamp"))
        return run(CLAMP, 0, 1601, 0, 4738, 800, 480, 0, 479, 4, 0, 3);
    if (!strcmp(argv[1], "bad-slot"))
        return run(BAD_SLOT, 0, 1601, 0, 4738, 800, 480, 799, 479, 0, EINVAL, 3);
    if (!strcmp(argv[1], "geometry"))
        return run(MT, 1, 1, 0, 4738, 800, 480, 0, 0, 0, EINVAL, 0);
    return 2;
}}
'''
    )
    output = directory / "touch-state-boundary"
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(output)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return output


@pytest.mark.parametrize(
    "case",
    ["mt", "legacy", "axis-failure", "clamp", "bad-slot", "geometry"],
)
def test_touch_seed_handles_evdev_state_boundaries(touch_state_boundary: Path, case: str) -> None:
    result = subprocess.run([str(touch_state_boundary), case], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
