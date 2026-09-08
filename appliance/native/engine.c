#ifndef _POSIX_C_SOURCE
#define _POSIX_C_SOURCE 200809L
#endif

#include "core.h"

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

enum { CLIENT_MAX = 256, MAX_CLIENTS = 8, RESPONSE_MAX = 192, TICK_MS = 20, CLIENT_DEADLINE_MS = 200 };

struct state {
    uint64_t revision, frames_written, underruns;
    unsigned volume;
    bool playing, fault, loop, null_sink, socket_created;
    int output_fd;
    char socket_path[sizeof(((struct sockaddr_un *)0)->sun_path)];
    struct core_wav wav;
};

struct client { int fd; char buffer[CLIENT_MAX + 1]; size_t length; int64_t deadline; };
static volatile sig_atomic_t stopping;

static void on_signal(int ignored) { (void)ignored; stopping = 1; }
static int64_t now_ms(void) { struct timespec ts; (void)clock_gettime(CLOCK_MONOTONIC, &ts); return (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000; }
static void usage(FILE *out) { (void)fprintf(out, "Usage: engine --socket PATH --wav PATH --output PATH [--loop]\n"); }

static int snapshot(char *out, size_t size, const char *kind, const struct state *s) {
    return snprintf(out, size, "%s %llu %u %u %llu %llu %llu %u\n", kind,
        (unsigned long long)s->revision, s->playing ? 1U : 0U, s->volume,
        (unsigned long long)s->wav.position_frames, (unsigned long long)s->frames_written,
        (unsigned long long)s->underruns, s->fault ? 1U : 0U);
}

static int check_socket_parent(const char *path, char *error, size_t error_size) {
    char parent[PATH_MAX]; char *slash; struct stat st;
    if (strlen(path) >= sizeof(((struct sockaddr_un *)0)->sun_path)) { snprintf(error, error_size, "socket path is too long"); return -1; }
    if (snprintf(parent, sizeof(parent), "%s", path) >= (int)sizeof(parent) || (slash = strrchr(parent, '/')) == NULL || slash == parent) { snprintf(error, error_size, "socket path must have an owner-only parent directory"); return -1; }
    *slash = '\0';
    if (stat(parent, &st) < 0 || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 0077) != 0) { snprintf(error, error_size, "socket parent must be an owner-only directory"); return -1; }
    return 0;
}

