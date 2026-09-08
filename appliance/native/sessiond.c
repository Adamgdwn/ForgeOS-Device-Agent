/* Fixed-function, local launcher broker. No network listener or command input.
 * Android's package manager supplies the app UID; root may diagnose locally. */
#define _GNU_SOURCE
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

enum { FRAME = 512 };
static const char PACKAGE[] = "org.forge.appliance";
static const char SOCKET_NAME[] = "forge.appliance.v1";
static volatile sig_atomic_t stopping;
static char install[PATH_MAX], journal[PATH_MAX];
static const char *state = "IDLE";
static int last_exit;
static pid_t child;
static bool recovery_child;
static long long child_started;
static unsigned long long child_ticks;
static long long now_ms(void) {
  struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
  return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static void stop_signal(int s) { (void)s; stopping = 1; }
static int path_join(char *out, size_t cap, const char *tail) {
  int n = snprintf(out, cap, "%s/%s", install, tail);
  return n > 0 && (size_t)n < cap ? 0 : -1;
}
static int trusted(const char *path, bool directory) {
  struct stat s;
  return lstat(path, &s) || s.st_uid != 0 || (s.st_mode & 0022) ||
    (directory ? !S_ISDIR(s.st_mode) : !S_ISREG(s.st_mode)) ? -1 : 0;
}
static unsigned long long start_ticks(pid_t pid) {
  char path[64], data[1024];
  snprintf(path, sizeof path, "/proc/%ld/stat", (long)pid);
  FILE *f = fopen(path, "re"); if (!f) return 0;
  char *got = fgets(data, sizeof data, f); fclose(f); if (!got) return 0;
  char *p = strrchr(data, ')'); if (!p || p[1] != ' ') return 0;
  p += 2;
  /* p begins with field 3 (state); starttime is field 22. */
  for (int field = 3; field < 22; field++) {
    p = strchr(p, ' '); if (!p) return 0; p++;
  }
  return strtoull(p, NULL, 10);
}
static int atomic_write(const char *path, const char *data, bool dashboard) {
  char next[PATH_MAX];
  if (snprintf(next, sizeof next, "%s.next", path) >= (int)sizeof next) return -1;
  int fd = open(next, O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW, 0600);
  if (fd < 0) return -1;
  size_t n = strlen(data);
  int bad = 0;
  if(write(fd,data,n)!=(ssize_t)n){perror("state write");bad=1;}
  else if(fchown(fd,0,dashboard?65000:0)){perror("state owner");bad=1;}
  else if(fchmod(fd,dashboard?0640:0600)){perror("state mode");bad=1;}
  else if(fsync(fd)){perror("state sync");bad=1;}
  if (close(fd)) bad = 1;
  /* Modern Bionic implements rename via renameat2, absent on this vendor
   * kernel. renameat provides the same atomic replacement with no flags. */
  if(!bad) {
#if defined(__ANDROID__) && defined(SYS_renameat)
    int renamed=(int)syscall(SYS_renameat,AT_FDCWD,next,AT_FDCWD,path);
#else
    int renamed=rename(next,path);
#endif
    if(renamed){perror("state rename");bad=1;}
  }
  if (bad) unlink(next);
  else {
    char parent[PATH_MAX]; snprintf(parent, sizeof parent, "%s", path);
    char *slash = strrchr(parent, '/'); if (!slash) return -1; *slash = 0;
    fd = open(parent, O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if (fd < 0) return -1;
    bad = fsync(fd); close(fd);
  }
  return bad ? -1 : 0;
}
static int save_state(const char *next) {
  char line[160];
  snprintf(line, sizeof line, "%s %d %ld %llu\n", next, last_exit, (long)child, child_ticks);
  if (atomic_write(journal, line, 0)) { state="FAILED"; return -1; }
  state = next; return 0;
}
/* Reject shared UIDs: package names alone must not authorize sibling apps. */
static bool package_uid(FILE *f, uid_t uid) {
  char line[4096], package[256], extra; unsigned candidate;
  unsigned matches = 0; bool own = false, malformed = false;
  while (fgets(line, sizeof line, f)) {
    if (!strchr(line, '\n')) { malformed = true; break; }
    if (sscanf(line, "%255s %u%c", package, &candidate, &extra) != 3 || extra != ' ') {
      malformed = true; break;
    }
    if (candidate == uid) { matches++; own = !strcmp(package, PACKAGE); }
  }
  return !malformed && !ferror(f) && uid >= 10000 && uid < 20000 && matches == 1 && own;
}
static bool authorized(int fd) {
  struct ucred peer; socklen_t n = sizeof peer;
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &peer, &n) || n != sizeof peer) return false;
  if (peer.uid == 0) return true;
  FILE *f = fopen("/data/system/packages.list", "re"); if (!f) return false;
  bool allowed = package_uid(f, peer.uid); fclose(f); return allowed;
}
static bool home_url(const char *s) {
  size_t n = strlen(s);
  if (!strcmp(s, "-")) return true;
  if (n > 256) return false;
  const char *host = !strncmp(s, "https://", 8) ? s+8 : !strncmp(s, "http://", 7) ? s+7 : NULL;
  if (!host || !*host || *host == '/' || *host == ':' || *host == '.') return false;
  const char *end = strchr(host, '/'); if (!end) end = s+n;
  if (end == host) return false;
  for (const char *p = s; *p; p++)
    if ((unsigned char)*p < 33 || (unsigned char)*p > 126 || strchr("@?#\\\"'`", *p)) return false;
  for (const char *p = host; p < end; p++)
    if (!isalnum((unsigned char)*p) && !strchr(".-:[]", *p)) return false;
  return true;
}
static void reply_status(char *out, size_t n) {
  snprintf(out, n, "OK %s %d\n", state, last_exit);
}
static int launch(bool recover) {
  char script[PATH_MAX], log[PATH_MAX]; int gate[2];
  if (path_join(script, sizeof script, recover ? "forge-recover.sh" : "forge-session.sh") ||
      path_join(log, sizeof log, recover ? "recovery-last.log" : "session-last.log") || trusted(script, false)) return -1;
  if (save_state(recover ? "RECOVERING" : "STARTING") || pipe2(gate, O_CLOEXEC)) return -1;
  pid_t p = fork();
  if (p < 0) { close(gate[0]); close(gate[1]); return -1; }
  if (!p) {
    close(gate[1]); pid_t parent = getppid();
    if (setsid() < 0 || prctl(PR_SET_PDEATHSIG, SIGTERM) || getppid() != parent || parent == 1) _exit(126);
    char go = 0; if (read(gate[0], &go, 1) != 1 || go != 'G') _exit(126); close(gate[0]);
    int fd = open(log, O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW, 0600);
    int in = open("/dev/null", O_RDONLY);
    if (fd < 0 || in < 0 || dup2(in, 0) < 0 || dup2(fd, 1) < 0 || dup2(fd, 2) < 0) _exit(126);
    if (fd > 2) close(fd);
    if (in > 2) close(in);
    clearenv(); setenv("PATH", "/system/bin:/system/xbin:/vendor/bin", 1);
    if (recover) execl("/system/bin/sh", "sh", script, install, (char *)NULL);
    else execl("/system/bin/sh", "sh", script, install, "appliance", (char *)NULL);
    _exit(127);
  }
  close(gate[0]); child = p; child_ticks = start_ticks(p); child_started = now_ms(); recovery_child = recover;
  if (!child_ticks || save_state(state) || write(gate[1], "G", 1) != 1) {
    close(gate[1]); kill(p, SIGTERM); waitpid(p, NULL, 0); child = 0; return -1;
  }
  close(gate[1]); return 0;
}
static void handle(const char *request, char *out, size_t n) {
  if (!strcmp(request, "STATUS")) { reply_status(out, n); return; }
  if (!strcmp(request, "START")) {
    if (strcmp(state, "IDLE") || child) { snprintf(out,n,"ERR BUSY\n"); return; }
    if (launch(false)) { last_exit=77; save_state("FAILED"); snprintf(out,n,"ERR START_FAILED\n"); }
    else reply_status(out,n);
    return;
  }
  if (!strcmp(request, "STOP")) {
    if (child) {
      if (!recovery_child && strcmp(state,"STOPPING")) {
        if (save_state("STOPPING")) { snprintf(out,n,"ERR STATE_IO\n"); return; }
        child_started=now_ms(); kill(child,SIGTERM);
      }
    } else if (strcmp(state,"IDLE") && launch(true)) { save_state("FAILED"); }
    reply_status(out,n); return;
  }
  if (!strncmp(request,"HOME ",5)) {
    if (child || strcmp(state,"IDLE")) { snprintf(out,n,"ERR BUSY\n"); return; }
    if (!home_url(request+5)) { snprintf(out,n,"ERR BAD_URL\n"); return; }
    char path[PATH_MAX], value[260];
    char directory[PATH_MAX];
    if (path_join(directory,sizeof directory,"linux-root/etc/forge") || trusted(directory,true) ||
        path_join(path,sizeof path,"linux-root/etc/forge/home.url")) { snprintf(out,n,"ERR STATE_IO\n"); return; }
    snprintf(value,sizeof value,"%s\n",strcmp(request+5,"-") ? request+5 : "");
    snprintf(out,n,atomic_write(path,value,true) ? "ERR STATE_IO\n" : "OK SAVED\n");
    return;
  }
  snprintf(out,n,"ERR BAD_REQUEST\n");
}
static void client(int fd) {
  char in[FRAME], out[128]; size_t got=0; long long deadline=now_ms()+250;
  if (!authorized(fd)) { send(fd,"ERR FORBIDDEN\n",14,MSG_NOSIGNAL); return; }
  while (got<sizeof in-1 && now_ms()<deadline) {
    struct pollfd p={fd,POLLIN,0};
    if (poll(&p,1,(int)(deadline-now_ms()))<=0) break;
    ssize_t n=recv(fd,in+got,sizeof in-1-got,0); if(n<=0)break; got+=(size_t)n;
    if(memchr(in,'\n',got))break;
  }
  bool valid=got>0 && in[got-1]=='\n';
  for(size_t i=0;i+1<got;i++) if((unsigned char)in[i]<32||(unsigned char)in[i]>126)valid=false;
  if (!valid) { send(fd,"ERR BAD_FRAME\n",14,MSG_NOSIGNAL); return; }
  in[got-1]=0; handle(in,out,sizeof out); send(fd,out,strlen(out),MSG_NOSIGNAL);
}
static void reap(void) {
  if (!child) return;
  int status; pid_t got=waitpid(child,&status,WNOHANG);
  if (got!=child) return;
  int code=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
  bool recovered=recovery_child; child=0; child_ticks=0;
  if (recovered) { if(code)last_exit=code; save_state(code==0 ? "IDLE" : "FAILED"); return; }
  last_exit=code;
  /* Even a graceful session must prove restoration before IDLE. */
  if (launch(true)) save_state("FAILED");
}
int main(int argc,char **argv) {
  umask(0077);
  if(argc!=2 || geteuid()!=0 || !realpath(argv[1],install) || !strcmp(install,"/") ||
     trusted(install,true) || path_join(journal,sizeof journal,".sessiond-state"))return 64;
  char path[PATH_MAX];
  const char *required[]={"forge-session.sh","forge-recover.sh","forge-panel","forge-namespace-run","forge-cdp-guard.sh"};
  for(size_t i=0;i<sizeof required/sizeof required[0];i++)
    if(path_join(path,sizeof path,required[i])||trusted(path,false))return 77;
  signal(SIGTERM,stop_signal);signal(SIGINT,stop_signal);signal(SIGHUP,stop_signal);signal(SIGPIPE,SIG_IGN);
  int listener=socket(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC|SOCK_NONBLOCK,0); if(listener<0){perror("launcher socket");return 1;}
  struct sockaddr_un a={.sun_family=AF_UNIX};memcpy(a.sun_path+1,SOCKET_NAME,sizeof SOCKET_NAME-1);
  if(bind(listener,(struct sockaddr *)&a,(socklen_t)(offsetof(struct sockaddr_un,sun_path)+sizeof SOCKET_NAME))||listen(listener,4)){perror("launcher bind/listen");close(listener);return 1;}
  /* Discard only our root-owned unfinished atomic-write staging file. */
  if(snprintf(path,sizeof path,"%s.next",journal)<(int)sizeof path && !trusted(path,false))unlink(path);
  char previous[32]="",line[160];
  FILE *f=fopen(journal,"re");
  if(f){if(fgets(line,sizeof line,f))sscanf(line,"%31s",previous);fclose(f);}
  path_join(path,sizeof path,".forge-session.lock");
  if(access(path,F_OK)==0 || (*previous && strcmp(previous,"IDLE"))) {
    if(launch(true))save_state("FAILED");
  } else if(save_state("IDLE")) {perror("launcher state journal");close(listener);return 1;}
  while(!stopping) {
    reap();
    if(child && !recovery_child && !strcmp(state,"STARTING")) {
      path_join(path,sizeof path,".forge-session.lock/ready");
      if(!trusted(path,false))save_state("RUNNING");
    }
    if(child && now_ms()-child_started > (recovery_child ? 180000 : !strcmp(state,"STOPPING") ? 180000 : !strcmp(state,"STARTING") ? 90000 : LLONG_MAX)) {
      kill(child,SIGKILL); /* Parent-death guards terminate its owned children. */
    }
    struct pollfd p={listener,POLLIN,0};
    if(poll(&p,1,100)>0 && (p.revents&POLLIN)) {
      int fd=accept4(listener,NULL,NULL,SOCK_CLOEXEC|SOCK_NONBLOCK);
      if(fd>=0){client(fd);close(fd);}
    }
  }
  close(listener);
  if(child){kill(child,SIGTERM);long long deadline=now_ms()+180000;while(child && now_ms()<deadline){reap();struct timespec t={0,100000000};nanosleep(&t,NULL);}}
  return child ? 1 : 0;
}
