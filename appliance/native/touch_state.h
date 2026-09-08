#ifndef FORGE_TOUCH_STATE_H
#define FORGE_TOUCH_STATE_H

#include <errno.h>
#include <linux/input.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>

/* evdev suppresses unchanged absolute coordinates. Seed slot zero before the
 * first event; starting at (0,0) misplaces taps that retain either axis. */
static inline int forge_touch_axis(int fd, unsigned mt, unsigned legacy,
                                  int *value) {
    int values[2] = {(int)mt, 0};
    if (!ioctl(fd, EVIOCGMTSLOTS(sizeof values), values)) {
        *value = values[1];
        return 0;
    }
    struct input_absinfo axis;
    if (ioctl(fd, EVIOCGABS(legacy), &axis)) return -1;
    *value = axis.value;
    return 0;
}

static inline int forge_touch_seed(int fd, int minx, int maxx, int miny,
                                   int maxy, int width, int height,
                                   int *x, int *y, int *slot) {
    int rawx, rawy;
    struct input_absinfo active;
    if (maxx <= minx || maxy <= miny || width < 1 || height < 1) {
        errno = EINVAL;
        return -1;
    }
    if (forge_touch_axis(fd, ABS_MT_POSITION_X, ABS_X, &rawx) ||
        forge_touch_axis(fd, ABS_MT_POSITION_Y, ABS_Y, &rawy)) return -1;
    *slot = 0;
    if (!ioctl(fd, EVIOCGABS(ABS_MT_SLOT), &active)) {
        if (active.value < active.minimum || active.value > active.maximum) {
            errno = EINVAL;
            return -1;
        }
        *slot = active.value;
    }
    if (rawx < minx) rawx = minx;
    if (rawx > maxx) rawx = maxx;
    if (rawy < miny) rawy = miny;
    if (rawy > maxy) rawy = maxy;
    *x = (int)(((int64_t)rawx - minx) * (width - 1) / ((int64_t)maxx - minx));
    *y = (int)(((int64_t)rawy - miny) * (height - 1) / ((int64_t)maxy - miny));
    return 0;
}

enum { FORGE_TOUCH_SLOTS=32 };
typedef struct {
    int fd,minx,maxx,miny,maxy,width,height,mt,slot,count,primary,dropped;
    int x[FORGE_TOUCH_SLOTS],y[FORGE_TOUCH_SLOTS];
    int beginx,beginy,endx,endy,released;
} ForgeTouch;
static inline int forge_touch_resync(ForgeTouch *s) {
    s->primary=-1;s->released=0;
    if(s->mt) {
        int values[FORGE_TOUCH_SLOTS+1]={ABS_MT_POSITION_X};
        struct input_absinfo active;
        if(ioctl(s->fd,EVIOCGMTSLOTS(sizeof values),values))return -1;
        for(int i=0;i<s->count;i++)s->x[i]=values[i+1];
        values[0]=ABS_MT_POSITION_Y;
        if(ioctl(s->fd,EVIOCGMTSLOTS(sizeof values),values)||
           ioctl(s->fd,EVIOCGABS(ABS_MT_SLOT),&active))return -1;
        for(int i=0;i<s->count;i++)s->y[i]=values[i+1];
        s->slot=active.value;
        if(s->slot<0||s->slot>=s->count){errno=EINVAL;return -1;}
    } else {
        struct input_absinfo x,y;
        if(ioctl(s->fd,EVIOCGABS(ABS_X),&x)||ioctl(s->fd,EVIOCGABS(ABS_Y),&y))return -1;
        s->x[0]=x.value;s->y[0]=y.value;s->slot=0;
    }
    return 0;
}
static inline int forge_touch_init(ForgeTouch *s,int fd,int width,int height) {
    struct input_absinfo slots,x,y;
    memset(s,0,sizeof *s);s->fd=fd;s->width=width;s->height=height;s->count=1;
    s->mt=!ioctl(fd,EVIOCGABS(ABS_MT_SLOT),&slots);
    if(s->mt) {
        if(slots.minimum!=0||slots.maximum<0||slots.maximum>=FORGE_TOUCH_SLOTS){errno=EINVAL;return -1;}
        s->count=slots.maximum+1;
    }
    if(ioctl(fd,EVIOCGABS(s->mt?ABS_MT_POSITION_X:ABS_X),&x)||
       ioctl(fd,EVIOCGABS(s->mt?ABS_MT_POSITION_Y:ABS_Y),&y))return -1;
    s->minx=x.minimum;s->maxx=x.maximum;s->miny=y.minimum;s->maxy=y.maximum;
    if(s->maxx<=s->minx||s->maxy<=s->miny||width<1||height<1){errno=EINVAL;return -1;}
    return forge_touch_resync(s);
}
static inline int forge_touch_scaled(int value,int min,int max,int size) {
    if(value<min)value=min;
    if(value>max)value=max;
    return (int)(((int64_t)value-min)*(size-1)/((int64_t)max-min));
}
/* Return one completed primary-contact gesture per SYN_REPORT. Secondary
 * fingers never become clicks, and dropped frames cancel rather than replay. */
static inline int forge_touch_event(ForgeTouch *s,const struct input_event *e,
                                    int *x,int *y,int *dx,int *dy) {
    if(e->type==EV_SYN&&e->code==SYN_DROPPED){s->dropped=1;s->primary=-1;s->released=0;return 0;}
    if(s->dropped) {
        if(e->type==EV_SYN&&e->code==SYN_REPORT) {
            if(forge_touch_resync(s))return -1;
            s->dropped=0;
        }
        return 0;
    }
    if(s->mt&&e->type==EV_ABS&&e->code==ABS_MT_SLOT) {
        if(e->value<0||e->value>=s->count){errno=EINVAL;return -1;}
        s->slot=e->value;
    }
    int slot=s->slot;
    if(e->type==EV_ABS&&e->code==(s->mt?ABS_MT_POSITION_X:ABS_X))s->x[slot]=e->value;
    if(e->type==EV_ABS&&e->code==(s->mt?ABS_MT_POSITION_Y:ABS_Y))s->y[slot]=e->value;
    int tracking=s->mt?(e->type==EV_ABS&&e->code==ABS_MT_TRACKING_ID):
                       (e->type==EV_KEY&&e->code==BTN_TOUCH);
    if(tracking) {
        int down=s->mt?e->value>=0:e->value!=0;
        if(down&&s->primary<0&&!s->released){s->primary=slot;s->beginx=INT32_MIN;}
        if(!down&&s->primary==slot){s->released=1;s->endx=s->x[slot];s->endy=s->y[slot];s->primary=-1;}
    }
    if(e->type==EV_SYN&&e->code==SYN_REPORT) {
        if(s->primary>=0&&s->beginx==INT32_MIN){s->beginx=s->x[s->primary];s->beginy=s->y[s->primary];}
        if(s->released) {
            s->released=0;
            *x=forge_touch_scaled(s->endx,s->minx,s->maxx,s->width);
            *y=forge_touch_scaled(s->endy,s->miny,s->maxy,s->height);
            *dx=s->beginx==INT32_MIN?0:*x-forge_touch_scaled(s->beginx,s->minx,s->maxx,s->width);
            *dy=s->beginx==INT32_MIN?0:*y-forge_touch_scaled(s->beginy,s->miny,s->maxy,s->height);
            return 1;
        }
    }
    return 0;
}

#endif
