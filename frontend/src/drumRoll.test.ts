/**
 * Unit tests for the DrumEvent <-> PianoRoll mapping (drumRoll.ts).
 * Run with: npm run test:roll
 * (esbuild bundles this file to /tmp and node --test runs it; no test
 * runner dependency is added to the repo.)
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  HIT_NOTE_LENGTH,
  diffNotes,
  instrumentToPitch,
  notesFromEvents,
  nudgeRollNote,
  parseMidiVelocity,
  pitchToInstrument,
  velocityToMidi,
  type DrumEventLike,
  type RollNote,
} from "./drumRoll";

const EVENTS: DrumEventLike[] = [
  { id: "a", time_seconds: 1.0, instrument: "kick", velocity: 100 },
  { id: "b", time_seconds: 2.0, instrument: "snare", velocity: 80 },
  { id: "c", time_seconds: 3.0, instrument: "closed_hihat", velocity: 64 },
];

test("lanes map to distinct pitches in timeline order", () => {
  assert.equal(instrumentToPitch("kick"), 46);
  assert.equal(instrumentToPitch("other"), 36);
  assert.equal(pitchToInstrument(46), "kick");
  assert.equal(pitchToInstrument(36), "other");
  assert.equal(pitchToInstrument(999), "other");
  assert.equal(instrumentToPitch("unknown-instrument"), instrumentToPitch("other"));
});

test("velocity scales between MIDI and 0..1", () => {
  assert.equal(velocityToMidi(1), 127);
  assert.equal(velocityToMidi(undefined), 96);
  assert.equal(velocityToMidi(0), 0);
  assert.equal(velocityToMidi(100 / 127), 100);
});

test("notesFromEvents keeps ids and sorts by time", () => {
  const notes = notesFromEvents([EVENTS[2], EVENTS[0]]);
  assert.deepEqual(
    notes.map((note) => note.id),
    ["a", "c"],
  );
  assert.equal(notes[0].pitch, instrumentToPitch("kick"));
  assert.equal(notes[0].length, HIT_NOTE_LENGTH);
  assert.equal(notes[0].velocity, 100 / 127);
});

test("diffNotes reports a drawn note as added", () => {
  const before = notesFromEvents(EVENTS);
  const after: RollNote[] = [
    ...before,
    {
      id: "draft-1",
      pitch: instrumentToPitch("crash"),
      start: 1.5,
      length: HIT_NOTE_LENGTH,
      velocity: 0.5,
    },
  ];
  const commit = diffNotes(before, after, EVENTS);
  assert.equal(commit.added.length, 1);
  assert.deepEqual(commit.added[0], {
    time_seconds: 1.5,
    instrument: "crash",
    velocity: 64,
  });
  assert.deepEqual(commit.changed, []);
  assert.deepEqual(commit.removed, []);
});

test("diffNotes reports a move, a reclassify and a velocity change", () => {
  const before = notesFromEvents(EVENTS);
  const after: RollNote[] = before.map((note) => {
    if (note.id === "a") return { ...note, start: 1.25 };
    if (note.id === "b") return { ...note, pitch: instrumentToPitch("crash") };
    if (note.id === "c") return { ...note, velocity: 127 / 127 };
    return note;
  });
  const commit = diffNotes(before, after, EVENTS);
  assert.deepEqual(commit.added, []);
  assert.deepEqual(commit.removed, []);
  assert.deepEqual(
    commit.changed.map((patch) => [patch.eventId, patch.changes]),
    [
      ["a", { time_seconds: 1.25 }],
      ["b", { instrument: "crash" }],
      ["c", { velocity: 127 }],
    ],
  );
});

test("diffNotes ignores length-only stretches and sub-millisecond moves", () => {
  const before = notesFromEvents(EVENTS);
  const after: RollNote[] = before.map((note) =>
    note.id === "a"
      ? { ...note, length: 0.9, start: 1.0005 }
      : note,
  );
  assert.deepEqual(diffNotes(before, after, EVENTS), {
    added: [],
    changed: [],
    removed: [],
  });
});

test("diffNotes reports a deleted note as removed", () => {
  const before = notesFromEvents(EVENTS);
  const after = before.filter((note) => note.id !== "b");
  const commit = diffNotes(before, after, EVENTS);
  assert.deepEqual(commit.removed, ["b"]);
  assert.deepEqual(commit.added, []);
  assert.deepEqual(commit.changed, []);
});

test("parseMidiVelocity accepts only integer values from 0 through 127", () => {
  assert.equal(parseMidiVelocity("0"), 0);
  assert.equal(parseMidiVelocity("127"), 127);
  for (const value of ["", "1.5", "-1", "128", "abc", "0x10", "1e2"]) {
    assert.equal(parseMidiVelocity(value), null);
  }
});

test("nudgeRollNote moves by a sixteenth, clamps song bounds and changes adjacent lanes", () => {
  const note = notesFromEvents(EVENTS)[0];
  assert.equal(nudgeRollNote(note, "left", 0.125, 10).start, 0.875);
  assert.equal(nudgeRollNote({ ...note, start: 0 }, "left", 0.125, 10).start, 0);
  assert.equal(nudgeRollNote({ ...note, start: 9.95 }, "right", 0.125, 10).start, 10);
  assert.equal(nudgeRollNote(note, "up", 0.125, 10).pitch, 46);
  assert.equal(nudgeRollNote(note, "down", 0.125, 10).pitch, 45);
});

test("nudgeRollNote moves by the containing measure when requested", () => {
  const note = { ...notesFromEvents(EVENTS)[0], start: 1.25 };
  assert.equal(nudgeRollNote(note, "right", 0.125, 8, [{ value: 0, label: "1" }, { value: 2, label: "2" }, { value: 4, label: "3" }], true).start, 3.25);
});
