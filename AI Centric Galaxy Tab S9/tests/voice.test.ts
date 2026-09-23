import assert from "node:assert/strict";
import test from "node:test";
import { VoiceHandoff } from "../server/voice.ts";
import { insertTranscript, nativeVoiceAvailable } from "../src/voice-draft.ts";

test("Talk appears only in a shell version with native voice support", () => {
  const local = "http://localhost:4318";
  assert.equal(nativeVoiceAvailable("Android GalaxyWorkspace/0.4.0", local), false);
  assert.equal(nativeVoiceAvailable("Android GalaxyWorkspace/0.4.1-preview", local), true);
  assert.equal(nativeVoiceAvailable("Android GalaxyWorkspace/0.5.0", local), true);
  assert.equal(nativeVoiceAvailable("Android GalaxyWorkspace/0.4.1", "https://example.org"), false);
});

test("dictation stays in the paired session and cannot be replayed", () => {
  const voice = new VoiceHandoff();
  const first = voice.start("session-one", "device:chat:project:conversation", 3);
  assert.deepEqual(voice.next("session-two"), { id: null });
  assert.equal(voice.status("session-two", first.id).state, "expired");
  assert.deepEqual(voice.next("session-one"), { id: first.id });
  assert.deepEqual(voice.next("session-one"), { id: null });
  assert.throws(() => voice.finish("session-two", first.id, "complete", "private words"));
  voice.finish("session-one", first.id, "complete", "meeting notes");
  assert.deepEqual(voice.status("session-one", first.id), {
    state: "complete", key: "device:chat:project:conversation", revision: 3, text: "meeting notes",
  });
  assert.equal(voice.status("session-one", first.id).state, "expired");
  assert.throws(() => voice.finish("session-one", first.id, "complete", "late result"));
});

test("cancel and replacement reject late recognition results", () => {
  const voice = new VoiceHandoff();
  const first = voice.start("session", "one", 0);
  voice.next("session");
  voice.cancel("session", first.id);
  assert.throws(() => voice.finish("session", first.id, "complete", "late"));
  const second = voice.start("session", "two", 0);
  voice.next("session");
  const third = voice.start("session", "three", 0);
  assert.throws(() => voice.finish("session", second.id, "complete", "late"));
  assert.deepEqual(voice.next("session"), { id: third.id });
  voice.finish("session", third.id, "canceled", "");
  assert.equal(voice.status("session", third.id).state, "canceled");
});

test("transcript replaces only the selected text and preserves the rest of the draft", () => {
  assert.deepEqual(insertTranscript("Meet Minster Newdorf tomorrow", 5, 12, "Minister"), {
    text: "Meet Minister Newdorf tomorrow", caret: 13,
  });
  assert.deepEqual(insertTranscript("Notes", 5, 5, "for the meeting"), {
    text: "Notes for the meeting", caret: 21,
  });
  assert.deepEqual(insertTranscript("", 0, 0, "First words"), {
    text: "First words", caret: 11,
  });
  assert.throws(() => insertTranscript("x".repeat(14000), 14000, 14000, "more"));
});
