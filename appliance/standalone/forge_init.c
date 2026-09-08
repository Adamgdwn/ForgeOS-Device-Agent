/* Forge first-stage Linux init. No Android init, property service or framework.
 * Optional bounded probes return to recovery; appliance mode supervises services.
 * /sbin/forge-admin is a physically trusted USB diagnostic helper.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/reboot.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef FORGE_PROBE_SECONDS
#define FORGE_PROBE_SECONDS 900
#endif
#ifndef FORGE_USB_SERIAL
/* Public builds use a generic USB identity; deployments may override it. */
#define FORGE_USB_SERIAL "forge-gteslte"
#endif
enum { PROBE_SECONDS = FORGE_PROBE_SECONDS };
static int logfd=-1;
static volatile sig_atomic_t recovery_requested;
static void request_recovery(int sig) { (void)sig; recovery_requested=1; }
static void report(const char *s) {
    if(logfd>=0)dprintf(logfd,"%s\n",s);
    dprintf(STDERR_FILENO,"%s\n",s);
}
static void directory(const char *s,mode_t mode) {
    if(mkdir(s,mode)&&errno!=EEXIST)report(s);
}
static int put(const char *path,const char *value) {
    int fd=open(path,O_WRONLY|O_CLOEXEC);if(fd<0)return -1;
    ssize_t n=write(fd,value,strlen(value));close(fd);
    return n==(ssize_t)strlen(value)?0:-1;
}
static pid_t spawn(char *const argv[]) {
    pid_t p=fork();
    if(!p){
        if(logfd>=0){(void)dup2(logfd,STDOUT_FILENO);(void)dup2(logfd,STDERR_FILENO);}
        execv(argv[0],argv);_exit(127);
    }
    return p;
}
static int run(char *const argv[]) {
    pid_t p=spawn(argv);int status=0;if(p<0)return -1;
    while(waitpid(p,&status,0)<0)if(errno!=EINTR)return -1;
    return WIFEXITED(status)?WEXITSTATUS(status):128;
}
static void recover(void) {
    report("FORGE: return to recovery");sync();
    syscall(__NR_reboot,LINUX_REBOOT_MAGIC1,LINUX_REBOOT_MAGIC2,
            LINUX_REBOOT_CMD_RESTART2,"recovery");
    for(;;)pause();
}
static void early_escape_timer(void) {
    if(!PROBE_SECONDS)return;
    pid_t child=fork();
    if(child==0) {
        /* Independent of PID 1's later device scan and filesystem mounts. */
        struct timespec delay={PROBE_SECONDS,0};
        while(nanosleep(&delay,&delay)&&errno==EINTR){}
        (void)kill(1,SIGUSR2);
        delay=(struct timespec){12,0};
        while(nanosleep(&delay,&delay)&&errno==EINTR){}
        syscall(__NR_reboot,LINUX_REBOOT_MAGIC1,LINUX_REBOOT_MAGIC2,
                LINUX_REBOOT_CMD_RESTART2,"recovery");
        _exit(1);
    }
}
int main(int argc,char **argv) {
    if(argc>1&&!strcmp(argv[1],"--shell")) {
        if(setgid(0)||setuid(0))return 77;
        execl("/bin/sh","sh",(char *)NULL);return 127;
    }
    if(argc>1&&!strcmp(argv[1],"--recover")) {
        if(setuid(0))return 77;
        int fd=open("/run/forge-recovery-request",O_CREAT|O_WRONLY|O_CLOEXEC,0600);
        if(fd<0)return 1;
        close(fd);return 0;
    }
    if(getpid()!=1){fputs("Forge init requires PID 1\n",stderr);return 77;}
    int early=open("/dev/kmsg",O_WRONLY|O_CLOEXEC);
    if(early>=0){(void)write(early,"<6>FORGE: entered standalone PID 1\n",34);close(early);}
    struct sigaction action={0};action.sa_handler=request_recovery;
    sigemptyset(&action.sa_mask);sigaction(SIGUSR2,&action,NULL);
    early_escape_timer();
    umask(022);setenv("PATH","/bin:/sbin:/usr/bin:/usr/sbin",1);
    setenv("HOME","/",1);setenv("TERM","linux",1);
    directory("/dev",0755);directory("/proc",0755);directory("/sys",0755);
    directory("/run",0755);directory("/tmp",01777);directory("/data",0700);directory("/os",0700);
    mount("devtmpfs","/dev","devtmpfs",MS_NOSUID,"mode=0755");
    mount("proc","/proc","proc",MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL);
    mount("sysfs","/sys","sysfs",MS_NOSUID|MS_NODEV|MS_NOEXEC,NULL);
    mount("tmpfs","/run","tmpfs",MS_NOSUID|MS_NODEV,"mode=0755,size=8m");
    mount("tmpfs","/tmp","tmpfs",MS_NOSUID|MS_NODEV,"mode=1777,size=16m");
    directory("/run/forge-usb",0755);
    (void)chown("/run/forge-usb",2000,2000);
    directory("/dev/pts",0755);directory("/dev/socket",0755);
    mount("devpts","/dev/pts","devpts",MS_NOSUID|MS_NOEXEC,"mode=0620,ptmxmode=0666");
    directory("/sys/fs/selinux",0755);
    mount("selinuxfs","/sys/fs/selinux","selinuxfs",0,NULL);
    (void)put("/sys/fs/selinux/enforce","0");
    (void)put("/sys/power/wake_lock","forge-core");
    (void)put("/proc/sys/kernel/hotplug","/bin/mdev");
    report("FORGE: before device scan");
    (void)run((char *const[]){"/bin/busybox","mdev","-s",NULL});
    report("FORGE: after device scan");
    directory("/dev/graphics",0755);
    (void)symlink("/dev/fb0","/dev/graphics/fb0");
    (void)run((char *const[]){"/bin/busybox","hwclock","-s","-u",NULL});
    int storage_ok=!mount("/dev/mmcblk0p22","/data","ext4",MS_NOSUID|MS_NODEV|MS_NOATIME,NULL);
    directory("/data/forge",0700);
    logfd=open("/data/forge/boot.log",O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);
    if(mount("/dev/mmcblk0p20","/os","ext4",MS_NOSUID|MS_NODEV|MS_NOATIME,NULL))storage_ok=0;
    if(storage_ok&&mount("/data/forge/state","/os/root/var/lib/forge",NULL,MS_BIND,NULL))storage_ok=0;
    (void)syscall(__NR_sethostname,"forge-tablet",12);
    report("FORGE CORE: PID 1 online; Android framework is absent");
    int watchdog=open("/dev/watchdog",O_WRONLY|O_CLOEXEC|O_NONBLOCK);
    (void)put("/sys/class/android_usb/android0/enable","0");
    (void)put("/sys/class/android_usb/android0/idVendor","04e8");
    (void)put("/sys/class/android_usb/android0/idProduct","685e");
    (void)put("/sys/class/android_usb/android0/iManufacturer","Forge");
    (void)put("/sys/class/android_usb/android0/iProduct","Forge Music and Home");
    (void)put("/sys/class/android_usb/android0/iSerial",FORGE_USB_SERIAL);
    /* Recovery adbd can drop to shell before opening the legacy gadget. */
    (void)chown("/dev/android_adb",2000,2000);
    (void)chmod("/dev/android_adb",0660);
    (void)chmod("/dev/ptmx",0666);
    (void)chmod("/dev/null",0666);
    (void)chmod("/dev/zero",0666);
    (void)chmod("/dev/random",0666);
    (void)chmod("/dev/urandom",0666);
    (void)put("/sys/class/android_usb/android0/functions","adb");
    (void)put("/sys/class/android_usb/android0/enable","1");
    pid_t adb=spawn((char *const[]){"/sbin/adbd",NULL});
    (void)put("/sys/class/graphics/fb0/blank","0");
    (void)put("/sys/class/backlight/panel/brightness","130");
    pid_t screen=spawn((char *const[]){"/bin/sh","/etc/forge/probe-screen.sh",NULL});
    pid_t network=storage_ok?spawn((char *const[]){"/bin/sh","/etc/forge/network-service.sh",NULL}):-1;
    pid_t runtime=storage_ok?spawn((char *const[]){"/bin/sh","/etc/forge/runtime.sh",NULL}):-1;
    if(logfd>=0)dprintf(logfd,"runtime-supervisor=%ld\n",(long)runtime);
    if(logfd>=0)dprintf(logfd,"diagnostics=%ld screen-supervisor=%ld\n",(long)adb,(long)screen);
    unsigned runtime_retry=0,network_retry=0,failures=0;
    for(unsigned seconds=0;!PROBE_SECONDS||seconds<PROBE_SECONDS;seconds++) {
        if(recovery_requested||!access("/run/forge-recovery-request",F_OK)||(!storage_ok&&seconds>=15))break;
        int status;pid_t p;
        while((p=waitpid(-1,&status,WNOHANG))>0) {
            if(logfd>=0)dprintf(logfd,"child=%ld status=%d\n",(long)p,status);
            if(p==screen)screen=-1;
            if(p==runtime){runtime=-1;runtime_retry=seconds+(++failures>=3?60:5);
                screen=spawn((char *const[]){"/bin/sh","/etc/forge/probe-screen.sh",NULL});}
            if(p==network){network=-1;network_retry=seconds+5;}
            if(p==adb)adb=spawn((char *const[]){"/sbin/adbd",NULL});
        }
        if(storage_ok&&runtime<0&&seconds>=runtime_retry)
            runtime=spawn((char *const[]){"/bin/sh","/etc/forge/runtime.sh",NULL});
        if(storage_ok&&network<0&&seconds>=network_retry)
            network=spawn((char *const[]){"/bin/sh","/etc/forge/network-service.sh",NULL});
        if(watchdog>=0)(void)write(watchdog,"K",1);
        struct timespec t={1,0};while(nanosleep(&t,&t)&&errno==EINTR){}
    }
    if(runtime>0)(void)kill(runtime,SIGTERM);
    if(network>0)(void)kill(network,SIGTERM);
    if(screen>0)(void)kill(screen,SIGTERM);
    for(unsigned n=0;n<8;n++) {
        int status;while(waitpid(-1,&status,WNOHANG)>0){}
        if(watchdog>=0)(void)write(watchdog,"K",1);
        struct timespec t={1,0};while(nanosleep(&t,&t)&&errno==EINTR){}
    }
    if(runtime>0)(void)kill(runtime,SIGKILL);
    if(network>0)(void)kill(network,SIGKILL);
    recover();return 0;
}
