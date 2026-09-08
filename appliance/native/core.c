#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include "core.h"

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__)
_Static_assert(__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__,
               "ForgeOS PCM input requires a little-endian target");
#else
#error "ForgeOS PCM input requires a compiler that reports target byte order"
#endif

static void set_error(char *error, size_t size, const char *format, ...) {
    va_list args;
    va_start(args, format);
    (void)vsnprintf(error, size, format, args);
    va_end(args);
}

static uint16_t le16(const unsigned char *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t le32(const unsigned char *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int read_exact(int fd, void *buffer, size_t size) {
    unsigned char *p = buffer;
    size_t done = 0;
    while (done < size) {
        ssize_t n = read(fd, p + done, size - done);
        if (n > 0) {
            done += (size_t)n;
        } else if (n == 0) {
            errno = EINVAL;
            return -1;
        } else if (errno != EINTR) {
            return -1;
        }
    }
    return 0;
}

int core_open_wav(struct core_wav *wav, const char *path, char *error,
                  size_t error_size) {
    unsigned char header[12];
    unsigned char chunk[8];
    struct stat st;
    bool got_fmt = false, got_data = false;
    off_t data_offset = 0;
    uint64_t data_bytes = 0;
    uint64_t riff_end, cursor;
    int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        set_error(error, error_size, "cannot open WAV: %s", strerror(errno));
        return -1;
    }
    if (fstat(fd, &st) < 0 || !S_ISREG(st.st_mode)) {
        set_error(error, error_size, "WAV must be a regular file");
        (void)close(fd);
        return -1;
    }
    if (read_exact(fd, header, sizeof(header)) < 0 ||
        memcmp(header, "RIFF", 4) != 0 || memcmp(header + 8, "WAVE", 4) != 0) {
        set_error(error, error_size, "WAV must start with RIFF/WAVE");
        (void)close(fd);
        return -1;
    }
    riff_end = (uint64_t)le32(header + 4) + 8U;
    if (riff_end < sizeof(header) || (uint64_t)st.st_size != riff_end) {
        set_error(error, error_size, "WAV RIFF length must match the file");
        (void)close(fd);
        return -1;
    }
    cursor = sizeof(header);
    while (cursor < riff_end) {
        uint32_t length;
        off_t body;
        uint64_t padded_length;
        if (riff_end - cursor < sizeof(chunk) ||
            read_exact(fd, chunk, sizeof(chunk)) < 0) {
            set_error(error, error_size, "WAV has a truncated chunk header");
            (void)close(fd);
            return -1;
        }
        cursor += sizeof(chunk);
        length = le32(chunk + 4);
        body = lseek(fd, 0, SEEK_CUR);
        padded_length = (uint64_t)length + (uint64_t)(length & 1U);
        if (body < 0 || padded_length > riff_end - cursor) {
            set_error(error, error_size, "WAV chunk exceeds file bounds");
            (void)close(fd);
            return -1;
        }
        if (memcmp(chunk, "fmt ", 4) == 0) {
            unsigned char fmt[16];
            if (got_fmt || length < sizeof(fmt) || read_exact(fd, fmt, sizeof(fmt)) < 0 ||
                le16(fmt) != 1 || le16(fmt + 2) != 2 || le32(fmt + 4) != 48000 ||
                le32(fmt + 8) != 192000 || le16(fmt + 12) != 4 || le16(fmt + 14) != 16) {
                set_error(error, error_size, "WAV must be PCM16 stereo 48000 Hz");
                (void)close(fd);
                return -1;
            }
            got_fmt = true;
        } else if (memcmp(chunk, "data", 4) == 0) {
            if (got_data || length % CORE_FRAME_BYTES != 0) {
                set_error(error, error_size, "WAV data must contain whole stereo frames");
                (void)close(fd);
                return -1;
            }
            data_offset = body;
            data_bytes = length;
            got_data = true;
        }
        if (lseek(fd, body + (off_t)padded_length, SEEK_SET) < 0) {
            set_error(error, error_size, "cannot seek WAV: %s", strerror(errno));
            (void)close(fd);
            return -1;
        }
        cursor += padded_length;
    }
    if (!got_fmt || !got_data || data_bytes == 0 ||
        lseek(fd, data_offset, SEEK_SET) < 0) {
        set_error(error, error_size, "WAV lacks valid fmt/data chunks");
        (void)close(fd);
        return -1;
    }
    wav->fd = fd;
    wav->data_offset = data_offset;
    wav->data_bytes = data_bytes;
    wav->position_frames = 0;
    return 0;
}

int core_rewind_wav(struct core_wav *wav, char *error, size_t error_size) {
    if (lseek(wav->fd, wav->data_offset, SEEK_SET) < 0) {
        set_error(error, error_size, "cannot rewind WAV: %s", strerror(errno));
        return -1;
    }
    wav->position_frames = 0;
    return 0;
}

int core_read_frames(struct core_wav *wav, int16_t *samples, size_t frames,
                     char *error, size_t error_size) {
    uint64_t total = wav->data_bytes / CORE_FRAME_BYTES;
    size_t wanted;
    size_t bytes;
    ssize_t got;
    if (wav->position_frames >= total) {
        return 0;
    }
    wanted = frames;
    if ((uint64_t)wanted > total - wav->position_frames) {
        wanted = (size_t)(total - wav->position_frames);
    }
    bytes = wanted * CORE_FRAME_BYTES;
    do {
        got = read(wav->fd, samples, bytes);
    } while (got < 0 && errno == EINTR);
    if (got <= 0 || ((size_t)got % CORE_FRAME_BYTES) != 0) {
        set_error(error, error_size, "cannot read WAV frames: %s",
                  got == 0 ? "unexpected EOF" : strerror(errno));
        return -1;
    }
    wav->position_frames += (uint64_t)got / CORE_FRAME_BYTES;
    return (int)((size_t)got / CORE_FRAME_BYTES);
}

void core_scale_pcm(int16_t *samples, size_t frames, unsigned volume) {
    size_t values = frames * 2U;
    for (size_t i = 0; i < values; ++i) {
        int32_t value = (int32_t)samples[i] * (int32_t)volume;
        samples[i] = (int16_t)(value / 100);
    }
}

void core_close_wav(struct core_wav *wav) {
    if (wav->fd >= 0) {
        (void)close(wav->fd);
        wav->fd = -1;
    }
}
