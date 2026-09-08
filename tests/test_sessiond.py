"""Conformance checks for the fixed-function Forge session broker.

The harness includes the production C file with narrowly scoped syscall fakes.
It drives ``client`` through a real UNIX socketpair, so framing and peer
credential decisions are exercised without a daemon, root actions, or exec.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "appliance" / "native" / "sessiond.c"


HARNESS = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <unistd.h>
static uid_t fake_uid;
static const char *fake_packages;
static int fake_getsockopt(int fd, int level, int option, void *value, socklen_t *length) {
  (void)fd; (void)level; (void)option;
  if (*length != sizeof(struct ucred)) return -1;
  *(struct ucred *)value = (struct ucred){.pid = 1, .uid = fake_uid, .gid = fake_uid};
  return 0;
}
static FILE *fake_fopen(const char *path, const char *mode) {
  (void)mode;
  if (strcmp(path, "/data/system/packages.list")) return NULL;
  FILE *f = tmpfile(); assert(f);
  fputs(fake_packages ? fake_packages : "", f); rewind(f); return f;
}
static ssize_t fake_recv(int fd, void *buffer, size_t count, int flags) {
  return syscall(SYS_recvfrom, fd, buffer, count, flags, NULL, NULL);
}
#define getsockopt fake_getsockopt
#define fopen fake_fopen
#define recv fake_recv
#define main sessiond_program_main
#define static
#include "SESSIOND_SOURCE"
#undef static
#undef main
#undef fopen
#undef getsockopt
#undef recv
static void exchange_bytes(const char *request, size_t length, const char *expected) {
  int pair[2]; assert(socketpair(AF_UNIX, SOCK_STREAM, 0, pair) == 0);
  assert(write(pair[1], request, length) == (ssize_t)length);
  shutdown(pair[1], SHUT_WR); client(pair[0]);
  char reply[128] = {0}; ssize_t n = read(pair[1], reply, sizeof(reply) - 1);
  assert(n > 0); assert(!strcmp(reply, expected)); close(pair[0]); close(pair[1]);
}
static void exchange(const char *request, const char *expected) { exchange_bytes(request,strlen(request),expected); }
int main(void) {
  fake_uid = 0; state = "IDLE"; last_exit = 0; child = 0;
  exchange("STATUS\n", "OK IDLE 0\n");
  fake_uid = 20000; exchange("STATUS\n", "ERR FORBIDDEN\n");
  fake_uid = 10001; fake_packages = "org.forge.appliance 10001 deb\n";
  exchange("STATUS\n", "OK IDLE 0\n");
  fake_packages = "org.forge.appliance 10001 deb\nsibling.app 10001 deb\n";
  exchange("STATUS\n", "ERR FORBIDDEN\n");
  fake_uid = 0;
  exchange("STATUS", "ERR BAD_FRAME\n");
  exchange_bytes("STATUS\0\n", 8, "ERR BAD_FRAME\n");
  exchange("STATUS\r\n", "ERR BAD_FRAME\n");
  exchange("STATUS\nSTART\n", "ERR BAD_FRAME\n");
  char huge[600]; memset(huge, 'A', sizeof(huge)); huge[sizeof(huge)-2] = '\n'; huge[sizeof(huge)-1] = 0;
  exchange(huge, "ERR BAD_FRAME\n");
  exchange("sh -c id\n", "ERR BAD_REQUEST\n");
  exchange("UNKNOWN\n", "ERR BAD_REQUEST\n");
  const char *states[] = {"IDLE", "STARTING", "RUNNING", "STOPPING", "RECOVERING", "FAILED"};
  for (size_t i = 0; i < sizeof(states) / sizeof(states[0]); i++) {
    char out[128] = {0}, expected[128] = {0};
    state = states[i]; child = 42; recovery_child = true;
    handle("START", out, sizeof(out)); assert(!strcmp(out, "ERR BUSY\n"));
    handle("HOME https://forge.local", out, sizeof(out)); assert(!strcmp(out, "ERR BUSY\n"));
    handle("STOP", out, sizeof(out));
    snprintf(expected, sizeof(expected), "OK %s 0\n", states[i]); assert(!strcmp(out, expected));
  }
  state = "IDLE"; child = 0; char out[128] = {0};
  handle("HOME javascript:alert(1)", out, sizeof(out)); assert(!strcmp(out, "ERR BAD_URL\n"));
  return 0;
}
'''


def test_sessiond_socket_framing_and_mocked_peer_authorization(tmp_path: Path) -> None:
    """Exercise production parsing with fake SO_PEERCRED and packages.list."""
    harness = tmp_path / "sessiond_harness.c"
    harness.write_text(HARNESS.replace("SESSIOND_SOURCE", str(SOURCE)))
    binary = tmp_path / "sessiond_harness"
    result = subprocess.run(
        ["cc", "-D_POSIX_C_SOURCE=200809L", "-std=c11", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(binary)],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=5)
    assert run.returncode == 0, run.stderr


LAUNCH_HARNESS = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
static int fail_sync,fail_fork,fail_pipe,forks,gates,kills,wait_ready,wait_code;
static pid_t killed;
static int kill_signal;
static uid_t written_uid;
static gid_t written_gid;
static const pid_t pretend_child=424242;
static char state_path[4096];
static int test_chown(int fd,uid_t uid,gid_t gid) {(void)fd;written_uid=uid;written_gid=gid;return 0;}
static int test_sync(int fd) {if(fail_sync){errno=ENOSPC;return -1;}return fsync(fd);}
static int test_stat(const char *p,struct stat *s) {int r=lstat(p,s);if(!r)s->st_uid=0;return r;}
static pid_t test_fork(void) {forks++;if(fail_fork){errno=EAGAIN;return -1;}return pretend_child;}
static int test_pipe(int p[2],int flags) {if(fail_pipe){errno=EMFILE;return -1;}return pipe2(p,flags);}
static int test_kill(pid_t p,int sig) {kills++;killed=p;kill_signal=sig;return 0;}
static pid_t test_wait(pid_t p,int *status,int flags) {
  assert(p==pretend_child);(void)flags;
  if(!wait_ready)return 0;
  if(status)*status=wait_code<<8;
  wait_ready=0;return p;
}
static FILE *test_open(const char *p,const char *mode) {
  if(!strcmp(p,"/proc/424242/stat")) {
    FILE *f=tmpfile();assert(f);fputs("424242 (sh) S",f);
    for(int i=4;i<22;i++)fputs(" 0",f);
    fputs(" 999\n",f);rewind(f);return f;
  }
  return fopen(p,mode);
}
static ssize_t test_write(int fd,const void *b,size_t n) {
  if(n==1 && *(const char *)b=='G') {
    char line[160];FILE *f=fopen(state_path,"r");assert(f&&fgets(line,sizeof line,f));fclose(f);
    assert(strstr(line,"424242 999\n")); /* identity durable before child is released */
    gates++;return 1;
  }
  return write(fd,b,n);
}
#define fchown test_chown
#define fsync test_sync
#define lstat test_stat
#define fork test_fork
#define pipe2 test_pipe
#define kill test_kill
#define waitpid test_wait
#define fopen test_open
#define write test_write
#define main sessiond_program_main
#include "SESSIOND_SOURCE"
#undef main
#undef fchown
#undef fsync
#undef lstat
#undef fork
#undef pipe2
#undef kill
#undef waitpid
#undef fopen
#undef write
static void command(const char *s,const char *expected) {char out[128];handle(s,out,sizeof out);if(strcmp(out,expected))fprintf(stderr,"request=%s expected=%s actual=%s\n",s,expected,out);assert(!strcmp(out,expected));}
static void stub(const char *tail) {char p[4096];assert(!path_join(p,sizeof p,tail));FILE *f=fopen(p,"w");assert(f);fputs("Never executed by this harness\n",f);fclose(f);assert(!chmod(p,0600));}
int main(int argc,char **argv) {
  assert(argc==2);assert(strlen(argv[1])<sizeof install);strcpy(install,argv[1]);
  assert(!path_join(journal,sizeof journal,"journal"));strcpy(state_path,journal);
  stub("forge-session.sh");stub("forge-recover.sh");
  char p[4096];const char *dirs[]={"linux-root","linux-root/etc","linux-root/etc/forge"};
  for(unsigned i=0;i<3;i++){assert(!path_join(p,sizeof p,dirs[i]));assert(!mkdir(p,0750));}
  state="IDLE";child=0;last_exit=0;
  command("START","OK STARTING 0\n");assert(forks==1&&gates==1&&child==pretend_child&&!recovery_child);
  command("START","ERR BUSY\n");assert(forks==1);
  command("STOP","OK STOPPING 0\n");assert(kills==1&&killed==pretend_child&&kill_signal==SIGTERM);
  command("STOP","OK STOPPING 0\n");assert(kills==1);
  wait_ready=1;wait_code=143;reap();assert(recovery_child&&forks==2&&gates==2&&!strcmp(state,"RECOVERING"));
  wait_ready=1;wait_code=0;reap();assert(!child&&!strcmp(state,"IDLE")&&last_exit==143&&forks==2);
  command("HOME http://192.0.2.1:8123","OK SAVED\n");assert(written_uid==0&&written_gid==65000);
  assert(!path_join(p,sizeof p,"linux-root/etc/forge/home.url"));
  struct stat st;assert(!stat(p,&st)&&(st.st_mode&0777)==0640);
  command("HOME https://user:pass@host/","ERR BAD_URL\n");
  command("HOME javascript:alert(1)","ERR BAD_URL\n");
  fail_sync=1;command("START","ERR START_FAILED\n");assert(!child&&forks==2&&gates==2&&!strcmp(state,"FAILED"));
  command("START","ERR BUSY\n");assert(forks==2);
  command("STOP","OK FAILED 77\n");assert(!child&&forks==2);
  fail_sync=0;state="IDLE";fail_fork=1;command("START","ERR START_FAILED\n");assert(forks==3&&gates==2&&!child&&!strcmp(state,"FAILED"));
  fail_fork=0;state="IDLE";fail_pipe=1;command("START","ERR START_FAILED\n");assert(forks==3&&gates==2&&!child);fail_pipe=0;
  state="RUNNING";child=pretend_child;recovery_child=false;fail_sync=1;
  command("STOP","ERR STATE_IO\n");assert(kills==1&&child==pretend_child&&!strcmp(state,"FAILED"));
  fail_sync=0;state="RECOVERING";recovery_child=true;wait_ready=1;wait_code=70;reap();
  assert(!child&&!strcmp(state,"FAILED")&&last_exit==70&&forks==3);
  const char *states[]={"STARTING","RUNNING","STOPPING","RECOVERING","FAILED"};
  for(unsigned i=0;i<5;i++){state=states[i];command("START","ERR BUSY\n");command("HOME https://example.test/","ERR BUSY\n");}
  return 0;
}
'''


def test_journal_gates_launch_and_failures_never_replay(tmp_path: Path) -> None:
    harness = tmp_path / "launch_harness.c"
    harness.write_text(LAUNCH_HARNESS.replace("SESSIOND_SOURCE", str(SOURCE)))
    binary = tmp_path / "launch_harness"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(harness), "-o", str(binary)], check=True, timeout=30)
    install = tmp_path / "install"
    install.mkdir()
    subprocess.run([str(binary), str(install)], check=True, timeout=5)
