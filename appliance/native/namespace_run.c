/* Linux service supervisor for the tablet. Tests have a bounded deadline;
 * explicit appliance mode lives until its service exits or receives a signal.
 * Private mount/PID namespaces keep children out of Android's runtime. */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <limits.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping;
static void stop_signal(int n) {(void)n;stopping=1;}
static double now(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void tick(void) {struct timespec t={0,50000000};nanosleep(&t,NULL);}
static int close_fds(void) {
    DIR *fds=opendir("/proc/self/fd");
    if(!fds)return -1;
    int own=dirfd(fds),result=0;
    struct dirent *entry;
    for(;;) {
        errno=0;entry=readdir(fds);
        if(!entry){if(errno)result=-1;break;}
        char *end;long fd=strtol(entry->d_name,&end,10);
        if(*end||fd<3||fd==own||fd>INT_MAX)continue;
        if(close((int)fd)&&errno!=EBADF){result=-1;break;}
    }
    if(closedir(fds))result=-1;
    return result;
}
static int directory(const char *p,mode_t mode) {
    if(mkdir(p,mode)&&errno!=EEXIST)return -1;
    struct stat s;if(lstat(p,&s)||!S_ISDIR(s.st_mode)){errno=EINVAL;return -1;}
    /* The root broker uses umask 077. Restore the explicit namespace mode
     * before dropping UID, especially /dev/snd which the audio service needs. */
    return chmod(p,mode);
}
static int node(const char *p,unsigned major_n,unsigned minor_n,mode_t mode,int uid) {
    dev_t dev=makedev(major_n,minor_n);
    if(mknod(p,S_IFCHR|mode,dev)&&errno!=EEXIST)return -1;
    struct stat s;if(lstat(p,&s)||!S_ISCHR(s.st_mode)||s.st_rdev!=dev){errno=EINVAL;return -1;}
    return chown(p,uid,uid)||chmod(p,mode)?-1:0;
}
static int setup_root(const char *root,int audio) {
    if(chdir(root)||chroot(".")||chdir("/"))return -1;
    const char *dirs[]={"/proc","/sys","/dev","/dev/shm","/tmp","/run"};
    for(unsigned i=0;i<sizeof dirs/sizeof dirs[0];i++)if(directory(dirs[i],0755))return -1;
    if(mount("proc","/proc","proc",MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL))return -1;
    if(mount("tmpfs","/dev","tmpfs",MS_NOSUID,"mode=0755,size=1m"))return -1;
    if(directory("/dev/shm",01777)||mount("tmpfs","/dev/shm","tmpfs",MS_NOSUID|MS_NODEV,"mode=1777,size=64m"))return -1;
    if(mount("tmpfs","/tmp","tmpfs",MS_NOSUID|MS_NODEV,"mode=1777,size=128m"))return -1;
    /* Xtrans refuses to create its socket directory after the UID drop. */
    if(directory("/tmp/.X11-unix",01777)||chmod("/tmp/.X11-unix",01777))return -1;
    if(mount("tmpfs","/run","tmpfs",MS_NOSUID|MS_NODEV,"mode=0755,size=4m"))return -1;
    if(node("/dev/null",1,3,0666,0)||node("/dev/zero",1,5,0666,0)||
       node("/dev/random",1,8,0666,0)||node("/dev/urandom",1,9,0666,0))return -1;
    if(symlink("/proc/self/fd","/dev/fd")||symlink("/proc/self/fd/0","/dev/stdin")||
       symlink("/proc/self/fd/1","/dev/stdout")||symlink("/proc/self/fd/2","/dev/stderr"))return -1;
    if(audio&&(directory("/dev/snd",0755)||node("/dev/snd/controlC0",116,0,0600,65000)||
       node("/dev/snd/pcmC0D0p",116,16,0600,65000)))return -1;
    return 0;
}
static int run_namespace(const char *root,int audio,char **command) {
    if(getpid()!=1){fprintf(stderr,"private PID namespace missing\n");return 1;}
    if(setup_root(root,audio)){perror("private root setup");return 1;}
    pid_t child=fork();
    if(child<0){perror("fork service");return 1;}
    if(!child) {
        if(close_fds()){perror("close inherited service descriptors");_exit(126);}
        gid_t groups[]={3003}; /* Android's vendor kernel internet group. */
        if(setgroups(1,groups)||setgid(65000)||setuid(65000)||prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0)) {
            perror("drop service privileges");_exit(126);
        }
        struct rlimit core={0,0},children={128,128};
        if(setrlimit(RLIMIT_CORE,&core)||setrlimit(RLIMIT_NPROC,&children)||clearenv()) {
            perror("service environment and limits");_exit(126);
        }
        setenv("HOME","/tmp/forge-browser",1);setenv("PATH","/usr/bin:/bin",1);
        setenv("LANG","C.UTF-8",1);setenv("TMPDIR","/tmp",1);
        execvp(command[0],command);perror("exec service");_exit(127);
    }
    int status=0,result=1;
    while(!stopping) {
        pid_t got=waitpid(-1,&status,WNOHANG);
        if(got==child){result=WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);break;}
        if(got<0&&errno==ECHILD)break;
        tick();
    }
    /* Only processes in this newly created PID namespace are visible here. */
    kill(-1,SIGTERM);
    double deadline=now()+1;
    while(now()<deadline) {
        if(waitpid(-1,NULL,WNOHANG)<0&&errno==ECHILD)break;
        tick();
    }
    kill(-1,SIGKILL);
    return stopping?124:result;
}
int main(int argc,char **argv) {
    const char *root=NULL;unsigned long seconds=0;int audio=0,index=0,appliance=0,timed=0;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--root")&&i+1<argc)root=argv[++i];
        else if(!strcmp(argv[i],"--seconds")&&i+1<argc) {
            timed=1;
            char *end;errno=0;seconds=strtoul(argv[++i],&end,10);
            if(errno||*end)seconds=0;
        } else if(!strcmp(argv[i],"--appliance")) {
            appliance=1;
        } else if(!strcmp(argv[i],"--audio"))audio=1;
        else if(!strcmp(argv[i],"--")&&i+1<argc){index=i+1;break;}
        else {fprintf(stderr,"Usage: %s --root PATH (--seconds 1..1800 | --appliance) [--audio] -- COMMAND [ARGS]\n",argv[0]);return 64;}
    }
    if(!root||root[0]!='/'||!index||(appliance?timed:(!seconds||seconds>1800)))return 64;
    if(geteuid()!=0){fprintf(stderr,"root is required to create private namespaces\n");return 77;}
    char resolved[PATH_MAX];struct stat s;
    if(!realpath(root,resolved)||stat(resolved,&s)||!S_ISDIR(s.st_mode)||s.st_uid!=0||
       (s.st_mode&0022)||!strcmp(resolved,"/")) {fprintf(stderr,"rootfs must be a private root-owned directory\n");return 77;}
    struct sigaction sa;memset(&sa,0,sizeof sa);sa.sa_handler=stop_signal;sigemptyset(&sa.sa_mask);
    sigaction(SIGINT,&sa,NULL);sigaction(SIGTERM,&sa,NULL);sigaction(SIGHUP,&sa,NULL);
    pid_t owner=getppid();
    if(owner==1||prctl(PR_SET_PDEATHSIG,SIGTERM)||getppid()!=owner)return 1;
    if(unshare(CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWIPC|CLONE_NEWUTS)||
       mount(NULL,"/",NULL,MS_REC|MS_PRIVATE,NULL)) {perror("private namespace setup");return 1;}
    int owner_pipe[2];
    if(pipe2(owner_pipe,O_CLOEXEC|O_NONBLOCK))return 1;
    pid_t init=fork();if(init<0){perror("fork namespace init");return 1;}
    if(!init) {
        close(owner_pipe[1]);
        if(prctl(PR_SET_PDEATHSIG,SIGKILL))return 1;
        struct pollfd owner_poll={owner_pipe[0],POLLIN,0};
        if(poll(&owner_poll,1,0)>0&&(owner_poll.revents&POLLHUP))return 1;
        close(owner_pipe[0]);
        return run_namespace(resolved,audio,&argv[index]);
    }
    close(owner_pipe[0]);
    double deadline=now()+seconds;int status;
    while(!stopping&&(appliance||now()<deadline)) {
        if(waitpid(init,&status,WNOHANG)==init)
            return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
        tick();
    }
    kill(init,SIGTERM);deadline=now()+2;
    while(now()<deadline){if(waitpid(init,&status,WNOHANG)==init)return 124;tick();}
    kill(init,SIGKILL);while(waitpid(init,&status,0)<0&&errno==EINTR){}
    return 124;
}
