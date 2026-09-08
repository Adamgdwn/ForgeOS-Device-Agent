/*
 * forge-pcm-sink: bounded raw PCM writer for a directly named ALSA PCM node.
 *
 * This deliberately uses the Linux ALSA UAPI rather than libasound/tinyalsa so
 * the target executable has no shared-library dependency.  It is intended for
 * controlled hardware bring-up, not as the appliance playback engine.
 */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <sound/asound.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

enum { RATE = 48000, CHANNELS = 2, BYTES_PER_FRAME = 4, PERIOD_FRAMES = 960,
       PERIODS = 4, MAX_SECONDS = 1800, IO_TIMEOUT_MS = 2000 };

static volatile sig_atomic_t interrupted;

static void on_signal(int unused) { (void)unused; interrupted = 1; }

static void usage(const char *program) {
    fprintf(stderr, "Usage: %s --input PATH --seconds 1..%d [--device PATH] [--idle-silence]\n"
            "Writes raw signed-16-bit little-endian stereo 48000 Hz PCM.\n"
            "Default device: /dev/snd/pcmC0D0p\n", program, MAX_SECONDS);
}

static void set_mask(struct snd_pcm_hw_params *p, unsigned int param,
                     unsigned int value) {
    struct snd_mask *mask = &p->masks[param - SNDRV_PCM_HW_PARAM_FIRST_MASK];
    memset(mask, 0, sizeof(*mask));
    mask->bits[value / 32U] |= 1U << (value % 32U);
    p->rmask |= 1U << param;
}

static void set_interval(struct snd_pcm_hw_params *p, unsigned int param,
                         unsigned int value) {
    struct snd_interval *i = &p->intervals[param - SNDRV_PCM_HW_PARAM_FIRST_INTERVAL];
    i->min = value;
    i->max = value;
    i->integer = 1;
    p->rmask |= 1U << param;
}

static int configure_pcm(int fd) {
    struct snd_pcm_hw_params hw;
    memset(&hw, 0, sizeof(hw));
    /* Unselected constraints mean ANY, not the empty mask/zero interval. */
    for (unsigned int n = SNDRV_PCM_HW_PARAM_FIRST_MASK;
         n <= SNDRV_PCM_HW_PARAM_LAST_MASK; ++n) {
        hw.masks[n - SNDRV_PCM_HW_PARAM_FIRST_MASK].bits[0] = UINT_MAX;
        hw.masks[n - SNDRV_PCM_HW_PARAM_FIRST_MASK].bits[1] = UINT_MAX;
    }
    for (unsigned int n = SNDRV_PCM_HW_PARAM_FIRST_INTERVAL;
         n <= SNDRV_PCM_HW_PARAM_LAST_INTERVAL; ++n)
        hw.intervals[n - SNDRV_PCM_HW_PARAM_FIRST_INTERVAL].max = UINT_MAX;
    hw.rmask = UINT_MAX;
    hw.info = UINT_MAX;
    set_mask(&hw, SNDRV_PCM_HW_PARAM_ACCESS, SNDRV_PCM_ACCESS_RW_INTERLEAVED);
    set_mask(&hw, SNDRV_PCM_HW_PARAM_FORMAT, SNDRV_PCM_FORMAT_S16_LE);
    set_interval(&hw, SNDRV_PCM_HW_PARAM_CHANNELS, CHANNELS);
    set_interval(&hw, SNDRV_PCM_HW_PARAM_RATE, RATE);
    set_interval(&hw, SNDRV_PCM_HW_PARAM_PERIOD_SIZE, PERIOD_FRAMES);
    set_interval(&hw, SNDRV_PCM_HW_PARAM_PERIODS, PERIODS);
    if (ioctl(fd, SNDRV_PCM_IOCTL_HW_PARAMS, &hw) < 0) return -1;
    struct snd_pcm_sw_params sw;
    memset(&sw, 0, sizeof(sw));
    sw.period_step = 1;
    sw.avail_min = PERIOD_FRAMES;
    sw.start_threshold = PERIOD_FRAMES * 3;
    sw.stop_threshold = PERIOD_FRAMES * PERIODS;
    sw.xfer_align = 1;
    sw.boundary = PERIOD_FRAMES * PERIODS;
    while (sw.boundary <= (unsigned long)LONG_MAX / 2 - PERIOD_FRAMES * PERIODS)
        sw.boundary *= 2;
    if (ioctl(fd, SNDRV_PCM_IOCTL_SW_PARAMS, &sw) < 0) return -1;
    return ioctl(fd, SNDRV_PCM_IOCTL_PREPARE);
}

