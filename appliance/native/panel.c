/* Forge appliance panel: original software renderer and Linux input frontend.
 * The framebuffer build depends on libc and Linux UAPI, not Android's framework.
 * X11 is an optional workstation development backend, not part of the target.
 */
#define _POSIX_C_SOURCE 200809L
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <limits.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>
#include "samsung_display.h"
#include "browser_surface.h"
#include "touch_state.h"
#ifdef FORGE_ANDROID_SURFACE
#include <android/native_window_jni.h>
#endif
#ifdef FORGE_X11
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/keysym.h>
#endif

enum { WIDTH = 800, HEIGHT = 1280 };
static uint32_t pixels[WIDTH * HEIGHT];
static volatile sig_atomic_t quitting;
static const uint32_t BG=0x101918, CARD=0x1b2926, DIM=0x8daca0;
static const uint32_t TEXT=0xf1f0df, ACCENT=0xcbed9c, ORANGE=0xf8a775;
static const char *socket_path, *capture_path, *status_path;
static int home_page, connected;
static int samsung_mode;
static int music_service;
static const char *web_surface_path, *web_socket_path;
static ForgeSurface browser_surface=FORGE_SURFACE_INIT;
static int browse_page, keyboard_open, keyboard_mode, keyboard_caps, browser_ready;
static int return_to_android_pending;
static int standalone;
static int home_dashboard, pending_browser_tab;
static int64_t browser_retry_at;
static char track_title[81]="SELECT A TRACK", track_artist[81]="YOUTUBE MUSIC";
static char output_label[81]="THIS TABLET";
static char player_status[16]="READY";
static uint64_t revision, position_frames, frames_written, underruns;
static unsigned playing, volume, fault;
static const char *notice = "";
static int64_t notice_retry_at;
static struct {
    int fd;
    char command[128], response[512];
    size_t sent, received;
    int64_t deadline;
} control = {.fd = -1};

