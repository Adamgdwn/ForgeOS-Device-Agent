/*
 * Narrow armhf ALSA SYNC_PTR time64 compatibility interposer for Linux 3.10.
 * Older kernels match the full ioctl value, so only the 136-byte request is
 * retried as its 132-byte legacy counterpart after ENOTTY.
 */
#include <stdarg.h>

/* The armhf service loader supplies these glibc symbols; avoid host headers
 * because the deliberate -nostdlib cross-build has no armhf sysroot. */
extern void *dlsym(void *, const char *);
extern int *__errno_location(void);
typedef unsigned int forge_u32;
#define FORGE_RTLD_NEXT ((void *)-1l)
#define FORGE_ERRNO (*__errno_location())
#define FORGE_EFAULT 14
#define FORGE_ENOTTY 25
#define FORGE_ENOSYS 38

#if !defined(FORGE_ALSA_COMPAT_TEST)
#if !defined(__arm__) || !defined(__BYTE_ORDER__) || (__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__)
#error "forge-alsa-compat is only for little-endian ARM32"
#endif
#endif

enum {
    FORGE_SYNC_PTR_TIME64 = 0xc0884123UL,
    FORGE_SYNC_PTR_LEGACY = 0xc0844123UL,
    FORGE_TIME64_WORDS = 34,
    FORGE_LEGACY_WORDS = 33,
    FORGE_UNION_WORDS = 16,
};

_Static_assert(sizeof(forge_u32) == 4, "uapi words must be 32-bit");
_Static_assert(FORGE_TIME64_WORDS * sizeof(forge_u32) == 136, "time64 ABI size");
_Static_assert(FORGE_LEGACY_WORDS * sizeof(forge_u32) == 132, "legacy ABI size");

typedef int (*forge_ioctl_fn)(int, unsigned long, void *);

#ifdef FORGE_ALSA_COMPAT_TEST
extern int forge_alsa_compat_test_ioctl(int, unsigned long, void *);
static forge_ioctl_fn resolve_ioctl(void) { return forge_alsa_compat_test_ioctl; }
#else
static forge_ioctl_fn resolve_ioctl(void) {
    /* The Debian armhf library imports this glibc symbol, not ioctl.
     * Avoid mutable lazy initialization: Chromium has multiple audio threads. */
    return (forge_ioctl_fn)dlsym(FORGE_RTLD_NEXT, "__ioctl_time64");
}
#endif

static forge_u32 sign_extend_seconds(forge_u32 seconds) {
    return (seconds & 0x80000000U) ? 0xffffffffU : 0U;
}

static void to_legacy(forge_u32 legacy[FORGE_LEGACY_WORDS],
                      const forge_u32 current[FORGE_TIME64_WORDS]) {
    for (unsigned int index = 0; index < FORGE_LEGACY_WORDS; ++index)
        legacy[index] = 0;
    legacy[0] = current[0];
    legacy[1] = current[2];
    legacy[2] = current[3];
    legacy[3] = current[4];
    legacy[4] = current[6];
    legacy[5] = current[8];
    legacy[6] = current[10];
    legacy[7] = current[12];
    legacy[8] = current[14];
    for (unsigned int index = 0; index < FORGE_UNION_WORDS; ++index)
        legacy[17 + index] = current[18 + index];
}

static void from_legacy(forge_u32 current[FORGE_TIME64_WORDS],
                        const forge_u32 legacy[FORGE_LEGACY_WORDS]) {
    current[0] = legacy[0];
    current[2] = legacy[1];
    current[3] = legacy[2];
    current[4] = legacy[3];
    current[6] = legacy[4];
    current[7] = sign_extend_seconds(legacy[4]);
    current[8] = legacy[5];
    current[9] = 0;
    current[10] = legacy[6];
    current[12] = legacy[7];
    current[13] = sign_extend_seconds(legacy[7]);
    current[14] = legacy[8];
    current[15] = 0;
    for (unsigned int index = 0; index < FORGE_UNION_WORDS; ++index)
        current[18 + index] = legacy[17 + index];
}

int forge_alsa_compat_ioctl(int fd, unsigned long request, void *argument) {
    int incoming_errno = FORGE_ERRNO;
    forge_ioctl_fn real_ioctl = resolve_ioctl();
    if (real_ioctl == 0) {
        FORGE_ERRNO = FORGE_ENOSYS;
        return -1;
    }
    if (request != FORGE_SYNC_PTR_TIME64)
        return real_ioctl(fd, request, argument);
    if (argument == 0) {
        FORGE_ERRNO = FORGE_EFAULT;
        return -1;
    }

    int result = real_ioctl(fd, request, argument);
    if (result != -1 || FORGE_ERRNO != FORGE_ENOTTY)
        return result;

    forge_u32 legacy[FORGE_LEGACY_WORDS];
    to_legacy(legacy, argument);
    result = real_ioctl(fd, FORGE_SYNC_PTR_LEGACY, legacy);
    if (result == 0) {
        from_legacy(argument, legacy);
        FORGE_ERRNO = incoming_errno;
    }
    return result;
}

#ifndef FORGE_ALSA_COMPAT_TEST
int __ioctl_time64(int fd, unsigned long request, ...) {
    void *argument;
    va_list arguments;
    va_start(arguments, request);
    argument = va_arg(arguments, void *);
    va_end(arguments);
    return forge_alsa_compat_ioctl(fd, request, argument);
}
#endif
