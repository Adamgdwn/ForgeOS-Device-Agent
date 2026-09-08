/* Forge's local music session. The browser owns service playback; this process
 * owns bounded control requests, revisions, and cached state for the panel. */
#define _GNU_SOURCE
#include "bridge_json.h"
#include "music_bridge_ui_maintenance.h"
#include "music_bridge_queue_maintenance.h"
#include <arpa/inet.h>
#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

enum { LIMIT = 16384, IO_MS = 1000, CLIENTS = 8 };
static volatile sig_atomic_t stopping;
static int64_t mono(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}
/* Only the single browser worker performs CDP IO. One absolute budget spans
 * connect, discovery, command dispatch and read-only confirmation polls. */
static int64_t worker_deadline;
static int64_t io_deadline(void) {
  int64_t deadline = mono() + IO_MS;
  return worker_deadline && worker_deadline < deadline ? worker_deadline : deadline;
}
static void on_signal(int sig) {
  (void)sig;
  stopping = 1;
}
static int random_bytes(void *buf, size_t n) {
  int fd = open("/dev/urandom", O_RDONLY | O_CLOEXEC);
  if (fd < 0)
    return -1;
  size_t done = 0;
  while (done < n) {
    ssize_t k = read(fd, (char *)buf + done, n - done);
    if (k > 0)
      done += (size_t)k;
    else if (k < 0 && errno == EINTR)
      continue;
    else
      break;
  }
  close(fd);
  return done == n ? 0 : -1;
}
static int transfer(int fd, void *buf, size_t n, bool sending,
                    int64_t deadline) {
  size_t done = 0;
  while (done < n && !stopping) {
    int left = (int)(deadline - mono());
    if (left <= 0)
      return -1;
    struct pollfd p = {fd, sending ? POLLOUT : POLLIN, 0};
    int r = poll(&p, 1, left);
    if (r < 0 && errno == EINTR)
      continue;
    if (r <= 0)
      return -1;
    ssize_t k = sending ? send(fd, (char *)buf + done, n - done, MSG_NOSIGNAL)
                        : recv(fd, (char *)buf + done, n - done, 0);
    if (k > 0)
      done += (size_t)k;
    else if (k < 0 && (errno == EINTR || errno == EAGAIN))
      continue;
    else
      return -1;
  }
  return done == n ? 0 : -1;
}
static int tcp_open(unsigned port) {
  int fd = socket(AF_INET, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  if (fd < 0)
    return -1;
  struct sockaddr_in a = {.sin_family = AF_INET,
                          .sin_port = htons((uint16_t)port),
                          .sin_addr = {htonl(INADDR_LOOPBACK)}};
  if (connect(fd, (struct sockaddr *)&a, sizeof a) < 0) {
    if (errno != EINPROGRESS) {
      close(fd);
      return -1;
    }
    struct pollfd p = {fd, POLLOUT, 0};
    int error = 0;
    socklen_t size = sizeof error;
    int remaining = (int)(io_deadline() - mono());
    if (remaining <= 0 || poll(&p, 1, remaining) <= 0 ||
        getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &size) || error) {
      close(fd);
      return -1;
    }
  }
  return fd;
}
static int http_header(int fd, char *out, size_t cap, int64_t deadline) {
  size_t n = 0;
  while (n + 1 < cap) {
    if (transfer(fd, out + n, 1, false, deadline))
      return -1;
    n++;
    out[n] = 0;
    if (n >= 4 && !memcmp(out + n - 4, "\r\n\r\n", 4))
      return 0;
  }
  return -1;
}
static int header_value(const char *header, const char *name, char *out,
                        size_t cap) {
  size_t n = strlen(name);
  const char *p = strstr(header, "\r\n");
  while (p && p[2]) {
    p += 2;
    const char *end = strstr(p, "\r\n");
    if (!end)
      return -1;
    if (!strncasecmp(p, name, n) && p[n] == ':') {
      p += n + 1;
      while (p < end && (*p == ' ' || *p == '\t'))
        p++;
      size_t length = (size_t)(end - p);
      if (length >= cap)
        return -1;
      memcpy(out, p, length);
      out[length] = 0;
      return 0;
    }
    p = end;
  }
  return -1;
}
static bool origin_ok(const char *s) {
  const char *base = "https://music.youtube.com";
  size_t n = strlen(base);
  return !strncmp(s, base, n) &&
         (s[n] == 0 || s[n] == '/' || s[n] == '?' || s[n] == '#');
}
static int cdp_path(unsigned port, char *path, size_t cap) {
  int fd = tcp_open(port);
  if (fd < 0)
    return -1;
  int result = -1;
  char request[256], header[2048], body[LIMIT], length[32];
  int count = snprintf(request, sizeof request,
                       "GET /json/list HTTP/1.1\r\nHost: "
                       "127.0.0.1:%u\r\nConnection: close\r\n\r\n",
                       port);
  int64_t deadline = io_deadline();
  if (count < 0 || transfer(fd, request, (size_t)count, true, deadline) ||
      http_header(fd, header, sizeof header, deadline) ||
      strncmp(header, "HTTP/1.1 200 ", 13) ||
      header_value(header, "Content-Length", length, sizeof length))
    goto done;
  char *end;
  errno = 0;
  unsigned long bytes = strtoul(length, &end, 10);
  if (errno || *end || !bytes || bytes >= sizeof body ||
      transfer(fd, body, bytes, false, deadline))
    goto done;
  body[bytes] = 0;
  Json json;
  if (jparse(&json, body) || json.t[0].kind != '[')
    goto done;
  unsigned eligible = 0;
  char selected[256] = {0};
  for (int at = 1; at < json.t[0].next; at = json.t[at].next) {
    char type[32], url[2048], ws[256];
    if (jstring(&json, jkey(&json, at, "type"), type, sizeof type) ||
        strcmp(type, "page") ||
        jstring(&json, jkey(&json, at, "url"), url, sizeof url) ||
        !origin_ok(url) ||
        jstring(&json, jkey(&json, at, "webSocketDebuggerUrl"), ws, sizeof ws))
      continue;
    char prefix[64];
    snprintf(prefix, sizeof prefix, "ws://127.0.0.1:%u/devtools/page/", port);
    if (strncmp(ws, prefix, strlen(prefix)))
      continue;
    const char *slash = strchr(ws + 5, '/');
    if (!slash || strlen(slash) >= cap)
      continue;
    bool safe = true;
    for (const char *p = slash; *p; p++)
      if (!isalnum((unsigned char)*p) && !strchr("/_-", *p))
        safe = false;
    if (!safe)
      continue;
    if (++eligible != 1)
      goto done;
    strcpy(selected, slash);
  }
  if (eligible == 1) {
    strcpy(path, selected);
    result = 0;
  }
done:
  close(fd);
  return result;
}
/* SHA-1 and base64 are only used to validate the WebSocket handshake. */
struct sha {
  uint32_t h[5];
  uint64_t bits;
  unsigned char b[64];
  size_t n;
};
static uint32_t rol(uint32_t x, unsigned n) {
  return (x << n) | (x >> (32 - n));
}
static void sha_block(struct sha *s, const unsigned char *b) {
  uint32_t w[80], a, bv, c, d, e, t;
  for (unsigned i = 0; i < 16; i++)
    w[i] = (uint32_t)b[4 * i] << 24 | (uint32_t)b[4 * i + 1] << 16 |
           (uint32_t)b[4 * i + 2] << 8 | b[4 * i + 3];
  for (unsigned i = 16; i < 80; i++)
    w[i] = rol(w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16], 1);
  a = s->h[0];
  bv = s->h[1];
  c = s->h[2];
  d = s->h[3];
  e = s->h[4];
  for (unsigned i = 0; i < 80; i++) {
    uint32_t f, k;
    if (i < 20) {
      f = (bv & c) | (~bv & d);
      k = 0x5a827999;
    } else if (i < 40) {
      f = bv ^ c ^ d;
      k = 0x6ed9eba1;
    } else if (i < 60) {
      f = (bv & c) | (bv & d) | (c & d);
      k = 0x8f1bbcdc;
    } else {
      f = bv ^ c ^ d;
      k = 0xca62c1d6;
    }
    t = rol(a, 5) + f + e + k + w[i];
    e = d;
    d = c;
    c = rol(bv, 30);
    bv = a;
    a = t;
  }
  s->h[0] += a;
  s->h[1] += bv;
  s->h[2] += c;
  s->h[3] += d;
  s->h[4] += e;
}
static void sha_add(struct sha *s, const void *p, size_t n) {
  const unsigned char *q = p;
  s->bits += (uint64_t)n * 8;
  while (n) {
    size_t z = 64 - s->n;
    if (z > n)
      z = n;
    memcpy(s->b + s->n, q, z);
    s->n += z;
    q += z;
    n -= z;
    if (s->n == 64) {
      sha_block(s, s->b);
      s->n = 0;
    }
  }
}
/* A compact independent finalizer avoids padding changing the recorded length.
 */