typedef struct { char c; unsigned char r[7]; } Glyph;
static const Glyph glyphs[] = {
 {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
 {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
 {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
 {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
 {'I',{31,4,4,4,4,4,31}}, {'J',{7,2,2,2,18,18,12}},
 {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
 {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
 {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
 {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
 {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
 {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
 {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
 {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
 {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
 {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
 {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
 {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
 {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
 {'.',{0,0,0,0,0,6,6}}, {':',{0,6,6,0,6,6,0}},
 {'-',{0,0,0,31,0,0,0}}, {'/',{1,2,2,4,8,8,16}},
 {'+',{0,4,4,31,4,4,0}}, {'%',{17,2,4,4,8,16,17}},
 {'?',{14,17,1,2,4,0,4}}, {'!',{4,4,4,4,4,0,4}},
 {'@',{14,17,23,21,23,16,14}}, {'_',{0,0,0,0,0,0,31}},
 {',',{0,0,0,0,6,4,8}}, {';',{0,6,6,0,6,4,8}},
 {'\'',{6,4,8,0,0,0,0}}, {'"',{10,10,10,0,0,0,0}},
 {'(',{2,4,8,8,8,4,2}}, {')',{8,4,2,2,2,4,8}},
 {'[',{14,8,8,8,8,8,14}}, {']',{14,2,2,2,2,2,14}},
 {'{',{3,4,4,8,4,4,3}}, {'}',{24,4,4,2,4,4,24}},
 {'#',{10,31,10,10,31,10,0}}, {'$',{4,15,20,14,5,30,4}},
 {'^',{4,10,17,0,0,0,0}}, {'&',{12,18,20,8,21,18,13}},
 {'*',{0,21,14,31,14,21,0}}, {'=',{0,31,0,31,0,0,0}},
 {'<',{1,2,4,8,4,2,1}}, {'>',{16,8,4,2,4,8,16}},
 {'\\',{16,8,8,4,2,2,1}}, {'|',{4,4,4,4,4,4,4}},
 {'`',{8,4,2,0,0,0,0}}, {'~',{0,0,9,22,0,0,0}}
};

static void rectangle(int x, int y, int w, int h, uint32_t color) {
    int x0=x<0?0:x, y0=y<0?0:y, x1=x+w>WIDTH?WIDTH:x+w;
    int y1=y+h>HEIGHT?HEIGHT:y+h;
    for (int row=y0; row<y1; row++)
        for (int col=x0; col<x1; col++) pixels[row*WIDTH+col]=color;
}
static void circle(int cx, int cy, int radius, uint32_t color) {
    for (int y=-radius; y<=radius; y++) for (int x=-radius; x<=radius; x++)
        if (x*x+y*y<=radius*radius) rectangle(cx+x,cy+y,1,1,color);
}
static void roundrect(int x,int y,int w,int h,int r,uint32_t color) {
    rectangle(x+r,y,w-2*r,h,color); rectangle(x,y+r,w,h-2*r,color);
    circle(x+r,y+r,r,color); circle(x+w-r-1,y+r,r,color);
    circle(x+r,y+h-r-1,r,color); circle(x+w-r-1,y+h-r-1,r,color);
}
static void label(int x,int y,int scale,uint32_t color,const char *s) {
    for (; *s; s++,x+=6*scale) {
        int c=toupper((unsigned char)*s);
        for (size_t g=0; g<sizeof glyphs/sizeof glyphs[0]; g++) if(glyphs[g].c==c) {
            for(int row=0;row<7;row++) for(int col=0;col<5;col++)
                if(glyphs[g].r[row] & (1u<<(4-col)))
                    rectangle(x+col*scale,y+row*scale,scale,scale,color);
            break;
        }
    }
}
static void centered(int y,int scale,uint32_t color,const char *s) {
    label((WIDTH-(int)strlen(s)*6*scale+scale)/2,y,scale,color,s);
}
static void limited_label(int x,int y,int scale,uint32_t color,const char *s,size_t limit) {
    char text[81];size_t n=strlen(s);
    if(limit>sizeof text-1)limit=sizeof text-1;
    if(n>limit)n=limit;
    memcpy(text,s,n);text[n]=0;
    if(strlen(s)>n&&n>=3)memcpy(text+n-3,"...",3);
    label(x,y,scale,color,text);
}
static void metadata_field(char *out,size_t size,const char *begin,const char *end) {
    size_t n=0;
    while(begin<end&&n+1<size) {
        unsigned char c=(unsigned char)*begin++;
        out[n++]=(c>=32&&c<=126)?(char)c:'?';
    }
    out[n]=0;
}
static int64_t milliseconds(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    return (int64_t)ts.tv_sec*1000+ts.tv_nsec/1000000;
}
static void signal_stop(int sig) { (void)sig; quitting=1; }

static const char *status_notice(void) {
    if(!strcmp(player_status,"STREAM_LIMIT"))return "STREAM LIMIT - STOP OTHER DEVICE";
    if(!strcmp(player_status,"CHOOSE"))return "SELECT MUSIC TO PLAY";
    if(!strcmp(player_status,"BUFFERING"))return "BUFFERING MUSIC";
    if(!strcmp(player_status,"PLAYER_ERROR"))return "PLAYER ERROR";
    return "PLAYER RESPONSE DELAYED";
}
/* Apply only fully validated bridge replies. FAILED remains a usable snapshot. */
static int apply_reply(char *response) {
    char result[16]; unsigned pstate,vol,fstate; uint64_t rev,pos,written,under;
    if(sscanf(response,"%15s %"SCNu64" %u %u %"SCNu64" %"SCNu64" %"SCNu64" %u",
        result,&rev,&pstate,&vol,&pos,&written,&under,&fstate)!=8 ||
        (strcmp(result,"OK")&&strcmp(result,"STALE")&&strcmp(result,"FAILED")) ||
        pstate>1 || vol>100 || fstate>1)return -1;
    if(music_service) {
        char *title=strchr(response,'\t');
        char *artist=title?strchr(title+1,'\t'):NULL;
        char *output=artist?strchr(artist+1,'\t'):NULL;
        char *status=output?strchr(output+1,'\t'):NULL;
        char *end=status?strchr(status+1,'\n'):output?strchr(output+1,'\n'):NULL;
        if(!title||!artist||!output||!end||(status&&(size_t)(end-status-1)>=sizeof player_status))return -1;
        metadata_field(track_title,sizeof track_title,title+1,artist);
        metadata_field(track_artist,sizeof track_artist,artist+1,output);
        metadata_field(output_label,sizeof output_label,output+1,status?status:end);
        if(status)metadata_field(player_status,sizeof player_status,status+1,end);
        else strcpy(player_status,"READY");
        if(strcmp(player_status,"READY")&&strcmp(player_status,"BUFFERING")&&
           strcmp(player_status,"CHOOSE")&&strcmp(player_status,"STREAM_LIMIT")&&
           strcmp(player_status,"PLAYER_ERROR"))return -1;
    }
    revision=rev;playing=pstate;volume=vol;position_frames=pos;
    frames_written=written;underruns=under;fault=fstate;connected=1;
    if(!strcmp(result,"STALE")) {notice="STATE CHANGED - TAP AGAIN";return 1;}
    return !strcmp(result,"FAILED")?2:0;
}
/* GET is short and bounded. Mutations use the nonblocking state machine below. */
static int exchange(const char *command) {
    if(strlen(socket_path)>=sizeof(((struct sockaddr_un *)0)->sun_path)) return -1;
    int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
    if(fd<0) return -1;
    struct sockaddr_un addr; memset(&addr,0,sizeof addr); addr.sun_family=AF_UNIX;
    memcpy(addr.sun_path,socket_path,strlen(socket_path)+1);
    int rc=connect(fd,(struct sockaddr *)&addr,sizeof addr);
    if(rc<0 && errno!=EINPROGRESS && errno!=EAGAIN) { close(fd); return -1; }
    int64_t deadline=milliseconds()+((music_service&&!strncmp(command,"DO ",3))?1500:80);
    size_t sent=0,received=0; char response[512];
    while(milliseconds()<deadline) {
        struct pollfd p={.fd=fd,.events=sent<strlen(command)?POLLOUT:POLLIN};
        int remaining=(int)(deadline-milliseconds());
        if(poll(&p,1,remaining<=0?1:remaining)<=0) continue;
        if(p.revents&(POLLERR|POLLNVAL)) break;
        if(sent<strlen(command)) {
            ssize_t n=send(fd,command+sent,strlen(command)-sent,MSG_NOSIGNAL);
            if(n>0) sent+=(size_t)n; else if(n<0&&errno!=EAGAIN&&errno!=EINTR) break;
        } else {
            ssize_t n=recv(fd,response+received,sizeof response-1-received,0);
            if(n<=0) { if(n<0&&(errno==EAGAIN||errno==EINTR)) continue; break; }
            received+=(size_t)n; response[received]=0;
            if(strchr(response,'\n')) {int result=apply_reply(response);close(fd);return result;}
            if(received==sizeof response-1) break;
        }
    }
    close(fd);return -1;
}
static void control_finish(int result) {
    if(control.fd>=0)close(control.fd);
    control.fd=-1;
    if(result==0)notice="";
    else if(result==2){notice=status_notice();notice_retry_at=milliseconds()+5000;}
    else if(result<0) {notice="COMMAND CONFIRMATION UNAVAILABLE";notice_retry_at=milliseconds()+5000;}
}
static void control_poll(void) {
    if(control.fd<0)return;
    if(milliseconds()>=control.deadline) {control_finish(-1);return;}
    struct pollfd p={.fd=control.fd,.events=control.sent<strlen(control.command)?POLLOUT:POLLIN};
    if(poll(&p,1,0)<=0)return;
    /* A peer may queue its complete reply and close in the same poll result. */
    if(p.revents&(POLLERR|POLLNVAL)) {control_finish(-1);return;}
    if(control.sent<strlen(control.command)) {
        ssize_t n=send(control.fd,control.command+control.sent,strlen(control.command)-control.sent,MSG_NOSIGNAL);
        if(n>0)control.sent+=(size_t)n;
        else if(n<0&&errno!=EAGAIN&&errno!=EINTR)control_finish(-1);
        return;
    }
    ssize_t n=recv(control.fd,control.response+control.received,sizeof control.response-1-control.received,0);
    if(n>0) {
        control.received+=(size_t)n;control.response[control.received]=0;
        if(strchr(control.response,'\n'))control_finish(apply_reply(control.response));
        else if(control.received==sizeof control.response-1)control_finish(-1);
    } else if(n==0||(n<0&&errno!=EAGAIN&&errno!=EINTR))control_finish(-1);
}
static int control_start(const char *command) {
    if(control.fd>=0||strlen(socket_path)>=sizeof(((struct sockaddr_un *)0)->sun_path))return -1;
    int fd=socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
    if(fd<0)return -1;
    struct sockaddr_un addr;memset(&addr,0,sizeof addr);addr.sun_family=AF_UNIX;
    memcpy(addr.sun_path,socket_path,strlen(socket_path)+1);
    int rc=connect(fd,(struct sockaddr *)&addr,sizeof addr);
    if(rc<0&&errno!=EINPROGRESS&&errno!=EAGAIN){close(fd);return -1;}
    control.fd=fd;strcpy(control.command,command);control.sent=control.received=0;
    /* Song transitions can take several seconds; the UI remains nonblocking. */
    control.deadline=milliseconds()+15000;
    return 0;
}
static void refresh(void) {
    control_poll();
    if(control.fd>=0)return;
    if(exchange("GET\n")<0) connected=0;
    else if(connected&&!fault&&milliseconds()>=notice_retry_at&&
            (!strcmp(notice,"COMMAND CONFIRMATION UNAVAILABLE")||!strcmp(notice,"PLAYER UNAVAILABLE")||
             !strcmp(notice,"PLAYER RESPONSE DELAYED")||!strcmp(notice,"STREAM LIMIT - STOP OTHER DEVICE")||
             !strcmp(notice,"BUFFERING MUSIC")||!strcmp(notice,"PLAYER ERROR")||!strcmp(notice,"SELECT MUSIC TO PLAY")))
        notice="";
}
static void mutate(const char *action) {
    char command[128];
    if(!connected||fault) { notice="PLAYER UNAVAILABLE"; notice_retry_at=milliseconds()+5000; return; }
    if(control.fd>=0) {notice="COMMAND IN PROGRESS";return;}
    snprintf(command,sizeof command,"DO %"PRIu64" %s\n",revision,action);
    if(control_start(command)) {notice="PLAYER UNAVAILABLE";notice_retry_at=milliseconds()+5000;}
    else notice=!strcmp(action,"NEXT")?"LOADING NEXT TRACK":"CONFIRMING COMMAND";
    /* A stale command is deliberately not automatically retried. */
}
static int browser_enabled(void) {return web_surface_path&&web_socket_path;}
static void browser_input_failed(void) {
    forge_surface_close(&browser_surface);
    browser_ready=0;browser_retry_at=milliseconds()+500;
    notice="RECONNECTING BROWSER INPUT";
}
static int browser_prepare(void) {
    if(!browser_ready&&milliseconds()>=browser_retry_at) {
        browser_retry_at=milliseconds()+1000;
        if(!forge_surface_open(&browser_surface,web_surface_path,web_socket_path)) {
            browser_ready=1;
            if(!strcmp(notice,"RECONNECTING BROWSER INPUT"))notice="";
        } else forge_surface_close(&browser_surface);
    }
    if(browser_ready&&pending_browser_tab) {
        if(forge_surface_tab(&browser_surface,(unsigned)pending_browser_tab))browser_input_failed();
        else pending_browser_tab=0;
    }
    return browser_ready;
}
static const char *keyboard_row(int row) {
    static const char *rows[3][3]={
        {"qwertyuiop","asdfghjkl@","zxcvbnm.-_"},
        {"1234567890","!@#$%^&*()","`~[]{}\\|;:"},
        {"=+/?'\",<> ",":;\\|[]{}~`","!@#$%^&*()"}
    };
    return rows[keyboard_mode][row];
}
static void browser_activate(int x,int y) {
    (void)browser_prepare();
    if(y>=1040&&y<1125) {
        if(x<390)keyboard_open=!keyboard_open;
        else if(browser_ready&&x<500&&forge_surface_key(&browser_surface,0xffc2))browser_input_failed();
        else if(browser_ready&&x>=500&&forge_surface_scroll(&browser_surface,x<630?-1:1))browser_input_failed();
        return;
    }
    if(!browser_ready)return;
    if(keyboard_open&&y>=790&&y<1040) {
        uint32_t key=0;
        for(int row=0;row<3;row++)if(y>=805+54*row&&y<851+54*row&&x>=32) {
            int col=(x-32)/74;
            if(col<10&&(x-32)%74<68)key=(unsigned char)keyboard_row(row)[col];
        }
        if(y>=970&&y<1026&&x>=24&&x<776) {
            int col=(x-24)/152;
            if((x-24)%152>=144)return;
            if(col==0){keyboard_caps=!keyboard_caps;return;}
            if(col==1){keyboard_mode=(keyboard_mode+1)%3;return;}
            if(col==2)key=' ';
            if(col==3)key=0xff08;
            if(col==4)key=0xff0d;
        }
        if(key&&keyboard_caps&&key>='a'&&key<='z')key=key-'a'+'A';
        if(key&&forge_surface_key(&browser_surface,key))browser_input_failed();
        return;
    }
    if(y>=0&&y<1040) {
        int sx=(int)((int64_t)x*browser_surface.width/WIDTH);
        int sy=(int)((int64_t)y*browser_surface.height/1040);
        if(forge_surface_click(&browser_surface,sx,sy))browser_input_failed();
    }
}
static void activate(int x,int y) {
    if(y>=1140&&y<=1230) {
        if(browser_enabled()) {
            int tab=x<285?0:x<520?1:2;
            browse_page=tab==1;home_page=tab==2;
            if(tab==1){pending_browser_tab=1;(void)browser_prepare();}
        } else home_page=x>=400;
        return_to_android_pending=0;notice="";return;
    }
    if(browse_page){browser_activate(x,y);return;}
    if(home_page) {
        if(home_dashboard&&x>=120&&x<=680&&y>=605&&y<=700) {
            browse_page=1;pending_browser_tab=2;notice="";(void)browser_prepare();return;
        }
        if(!standalone&&x>=48&&x<=752&&y>=984&&y<=1084) {
            if(return_to_android_pending) quitting=1;
            else { return_to_android_pending=1; notice="TAP RETURN AGAIN TO EXIT"; }
        }
        return;
    }
    if(browser_enabled()&&x>=48&&x<=752&&y>=242&&y<=785) {
        browse_page=1;pending_browser_tab=1;notice="";(void)browser_prepare();return;
    }
    if(x>=302&&x<=498&&y>=818&&y<=948) mutate(playing?"PAUSE":"PLAY");
    else if(x>=100&&x<=250&&y>=828&&y<=942) mutate(music_service?"NEXT":"REWIND");
    else if(x>=80&&x<=720&&y>=995&&y<=1075) {
        char command[40]; unsigned value=(unsigned)((x-80)*100/640);
        snprintf(command,sizeof command,"VOLUME %u",value);mutate(command);
    }
}

static void gesture(int x,int y,int dx,int dy) {
    if(abs(dx)>24||abs(dy)>24) {
        if(browse_page&&browser_ready&&y>=0&&y<1040&&
           !(keyboard_open&&y>=790)&&abs(dy)>abs(dx)) {
            int count=abs(dy)/60+1;if(count>8)count=8;
            int sx=(int)((int64_t)x*browser_surface.width/WIDTH);
            int sy=(int)((int64_t)y*browser_surface.height/1040);
            if(forge_surface_fake(&browser_surface,6,0,sx,sy)){browser_input_failed();return;}
            for(int i=0;i<count;i++)if(forge_surface_scroll(&browser_surface,dy<0?1:-1)) {
                browser_input_failed();break;
            }
        } else if(!browse_page&&!home_page&&y>=995&&y<=1075)activate(x,y);
        return;
    }
    activate(x,y);
}

static int consume_touch(ForgeTouch *touch) {
    struct input_event e;
    while(read(touch->fd,&e,sizeof e)==sizeof e) {
        int x,y,dx,dy,result=forge_touch_event(touch,&e,&x,&y,&dx,&dy);
        if(result<0)return -1;
        if(result)gesture(x,y,dx,dy);
    }
    return 0;
}

static void navigation(void) {
    roundrect(48,1140,704,88,24,CARD);
    if(browser_enabled()) {
        int tab=home_page?2:browse_page?1:0;
        roundrect(54+233*tab,1146,226,76,20,0x344636);
        label(124,1175,3,tab==0?ACCENT:DIM,"MUSIC");
        label(345,1175,3,tab==1?ACCENT:DIM,"BROWSE");
        label(596,1175,3,tab==2?ACCENT:DIM,"HOME");
    } else {
        roundrect(home_page?401:54,1146,345,76,20,0x344636);
        label(160,1175,3,home_page?DIM:ACCENT,"MUSIC");
        label(525,1175,3,home_page?ACCENT:DIM,"HOME");
    }
    centered(1252,1,DIM,music_service?"YOUR MUSIC. YOUR HOME. A LITTLE MORE LIFE.":"NATIVE RUNTIME PROTOTYPE / YOUTUBE MUSIC NOT CONNECTED");
}
static void render_browser(void) {
    (void)browser_prepare();
    if(browser_ready&&forge_surface_draw(&browser_surface,pixels,WIDTH,WIDTH,1040)) {
        forge_surface_close(&browser_surface);browser_ready=0;
    }
    if(!browser_ready) {
        centered(430,5,TEXT,"OPENING YOUR MUSIC");
        centered(500,2,DIM,"ONE MOMENT...");
    }
    if(keyboard_open) {
        roundrect(16,785,768,251,14,BG);
        for(int row=0;row<3;row++)for(int col=0;col<10;col++) {
            int x=32+col*74,y=805+row*54;char key[2]={keyboard_row(row)[col],0};
            roundrect(x,y,68,46,8,CARD);label(x+25,y+12,3,TEXT,key);
        }
        const char *names[]={"CAPS",keyboard_mode==0?"123":keyboard_mode==1?"MORE":"ABC","SPACE","BACK","ENTER"};
        for(int col=0;col<5;col++) {
            int x=24+col*152;uint32_t color=col==0&&keyboard_caps?ACCENT:CARD;
            roundrect(x,970,144,56,8,color);
            label(x+(144-(int)strlen(names[col])*12)/2,990,2,color==ACCENT?BG:TEXT,names[col]);
        }
    }
    roundrect(32,1048,348,72,14,keyboard_open?ACCENT:CARD);
    label(65,1073,3,keyboard_open?BG:TEXT,keyboard_open?"HIDE KEYBOARD":"KEYBOARD");
    roundrect(392,1048,100,72,14,CARD);label(412,1077,2,TEXT,"RETRY");
    roundrect(500,1048,118,72,14,CARD);label(540,1073,3,TEXT,"UP");
    roundrect(632,1048,136,72,14,CARD);label(664,1073,3,TEXT,"DOWN");
    if(*notice)centered(1128,1,ORANGE,notice);
}
static void render(void) {
    if(status_path) {
        char status[320];
        int n=snprintf(status,sizeof status,"connected=%d\nfault=%u\nplaying=%u\nrevision=%"PRIu64"\nposition=%"PRIu64"\nstatus=%s\nnotice=%s\n",
            connected,fault,playing,revision,position_frames,player_status,notice);
        if(n>0&&(size_t)n<sizeof status) {
            int fd=open(status_path,O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC|O_NOFOLLOW,0600);
            if(fd>=0){(void)write(fd,status,(size_t)n);close(fd);}
        }
    }
    char text[100]; rectangle(0,0,WIDTH,HEIGHT,BG);
    if(browse_page){render_browser();navigation();return;}
    label(48,46,3,ACCENT,"F O R G E");
    circle(650,55,6,connected?(fault?ORANGE:ACCENT):DIM);
    label(670,46,2,DIM,connected?(music_service?"MUSIC":"LOCAL"):"OFFLINE");
    label(48,118,7,TEXT,home_page?"AT HOME.":"JUST LISTEN.");
    label(48,190,2,DIM,home_page?"YOUR HOME, WITHOUT LEAVING THE MUSIC.":"A SMALL SYSTEM. A LITTLE MORE LIFE.");
    if(!home_page) {
        roundrect(48,242,704,475,24,CARD);
        /* Original procedural artwork, deterministic and independent of audio. */
        for(int i=0;i<62;i++) {
            int height=24+((i*17+i*i*7)%113);
            if(i>14&&i<47) height+=80;
            roundrect(88+i*10,442-height/2,5,height,2,i<31?ACCENT:ORANGE);
        }
        label(80,275,2,DIM,music_service?"YOUTUBE MUSIC / LIVE SESSION":"ORIGINAL AUDIO STUDY / 001");
        if(music_service) limited_label(500,275,2,DIM,output_label,20);
        limited_label(80,598,2,TEXT,music_service?track_title:"FIRST LIGHT",50);
        if(browser_enabled()) {
            roundrect(80,628,300,58,16,ACCENT);
            label(102,645,3,BG,"SELECT MUSIC");
        }
        limited_label(48,735,music_service?4:5,TEXT,music_service?track_title:"FIRST LIGHT",music_service?23:19);
        limited_label(50,786,2,DIM,music_service?track_artist:"LOCAL TEST COMPOSITION",56);
        snprintf(text,sizeof text,"%02"PRIu64":%02"PRIu64,position_frames/48000/60,(position_frames/48000)%60);
        label(640,751,3,ACCENT,text);
        roundrect(302,818,196,130,40,connected&&!fault?ACCENT:CARD);
        if(playing) { rectangle(369,855,18,54,BG);rectangle(412,855,18,54,BG); }
        else for(int dx=0;dx<48;dx++) rectangle(382+dx,851+dx/2,1,64-dx,BG);
        roundrect(100,841,150,84,22,CARD); label(121,872,3,TEXT,music_service?"NEXT":"RESET");
        label(538,863,2,fault?ORANGE:DIM,!connected?(music_service?"CONNECTING":"OFFLINE"):fault?(music_service?"CONNECTING MUSIC":"AUDIO ERROR"):playing?"PLAYING":"PAUSED");
        if(music_service&&strcmp(player_status,"READY")) centered(959,2,ORANGE,status_notice());
        label(80,986,2,DIM,"VOLUME");
        snprintf(text,sizeof text,"%u%%",volume);label(655,986,2,TEXT,text);
        roundrect(80,1030,640,8,4,CARD);
        if(volume) roundrect(80,1030,(int)volume*640/100,8,4,ACCENT);
        circle(80+(int)volume*640/100,1034,13,TEXT);
    } else {
        roundrect(48,264,704,460,24,CARD);
        circle(400,377,55,0x304239);
        for(int i=0;i<45;i++) rectangle(356+i,389-i,90-2*i,3,ACCENT);
        rectangle(372,390,56,38,ACCENT); rectangle(394,406,14,22,0x304239);
        centered(474,4,TEXT,home_dashboard?"YOUR HOME":"CONNECT YOUR HOME");
        centered(535,2,DIM,home_dashboard?"HOME ASSISTANT / YOUR DASHBOARD":"SET A HOME ADDRESS IN THE FORGE LAUNCHER.");
        centered(578,2,DIM,"YOUR MUSIC IS STILL CLOSE AT HAND.");
        if(home_dashboard) {
            roundrect(120,605,560,95,20,ACCENT);
            centered(638,3,BG,"OPEN DASHBOARD");
        }
        roundrect(48,782,704,175,24,CARD);
        label(82,815,2,DIM,"MUSIC SESSION");
        label(82,858,4,TEXT,connected&&!fault?(playing?"STILL PLAYING":"PAUSED"):"CONNECTING MUSIC");
        label(82,916,2,DIM,"YOUR MUSIC CONTINUES WHILE YOU ARE HERE.");
        if(!standalone) {
            roundrect(48,984,704,100,24,return_to_android_pending?ORANGE:CARD);
            centered(1008,3,return_to_android_pending?BG:TEXT,"RETURN TO ANDROID");
            centered(1056,2,return_to_android_pending?BG:DIM,return_to_android_pending?"TAP AGAIN TO CONFIRM":"TAP TWICE TO EXIT FORGE");
        } else {
            roundrect(48,984,704,100,24,CARD);
            centered(1008,2,connected&&!fault?ACCENT:ORANGE,connected&&!fault?"MUSIC PLAYER CONNECTED":"WAITING FOR MUSIC PLAYER");
            centered(1056,2,DIM,"USE MUSIC BELOW TO RETURN TO YOUR SESSION");
        }
    }
    if(*notice) centered(1096,2,ORANGE,notice);
    navigation();
}

static int snapshot(const char *path) {
    /* Browser/auth surfaces are transient monitor pixels, never evidence. */
    if(browse_page){errno=EPERM;return -1;}
    int fd=open(path,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_CLOEXEC,0600);
    if(fd<0) { perror("snapshot");return -1; }
    FILE *f=fdopen(fd,"wb");if(!f) {close(fd);return -1;}
    fprintf(f,"P6\n%d %d\n255\n",WIDTH,HEIGHT);
    unsigned char row[WIDTH*3];
    for(int y=0;y<HEIGHT;y++) {
        for(int x=0;x<WIDTH;x++) {uint32_t c=pixels[y*WIDTH+x];row[x*3]=(unsigned char)(c>>16);row[x*3+1]=(unsigned char)(c>>8);row[x*3+2]=(unsigned char)c;}
        if(fwrite(row,1,sizeof row,f)!=sizeof row) {fclose(f);return -1;}
    }
    return fclose(f);
}

typedef struct { int fd,input; struct fb_var_screeninfo var;struct fb_fix_screeninfo fix;unsigned char *mem;size_t map_length;int minx,maxx,miny,maxy;SamsungDisplay samsung;int submitted; } Framebuffer;
static int fb_open(Framebuffer *fb,const char *path,const char *input) {
    memset(fb,0,sizeof *fb);fb->fd=-1;fb->input=-1;
    samsung_init(&fb->samsung);
    fb->fd=open(path,O_RDWR|O_CLOEXEC);if(fb->fd<0) {perror("open framebuffer");return -1;}
    if(ioctl(fb->fd,FBIOGET_VSCREENINFO,&fb->var)||ioctl(fb->fd,FBIOGET_FSCREENINFO,&fb->fix)) {perror("framebuffer geometry");return -1;}
    struct fb_var_screeninfo *v=&fb->var;
    if(samsung_mode) {
        if(v->xres!=WIDTH||v->yres!=HEIGHT) {errno=ENOTSUP;return -1;}
        if(samsung_allocate(&fb->samsung,WIDTH*HEIGHT*4)) {perror("Samsung ION allocation");return -1;}
        v->xoffset=v->yoffset=0;v->bits_per_pixel=32;
        v->red=(struct fb_bitfield){0,8,0};v->green=(struct fb_bitfield){8,8,0};
        v->blue=(struct fb_bitfield){16,8,0};v->transp=(struct fb_bitfield){24,8,0};
        fb->fix.line_length=WIDTH*4;fb->fix.smem_len=WIDTH*HEIGHT*4;
    }
    if(v->xres!=WIDTH||v->yres!=HEIGHT||v->grayscale||v->nonstd||
       fb->fix.type!=FB_TYPE_PACKED_PIXELS||(!samsung_mode&&fb->fix.visual!=FB_VISUAL_TRUECOLOR)||
       (v->bits_per_pixel!=16&&v->bits_per_pixel!=32)) {errno=ENOTSUP;return -1;}
    unsigned bytes=v->bits_per_pixel/8;
    uint64_t end=((uint64_t)v->yoffset+HEIGHT-1)*fb->fix.line_length+((uint64_t)v->xoffset+WIDTH)*bytes;
    if(end>fb->fix.smem_len||((uint64_t)v->xoffset+WIDTH)*bytes>fb->fix.line_length) {errno=EINVAL;return -1;}
    struct fb_bitfield fields[]={v->red,v->green,v->blue,v->transp};
    uint32_t masks=0;
    for(unsigned i=0;i<4;i++) {
        if(fields[i].msb_right||fields[i].length>8||fields[i].offset+fields[i].length>v->bits_per_pixel||(!fields[i].length&&i<3)) {errno=ENOTSUP;return -1;}
        uint32_t mask=fields[i].length?((1u<<fields[i].length)-1)<<fields[i].offset:0;
        if(mask&masks) {errno=EINVAL;return -1;}masks|=mask;
    }
    /* Map only the visible span. Samsung's reported allocation may include
     * padding that the active DMA buffer does not permit userspace to map. */
    fb->map_length=(size_t)end;
    fb->mem=samsung_mode?fb->samsung.memory[0]:mmap(NULL,fb->map_length,PROT_READ|PROT_WRITE,MAP_SHARED,fb->fd,0);
    if(fb->mem==MAP_FAILED) {perror("framebuffer mmap");fb->mem=NULL;return -1;}
    if(input) {
        fb->input=open(input,O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(fb->input<0) {perror("open touch input");return -1;}
        /* Android stays alive for Wi-Fi. Its hidden activity must not receive
         * the same touches as Forge; closing this fd releases the grab. */
        if(ioctl(fb->input,EVIOCGRAB,1)) {perror("exclusive touch input");return -1;}
        struct input_absinfo x,y;
        if(ioctl(fb->input,EVIOCGABS(ABS_MT_POSITION_X),&x)||ioctl(fb->input,EVIOCGABS(ABS_MT_POSITION_Y),&y)) {
            if(ioctl(fb->input,EVIOCGABS(ABS_X),&x)||ioctl(fb->input,EVIOCGABS(ABS_Y),&y)) {perror("touch calibration");return -1;}
        }
        if(x.maximum<=x.minimum||y.maximum<=y.minimum) {errno=EINVAL;return -1;}
        fb->minx=x.minimum;fb->maxx=x.maximum;fb->miny=y.minimum;fb->maxy=y.maximum;
    }
    return 0;
}
static uint32_t component(unsigned value,struct fb_bitfield b) {
    if(!b.length) return 0;
    return ((value*((1u<<b.length)-1)+127)/255)<<b.offset;
}
static int fb_draw(Framebuffer *fb) {
    if(samsung_mode) {
        fb->mem=samsung_begin(&fb->samsung);
        if(!fb->mem) {perror("Samsung release fence");return -1;}
    }
    struct fb_var_screeninfo *v=&fb->var;unsigned bytes=v->bits_per_pixel/8;
    if(bytes==4 && !v->red.offset && v->red.length==8 && !v->red.msb_right &&
       v->green.offset==8 && v->green.length==8 && !v->green.msb_right &&
       v->blue.offset==16 && v->blue.length==8 && !v->blue.msb_right &&
       v->transp.offset==24 && v->transp.length==8 && !v->transp.msb_right) {
        for(unsigned y=0;y<HEIGHT;y++) for(unsigned x=0;x<WIDTH;x++) {
            uint32_t c=pixels[y*WIDTH+x];
            uint32_t p=0xff000000U|((c&0x000000ffU)<<16)|(c&0x0000ff00U)|((c&0x00ff0000U)>>16);
            unsigned char *dst=fb->mem+(y+v->yoffset)*fb->fix.line_length+(x+v->xoffset)*4U;
            memcpy(dst,&p,4);
        }
    } else for(unsigned y=0;y<HEIGHT;y++) for(unsigned x=0;x<WIDTH;x++) {
        uint32_t c=pixels[y*WIDTH+x];uint32_t p=component((c>>16)&255,v->red)|component((c>>8)&255,v->green)|component(c&255,v->blue)|component(255,v->transp);
        unsigned char *dst=fb->mem+(y+v->yoffset)*fb->fix.line_length+(x+v->xoffset)*bytes;
        if(bytes==2) {uint16_t p16=(uint16_t)p;memcpy(dst,&p16,2);}else memcpy(dst,&p,4);
    }
    if(samsung_mode) {
        if(samsung_submit(&fb->samsung,fb->fd,1)) {perror("Samsung display submit");return -1;}
        else fb->submitted=1;
    }
    return 0;
}
static void fb_close(Framebuffer *fb) {
    if(fb->submitted) (void)samsung_submit(&fb->samsung,fb->fd,0);
    if(fb->mem&&!samsung_mode) munmap(fb->mem,fb->map_length);
    samsung_release(&fb->samsung);
    if(fb->input>=0) { (void)ioctl(fb->input,EVIOCGRAB,0); close(fb->input); }
    if(fb->fd>=0) close(fb->fd);
}
static int framebuffer_run(const char *path,const char *input) {
    Framebuffer fb;if(fb_open(&fb,path,input)) {perror("framebuffer/input");fb_close(&fb);return 1;}
    int result=0;int64_t next=0;ForgeTouch touch;
    if(fb.input>=0&&forge_touch_init(&touch,fb.input,WIDTH,HEIGHT)) {
        perror("initial touch state");fb_close(&fb);return 1;
    }
    while(!quitting) {
        if(milliseconds()>=next) {refresh();render();if(fb_draw(&fb)) {result=1;break;}next=milliseconds()+200;}
        struct pollfd p={.fd=fb.input,.events=POLLIN};poll(&p,1,20);
        if(fb.input>=0&&p.revents&POLLIN){if(consume_touch(&touch)){result=1;break;}next=0;}
    }
    if(capture_path&&!browse_page) snapshot(capture_path);
    forge_surface_close(&browser_surface);
    fb_close(&fb);return result;
}

#ifdef FORGE_ANDROID_SURFACE
/* The original renderer submits pixels through Android's compositor. Keeping
 * its display/audio services alive avoids system_server watchdog deadlocks. */
JNIEXPORT jint JNICALL Java_org_forge_surface_ForgeSurface_run(
    JNIEnv *env,jclass cls,jobject surface,jstring music,jstring web,
    jstring x11,jboolean home) {
    (void)cls;
    const char *m=NULL,*w=NULL,*s=NULL;
    ANativeWindow *window=NULL;int input=-1,result=1;ForgeTouch touch;
    pid_t owner=getppid();
    if(owner==1||prctl(PR_SET_PDEATHSIG,SIGTERM)||getppid()!=owner)return 1;
    if(!music||!web||!x11||!surface)return 1;
    m=(*env)->GetStringUTFChars(env,music,NULL);if(!m)goto done;
    w=(*env)->GetStringUTFChars(env,web,NULL);if(!w)goto done;
    s=(*env)->GetStringUTFChars(env,x11,NULL);if(!s)goto done;
    socket_path=m;web_surface_path=w;web_socket_path=s;music_service=1;home_dashboard=home;
    signal(SIGINT,signal_stop);signal(SIGTERM,signal_stop);
    window=ANativeWindow_fromSurface(env,surface);if(!window)goto done;
    if(ANativeWindow_setBuffersGeometry(window,WIDTH,HEIGHT,WINDOW_FORMAT_RGBA_8888))goto done;
    input=open("/dev/input/event1",O_RDONLY|O_NONBLOCK|O_CLOEXEC);
    if(input<0||ioctl(input,EVIOCGRAB,1)||forge_touch_init(&touch,input,WIDTH,HEIGHT))goto done;
    int64_t next=0;
    while(!quitting) {
        if(milliseconds()>=next) {
            ANativeWindow_Buffer buffer;
            refresh();render();
            if(ANativeWindow_lock(window,&buffer,NULL))goto done;
            int valid=buffer.width==WIDTH&&buffer.height==HEIGHT&&buffer.stride>=WIDTH&&
                      buffer.format==WINDOW_FORMAT_RGBA_8888&&buffer.bits;
            if(valid)for(int y=0;y<HEIGHT;y++) {
                uint32_t *out=(uint32_t *)buffer.bits+(size_t)y*buffer.stride;
                for(int x=0;x<WIDTH;x++) {
                    uint32_t c=pixels[y*WIDTH+x];
                    out[x]=0xff000000U|((c&255U)<<16)|(c&0xff00U)|((c>>16)&255U);
                }
            }
            if(ANativeWindow_unlockAndPost(window)||!valid)goto done;
            next=milliseconds()+200;
        }
        struct pollfd p={.fd=input,.events=POLLIN};
        if(poll(&p,1,20)<0&&errno!=EINTR)goto done;
        if(p.revents&(POLLHUP|POLLERR|POLLNVAL))goto done;
        if(p.revents&POLLIN){if(consume_touch(&touch))goto done;next=0;}
    }
    result=0;
done:
    forge_surface_close(&browser_surface);
    if(input>=0){(void)ioctl(input,EVIOCGRAB,0);close(input);}
    if(window)ANativeWindow_release(window);
    if(s)(*env)->ReleaseStringUTFChars(env,x11,s);
    if(w)(*env)->ReleaseStringUTFChars(env,web,w);
    if(m)(*env)->ReleaseStringUTFChars(env,music,m);
    socket_path=web_surface_path=web_socket_path=NULL;
    return result;
}
#endif

#ifdef FORGE_X11
static int x11_run(void) {
    Display *d=XOpenDisplay(NULL);if(!d) {fprintf(stderr,"Cannot open X11 display\n");return 1;}
    int screen=DefaultScreen(d);Visual *visual=DefaultVisual(d,screen);
    if(visual->red_mask!=0xff0000||visual->green_mask!=0xff00||visual->blue_mask!=0xff) {fprintf(stderr,"X11 requires RGB888 visual\n");XCloseDisplay(d);return 1;}
    Window w=XCreateSimpleWindow(d,RootWindow(d,screen),0,0,WIDTH,HEIGHT,0,0,BG);
    XStoreName(d,w,"Forge | Native Music Appliance");
    XSizeHints hints={.flags=PMinSize|PMaxSize,.min_width=WIDTH,.max_width=WIDTH,.min_height=HEIGHT,.max_height=HEIGHT};
    XSetWMNormalHints(d,w,&hints);XSelectInput(d,w,ExposureMask|ButtonReleaseMask|KeyPressMask);
    Atom close_atom=XInternAtom(d,"WM_DELETE_WINDOW",False);XSetWMProtocols(d,w,&close_atom,1);
    XMapWindow(d,w);GC gc=XCreateGC(d,w,0,NULL);
    XImage *im=XCreateImage(d,visual,(unsigned)DefaultDepth(d,screen),ZPixmap,0,(char *)pixels,WIDTH,HEIGHT,32,WIDTH*4);
    if(!im) {XFreeGC(d,gc);XDestroyWindow(d,w);XCloseDisplay(d);return 1;}
    int64_t next=0;
    while(!quitting) {
        while(XPending(d)) {
            XEvent e;XNextEvent(d,&e);
            if(e.type==ClientMessage&&(Atom)e.xclient.data.l[0]==close_atom) quitting=1;
            if(e.type==ButtonRelease&&e.xbutton.button==1) {activate(e.xbutton.x,e.xbutton.y);next=0;}
            if(e.type==Expose) next=0;
            if(e.type==KeyPress) {
                KeySym k=XLookupKeysym(&e.xkey,(e.xkey.state&ShiftMask)?1:0);
                if(browse_page) {
                    if(k==XK_Escape)browse_page=0;
                    else if(browser_ready)forge_surface_key(&browser_surface,(uint32_t)k);
                    next=0;continue;
                }
                if(k==XK_Escape||k==XK_q) quitting=1;
                if(k==XK_space) mutate(playing?"PAUSE":"PLAY");
                if(k==XK_h) home_page=1;
                if(k==XK_m) home_page=0;
                if(k==XK_s&&capture_path) {render();snapshot(capture_path);}
                next=0;
            }
        }
        if(milliseconds()>=next) {refresh();render();XPutImage(d,w,gc,im,0,0,0,0,WIDTH,HEIGHT);XFlush(d);next=milliseconds()+200;}
        struct pollfd p={.fd=ConnectionNumber(d),.events=POLLIN};poll(&p,1,20);
    }
    if(capture_path&&!browse_page) snapshot(capture_path);
    forge_surface_close(&browser_surface);
    im->data=NULL;XDestroyImage(im);XFreeGC(d,gc);XDestroyWindow(d,w);XCloseDisplay(d);return 0;
}
#endif
int main(int argc,char **argv) {
    const char *fb=NULL,*input=NULL,*snap=NULL;int x11=0;
    for(int i=1;i<argc;i++) {
        if(!strcmp(argv[i],"--socket")&&i+1<argc) socket_path=argv[++i];
        else if(!strcmp(argv[i],"--fb")&&i+1<argc) fb=argv[++i];
        else if(!strcmp(argv[i],"--input")&&i+1<argc) input=argv[++i];
        else if(!strcmp(argv[i],"--snapshot")&&i+1<argc) snap=argv[++i];
        else if(!strcmp(argv[i],"--capture")&&i+1<argc) capture_path=argv[++i];
        else if(!strcmp(argv[i],"--home")) home_page=1;
        else if(!strcmp(argv[i],"--samsung")) samsung_mode=1;
        else if(!strcmp(argv[i],"--music-service")) music_service=1;
        else if(!strcmp(argv[i],"--home-dashboard")) home_dashboard=1;
        else if(!strcmp(argv[i],"--standalone")) standalone=1;
        else if(!strcmp(argv[i],"--status-file")&&i+1<argc) status_path=argv[++i];
        else if(!strcmp(argv[i],"--web-surface")&&i+1<argc) web_surface_path=argv[++i];
        else if(!strcmp(argv[i],"--x11-socket")&&i+1<argc) web_socket_path=argv[++i];
        else if(!strcmp(argv[i],"--x11")) x11=1;
        else {fprintf(stderr,"Usage: %s --socket PATH [--x11 | --fb DEVICE [--samsung] [--input DEVICE] | --snapshot FILE.ppm] [--capture FILE.ppm] [--home] [--standalone] [--music-service [--web-surface XWD --x11-socket PATH]]\n",argv[0]);return !strcmp(argv[i],"--help")?0:2;}
    }
    if(!socket_path||!!fb+!!snap+x11!=1||(input&&!fb)||(samsung_mode&&!fb)||
       (!!web_surface_path!=!!web_socket_path)||(web_surface_path&&(!music_service||snap||capture_path))) {fprintf(stderr,"Specify socket and exactly one display mode; browser needs paired paths and music service, without capture\n");return 2;}
    signal(SIGINT,signal_stop);signal(SIGTERM,signal_stop);
    refresh();render();
    if(snap) return snapshot(snap)?1:0;
    if(fb) {
        pid_t owner=getppid();
        if(owner==1||prctl(PR_SET_PDEATHSIG,SIGTERM)||getppid()!=owner)return 1;
        return framebuffer_run(fb,input);
    }
#ifdef FORGE_X11
    return x11_run();
#else
    fprintf(stderr,"This build excludes X11; use framebuffer or snapshot mode\n");return 2;
#endif
}