static int wait_ready(int fd, short events) {
    struct pollfd pfd = { .fd = fd, .events = events };
    int rc;
    do { rc = poll(&pfd, 1, IO_TIMEOUT_MS); } while (rc < 0 && errno == EINTR && !interrupted);
    if (rc == 0) { errno = ETIMEDOUT; return -1; }
    if (rc < 0) return -1;
    /* A FIFO may report POLLIN and POLLHUP together for its final bytes. */
    if (pfd.revents & events) return 0;
    /* ALSA signals XRUN through POLLERR; the next transfer reports EPIPE. */
    if (events == POLLOUT && (pfd.revents & POLLERR)) return 0;
    errno = (pfd.revents & POLLHUP) ? EPIPE : EIO;
    return -1;
}

static int write_frames(int pcm_fd, const uint8_t *data, size_t frames,
                        unsigned int *recoveries, uint64_t *written) {
    size_t offset = 0;
    while (offset < frames && !interrupted) {
        struct snd_xferi xfer = {
            .buf = (void *)(data + offset * BYTES_PER_FRAME), .frames = frames - offset
        };
        if (wait_ready(pcm_fd, POLLOUT) < 0) return -1;
        errno = 0;
        int rc = ioctl(pcm_fd, SNDRV_PCM_IOCTL_WRITEI_FRAMES, &xfer);
        if (rc == 0 && xfer.result > 0) {
            if ((uint64_t)xfer.result > frames - offset) { errno = EPROTO; return -1; }
            offset += (size_t)xfer.result;
            *written += (uint64_t)xfer.result;
            continue;
        }
        int error = rc < 0 ? errno : xfer.result < 0 ? (int)-xfer.result : EIO;
        if (error == EAGAIN || error == EINTR) continue;
        if (error == EPIPE && *recoveries < 3U) {
            if (ioctl(pcm_fd, SNDRV_PCM_IOCTL_PREPARE) < 0) return -1;
            ++*recoveries;
            continue;
        }
        errno = error;
        return -1;
    }
    return interrupted ? -1 : 0;
}

