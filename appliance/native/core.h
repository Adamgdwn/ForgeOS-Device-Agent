#ifndef FORGEOS_APPLIANCE_CORE_H
#define FORGEOS_APPLIANCE_CORE_H

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

enum { CORE_FRAME_BYTES = 4, CORE_TICK_FRAMES = 960 };

struct core_wav {
    int fd;
    off_t data_offset;
    uint64_t data_bytes;
    uint64_t position_frames;
};

int core_open_wav(struct core_wav *wav, const char *path, char *error,
                  size_t error_size);
int core_rewind_wav(struct core_wav *wav, char *error, size_t error_size);
/* Returns frames read, zero at EOF, or -1 on error. */
int core_read_frames(struct core_wav *wav, int16_t *samples, size_t frames,
                     char *error, size_t error_size);
void core_scale_pcm(int16_t *samples, size_t frames, unsigned volume);
void core_close_wav(struct core_wav *wav);

#endif
