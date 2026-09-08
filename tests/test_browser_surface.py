from __future__ import annotations

import os
import socket
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compile(source: Path, output: Path, compiler: str = "cc", libraries: list[str] | None = None) -> None:
    subprocess.run([compiler, "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(output), *(libraries or [])], check=True)


def _abstract_socket_is_available(display_number: int) -> bool:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(0.1)
        client.connect(b"\0/tmp/.X11-unix/X" + str(display_number).encode())
    except OSError:
        return True
    finally:
        client.close()
    return False


def _listener_belongs_to(pid: int, path: str) -> bool:
    socket_inodes = set()
    for entry in Path(f"/proc/{pid}/fd").iterdir():
        try:
            link = os.readlink(entry)
        except FileNotFoundError:
            continue  # The checked process may close an fd during enumeration.
        if link.startswith("socket:["):
            socket_inodes.add(link.removeprefix("socket:[").removesuffix("]"))
    for line in Path("/proc/net/unix").read_text().splitlines()[1:]:
        fields = line.split(maxsplit=7)
        if len(fields) == 8 and fields[7] == path:
            return fields[6] in socket_inodes
    return False


def _start_private_xvfb(tmp_path: Path) -> tuple[subprocess.Popen[bytes], int, Path]:
    fbdir = tmp_path / "fb"
    fbdir.mkdir()
    for display_number in range(200, 240):
        x_socket = Path(f"/tmp/.X11-unix/X{display_number}")
        if x_socket.exists() or not _abstract_socket_is_available(display_number):
            continue
        xvfb = subprocess.Popen(
            ["Xvfb", f":{display_number}", "-fbdir", str(fbdir), "-screen", "0", "800x1040x24",
             "-nolisten", "tcp", "-nolisten", "local", "-ac"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        for _ in range(50):
            if xvfb.poll() is not None:
                break
            if x_socket.exists() and _listener_belongs_to(xvfb.pid, str(x_socket)):
                return xvfb, display_number, fbdir
            time.sleep(0.02)
        if xvfb.poll() is None:
            xvfb.terminate()
            xvfb.wait(timeout=5)
    raise AssertionError("could not start a private pathname-only Xvfb listener")


def test_xwd_validation_scaling_and_xvfb_xtest(tmp_path: Path) -> None:
    """The helper speaks the owned local Xvfb socket; no Xlib is linked by it."""
    xvfb, display_number, fbdir = _start_private_xvfb(tmp_path)
    try:
        display = f":{display_number}"
        x_socket = f"/tmp/.X11-unix/X{display_number}"
        xwd = fbdir / "Xvfb_screen0"
        for _ in range(50):
            if xwd.exists() and Path(x_socket).exists():
                break
            time.sleep(0.05)
        assert xwd.exists() and _listener_belongs_to(xvfb.pid, x_socket)
        assert _abstract_socket_is_available(display_number)
        source = tmp_path / "surface.c"
        source.write_text(r'''#include <X11/Xlib.h>
        #include <X11/Xutil.h>
        #include <time.h>
        #include <assert.h>
        #include <errno.h>
        #include <stdint.h>
        #include "appliance/native/browser_surface.h"
        int main(int argc, char **argv) {
          ForgeSurface s = FORGE_SURFACE_INIT; uint32_t pixels[16] = {0}; Display *d; XEvent e; int keys = 0, buttons = 0, lower = 0, upper = 0, at = 0;
          assert(argc == 4); assert(forge_surface_open(&s, argv[1], argv[2]) == 0);
          d = XOpenDisplay(argv[3]); assert(d); XSelectInput(d, DefaultRootWindow(d), KeyPressMask | ButtonPressMask); XSetWindowBackground(d, DefaultRootWindow(d), 0x336699); XClearWindow(d, DefaultRootWindow(d)); XSync(d, False);
          assert(s.width == 800 && s.height == 1040 && s.x_opcode != 0);
          assert(forge_surface_draw(&s, pixels, 4, 4, 4) == 0);
          for(int i=0;i<16;i++)assert(pixels[i]==0x336699);
          assert(forge_surface_click(&s, 7, 9) == 0);
          assert(forge_surface_scroll(&s, -1) == 0 && forge_surface_scroll(&s, 1) == 0);
          assert(forge_surface_key(&s, 'a') == 0 && forge_surface_key(&s, 'A') == 0 && forge_surface_key(&s, '@') == 0 && forge_surface_key(&s, 0xff0d) == 0);
          for(int attempt=0;attempt<100;attempt++) {
            XSync(d, False);
            while(XPending(d)){XNextEvent(d,&e);if(e.type==KeyPress){char text[16];KeySym key;int n=XLookupString(&e.xkey,text,sizeof text,&key,NULL);keys++;if(n==1){lower+=text[0]=='a';upper+=text[0]=='A';at+=text[0]=='@';}}if(e.type==ButtonPress)buttons++;}
            if(lower&&upper&&at&&buttons>=3)break;
            struct timespec delay={0,10000000};nanosleep(&delay,NULL);
          }
          assert(keys>=4 && lower==1 && upper==1 && at==1 && buttons>=3); XCloseDisplay(d);
          forge_surface_close(&s); errno = 0;
          assert(forge_surface_open(&s, "/no/such/file", argv[2]) < 0 && errno == ENOENT);
          return 0;
        }''')
        exe = tmp_path / "surface"
        _compile(source, exe, libraries=["-lX11"])
        # The display number may also name another server's abstract socket.
        # Select our pathname transport explicitly, just as the native helper does.
        subprocess.run([str(exe), str(xwd), x_socket, "unix" + display], check=True)
    finally:
        xvfb.terminate()
        xvfb.wait(timeout=5)


def test_malformed_xwd_and_armv7_static_compile(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xwd"
    bad.write_bytes(b"\0" * 100)
    source = tmp_path / "bad.c"
    source.write_text(r'''#include <assert.h>
        #include <errno.h>
        #include "appliance/native/browser_surface.h"
        int main(int argc, char **argv) { ForgeSurface s = FORGE_SURFACE_INIT; (void)argc; assert(forge_surface_open(&s, argv[1], "/tmp/no") < 0); assert(errno == EPROTO); return 0; }''')
    _compile(source, tmp_path / "bad")
    subprocess.run([str(tmp_path / "bad"), str(bad)], check=True)
    ndk = Path("/home/adamgoodwin/Android/Sdk/ndk/27.1.12297006/toolchains/llvm/prebuilt/linux-x86_64/bin/armv7a-linux-androideabi21-clang")
    subprocess.run([str(ndk), "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), "-c", str(source), "-o", str(tmp_path / "surface-arm.o")], check=True)


def test_surface_and_framebuffer_fast_paths_preserve_bytes(tmp_path: Path) -> None:
    source = tmp_path / "display.c"
    source.write_text(r'''#include <assert.h>
        #include <stdint.h>
        #include <string.h>
        #include "appliance/native/browser_surface.h"
        #define main forge_panel_entry
        #include "appliance/native/panel.c"
        #undef main
        static void exact_surface(int little) {
          unsigned char image[24] = {0}; uint32_t out[8];
          ForgeSurface s = FORGE_SURFACE_INIT;
          s.map=image; s.image=0; s.line=12; s.source_width=2; s.source_height=2; s.source_little=little;
          if (little) { forge_surface_put32(image,0x00112233); forge_surface_put32(image+4,0x00445566); forge_surface_put32(image+12,0x00778899); forge_surface_put32(image+16,0x00aabbcc); }
          else { image[0]=0;image[1]=0x11;image[2]=0x22;image[3]=0x33; image[4]=0;image[5]=0x44;image[6]=0x55;image[7]=0x66; image[12]=0;image[13]=0x77;image[14]=0x88;image[15]=0x99; image[16]=0;image[17]=0xaa;image[18]=0xbb;image[19]=0xcc; }
          memset(out,0xa5,sizeof out); assert(!forge_surface_draw(&s,out,4,2,2));
          assert(out[0]==0x112233 && out[1]==0x445566 && out[4]==0x778899 && out[5]==0xaabbcc); assert(out[2]==0xa5a5a5a5U && out[6]==0xa5a5a5a5U);
        }
        int main(void) {
          unsigned char scaled_image[8] = {0x33,0x22,0x11,0,0x66,0x55,0x44,0}; uint32_t scaled[4]; ForgeSurface s=FORGE_SURFACE_INIT;
          exact_surface(1); exact_surface(0);
          s.map=scaled_image;s.image=0;s.line=8;s.source_width=2;s.source_height=1;s.source_little=1; assert(!forge_surface_draw(&s,scaled,2,2,2)); assert(scaled[0]==0x112233&&scaled[1]==0x445566&&scaled[2]==0x112233&&scaled[3]==0x445566);
          unsigned char memory[(HEIGHT+3)*(WIDTH*4+16)]; Framebuffer fb; size_t first; memset(&fb,0,sizeof fb); memset(memory,0xa5,sizeof memory); fb.mem=memory; fb.fix.line_length=WIDTH*4+16; fb.var.bits_per_pixel=32; fb.var.xoffset=1; fb.var.yoffset=1; fb.var.red=(struct fb_bitfield){0,8,0};fb.var.green=(struct fb_bitfield){8,8,0};fb.var.blue=(struct fb_bitfield){16,8,0};fb.var.transp=(struct fb_bitfield){24,8,0}; pixels[0]=0x00112233; pixels[1]=0x00445566; assert(!fb_draw(&fb)); first=fb.fix.line_length+4; assert(memory[first]==0x11&&memory[first+1]==0x22&&memory[first+2]==0x33&&memory[first+3]==0xff); assert(memory[first+4]==0x44&&memory[first+5]==0x55&&memory[first+6]==0x66&&memory[first+7]==0xff); assert(memory[first-1]==0xa5&&memory[first+WIDTH*4]==0xa5);
          memset(memory,0xa5,sizeof memory); fb.fix.line_length=WIDTH*2+8; fb.var.bits_per_pixel=16; fb.var.xoffset=0;fb.var.yoffset=0;fb.var.red=(struct fb_bitfield){11,5,0};fb.var.green=(struct fb_bitfield){5,6,0};fb.var.blue=(struct fb_bitfield){0,5,0};fb.var.transp=(struct fb_bitfield){0,0,0}; pixels[0]=0x00112233; assert(!fb_draw(&fb)); assert(memory[0]==0x06&&memory[1]==0x11&&memory[WIDTH*2]==0xa5);
          home_page=1; quitting=0; return_to_android_pending=0; notice="";
          activate(400,1034); assert(!quitting && return_to_android_pending && !strcmp(notice,"TAP RETURN AGAIN TO EXIT"));
          activate(400,1034); assert(quitting);
          return 0;
        }''')
    exe = tmp_path / "display"
    _compile(source, exe)
    subprocess.run([str(exe)], check=True)


def test_browser_session_refuses_capture_in_every_page_state(tmp_path: Path) -> None:
    """No capture is allowed even when Browse is initially hidden by Music."""
    panel = tmp_path / "panel"
    _compile(ROOT / "appliance/native/panel.c", panel)
    output = tmp_path / "must-not-exist.ppm"
    common = [str(panel), "--socket", str(tmp_path / "control.sock"),
              "--music-service", "--web-surface", str(tmp_path / "browser.xwd"),
              "--x11-socket", str(tmp_path / "x11.sock")]
    for arguments in (["--snapshot", str(output)],
                      ["--fb", "/no/device", "--capture", str(output)]):
        result = subprocess.run(common + arguments, capture_output=True, text=True, timeout=2)
        assert result.returncode == 2
        assert "without capture" in result.stderr
        assert not output.exists()
