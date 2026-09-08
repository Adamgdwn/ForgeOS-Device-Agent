"""Event-stream conformance tests for the production ForgeTouch decoder."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "appliance" / "native" / "touch_state.h"


@pytest.fixture(scope="module")
def touch_stream_harness(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Compile the actual header with deterministic ioctl state at its boundary."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for touch stream test")
    directory = tmp_path_factory.mktemp("touch-stream")
    source = directory / "touch-stream.c"
    source.write_text(
        f'''\
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int forge_fake_ioctl(int fd, unsigned long request, ...);
#define ioctl forge_fake_ioctl
#include "{HEADER}"
#undef ioctl

static int mt = 1;
static int current_slot;
static int raw_x[FORGE_TOUCH_SLOTS];
static int raw_y[FORGE_TOUCH_SLOTS];

int forge_fake_ioctl(int fd, unsigned long request, ...) {{
    va_list arguments;
    void *output;
    (void)fd;
    va_start(arguments, request);
    output = va_arg(arguments, void *);
    va_end(arguments);
    if (request == EVIOCGABS(ABS_MT_SLOT)) {{
        struct input_absinfo *axis = output;
        if (!mt) {{ errno = ENOTTY; return -1; }}
        memset(axis, 0, sizeof(*axis));
        axis->minimum = 0; axis->maximum = 2; axis->value = current_slot;
        return 0;
    }}
    if (request == EVIOCGABS(ABS_MT_POSITION_X) || request == EVIOCGABS(ABS_MT_POSITION_Y) ||
        request == EVIOCGABS(ABS_X) || request == EVIOCGABS(ABS_Y)) {{
        struct input_absinfo *axis = output;
        int is_x = request == EVIOCGABS(ABS_MT_POSITION_X) || request == EVIOCGABS(ABS_X);
        memset(axis, 0, sizeof(*axis));
        axis->minimum = 0; axis->maximum = 1000;
        axis->value = is_x ? raw_x[current_slot] : raw_y[current_slot];
        return 0;
    }}
    if (_IOC_TYPE(request) == _IOC_TYPE(EVIOCGMTSLOTS(0))) {{
        int *values = output;
        if (!mt) {{ errno = ENOTTY; return -1; }}
        for (int slot = 0; slot < 3; slot++) values[slot + 1] =
            values[0] == ABS_MT_POSITION_X ? raw_x[slot] : raw_y[slot];
        return 0;
    }}
    errno = EINVAL;
    return -1;
}}

typedef struct {{ int result, x, y, dx, dy; }} Got;

static int send_event(ForgeTouch *state, unsigned short type, unsigned short code,
                      int value, Got *got) {{
    struct input_event event;
    memset(&event, 0, sizeof(event));
    event.type = type; event.code = code; event.value = value;
    got->result = forge_touch_event(state, &event, &got->x, &got->y, &got->dx, &got->dy);
    return got->result;
}}
static int report(ForgeTouch *state, Got *got) {{ return send_event(state, EV_SYN, SYN_REPORT, 0, got); }}
static int expect(Got got, int result, int x, int y, int dx, int dy) {{
    return got.result == result && (!result || (got.x == x && got.y == y && got.dx == dx && got.dy == dy));
}}
static int init(ForgeTouch *state, int multi) {{
    mt = multi; current_slot = 0;
    memset(raw_x, 0, sizeof(raw_x)); memset(raw_y, 0, sizeof(raw_y));
    return forge_touch_init(state, 9, 1001, 1001);
}}

static int retained(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    raw_x[0] = 333; raw_y[0] = 444;
    if (forge_touch_resync(&state) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 9, &got) || report(&state, &got)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 333, 444, 0, 0);
}}
static int nonzero_slot(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_SLOT, 2, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_X, 600, &got) ||
        send_event(&state, EV_ABS, ABS_MT_POSITION_Y, 700, &got) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 3, &got) || report(&state, &got)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 600, 700, 0, 0);
}}
static int secondary(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_POSITION_X, 100, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_Y, 200, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 1, &got) || report(&state, &got) ||
        send_event(&state, EV_ABS, ABS_MT_SLOT, 1, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_X, 800, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 2, &got) || report(&state, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_SLOT, 0, &got) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 100, 200, 0, 0);
}}
static int separate_slots(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_POSITION_X, 10, &got) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 1, &got) || report(&state, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1 || !expect(got, 1, 10, 0, 0, 0) ||
        send_event(&state, EV_ABS, ABS_MT_SLOT, 2, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_X, 900, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_Y, 800, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 2, &got) || report(&state, &got) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 900, 800, 0, 0);
}}
static int dropped(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 4, &got) || report(&state, &got) ||
        send_event(&state, EV_SYN, SYN_DROPPED, 0, &got) || send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) || report(&state, &got)) return 1;
    return 0;
}}
static int legacy(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 0)) return 1;
    if (send_event(&state, EV_ABS, ABS_X, 250, &got) || send_event(&state, EV_ABS, ABS_Y, 750, &got) ||
        send_event(&state, EV_KEY, BTN_TOUCH, 1, &got) || report(&state, &got) || send_event(&state, EV_KEY, BTN_TOUCH, 0, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 250, 750, 0, 0);
}}
static int drag(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    if (send_event(&state, EV_ABS, ABS_MT_POSITION_X, 10, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_Y, 10, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, 7, &got) || report(&state, &got) ||
        send_event(&state, EV_ABS, ABS_MT_POSITION_X, 110, &got) || send_event(&state, EV_ABS, ABS_MT_POSITION_Y, 180, &got) || report(&state, &got) ||
        send_event(&state, EV_ABS, ABS_MT_TRACKING_ID, -1, &got) || report(&state, &got) != 1) return 1;
    return !expect(got, 1, 110, 180, 100, 170);
}}
static int invalid_slot(void) {{
    ForgeTouch state; Got got = {{0}};
    if (init(&state, 1)) return 1;
    errno = 0;
    return !(send_event(&state, EV_ABS, ABS_MT_SLOT, 3, &got) == -1 && errno == EINVAL);
}}
int main(int argc, char **argv) {{
    if (argc != 2) return 2;
    if (!strcmp(argv[1], "retained")) return retained();
    if (!strcmp(argv[1], "nonzero-slot")) return nonzero_slot();
    if (!strcmp(argv[1], "secondary")) return secondary();
    if (!strcmp(argv[1], "separate-slots")) return separate_slots();
    if (!strcmp(argv[1], "dropped")) return dropped();
    if (!strcmp(argv[1], "legacy")) return legacy();
    if (!strcmp(argv[1], "drag")) return drag();
    if (!strcmp(argv[1], "invalid-slot")) return invalid_slot();
    return 2;
}}
'''
    )
    binary = directory / "touch-stream"
    result = subprocess.run(
        [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return binary


@pytest.mark.parametrize(
    "case",
    ["retained", "nonzero-slot", "secondary", "separate-slots", "dropped", "legacy", "drag", "invalid-slot"],
)
def test_forge_touch_event_streams(touch_stream_harness: Path, case: str) -> None:
    result = subprocess.run([str(touch_stream_harness), case], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


def test_nonzero_slot_stream_reaches_panel_gesture_routing(tmp_path: Path) -> None:
    """A decoded slot-two tap must reach the Music-to-Browse panel action."""
    cc = shutil.which("cc")
    if not cc:
        pytest.skip("no C compiler available for panel routing test")
    source = tmp_path / "touch-routing.c"
    source.write_text(
        f'''\
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <string.h>
int forge_fake_ioctl(int fd, unsigned long request, ...);
#define ioctl forge_fake_ioctl
#define main forge_panel_entry
#include "{ROOT / "appliance" / "native" / "panel.c"}"
#undef main
#undef ioctl

static int raw_x[3], raw_y[3], current_slot;
int forge_fake_ioctl(int fd, unsigned long request, ...) {{
  va_list arguments; void *out; (void)fd; va_start(arguments, request); out=va_arg(arguments, void *); va_end(arguments);
  if(request==EVIOCGABS(ABS_MT_SLOT)) {{ struct input_absinfo *a=out; memset(a,0,sizeof *a);a->maximum=2;a->value=current_slot;return 0; }}
  if(request==EVIOCGABS(ABS_MT_POSITION_X)||request==EVIOCGABS(ABS_MT_POSITION_Y)) {{ struct input_absinfo *a=out; memset(a,0,sizeof *a);a->maximum=1000;a->value=request==EVIOCGABS(ABS_MT_POSITION_X)?raw_x[current_slot]:raw_y[current_slot];return 0; }}
  if(_IOC_TYPE(request)==_IOC_TYPE(EVIOCGMTSLOTS(0))) {{ int *v=out;for(int i=0;i<3;i++)v[i+1]=v[0]==ABS_MT_POSITION_X?raw_x[i]:raw_y[i];return 0; }}
  errno=EINVAL;return -1;
}}
static int event(ForgeTouch *state,unsigned short type,unsigned short code,int value,int *x,int *y,int *dx,int *dy) {{
  struct input_event input={{0}};input.type=type;input.code=code;input.value=value;return forge_touch_event(state,&input,x,y,dx,dy);
}}
int main(void) {{
  ForgeTouch state;int x,y,dx,dy;
  assert(!forge_touch_init(&state,9,1001,1001));
  assert(!event(&state,EV_ABS,ABS_MT_SLOT,2,&x,&y,&dx,&dy));
  assert(!event(&state,EV_ABS,ABS_MT_POSITION_X,400,&x,&y,&dx,&dy));
  assert(!event(&state,EV_ABS,ABS_MT_POSITION_Y,500,&x,&y,&dx,&dy));
  assert(!event(&state,EV_ABS,ABS_MT_TRACKING_ID,6,&x,&y,&dx,&dy));
  assert(!event(&state,EV_SYN,SYN_REPORT,0,&x,&y,&dx,&dy));
  assert(!event(&state,EV_ABS,ABS_MT_TRACKING_ID,-1,&x,&y,&dx,&dy));
  assert(event(&state,EV_SYN,SYN_REPORT,0,&x,&y,&dx,&dy)==1);
  web_surface_path="surface";web_socket_path="socket";browse_page=home_page=pending_browser_tab=0;
  gesture(x,y,dx,dy);
  assert(browse_page&&pending_browser_tab==1);
  return 0;
}}
'''
    )
    executable = tmp_path / "touch-routing"
    compiled = subprocess.run(
        [cc, "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert compiled.returncode == 0, compiled.stderr
    result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