int main(int argc, char **argv) {
    const char *input = NULL, *device = "/dev/snd/pcmC0D0p";
    unsigned long seconds = 0;
    bool idle_silence = false;
    int input_fd = -1, pcm_fd = -1, exit_code = 1;
    uint64_t target_frames, read_frames = 0, written = 0, silence_frames = 0;
    unsigned int recoveries = 0;
    uint8_t buffer[PERIOD_FRAMES * BYTES_PER_FRAME];
    struct sigaction sa;

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--input") && i + 1 < argc) input = argv[++i];
        else if (!strcmp(argv[i], "--device") && i + 1 < argc) device = argv[++i];
        else if (!strcmp(argv[i], "--idle-silence")) idle_silence = true;
        else if (!strcmp(argv[i], "--seconds") && i + 1 < argc) {
            char *end = NULL; errno = 0; seconds = strtoul(argv[++i], &end, 10);
            if (errno || !end || *end) seconds = 0;
        } else { usage(argv[0]); return 64; }
    }
    if (!input || seconds == 0 || seconds > MAX_SECONDS) { usage(argv[0]); return 64; }
    target_frames = (uint64_t)seconds * RATE;

    memset(&sa, 0, sizeof(sa)); sa.sa_handler = on_signal;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGINT, &sa, NULL) || sigaction(SIGTERM, &sa, NULL) ||
        sigaction(SIGALRM, &sa, NULL)) { perror("sigaction"); goto cleanup; }
    alarm((unsigned int)(seconds + 5U));

    input_fd = open(input, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (input_fd < 0) { perror("open input"); goto cleanup; }
    struct stat input_stat;
    if (fstat(input_fd, &input_stat) < 0) { perror("input metadata"); goto cleanup; }
    if ((!S_ISFIFO(input_stat.st_mode) && !S_ISREG(input_stat.st_mode)) ||
        (idle_silence && !S_ISFIFO(input_stat.st_mode))) {
        fprintf(stderr,"input must be a regular PCM file or FIFO; idle silence requires FIFO\n");goto cleanup;
    }
    pcm_fd = open(device, O_WRONLY | O_NONBLOCK | O_CLOEXEC);
    if (pcm_fd < 0) { perror("open PCM"); goto cleanup; }
    if (configure_pcm(pcm_fd) < 0) { perror("configure PCM"); goto cleanup; }

    while (read_frames < target_frames && !interrupted) {
        size_t wanted = (size_t)((target_frames - read_frames) < PERIOD_FRAMES ?
            (target_frames - read_frames) : PERIOD_FRAMES) * BYTES_PER_FRAME;
        ssize_t got;
        int idle = 0;
        if (idle_silence) {
            struct pollfd pfd = {.fd=input_fd,.events=POLLIN};
            /* ALSA's writable frames provide the clock. Waiting another
             * period on an empty FIFO would accumulate scheduling drift. */
            int rc = poll(&pfd,1,0);
            if (rc < 0 && errno == EINTR) continue;
            if (rc < 0) {perror("input poll");goto cleanup;}
            idle = rc == 0;
        } else if (wait_ready(input_fd, POLLIN) < 0) { perror("read input"); goto cleanup; }
        if (idle) {memset(buffer,0,wanted);got=(ssize_t)wanted;silence_frames+=wanted/BYTES_PER_FRAME;}
        else do { got = read(input_fd, buffer, wanted); } while (got < 0 && errno == EINTR && !interrupted);
        if (got < 0 && errno == EAGAIN) continue;
        if (got <= 0) { if (got == 0) errno = ENODATA; perror("read input"); goto cleanup; }
        if ((size_t)got % BYTES_PER_FRAME) { fprintf(stderr, "input ended on a partial PCM frame\n"); goto cleanup; }
        if (write_frames(pcm_fd, buffer, (size_t)got / BYTES_PER_FRAME, &recoveries, &written) < 0) {
            perror(interrupted ? "interrupted" : "write PCM"); goto cleanup;
        }
        read_frames += (uint64_t)got / BYTES_PER_FRAME;
    }
    if (interrupted) { fprintf(stderr, "playback interrupted or exceeded deadline\n"); goto cleanup; }
    /* A nonblocking drain returns EAGAIN while samples remain. The existing
     * alarm bounds a blocking drain and its signal handler does not restart it. */
    int flags = fcntl(pcm_fd, F_GETFL);
    if (flags < 0 || fcntl(pcm_fd, F_SETFL, flags & ~O_NONBLOCK) < 0 ||
        ioctl(pcm_fd, SNDRV_PCM_IOCTL_DRAIN) < 0) { perror("drain PCM"); goto cleanup; }
    fprintf(stdout, "OK frames=%llu silence_frames=%llu recoveries=%u device=%s\n",
            (unsigned long long)written, (unsigned long long)silence_frames, recoveries, device);
    exit_code = 0;

cleanup:
    alarm(0);
    if (pcm_fd >= 0) {
        if (exit_code != 0) (void)ioctl(pcm_fd, SNDRV_PCM_IOCTL_DROP);
        (void)close(pcm_fd);
    }
    if (input_fd >= 0) (void)close(input_fd);
    return exit_code;
}