static void sha_digest(const void *p, size_t n, unsigned char out[20]) {
  struct sha s = {
      {0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0}, 0, {0}, 0};
  uint64_t bits = (uint64_t)n * 8;
  unsigned char x = 0x80, zero = 0, tail[8];
  sha_add(&s, p, n);
  sha_add(&s, &x, 1);
  while (s.n != 56)
    sha_add(&s, &zero, 1);
  for (unsigned i = 0; i < 8; i++)
    tail[7 - i] = (unsigned char)(bits >> (8 * i));
  sha_add(&s, tail, 8);
  for (unsigned i = 0; i < 5; i++)
    for (unsigned j = 0; j < 4; j++)
      out[i * 4 + j] = (unsigned char)(s.h[i] >> (24 - 8 * j));
}
static void b64(const unsigned char *p, size_t n, char *out) {
  static const char a[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  size_t r = 0;
  for (size_t i = 0; i < n; i += 3) {
    unsigned v = (unsigned)p[i] << 16 |
                 (i + 1 < n ? (unsigned)p[i + 1] << 8 : 0) |
                 (i + 2 < n ? p[i + 2] : 0);
    out[r++] = a[v >> 18];
    out[r++] = a[v >> 12 & 63];
    out[r++] = i + 1 < n ? a[v >> 6 & 63] : '=';
    out[r++] = i + 2 < n ? a[v & 63] : '=';
  }
  out[r] = 0;
}
static int ws_open(unsigned port, const char *path) {
  unsigned char random[16], digest[20];
  char key[32], expected[32], input[96], request[512], header[2048], accept[64],
      upgrade[32];
  if (random_bytes(random, sizeof random))
    return -1;
  b64(random, sizeof random, key);
  snprintf(input, sizeof input, "%s258EAFA5-E914-47DA-95CA-C5AB0DC85B11", key);
  sha_digest(input, strlen(input), digest);
  b64(digest, sizeof digest, expected);
  int fd = tcp_open(port);
  if (fd < 0)
    return -1;
  int n = snprintf(request, sizeof request,
                   "GET %s HTTP/1.1\r\nHost: 127.0.0.1:%u\r\nUpgrade: "
                   "websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Version: "
                   "13\r\nSec-WebSocket-Key: %s\r\n\r\n",
                   path, port, key);
  int64_t deadline = io_deadline();
  if (n < 0 || n >= (int)sizeof request ||
      transfer(fd, request, (size_t)n, true, deadline) ||
      http_header(fd, header, sizeof header, deadline) ||
      strncmp(header, "HTTP/1.1 101 ", 13) ||
      header_value(header, "Sec-WebSocket-Accept", accept, sizeof accept) ||
      strcmp(accept, expected) ||
      header_value(header, "Upgrade", upgrade, sizeof upgrade) ||
      strcasecmp(upgrade, "websocket")) {
    close(fd);
    return -1;
  }
  return fd;
}
static int ws_send(int fd, unsigned opcode, const void *data, size_t n,
                   int64_t deadline) {
  unsigned char frame[LIMIT + 8], mask[4];
  size_t p = 0;
  if (n > LIMIT || random_bytes(mask, 4))
    return -1;
  frame[p++] = (unsigned char)(0x80 | opcode);
  if (n < 126)
    frame[p++] = (unsigned char)(0x80 | n);
  else {
    frame[p++] = 0xfe;
    frame[p++] = (unsigned char)(n >> 8);
    frame[p++] = (unsigned char)n;
  }
  memcpy(frame + p, mask, 4);
  p += 4;
  for (size_t i = 0; i < n; i++)
    frame[p + i] = ((const unsigned char *)data)[i] ^ mask[i % 4];
  return transfer(fd, frame, p + n, true, deadline);
}
static int ws_message(int fd, char *out, size_t cap, int64_t deadline) {
  size_t used = 0;
  bool fragmented = false;
  for (int packets = 0; packets < 32; packets++) {
    unsigned char h[2], extended[8];
    if (transfer(fd, h, 2, false, deadline) || (h[0] & 0x70) || (h[1] & 0x80))
      return -1;
    unsigned opcode = h[0] & 15;
    bool final = (h[0] & 0x80) != 0;
    uint64_t n = h[1] & 127;
    if (n == 126) {
      if (transfer(fd, extended, 2, false, deadline))
        return -1;
      n = ((unsigned)extended[0] << 8) | extended[1];
    } else if (n == 127) {
      if (transfer(fd, extended, 8, false, deadline))
        return -1;
      n = 0;
      for (int k = 0; k < 8; k++)
        n = (n << 8) | extended[k];
    }
    if (opcode >= 8) {
      unsigned char payload[125];
      if (!final || n > 125 ||
          transfer(fd, payload, (size_t)n, false, deadline))
        return -1;
      if (opcode == 8)
        return -1;
      if (opcode == 9) {
        if (ws_send(fd, 10, payload, (size_t)n, deadline))
          return -1;
      } else if (opcode != 10)
        return -1;
      continue;
    }
    if ((!fragmented && opcode != 1) || (fragmented && opcode != 0) ||
        n >= cap - used || transfer(fd, out + used, (size_t)n, false, deadline))
      return -1;
    used += (size_t)n;
    if (final) {
      out[used] = 0;
      return memchr(out, 0, used) ? -1 : 0;
    }
    fragmented = true;
  }
  return -1;
}
static int evaluate(unsigned port, const char *expression, char *out,
                    size_t cap) {
  char path[256], quoted[8192], request[9000], response[LIMIT];
  if (cdp_path(port, path, sizeof path) ||
      (expression && jquote(expression, quoted, sizeof quoted)))
    return -1;
  int fd = ws_open(port, path);
  if (fd < 0)
    return -1;
  int result = -1;
  int n = expression ? snprintf(
      request, sizeof request,
      "{\"id\":1,\"method\":\"Runtime.evaluate\",\"params\":{\"expression\":%s,"
      "\"returnByValue\":true,\"awaitPromise\":true,\"userGesture\":true}}",
      quoted) : snprintf(request,sizeof request,"{\"id\":1,\"method\":\"Page.bringToFront\"}");
  int64_t deadline = io_deadline();
  if (n < 0 || n >= (int)sizeof request ||
      ws_send(fd, 1, request, (size_t)n, deadline))
    goto done;
  for (int events = 0; events < 16; events++) {
    if (ws_message(fd, response, sizeof response, deadline))
      break;
    Json json;
    if (jparse(&json, response))
      break;
    uint64_t id;
    int token = jkey(&json, 0, "id");
    if (token < 0)
      continue;
    if (juint(&json, token, &id) || id != 1)
      continue;
    int outer = jkey(&json, 0, "result");
    if (outer < 0 || jkey(&json, outer, "exceptionDetails") >= 0)
      break;
    if(!expression){result=0;break;}
    int inner = jkey(&json, outer, "result");
    char type[16];
    if (jstring(&json, jkey(&json, inner, "type"), type, sizeof type) ||
        strcmp(type, "string"))
      break;
    result = jstring(&json, jkey(&json, inner, "value"), out, cap);
    break;
  }
done:
  close(fd);
  return result;
}
struct view {
  uint64_t rev, pos;
  unsigned playing, volume;
  bool connected;
  char title[81], artist[81], output[81], status[16], video_id[12];
};
struct session {
  pthread_mutex_t lock;
  struct view view;
  unsigned port;
  bool stop, busy, processing, done;
  char action[16];
  unsigned volume;
  int outcome;
  bool outcome_observed;
  int64_t action_deadline;
};
static const char STATE[] =
    "(()=>{if(location.origin!=='https://music.youtube.com')throw "
    "Error('origin');const p=document.querySelector('#movie_player'),need="
    "['getPlayerState','getCurrentTime','getVolume','getVideoData','getOption'];if(!p||"
    "!need.every(k=>typeof p[k]==='function'))throw Error('player');const "
    "clean=s=>String(s||'').replace(/[^ -~]/g,' ').slice(0,80),data=p."
    "getVideoData()||{},state=p.getPlayerState(),time=Number(p.getCurrentTime()),volume=Number(p."
    "getVolume()),id=String(data.video_id||''),title=clean(data.title||'').trim();const casting=p.getOption('remote','casting');if(typeof "
    "casting!=='boolean')throw Error('output');let output='THIS TABLET';"
    "if(casting){output='CAST SPEAKERS';const r=p.getOption('remote',"
    "'currentReceiver'),name=clean(r&&r.name).trim();if(name)output=name}const errors=Array.from(document.querySelectorAll?document.querySelectorAll("
    "'.ytp-error-content-wrap,yt-playability-error-supported-renderers'):[]).slice(0,8).map(e=>({e,text:clean(e.textContent).trim()})).filter(x=>x.text&&"
    "(typeof x.e.checkVisibility==='function'?x.e.checkVisibility():x.e.offsetParent!==null));const error=errors.find(x=>/too many devices streaming|streaming on your plan right now/i.test(x.text));const status=error?'STREAM_LIMIT':errors.length?'PLAYER_ERROR':!id||!title?'CHOOSE':state===3?'BUFFERING':'READY';return "
    "[Number(state===1),Math.floor("
    "Number.isFinite(time)&&time>=0&&time<=86400?time*48000:0),Math.round("
    "Number.isFinite(volume)&&volume>=0&&volume<=100?volume:0),clean(data."
    "title||'SELECT A TRACK'),clean(data.author||'YOUTUBE MUSIC'),output,status,id]."
    "join('\t')})()";
/* An interrupted cold load can leave only bootstrap scripts and no app. Retry
 * that exact empty root page once; never reload a live player or sign-in form. */
static const char RECOVER_EMPTY[] =
    "(()=>{if(location.origin!=='https://music.youtube.com'||location.pathname!=='/'||"
    "document.readyState!=='complete'||!document.body||document.querySelector('ytmusic-app')||"
    "!Array.from(document.body.children).every(e=>e.tagName==='SCRIPT'||e.tagName==='NOSCRIPT'))"
    "return 'leave';setTimeout(()=>location.reload(),0);return 'retry'})()";
static int number(const char *s, uint64_t max, uint64_t *out) {
  if (!*s)
    return -1;
  uint64_t v = 0;
  for (; *s; s++) {
    if (*s < '0' || *s > '9' || v > (max - (unsigned)(*s - '0')) / 10 ||
        (unsigned)(*s - '0') > max)
      return -1;
    v = v * 10 + (unsigned)(*s - '0');
  }
  *out = v;
  return 0;
}
static int read_view(unsigned port, struct view *v) {
  char raw[512];
  if (evaluate(port, STATE, raw, sizeof raw))
    return -1;
  char *fields[8] = {raw};
  int n = 1;
  for (char *p = raw; *p; p++)
    if (*p == '\t') {
      *p = 0;
      if (n >= 8)
        return -1;
      fields[n++] = p + 1;
    }
  if (n != 6 && n != 7 && n != 8)
    return -1;
  uint64_t playing, pos, volume;
  if (number(fields[0], 1, &playing) || number(fields[1], UINT64_MAX, &pos) ||
      number(fields[2], 100, &volume) || strlen(fields[3]) > 80 ||
      strlen(fields[4]) > 80 || strlen(fields[5]) > 80 ||
      (n >= 7 && strlen(fields[6]) >= sizeof v->status) ||
      (n == 8 && (strlen(fields[7]) != 11 || strspn(fields[7], "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-") != 11)))
    return -1;
  for (int k = 3; k < n; k++)
    for (char *p = fields[k]; *p; p++)
      if ((unsigned char)*p < 32 || (unsigned char)*p > 126)
        return -1;
  v->playing = (unsigned)playing;
  v->pos = pos;
  v->volume = (unsigned)volume;
  strcpy(v->title, fields[3]);
  strcpy(v->artist, fields[4]);
  strcpy(v->output, fields[5]);
  strcpy(v->status, n < 7 ? "READY" : fields[6]);
  strcpy(v->video_id, n == 8 ? fields[7] : "");
  if (strcmp(v->status, "READY") && strcmp(v->status, "BUFFERING") &&
      strcmp(v->status, "CHOOSE") && strcmp(v->status, "STREAM_LIMIT") &&
      strcmp(v->status, "PLAYER_ERROR"))
    return -1;
  v->connected = true;
  return 0;
}
static const char ACTION_PREFIX[] =
    "(async()=>{if(location.origin!=='https://music.youtube.com')throw "
    "Error('origin');const p=document.querySelector('#movie_player');if(!p)"
    "throw Error('player');";
static const char ACTION_SUFFIX[] = "return 'ok'})()";
static int do_action(unsigned port, const char *action, unsigned volume, char expected_id[12]) {
  char expression[5000], operation[4000], response[32];
  if (!strcmp(action, "PLAY"))
    strcpy(operation, "if(typeof p.playVideo!=='function')throw Error('play');p.playVideo();");
  else if (!strcmp(action, "PAUSE"))
    strcpy(operation, "if(typeof p.pauseVideo!=='function')throw Error('pause');p.pauseVideo();");
  else if (!strcmp(action, "REWIND"))
    strcpy(operation, "if(typeof p.pauseVideo!=='function'||typeof p.seekTo!=="
                      "'function')throw Error('rewind');p.pauseVideo();p.seekTo(0,true);");
  else if (!strcmp(action, "VOLUME"))
    snprintf(operation, sizeof operation, "if(typeof p.setVolume!=='function')"
                                         "throw Error('volume');p.setVolume(%u);", volume);
  else if (!strcmp(action, "NEXT"))
    strcpy(operation, "const q=Array.from(document.querySelectorAll('ytmusic-player-queue ytmusic-player-queue-item'));"
                      "if(q.length>1000)throw Error('queue');"
                      "const selected=q.filter(x=>x.hasAttribute('selected')&&"
                      "x.data?.navigationEndpoint?.watchEndpoint?.videoId===p.getVideoData()?.video_id);"
                      "if(selected.length!==1)throw Error('queue');"
                      "const current=selected[0].data?.navigationEndpoint?.watchEndpoint;"
                      "if(!current||!Number.isInteger(current.index)||current.index<0||"
                      "typeof p.getVideoData!=='function'||current.videoId!==p.getVideoData()?.video_id)throw Error('queue');"
                      "const root=selected[0].closest?.('ytmusic-player-queue');if(!root)throw Error('queue');"
                      "const seeded=!(typeof current.playlistId==='string'&&current.playlistId);const items=!seeded?q:"
                      "Array.from(root.querySelectorAll('#automix-contents ytmusic-player-queue-item'));"
                      "if(seeded&&current.index!==0)throw Error('seed');"
                      "if(items.length>1000)throw Error('queue');let next=null,index=Infinity,count=0;"
                      "for(const item of items){if(seeded&&item.closest?.('#counterpart-renderer'))continue;"
                      "const w=item.data?.navigationEndpoint?.watchEndpoint;"
                      "const playlist=typeof current.playlistId==='string'&&current.playlistId?"
                      "w?.playlistId===current.playlistId:typeof w?.playlistId==='string'&&!!w.playlistId;"
                      "if(playlist&&Number.isInteger(w.index)&&w.index>current.index&&typeof w.videoId==='string'&&"
                      "/^[A-Za-z0-9_-]{11}$/.test(w.videoId)&&typeof item.resolveCommand==='function'){"
                      "if(w.index<index){next=item;index=w.index;count=1}else if(seeded&&w.index===index)count++}}"
                      "if(!next||(seeded&&count!==1))throw Error('next');"
                      "next.resolveCommand(next.data.navigationEndpoint);return next.data.navigationEndpoint.watchEndpoint.videoId;");
  else
    return -1;
  snprintf(
      expression, sizeof expression,
      "%s%s%s", ACTION_PREFIX, operation, ACTION_SUFFIX);
  if (evaluate(port, expression, response, sizeof response)) return -1;
  if (strcmp(action, "NEXT")) return strcmp(response, "ok") ? -1 : 0;
  if (strlen(response) != 11 || strspn(response, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-") != 11)
    return -1;
  strcpy(expected_id, response);
  return 0;
}
static bool action_matches(const char *command, unsigned volume, const char *expected_id,
                           const struct view *v) {
  if (!strcmp(command, "PLAY"))return v->playing && strcmp(v->status,"STREAM_LIMIT") && strcmp(v->status,"PLAYER_ERROR");
  if (!strcmp(command, "PAUSE"))return !v->playing;
  if (!strcmp(command, "REWIND"))return !v->playing && v->pos <= 48000;
  if (!strcmp(command, "VOLUME"))return v->volume == volume;
  if (!strcmp(command, "NEXT"))return expected_id[0] && !strcmp(v->video_id,expected_id);
  return false;
}
static void *browser_worker(void *arg) {
  struct session *s = arg;
  int64_t next = 0;
  int64_t maintenance_next = 0;
  bool activated = false;
  bool startup_checked = false, ever_ready = false;
  int64_t startup_retry_at = mono() + 45000;
  for (;;) {
    pthread_mutex_lock(&s->lock);
    bool quit = s->stop;
    bool action = s->busy && !s->processing;
    char command[16];
    strcpy(command, s->action);
    unsigned volume = s->volume;
    worker_deadline = action ? s->action_deadline : 0;
    if (action)
      s->processing = true;
    pthread_mutex_unlock(&s->lock);
    if (quit || stopping)
      break;
    if (action || mono() >= next) {
      struct view fresh = {0};
      int result = 0;
      bool observed = false;
      char expected_id[12] = "";
      /* With no desktop window manager, Chromium needs one explicit initial
       * activation before native X11 clicks reach its page. Never repeat this
       * on later read failures: the owner may be using the Home dashboard. */
      if(!activated) {
        char unused[1]; result=evaluate(s->port,NULL,unused,sizeof unused);
        if(!result)activated=true;
      }
      /* This is deliberately separate from STATE: it is a low-frequency UI
       * maintenance probe for the known stalled player-page transition.  Do
       * not run it in an action cycle, so a control keeps its absolute bound. */
      if (!result && !action && mono() >= maintenance_next) {
        char ignored[16];
        (void)evaluate(s->port, RECOVER_STALLED_PLAYER_UI, ignored,
                       sizeof ignored);
        (void)evaluate(s->port, MAINTAIN_MUSIC_QUEUE_RENDERING, ignored,
                       sizeof ignored);
        maintenance_next = mono() + 2000;
      }
      if (!result && action) {
        /* Observe before dispatch: policy status is authoritative for PLAY/NEXT. */
        result = read_view(s->port, &fresh);
        observed = !result;
        if (!result && ((!strcmp(command, "PLAY") || !strcmp(command, "NEXT")) &&
                        !strcmp(fresh.status, "STREAM_LIMIT")))
          result = -1;
        if (!result)
          result = do_action(s->port, command, volume, expected_id);
        if (!result) {
          result = -1;
          while (!stopping && mono() < worker_deadline) {
            struct view after = {0};
            if (!read_view(s->port, &after)) {
              fresh = after; observed = true;
              if (action_matches(command, volume, expected_id, &fresh)) { result=0; break; }
              if (!strcmp(fresh.status,"STREAM_LIMIT") || !strcmp(fresh.status,"PLAYER_ERROR"))break;
            }
            struct timespec wait={0,80000000};nanosleep(&wait,NULL);
          }
        }
      } else if (!result) {
        result = read_view(s->port, &fresh);
        observed = !result;
      }
      if(observed)ever_ready=true;
      if(result&&!action&&!ever_ready&&!startup_checked&&mono()>=startup_retry_at) {
        char ignored[16];startup_checked=true;
        (void)evaluate(s->port,RECOVER_EMPTY,ignored,sizeof ignored);
      }
      pthread_mutex_lock(&s->lock);
      struct view *old = &s->view;
      if (!result || (action && observed)) {
        bool changed = !old->connected || old->playing != fresh.playing ||
                       old->volume != fresh.volume ||
                       strcmp(old->title, fresh.title) ||
                       strcmp(old->artist, fresh.artist) ||
                       strcmp(old->output, fresh.output) ||
                       strcmp(old->status, fresh.status);
        fresh.rev = old->rev + (!action && changed ? 1 : 0);
        *old = fresh;
      } else {
        if (old->connected && !action)
          old->rev++;
        old->connected = false;
      }
      if (action) {
        s->done = true;
        s->outcome = result;
        s->outcome_observed = observed;
      }
      pthread_mutex_unlock(&s->lock);
      next = mono() + 500;
    }
    struct timespec delay = {0, 20000000};
    nanosleep(&delay, NULL);
  }
  return NULL;
}
struct client {
  int fd;
  char input[192], output[512];
  size_t received, sent, size;
  int64_t deadline;
  bool pending;
};
static void state_reply(struct client *c, const char *kind,
                        const struct view *v) {
  int n = snprintf(c->output, sizeof c->output,
                   "%s %" PRIu64 " %u %u %" PRIu64 " 0 0 %u\t%s\t%s\t%s\t%s\n", kind,
                   v->rev, v->playing, v->volume, v->pos, v->connected ? 0 : 1,
                   v->title, v->artist, v->output, v->status);
  c->size = n > 0 ? (size_t)n : 0;
  c->deadline = mono() + 200;
}
static void error_reply(struct client *c, const char *error) {
  int n = snprintf(c->output, sizeof c->output, "ERR %s\n", error);
  c->size = n > 0 ? (size_t)n : 0;
  c->deadline = mono() + 200;
}
static void handle(struct client *c, struct session *s) {
  c->input[c->received] = 0;
  if (c->received == 0 || c->input[c->received - 1] != '\n' ||
      memchr(c->input, 0, c->received) ||
      memchr(c->input, '\n', c->received - 1)) {
    error_reply(c, "invalid command");
    return;
  }
  c->input[c->received - 1] = 0;
  pthread_mutex_lock(&s->lock);
  if (!strcmp(c->input, "GET")) {
    state_reply(c, "OK", &s->view);
    goto done;
  }
  char *save = NULL, *do_word = strtok_r(c->input, " ", &save),
       *revision = strtok_r(NULL, " ", &save),
       *action = strtok_r(NULL, " ", &save),
       *value = strtok_r(NULL, " ", &save), *extra = strtok_r(NULL, " ", &save);
  uint64_t rev = 0, vol = 0;
  if (!do_word || strcmp(do_word, "DO") || !revision ||
      number(revision, UINT64_MAX, &rev) || !action || extra) {
    error_reply(c, "invalid command");
    goto done;
  }
  bool valid =
      !strcmp(action, "VOLUME")
          ? (value && !number(value, 100, &vol))
          : (!value && (!strcmp(action, "PLAY") || !strcmp(action, "PAUSE") ||
                        !strcmp(action, "NEXT") || !strcmp(action, "REWIND")));
  if (!valid) {
    error_reply(c, "invalid command");
    goto done;
  }
  if (rev != s->view.rev) {
    state_reply(c, "STALE", &s->view);
    goto done;
  }
  if (s->busy) {
    error_reply(c, "busy");
    goto done;
  }
  if (!s->view.connected) {
    error_reply(c, "browser unavailable");
    goto done;
  }
  s->view.rev++;
  s->busy = true;
  s->processing = false;
  s->done = false;
  s->outcome_observed = false;
  strcpy(s->action, action);
  s->volume = (unsigned)vol;
  c->pending = true;
  c->deadline = mono() + 14000;
  s->action_deadline = c->deadline - 250;
done:
  pthread_mutex_unlock(&s->lock);
}
static bool same_socket(const char *path, const struct stat *owned) {
  struct stat st;
  return !lstat(path, &st) && S_ISSOCK(st.st_mode) &&
         st.st_dev == owned->st_dev && st.st_ino == owned->st_ino;
}
int main(int argc, char **argv) {
  const char *path = NULL;
  uint64_t port = 0, seconds = 0;
  bool appliance = false, timed = false;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--help")) {
      puts(
          "forge-music-bridge --socket PATH --cdp-port PORT (--seconds 1..1800 | --appliance)");
      return 0;
    }
    if (!strcmp(argv[i], "--appliance")) {
      appliance = true;
      continue;
    }
    if (i + 1 == argc)
      return 2;
    if (!strcmp(argv[i], "--socket"))
      path = argv[++i];
    else if (!strcmp(argv[i], "--cdp-port")) {
      if (number(argv[++i], 65535, &port))
        return 2;
    } else if (!strcmp(argv[i], "--seconds")) {
      timed = true;
      if (number(argv[++i], 1800, &seconds))
        return 2;
    } else
      return 2;
  }
  if (!path || path[0] != '/' ||
      strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path) || !port ||
      (appliance ? timed : !seconds))
    return 2;
  char parent[108];
  strcpy(parent, path);
  char *slash = strrchr(parent, '/');
  if (!slash || slash == parent)
    return 2;
  *slash = 0;
  struct stat st, owned;
  if (lstat(parent, &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() ||
      (st.st_mode & 0077)) {
    fputs("private socket directory required\n", stderr);
    return 1;
  }
  if (!lstat(path, &st) || errno != ENOENT) {
    fputs("socket collision\n", stderr);
    return 1;
  }
  struct session s = {.lock = PTHREAD_MUTEX_INITIALIZER,
                      .port = (unsigned)port,
                      .view = {.volume = 35}};
  if (random_bytes(&s.view.rev, sizeof s.view.rev))
    return 1;
  s.view.rev &= UINT64_MAX >> 1;
  if (!s.view.rev)
    s.view.rev = 1;
  strcpy(s.view.title, "SELECT A TRACK");
  strcpy(s.view.artist, "YOUTUBE MUSIC");
  strcpy(s.view.status, "READY");
  int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
  if (listener < 0)
    return 1;
  struct sockaddr_un address = {.sun_family = AF_UNIX};
  strcpy(address.sun_path, path);
  mode_t oldmask = umask(0077);
  int result = bind(listener, (struct sockaddr *)&address, sizeof address);
  umask(oldmask);
  if (result) {
    close(listener);
    return 1;
  }
  if (lstat(path, &owned)) {
    close(listener);
    return 1;
  }
  if (chmod(path, 0600) || listen(listener, 8)) {
    close(listener);
    if (same_socket(path, &owned))
      unlink(path);
    return 1;
  }
  signal(SIGINT, on_signal);
  signal(SIGTERM, on_signal);
  signal(SIGHUP, on_signal);
  signal(SIGPIPE, SIG_IGN);
  pthread_t worker;
  if (pthread_create(&worker, NULL, browser_worker, &s)) {
    close(listener);
    if (same_socket(path, &owned))
      unlink(path);
    return 1;
  }
  struct client clients[CLIENTS];
  for (int i = 0; i < CLIENTS; i++)
    clients[i] = (struct client){.fd = -1};
  int64_t deadline = mono() + (int64_t)seconds * 1000;
  while (!stopping && (appliance || mono() < deadline)) {
    struct pollfd polls[CLIENTS + 1];
    polls[0] = (struct pollfd){listener, POLLIN, 0};
    for (int i = 0; i < CLIENTS; i++)
      polls[i + 1] =
          (struct pollfd){clients[i].fd, clients[i].size ? POLLOUT : POLLIN, 0};
    poll(polls, CLIENTS + 1, 20);
    if (polls[0].revents & POLLIN) {
      int fd = accept4(listener, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
      if (fd >= 0) {
        int i;
        for (i = 0; i < CLIENTS && clients[i].fd >= 0; i++) {
        }
        if (i == CLIENTS)
          close(fd);
        else
          clients[i] = (struct client){.fd = fd, .deadline = mono() + 200};
      }
    }
    pthread_mutex_lock(&s.lock);
    if (s.done) {
      for (int i = 0; i < CLIENTS; i++)
        if (clients[i].fd >= 0 && clients[i].pending) {
          clients[i].pending = false;
          if (s.outcome && s.outcome_observed)
            state_reply(&clients[i], "FAILED", &s.view);
          else if (s.outcome)
            error_reply(&clients[i], "confirmation unavailable");
          else
            state_reply(&clients[i], "OK", &s.view);
        }
      s.busy = false;
      s.processing = false;
      s.done = false;
    }
    pthread_mutex_unlock(&s.lock);
    for (int i = 0; i < CLIENTS; i++) {
      struct client *c = &clients[i];
      if (c->fd < 0)
        continue;
      short events = polls[i + 1].revents;
      if (events & (POLLERR | POLLHUP | POLLNVAL)) {
        close(c->fd);
        c->fd = -1;
        continue;
      }
      if (!c->size && !c->pending && (events & POLLIN)) {
        ssize_t n = recv(c->fd, c->input + c->received,
                         sizeof c->input - 1 - c->received, 0);
        if (n > 0) {
          c->received += (size_t)n;
          if (memchr(c->input, '\n', c->received))
            handle(c, &s);
          else if (c->received == sizeof c->input - 1)
            error_reply(c, "command too long");
        } else if (n == 0 || (errno != EINTR && errno != EAGAIN)) {
          close(c->fd);
          c->fd = -1;
          continue;
        }
      }
      if (c->size && (events & POLLOUT)) {
        ssize_t n =
            send(c->fd, c->output + c->sent, c->size - c->sent, MSG_NOSIGNAL);
        if (n > 0)
          c->sent += (size_t)n;
        else if (n < 0 && errno != EAGAIN && errno != EINTR)
          c->deadline = 0;
        if (c->sent == c->size) {
          close(c->fd);
          c->fd = -1;
          continue;
        }
      }
      if (mono() >= c->deadline) {
        close(c->fd);
        c->fd = -1;
      }
    }
  }
  stopping = 1;
  pthread_mutex_lock(&s.lock);
  s.stop = true;
  pthread_mutex_unlock(&s.lock);
  pthread_join(worker, NULL);
  for (int i = 0; i < CLIENTS; i++)
    if (clients[i].fd >= 0)
      close(clients[i].fd);
  close(listener);
  if (same_socket(path, &owned))
    unlink(path);
  pthread_mutex_destroy(&s.lock);
  return 0;
}