static int open_output(const char *path, struct state *s, char *error, size_t error_size) {
    struct stat st;
    if (strcmp(path, "/dev/null") == 0) { s->null_sink = true; s->output_fd = -1; return 0; }
    if (lstat(path, &st) == 0) {
        if (!S_ISFIFO(st.st_mode)) { snprintf(error, error_size, "output file already exists; use a new path or FIFO"); return -1; }
        s->output_fd = open(path, O_WRONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        if (s->output_fd < 0) { snprintf(error, error_size, "cannot open output FIFO (reader required): %s", strerror(errno)); return -1; }
        return 0;
    }
    if (errno != ENOENT) { snprintf(error, error_size, "cannot inspect output: %s", strerror(errno)); return -1; }
    s->output_fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
    if (s->output_fd < 0) { snprintf(error, error_size, "cannot create output file: %s", strerror(errno)); return -1; }
    return 0;
}

static void fault(struct state *s) { if (!s->fault || s->playing) { s->fault = true; s->playing = false; ++s->revision; } }
static void render(struct state *s) {
    int16_t pcm[CORE_TICK_FRAMES * 2]; char error[128]; size_t filled = 0;
    if (!s->playing) return;
    while (filled < CORE_TICK_FRAMES) {
        int frames = core_read_frames(&s->wav, pcm + filled * 2U,
                                     CORE_TICK_FRAMES - filled, error, sizeof(error));
        if (frames < 0) { fault(s); return; }
        if (frames > 0) { filled += (size_t)frames; continue; }
        if (!s->loop) { s->playing = false; ++s->revision; break; }
        if (core_rewind_wav(&s->wav, error, sizeof(error)) < 0) { fault(s); return; }
    }
    if (filled == 0) return;
    core_scale_pcm(pcm, filled, s->volume);
    if (s->null_sink) { s->frames_written += (uint64_t)filled; return; }
    { ssize_t n = write(s->output_fd, pcm, filled * CORE_FRAME_BYTES);
      if (n > 0) s->frames_written += (uint64_t)n / CORE_FRAME_BYTES;
      if (n != (ssize_t)(filled * CORE_FRAME_BYTES)) {
          ++s->underruns;
          if (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) fault(s);
      }
    }
}

static void respond_and_close(struct client *client, const char *text) { (void)send(client->fd, text, strlen(text), MSG_DONTWAIT | MSG_NOSIGNAL); (void)close(client->fd); client->fd = -1; }
static void process_command(struct client *c, struct state *s) {
    char response[RESPONSE_MAX], action[16], *line = c->buffer;
    unsigned long long expected;
    unsigned volume;
    int consumed;
    const char *tail;
    line[c->length] = '\0'; if (c->length == 0 || line[c->length - 1] != '\n') { respond_and_close(c, "ERR command must end with newline\n"); return; }
    line[c->length - 1] = '\0';
    if (strcmp(line, "GET") == 0) { (void)snapshot(response, sizeof(response), "OK", s); respond_and_close(c, response); return; }
    if (sscanf(line, "DO %llu %15s%n", &expected, action, &consumed) != 2) { respond_and_close(c, "ERR invalid command\n"); return; }
    tail = line + consumed;
    if (*tail == '\0' && strcmp(action, "PLAY") == 0) { if (expected != s->revision) { (void)snapshot(response, sizeof(response), "STALE", s); } else if (s->fault) { (void)snprintf(response, sizeof(response), "ERR audio fault\n"); } else { s->playing = true; ++s->revision; (void)snapshot(response, sizeof(response), "OK", s); } respond_and_close(c, response); return; }
    if (*tail == '\0' && strcmp(action, "PAUSE") == 0) { if (expected != s->revision) { (void)snapshot(response, sizeof(response), "STALE", s); } else { s->playing = false; ++s->revision; (void)snapshot(response, sizeof(response), "OK", s); } respond_and_close(c, response); return; }
    if (*tail == '\0' && strcmp(action, "REWIND") == 0) { if (expected != s->revision) { (void)snapshot(response, sizeof(response), "STALE", s); } else if (core_rewind_wav(&s->wav, response, sizeof(response)) < 0) { respond_and_close(c, "ERR cannot rewind WAV\n"); return; } else { s->playing = false; ++s->revision; (void)snapshot(response, sizeof(response), "OK", s); } respond_and_close(c, response); return; }
    if (strcmp(action, "VOLUME") == 0 && sscanf(tail, " %u %c", &volume, action) == 1 && volume <= 100) { if (expected != s->revision) { (void)snapshot(response, sizeof(response), "STALE", s); } else { s->volume = volume; ++s->revision; (void)snapshot(response, sizeof(response), "OK", s); } respond_and_close(c, response); return; }
    respond_and_close(c, "ERR invalid command\n");
}

int main(int argc, char **argv) {
    const char *socket_path = NULL, *wav_path = NULL, *output_path = NULL; char error[160]; struct state s = { .volume = 100, .output_fd = -1, .wav = { .fd = -1 } }; struct client clients[MAX_CLIENTS]; int listener = -1; int64_t next_tick;
    for (size_t i = 0; i < MAX_CLIENTS; ++i) clients[i].fd = -1;
    for (int i = 1; i < argc; ++i) { if (strcmp(argv[i], "--help") == 0) { usage(stdout); return 0; } if (strcmp(argv[i], "--loop") == 0) { s.loop = true; continue; } if ((strcmp(argv[i], "--socket") == 0 || strcmp(argv[i], "--wav") == 0 || strcmp(argv[i], "--output") == 0) && i + 1 < argc) { const char *v = argv[++i]; if (strcmp(argv[i - 1], "--socket") == 0) socket_path = v; else if (strcmp(argv[i - 1], "--wav") == 0) wav_path = v; else output_path = v; continue; } usage(stderr); return 2; }
    if (!socket_path || !wav_path || !output_path) { usage(stderr); return 2; }
    if (check_socket_parent(socket_path, error, sizeof(error)) < 0 || core_open_wav(&s.wav, wav_path, error, sizeof(error)) < 0) { (void)fprintf(stderr, "engine: %s\n", error); core_close_wav(&s.wav); return 1; }
    listener = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0); { struct sockaddr_un addr = { .sun_family = AF_UNIX }; struct stat st; if (listener < 0 || lstat(socket_path, &st) == 0 || (errno != ENOENT) || snprintf(addr.sun_path, sizeof(addr.sun_path), "%s", socket_path) >= (int)sizeof(addr.sun_path) || bind(listener, (struct sockaddr *)&addr, sizeof(addr)) < 0) { (void)fprintf(stderr, "engine: cannot create socket safely: %s\n", strerror(errno)); if (listener >= 0) (void)close(listener); core_close_wav(&s.wav); return 1; } }
    s.socket_created = true;
    (void)snprintf(s.socket_path, sizeof(s.socket_path), "%s", socket_path);
    if (chmod(socket_path, 0600) < 0 || listen(listener, 8) < 0) { (void)fprintf(stderr, "engine: cannot create socket safely: %s\n", strerror(errno)); (void)close(listener); (void)unlink(s.socket_path); core_close_wav(&s.wav); return 1; }
    if (open_output(output_path, &s, error, sizeof(error)) < 0) {
        (void)fprintf(stderr, "engine: %s\n", error);
        (void)close(listener);
        (void)unlink(s.socket_path);
        core_close_wav(&s.wav);
        return 1;
    }
    signal(SIGTERM, on_signal); signal(SIGINT, on_signal); signal(SIGPIPE, SIG_IGN); next_tick = now_ms() + TICK_MS;
    while (!stopping) {
        struct pollfd fds[1 + MAX_CLIENTS];
        int64_t now = now_ms(), due = next_tick - now;
        int timeout = due <= 0 ? 0 : (due > INT_MAX ? INT_MAX : (int)due);
        fds[0] = (struct pollfd){ .fd = listener, .events = POLLIN };
        for (size_t i = 0; i < MAX_CLIENTS; ++i) {
            fds[i + 1] = (struct pollfd){ .fd = clients[i].fd, .events = POLLIN | POLLHUP | POLLERR };
            if (clients[i].fd >= 0 && clients[i].deadline - now < timeout) {
                timeout = clients[i].deadline <= now ? 0 : (int)(clients[i].deadline - now);
            }
        }
        (void)poll(fds, 1 + MAX_CLIENTS, timeout);
        now = now_ms();
        for (size_t i = 0; i < MAX_CLIENTS; ++i) {
            struct client *c = &clients[i];
            short client_events = fds[i + 1].revents;
            if (c->fd >= 0 && (client_events & (POLLHUP | POLLERR))) {
                (void)close(c->fd); c->fd = -1;
            } else if (c->fd >= 0 && (client_events & POLLIN)) {
                ssize_t n = recv(c->fd, c->buffer + c->length, CLIENT_MAX - c->length, 0);
                if (n > 0) {
                    c->length += (size_t)n;
                    if (memchr(c->buffer, '\n', c->length) || c->length == CLIENT_MAX) process_command(c, &s);
                } else if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
                    (void)close(c->fd); c->fd = -1;
                }
            }
            if (c->fd >= 0 && now >= c->deadline) respond_and_close(c, "ERR command timeout\n");
        }
        for (size_t accepted = 0; (fds[0].revents & POLLIN) && accepted < MAX_CLIENTS; ++accepted) {
            int fd = accept(listener, NULL, NULL);
            if (fd < 0) break;
            {
                int flags = fcntl(fd, F_GETFL);
                size_t slot = MAX_CLIENTS;
                (void)fcntl(fd, F_SETFD, FD_CLOEXEC);
                if (flags >= 0) (void)fcntl(fd, F_SETFL, flags | O_NONBLOCK);
                for (size_t i = 0; i < MAX_CLIENTS; ++i) if (clients[i].fd < 0) { slot = i; break; }
                if (slot == MAX_CLIENTS) (void)close(fd);
                else { clients[slot].fd = fd; clients[slot].length = 0; clients[slot].deadline = now + CLIENT_DEADLINE_MS; }
            }
        }
        if (now >= next_tick) { render(&s); next_tick = now + TICK_MS; }
    }
    for (size_t i = 0; i < MAX_CLIENTS; ++i) if (clients[i].fd >= 0) (void)close(clients[i].fd);
    (void)close(listener);
    if (s.socket_created) (void)unlink(s.socket_path);
    if (s.output_fd >= 0) (void)close(s.output_fd);
    core_close_wav(&s.wav);
    return 0;
}
