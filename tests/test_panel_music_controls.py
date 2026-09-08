"""Focused panel checks for the asynchronous native music-control path."""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_music_selection_is_obvious_and_command_confirmation_never_blocks(tmp_path: Path) -> None:
    source = tmp_path / "panel-music.c"
    source.write_text(
        f'''\
#include <assert.h>
#include <string.h>
#include <sys/socket.h>
#define main forge_panel_entry
#include "{ROOT / 'appliance' / 'native' / 'panel.c'}"
#undef main
int main(int argc, char **argv) {{
  char failed[]="FAILED 9 0 35 0 0 0 0\\tTrack\\tArtist\\tTHIS TABLET\\tSTREAM_LIMIT\\n";
  char legacy[]="OK 10 0 35 0 0 0 0\\tOld Track\\tOld Artist\\tTHIS TABLET\\n";
  (void)argc; socket_path=argv[1]; music_service=1; connected=1; revision=7;
  assert(apply_reply(failed)==2 && connected && revision==9 && !strcmp(player_status,"STREAM_LIMIT"));
  assert(!strcmp(status_notice(),"STREAM LIMIT - STOP OTHER DEVICE"));
  assert(apply_reply(legacy)==0 && !strcmp(player_status,"READY"));
  web_surface_path="surface"; web_socket_path="socket"; browse_page=home_page=pending_browser_tab=0;
  activate(200,660); assert(browse_page && pending_browser_tab==1);
  browse_page=0; pending_browser_tab=0;
  int64_t start=milliseconds(); mutate("PLAY");
  assert(milliseconds()-start<50 && control.fd>=0 && !strcmp(notice,"CONFIRMING COMMAND"));
  close(control.fd); control.fd=-1;
  int pair[2]; assert(!socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,pair));
  control.fd=pair[0]; strcpy(control.command,"DO 10 PLAY\\n"); control.sent=strlen(control.command); control.received=0;
  const char *ok="OK 11 1 35 0 0 0 0\\tNext\\tArtist\\tTHIS TABLET\\tREADY\\n";
  assert(send(pair[1],ok,strlen(ok),MSG_NOSIGNAL)>0);
  close(pair[1]); control_poll();
  assert(control.fd<0 && revision==11 && playing==1 && !strcmp(notice,""));
  assert(!socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,pair));
  control.fd=pair[0]; strcpy(control.command,"DO 11 NEXT\\n"); control.sent=strlen(control.command); control.received=0;
  const char *failed_reply="FAILED 12 1 35 0 0 0 0\\tNext\\tArtist\\tTHIS TABLET\\tSTREAM_LIMIT\\n";
  assert(send(pair[1],failed_reply,strlen(failed_reply),MSG_NOSIGNAL)>0);
  close(pair[1]); control_poll();
  assert(control.fd<0 && revision==12 && !strcmp(player_status,"STREAM_LIMIT") && !strcmp(notice,"STREAM LIMIT - STOP OTHER DEVICE"));
  assert(!socketpair(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK,0,pair));
  control.fd=pair[0]; strcpy(control.command,"DO 12 PAUSE\\n"); control.sent=strlen(control.command); control.received=0; control.deadline=milliseconds()-1;
  start=milliseconds(); control_poll();
  assert(milliseconds()-start<50 && control.fd<0 && !strcmp(notice,"COMMAND CONFIRMATION UNAVAILABLE"));
  close(pair[1]);
  return 0;
}}'''
    )
    binary = tmp_path / "panel-music"
    compiled = subprocess.run(
        ["cc", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT), str(source), "-o", str(binary)],
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert compiled.returncode == 0, compiled.stderr
    path = tmp_path / "bridge.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        listener.listen(1)
        run = subprocess.run([str(binary), str(path)], text=True, capture_output=True, timeout=2)
    assert run.returncode == 0, run.stderr
