#ifndef FORGE_BROWSER_SURFACE_H
#define FORGE_BROWSER_SURFACE_H

/* Transient Xvfb monitor surface.  It intentionally has no capture or log API.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
#ifndef SOCK_CLOEXEC
#define SOCK_CLOEXEC 0
#endif

typedef struct {
  unsigned width, height;
  int fd, xfd;
  const unsigned char *map;
  size_t map_size, image, line;
  unsigned source_width, source_height;
  int source_little, x_opcode;
  uint32_t root;
  uint16_t sequence;
  unsigned char min_key, max_key, keysyms_per_key;
  uint32_t keysyms[256][2];
} ForgeSurface;

#define FORGE_SURFACE_INIT                                                     \
  { .fd = -1, .xfd = -1 }

static inline uint32_t forge_surface_be32(const unsigned char *p) {
  return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
         ((uint32_t)p[2] << 8) | p[3];
}
static inline uint16_t forge_surface_le16(const unsigned char *p) {
  return (uint16_t)(p[0] | ((uint16_t)p[1] << 8));
}
static inline uint32_t forge_surface_le32(const unsigned char *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
         ((uint32_t)p[3] << 24);
}
static inline void forge_surface_put16(unsigned char *p, uint16_t x) {
  p[0] = (unsigned char)x;
  p[1] = (unsigned char)(x >> 8);
}
static inline void forge_surface_put32(unsigned char *p, uint32_t x) {
  p[0] = (unsigned char)x;
  p[1] = (unsigned char)(x >> 8);
  p[2] = (unsigned char)(x >> 16);
  p[3] = (unsigned char)(x >> 24);
}

static inline int64_t forge_surface_now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
static inline int forge_surface_io_until(int fd, void *buf, size_t n,
                                         int writing, int64_t deadline) {
  unsigned char *p = buf;
  while (n) {
    int left = (int)(deadline - forge_surface_now());
    if (left <= 0) {
      errno = ETIMEDOUT;
      return -1;
    }
    struct pollfd q = {.fd = fd, .events = writing ? POLLOUT : POLLIN};
    int r = poll(&q, 1, left);
    if (r < 0 && errno == EINTR)
      continue;
    if (r <= 0) {
      if (!r)
        errno = ETIMEDOUT;
      return -1;
    }
    ssize_t z = writing ? send(fd, p, n, MSG_NOSIGNAL) : read(fd, p, n);
    if (z < 0 && (errno == EINTR || errno == EAGAIN))
      continue;
    if (z <= 0) {
      if (!z)
        errno = EPIPE;
      return -1;
    }
    p += (size_t)z;
    n -= (size_t)z;
  }
  return 0;
}
static inline int forge_surface_io(int fd, void *buf, size_t n, int writing) {
  return forge_surface_io_until(fd, buf, n, writing, forge_surface_now() + 350);
}
static inline int forge_surface_reply(ForgeSurface *s, unsigned char reply[32],
                                      unsigned char *extra, size_t cap) {
  int64_t deadline = forge_surface_now() + 500;
  for (unsigned packets = 0; packets < 16; packets++) {
    uint64_t bytes;
    if (forge_surface_io_until(s->xfd, reply, 32, 0, deadline) < 0)
      return -1;
    if (reply[0] == 1) {
      bytes = (uint64_t)forge_surface_le32(reply + 4) * 4U;
      if (bytes > cap || bytes > 16384U) {
        errno = EOVERFLOW;
        return -1;
      }
      if (forge_surface_le16(reply + 2) != s->sequence) {
        errno = EPROTO;
        return -1;
      }
      return bytes ? forge_surface_io_until(s->xfd, extra, (size_t)bytes, 0,
                                            deadline)
                   : 0;
    }
    if (reply[0] == 0) {
      errno = EPROTO;
      return -1;
    } /* errors never masquerade as replies */
    /* Core events are 32 bytes. No generic extension events were selected. */
    if ((reply[0] & 127) == 35) {
      errno = EPROTO;
      return -1;
    }
  }
  errno = EOVERFLOW;
  return -1;
}
static inline int forge_surface_request_reply(ForgeSurface *s,
                                              const void *request, size_t size,
                                              unsigned char reply[32],
                                              unsigned char *extra,
                                              size_t cap) {
  if (forge_surface_io(s->xfd, (void *)request, size, 1) < 0)
    return -1;
  s->sequence++;
  return forge_surface_reply(s, reply, extra, cap);
}
static inline int forge_surface_fake(ForgeSurface *s, unsigned type,
                                     unsigned detail, int x, int y) {
  unsigned char r[36] = {0};
  if (s->xfd < 0 || s->x_opcode <= 0) {
    errno = ENOTCONN;
    return -1;
  }
  r[0] = (unsigned char)s->x_opcode;
  r[1] = 2;
  forge_surface_put16(r + 2, 9);
  r[4] = (unsigned char)type;
  r[5] = (unsigned char)detail;
  forge_surface_put32(r + 12, s->root);
  forge_surface_put16(r + 24, (uint16_t)x);
  forge_surface_put16(r + 26, (uint16_t)y);
  int result = forge_surface_io(s->xfd, r, sizeof r, 1);
  if (!result)
    s->sequence++;
  return result;
}
static inline int forge_surface_connect(ForgeSurface *s, const char *path) {
  struct sockaddr_un addr;
  unsigned char hello[12] = {'l', 0, 11, 0}, prefix[8], *setup = NULL,
                reply[32], extra[8192];
  size_t setup_bytes, root_at, formats;
  unsigned char request[16] = {98, 0,   4,   0,   5,   0,  0,
                               0,  'X', 'T', 'E', 'S', 'T'};
  if (!path || strlen(path) >= sizeof addr.sun_path) {
    errno = ENAMETOOLONG;
    return -1;
  }
  s->xfd = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC | SOCK_NONBLOCK, 0);
  if (s->xfd < 0)
    return -1;
  memset(&addr, 0, sizeof addr);
  addr.sun_family = AF_UNIX;
  memcpy(addr.sun_path, path, strlen(path) + 1);
  if (connect(s->xfd, (struct sockaddr *)&addr, sizeof addr) < 0) {
    if (errno != EINPROGRESS && errno != EAGAIN)
      goto fail;
    struct pollfd q = {.fd = s->xfd, .events = POLLOUT};
    int error = 0;
    socklen_t count = sizeof error;
    if (poll(&q, 1, 350) <= 0 ||
        getsockopt(s->xfd, SOL_SOCKET, SO_ERROR, &error, &count) || error)
      goto fail;
  }
  if (forge_surface_io(s->xfd, hello, sizeof hello, 1) < 0 ||
      forge_surface_io(s->xfd, prefix, sizeof prefix, 0) < 0)
    goto fail;
  setup_bytes = forge_surface_le16(prefix + 6) * 4U;
  if (prefix[0] != 1 || setup_bytes < 32 || setup_bytes > 4096) {
    errno = EPROTO;
    goto fail;
  }
  setup = malloc(setup_bytes);
  if (!setup || forge_surface_io(s->xfd, setup, setup_bytes, 0) < 0)
    goto fail;
  formats = setup[21];
  root_at = 32U + ((forge_surface_le16(setup + 16) + 3U) & ~3U) + formats * 8U;
  if (!setup[20] || root_at + 4 > setup_bytes) {
    errno = EPROTO;
    goto fail;
  }
  s->root = forge_surface_le32(setup + root_at);
  s->min_key = setup[26];
  s->max_key = setup[27];
  if (s->min_key < 8 || s->max_key < s->min_key) {
    errno = EPROTO;
    goto fail;
  }
  free(setup);
  setup = NULL;
  if (forge_surface_request_reply(s, request, 16, reply, extra, sizeof extra) <
          0 ||
      !reply[8] || !reply[9]) {
    errno = EPROTONOSUPPORT;
    goto fail;
  }
  s->x_opcode = reply[9];
  {
    unsigned char keys[8] = {
        101, 0, 2, 0, s->min_key, (unsigned char)(s->max_key - s->min_key + 1U),
        0,   0};
    size_t n, i;
    if (forge_surface_request_reply(s, keys, sizeof keys, reply, extra,
                                    sizeof extra) < 0)
      goto fail;
    s->keysyms_per_key = reply[1];
    n = (size_t)(s->max_key - s->min_key + 1U) * s->keysyms_per_key;
    if (!s->keysyms_per_key || n * 4U > sizeof extra ||
        forge_surface_le32(reply + 4) != (uint32_t)n) {
      errno = EOVERFLOW;
      goto fail;
    }
    for (i = 0; i < n && i / s->keysyms_per_key < 256; i++)
      if (i % s->keysyms_per_key < 2)
        s->keysyms[i / s->keysyms_per_key][i % s->keysyms_per_key] =
            forge_surface_le32(extra + i * 4U);
  }
  return 0;
