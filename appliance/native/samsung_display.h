/* Exynos3475 userspace display ABI, from the generated decon-fb.h in
 * Exynos3475/android_hardware_samsung_slsi_exynos3475 at
 * bae71359525e180951307e70d783f9fab67ae7eb, include/decon-fb.h.
 * These declarations describe the kernel syscall ABI; no Android HAL is used.
 * Only explicit --samsung mode uses this device-specific interface. */
#ifndef FORGE_SAMSUNG_DISPLAY_H
#define FORGE_SAMSUNG_DISPLAY_H
#include <stdbool.h>
typedef struct { int32_t x,y; uint32_t w,h; } ForgeRect;
typedef struct { int32_t x,y; uint32_t w,h,fw,fh; } ForgeFrame;
typedef struct {
    int32_t state;
    union {
        uint32_t color;
        struct {
            int32_t fd[3], fence_fd, alpha, blending, idma, format;
            struct { uint32_t addr[3]; int32_t rotation,csc; } vpp;
            ForgeRect block,transparent,opaque;
            ForgeFrame src;
        };
    };
    ForgeFrame dst;
    bool protection;
} ForgeWindow;
typedef struct { int32_t fence,odma; ForgeWindow windows[8]; } ForgeWindows;
typedef struct { uint32_t length,align,heaps,flags; int32_t handle; } ForgeIonAlloc;
typedef struct { int32_t handle,fd; } ForgeIonFd;
_Static_assert(sizeof(ForgeWindow)==156,"Exynos3475 window ABI");
_Static_assert(sizeof(ForgeWindows)==1256,"Exynos3475 submit ABI");
_Static_assert(sizeof(ForgeIonAlloc)==20,"legacy ARM32 ION ABI");
#define FORGE_WIN_CONFIG _IOW('F',209,ForgeWindows)
#define FORGE_ION_ALLOC _IOWR('I',0,ForgeIonAlloc)
#define FORGE_ION_FREE _IOWR('I',1,int32_t)
#define FORGE_ION_SHARE _IOWR('I',4,ForgeIonFd)

typedef struct { int ion,buffer[2],fence[2],next; int32_t handle[2]; unsigned char *memory[2];size_t size; } SamsungDisplay;
static void samsung_init(SamsungDisplay *s) {
    memset(s,0,sizeof *s);s->ion=-1;
    for(int i=0;i<2;i++)s->buffer[i]=s->fence[i]=-1;
}
static int samsung_allocate(SamsungDisplay *s,size_t size) {
    samsung_init(s);s->size=size;
    if(sizeof(void *)!=4) {errno=ENOTSUP;return -1;}
    s->ion=open("/dev/ion",O_RDWR|O_CLOEXEC);
    if(s->ion<0) return -1;
    for(int i=0;i<2;i++) {
        ForgeIonAlloc a={.length=(uint32_t)size,.align=4096,.heaps=1,.flags=0};
        if(ioctl(s->ion,FORGE_ION_ALLOC,&a)<0) return -1;
        s->handle[i]=a.handle;
        ForgeIonFd shared={.handle=a.handle,.fd=-1};
        if(ioctl(s->ion,FORGE_ION_SHARE,&shared)<0) return -1;
        s->buffer[i]=shared.fd;
        (void)fcntl(s->buffer[i],F_SETFD,FD_CLOEXEC);
        s->memory[i]=mmap(NULL,size,PROT_READ|PROT_WRITE,MAP_SHARED,shared.fd,0);
        if(s->memory[i]==MAP_FAILED) {s->memory[i]=NULL;return -1;}
    }
    return 0;
}
static unsigned char *samsung_begin(SamsungDisplay *s) {
    int i=s->next;
    if(s->fence[i]>=0) {
        struct pollfd p={.fd=s->fence[i],.events=POLLIN};
        int rc=poll(&p,1,1000);int saved=errno;
        close(s->fence[i]);s->fence[i]=-1;
        if(rc<=0||!(p.revents&POLLIN)) {errno=rc==0?ETIMEDOUT:rc<0?saved:EIO;return NULL;}
    }
    return s->memory[i];
}
static int samsung_submit(SamsungDisplay *s,int fb_fd,int enabled) {
    ForgeWindows config;memset(&config,0,sizeof config);
    config.fence=-1;config.odma=-1;
    for(unsigned i=0;i<8;i++) {
        config.windows[i].fence_fd=-1;
        for(unsigned j=0;j<3;j++)config.windows[i].fd[j]=-1;
    }
    if(enabled) {
        ForgeWindow *w=&config.windows[0];
        w->state=2;w->fd[0]=s->buffer[s->next];w->alpha=255;
        w->blending=0;w->idma=0;w->format=2; /* RGBA8888 */
        w->src=(ForgeFrame){0,0,800,1280,800,1280};w->dst=w->src;
    }
    if(ioctl(fb_fd,FORGE_WIN_CONFIG,&config)<0) return -1;
    if(enabled&&config.fence<0) {errno=EPROTO;return -1;}
    /* This is a release fence: it signals after a subsequent presentation.
     * Waiting on it immediately would deadlock a single outstanding frame. */
    if(enabled) {s->fence[s->next]=config.fence;s->next^=1;}
    else if(config.fence>=0)close(config.fence);
    return 0;
}
static void samsung_release(SamsungDisplay *s) {
    for(int i=0;i<2;i++) {
        if(s->fence[i]>=0)close(s->fence[i]);
        if(s->memory[i])munmap(s->memory[i],s->size);
        if(s->buffer[i]>=0)close(s->buffer[i]);
        if(s->ion>=0&&s->handle[i]) (void)ioctl(s->ion,FORGE_ION_FREE,&s->handle[i]);
    }
    if(s->ion>=0)close(s->ion);
}
#endif
