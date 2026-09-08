#ifndef FORGE_BRIDGE_JSON_H
#define FORGE_BRIDGE_JSON_H
#include <ctype.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
/* Bounded JSON reader for CDP envelopes. Offsets refer to an immutable buffer.
 */
typedef struct {
  int start, end, next, kind;
} JsonToken;
typedef struct {
  const char *s;
  size_t length, pos;
  JsonToken t[512];
  int count;
} Json;
static void jspace(Json *j) {
  while (j->pos < j->length && strchr(" \r\n\t", j->s[j->pos]))
    j->pos++;
}
static int jvalue(Json *j, int depth) {
  jspace(j);
  if (depth > 24 || j->count >= 512 || j->pos >= j->length)
    return -1;
  int at = j->count++, kind = (unsigned char)j->s[j->pos];
  j->t[at] = (JsonToken){.start = (int)j->pos, .kind = kind};
  j->pos++;
  if (kind == '"') {
    bool closed = false;
    while (j->pos < j->length) {
      unsigned char c = (unsigned char)j->s[j->pos++];
      if (c == '"') {
        closed = true;
        break;
      }
      if (c < 32)
        return -1;
      if (c == '\\') {
        if (j->pos >= j->length)
          return -1;
        c = (unsigned char)j->s[j->pos++];
        if (c == 'u') {
          for (int k = 0; k < 4; k++)
            if (j->pos >= j->length || !isxdigit((unsigned char)j->s[j->pos++]))
              return -1;
        } else if (!strchr("\"\\/bfnrt", c))
          return -1;
      }
    }
    if (!closed)
      return -1;
  } else if (kind == '{' || kind == '[') {
    jspace(j);
    char end = kind == '{' ? '}' : ']';
    if (j->pos < j->length && j->s[j->pos] == end)
      j->pos++;
    else
      for (;;) {
        if (kind == '{') {
          jspace(j);
          if (j->pos >= j->length || j->s[j->pos] != '"' ||
              jvalue(j, depth + 1) < 0)
            return -1;
          jspace(j);
          if (j->pos >= j->length || j->s[j->pos++] != ':')
            return -1;
        }
        if (jvalue(j, depth + 1) < 0)
          return -1;
        jspace(j);
        if (j->pos >= j->length)
          return -1;
        char c = j->s[j->pos++];
        if (c == end)
          break;
        if (c != ',')
          return -1;
      }
  } else {
    j->pos--;
    const char *word = kind == 't'   ? "true"
                       : kind == 'f' ? "false"
                       : kind == 'n' ? "null"
                                     : NULL;
    if (word) {
      size_t n = strlen(word);
      if (j->length - j->pos < n || memcmp(j->s + j->pos, word, n))
        return -1;
      j->pos += n;
    } else {
      if (j->s[j->pos] == '-')
        j->pos++;
      if (j->pos >= j->length)
        return -1;
      if (j->s[j->pos] == '0')
        j->pos++;
      else {
        size_t b = j->pos;
        while (j->pos < j->length && isdigit((unsigned char)j->s[j->pos]))
          j->pos++;
        if (b == j->pos)
          return -1;
      }
      if (j->pos < j->length && j->s[j->pos] == '.') {
        size_t b = ++j->pos;
        while (j->pos < j->length && isdigit((unsigned char)j->s[j->pos]))
          j->pos++;
        if (b == j->pos)
          return -1;
      }
      if (j->pos < j->length && (j->s[j->pos] == 'e' || j->s[j->pos] == 'E')) {
        j->pos++;
        if (j->pos < j->length && (j->s[j->pos] == '+' || j->s[j->pos] == '-'))
          j->pos++;
        size_t b = j->pos;
        while (j->pos < j->length && isdigit((unsigned char)j->s[j->pos]))
          j->pos++;
        if (b == j->pos)
          return -1;
      }
    }
  }
  j->t[at].end = (int)j->pos;
  j->t[at].next = j->count;
  return at;
}
static int jparse(Json *j, const char *s) {
  memset(j, 0, sizeof *j);
  j->s = s;
  j->length = strlen(s);
  if (jvalue(j, 0) != 0)
    return -1;
  jspace(j);
  return j->pos == j->length ? 0 : -1;
}
static int jstring(const Json *j, int at, char *out, size_t cap) {
  if (at < 0 || at >= j->count || j->t[at].kind != '"' || !cap)
    return -1;
  size_t n = 0;
  int end = j->t[at].end - 1;
  for (int p = j->t[at].start + 1; p < end; p++) {
    unsigned char c = (unsigned char)j->s[p];
    if (c == '\\') {
      c = (unsigned char)j->s[++p];
      if (c == 'u') {
        unsigned v = 0;
        for (int k = 0; k < 4; k++) {
          unsigned char d = (unsigned char)j->s[++p];
          v = v * 16 + (d <= '9' ? d - '0' : (d | 32) - 'a' + 10);
        }
        c = v >= 32 && v <= 126 ? (unsigned char)v : '?';
      } else if (c == 'n')
        c = '\n';
      else if (c == 'r')
        c = '\r';
      else if (c == 't')
        c = '\t';
      else if (c == 'b')
        c = '\b';
      else if (c == 'f')
        c = '\f';
    }
    if (n + 1 >= cap)
      return -1;
    out[n++] = (char)c;
  }
  out[n] = 0;
  return 0;
}
static int jkey(const Json *j, int object, const char *key) {
  if (object < 0 || j->t[object].kind != '{')
    return -1;
  for (int p = object + 1; p < j->t[object].next;) {
    char name[80];
    int value = p + 1;
    if (value >= j->count)
      return -1;
    if (!jstring(j, p, name, sizeof name) && !strcmp(name, key))
      return value;
    p = j->t[value].next;
  }
  return -1;
}
static int juint(const Json *j, int at, uint64_t *value) {
  if (at < 0 || j->t[at].kind < '0' || j->t[at].kind > '9')
    return -1;
  uint64_t v = 0;
  for (int p = j->t[at].start; p < j->t[at].end; p++) {
    unsigned char c = (unsigned char)j->s[p];
    if (c < '0' || c > '9' || v > (UINT64_MAX - (c - '0')) / 10)
      return -1;
    v = v * 10 + c - '0';
  }
  *value = v;
  return 0;
}
static int jquote(const char *s, char *out, size_t cap) {
  size_t n = 0;
  if (cap < 3)
    return -1;
  out[n++] = '"';
  for (; *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c < 32 || c == '"' || c == '\\') {
      if (n + 6 >= cap)
        return -1;
      int k = snprintf(out + n, cap - n, "\\u%04x", c);
      if (k != 6)
        return -1;
      n += 6;
    } else {
      if (n + 2 >= cap)
        return -1;
      out[n++] = (char)c;
    }
  }
  out[n++] = '"';
  out[n] = 0;
  return 0;
}

#endif