fail:
  free(setup);
  close(s->xfd);
  s->xfd = -1;
  return -1;
}

static inline int forge_surface_open(ForgeSurface *s, const char *xwd_path,
                                     const char *x11_socket) {
  struct stat st;
  unsigned char h[100];
  size_t image, pixels;
  if (!s || !xwd_path || !x11_socket) {
    errno = EINVAL;
    return -1;
  }
  *s = (ForgeSurface)FORGE_SURFACE_INIT;
  s->fd = open(xwd_path, O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
  if (s->fd < 0)
    return -1;
  if (fstat(s->fd, &st) < 0 || !S_ISREG(st.st_mode) ||
      st.st_size < (off_t)sizeof h || st.st_size > 32 * 1024 * 1024 ||
      forge_surface_io(s->fd, h, sizeof h, 0) < 0)
    goto fail;
  s->source_width = forge_surface_be32(h + 16);
  s->source_height = forge_surface_be32(h + 20);
  s->line = forge_surface_be32(h + 48);
  s->source_little = forge_surface_be32(h + 28) == 0;
  image = (size_t)forge_surface_be32(h);
  uint64_t offset = (uint64_t)image + (uint64_t)forge_surface_be32(h + 76) * 12;
  if (offset > SIZE_MAX || offset > (uint64_t)st.st_size) {
    errno = EPROTO;
    goto fail;
  }
  pixels = (size_t)offset;
  if (forge_surface_be32(h + 4) != 7 || forge_surface_be32(h + 12) != 24 ||
      forge_surface_be32(h + 28) > 1 || forge_surface_be32(h + 8) != 2 ||
      forge_surface_be32(h + 44) != 32 || forge_surface_be32(h + 52) != 4 ||
      s->source_width == 0 || s->source_height == 0 || s->source_width > 2048 ||
      s->source_height > 2048 || forge_surface_be32(h + 56) != 0xff0000 ||
      forge_surface_be32(h + 60) != 0xff00 ||
      forge_surface_be32(h + 64) != 0xff || image < 100 || pixels < image ||
      s->line < (size_t)s->source_width * 4U ||
      s->line > (size_t)s->source_width * 4 + 256 ||
      s->source_height > (SIZE_MAX - pixels) / s->line ||
      pixels + s->source_height * s->line > (size_t)st.st_size) {
    errno = EPROTO;
    goto fail;
  }
  s->map_size = (size_t)st.st_size;
  s->map = mmap(NULL, s->map_size, PROT_READ, MAP_PRIVATE, s->fd, 0);
  if (s->map == MAP_FAILED) {
    s->map = NULL;
    goto fail;
  }
  s->image = pixels;
  s->width = s->source_width;
  s->height = s->source_height;
  if (forge_surface_connect(s, x11_socket) < 0)
    goto fail;
  return 0;
fail: {
  int saved = errno;
  if (s->map)
    munmap((void *)s->map, s->map_size);
  if (s->fd >= 0)
    close(s->fd);
  *s = (ForgeSurface)FORGE_SURFACE_INIT;
  errno = saved;
  return -1;
}
}
static inline int forge_surface_draw(ForgeSurface *s, uint32_t *rgb,
                                     size_t stride, unsigned width,
                                     unsigned height) {
  unsigned y, x;
  if (!s || !s->map || !rgb || !width || !height || width > 2048 ||
      height > 2048 || stride < width) {
    errno = EINVAL;
    return -1;
  }
  if (s->source_width == width && s->source_height == height) {
    for (y = 0; y < height; y++) {
      const unsigned char *p = s->map + s->image + (size_t)y * s->line;
      uint32_t *out = rgb + (size_t)y * stride;
      for (x = 0; x < width; x++, p += 4U) {
        uint32_t v =
            s->source_little ? forge_surface_le32(p) : forge_surface_be32(p);
        out[x] = v & 0x00ffffffU;
      }
    }
    return 0;
  }
  for (y = 0; y < height; y++)
    for (x = 0; x < width; x++) {
      const unsigned char *p =
          s->map + s->image +
          (size_t)(y * s->source_height / height) * s->line +
          (size_t)(x * s->source_width / width) * 4U;
      uint32_t v =
          s->source_little ? forge_surface_le32(p) : forge_surface_be32(p);
      rgb[(size_t)y * stride + x] = v & 0x00ffffffU;
    }
  return 0;
}
static inline int forge_surface_click(ForgeSurface *s, int x, int y) {
  return forge_surface_fake(s, 6, 0, x, y) ||
                 forge_surface_fake(s, 4, 1, x, y) ||
                 forge_surface_fake(s, 5, 1, x, y)
             ? -1
             : 0;
}
static inline int forge_surface_scroll(ForgeSurface *s, int direction) {
  unsigned b = direction < 0 ? 4U : direction > 0 ? 5U : 0U;
  if (!b) {
    errno = EINVAL;
    return -1;
  }
  return forge_surface_fake(s, 4, b, 0, 0) || forge_surface_fake(s, 5, b, 0, 0)
             ? -1
             : 0;
}
static inline int forge_surface_key(ForgeSurface *s, uint32_t keysym) {
  unsigned code = 0, shift = 0;
  int shifted = 0;
  for (unsigned i = 0; i <= (unsigned)(s->max_key - s->min_key) && i < 256;
       i++) {
    if (s->keysyms[i][0] == 0xffe1)
      shift = s->min_key + i;
    for (unsigned level = 0; level < 2; level++)
      if (!code && s->keysyms[i][level] == keysym) {
        code = s->min_key + i;
        shifted = level != 0;
      }
  }
  if (!code || (shifted && !shift)) {
    errno = EINVAL;
    return -1;
  }
  int result = 0;
  if (shifted && forge_surface_fake(s, 2, shift, 0, 0))
    result = -1;
  if (!result && forge_surface_fake(s, 2, code, 0, 0))
    result = -1;
  if (forge_surface_fake(s, 3, code, 0, 0))
    result = -1;
  if (shifted && forge_surface_fake(s, 3, shift, 0, 0))
    result = -1;
  return result;
}
/* Switch between the fixed music and dashboard tabs without URL/script input. */
static inline int forge_surface_tab(ForgeSurface *s, unsigned tab) {
  unsigned control=0;
  if(tab<1||tab>2){errno=EINVAL;return -1;}
  for(unsigned i=0;i<=(unsigned)(s->max_key-s->min_key)&&i<256;i++)
    if(s->keysyms[i][0]==0xffe3){control=s->min_key+i;break;}
  if(!control){errno=EINVAL;return -1;}
  /* Chromium's restore/password bubbles can retain an input grab even when
   * another page is activated. Leaving a Forge section dismisses that popup. */
  int result=forge_surface_key(s,0xff1b);
  if(!result)result=forge_surface_fake(s,2,control,0,0);
  if(!result)result=forge_surface_key(s,'0'+tab);
  if(forge_surface_fake(s,3,control,0,0))result=-1;
  return result;
}
static inline void forge_surface_close(ForgeSurface *s) {
  if (!s)
    return;
  if (s->map)
    munmap((void *)s->map, s->map_size);
  if (s->fd >= 0)
    close(s->fd);
  if (s->xfd >= 0)
    close(s->xfd);
  *s = (ForgeSurface)FORGE_SURFACE_INIT;
}

#endif
