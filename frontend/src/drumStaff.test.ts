/**
 * Unit tests for the DrumEvent <-> staff mapping (drumStaff.ts).
 * Run with: npm run test:roll
 * (esbuild bundles the test files to /tmp and node --test runs them;
 * no test runner dependency is added to the repo.)
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  SLOTS_PER_BAR,
  buildStaffBars,
  instrumentAtStep,
  isCymbal,
  positionForInstrument,
  slotTimeSeconds,
  snapToSlot,
  type StaffBar,
} from "./drumStaff";

const BARS: StaffBar[] = [
  { number: 1, start: 0, end: 2 },
  { number: 2, start: 2, end: 4 },
  { number: 3, start: 4, end: 6 },
];

test("kick / snare / hats sit on distinct staff steps with the right heads", () => {
  assert.equal(positionForInstrument("kick").key, "f/4");
  assert.equal(positionForInstrument("kick").step, 1);
  assert.equal(positionForInstrument("kick").noteType, undefined);
  assert.equal(positionForInstrument("snare").key, "c/5");
  assert.equal(positionForInstrument("snare").step, 5);
  assert.equal(positionForInstrument("closed_hihat").key, "g/5");
  assert.equal(positionForInstrument("closed_hihat").noteType, "x");
  assert.equal(positionForInstrument("open_hihat").key, "a/5");
  assert.equal(positionForInstrument("open_hihat").noteType, "x");
  assert.equal(positionForInstrument("crash").key, "b/5");
  assert.equal(positionForInstrument("crash").noteType, "x");
  assert.equal(positionForInstrument("ride").noteType, "x");
  assert.equal(positionForInstrument("pedal_hihat").key, "d/4");
  assert.equal(positionForInstrument("pedal_hihat").step, -1);
  assert.equal(isCymbal("kick"), false);
  assert.equal(isCymbal("crash"), true);
  assert.equal(positionForInstrument("unknown").instrument, "other");
});

test("drag target snaps to the nearest lane by step", () => {
  assert.equal(instrumentAtStep(1), "kick");
  assert.equal(instrumentAtStep(5), "snare");
  assert.equal(instrumentAtStep(9), "closed_hihat");
  assert.equal(instrumentAtStep(10), "open_hihat");
  assert.equal(instrumentAtStep(11), "crash");
  assert.equal(instrumentAtStep(-1), "pedal_hihat");
  assert.equal(instrumentAtStep(0), "kick");
  assert.equal(instrumentAtStep(2), "low_tom");
});

test("events land in the right bar and slot, 16 slots per bar", () => {
  const laid = buildStaffBars(
    [
      { id: "a", time_seconds: 0.0, instrument: "kick", velocity: 100 },
      { id: "b", time_seconds: 0.13, instrument: "snare", velocity: 90 },
      { id: "c", time_seconds: 1.0, instrument: "closed_hihat", velocity: 80 },
    ],
    BARS,
  );
  assert.equal(laid.length, 3);
  for (const barNotes of laid) assert.equal(barNotes.slots.length, SLOTS_PER_BAR);
  // Bar 1 is 2s long: a 16th is 0.125s. 0.13s snaps to slot 1.
  assert.equal(laid[0].slots[0].hits[0].eventId, "a");
  assert.equal(laid[0].slots[1].hits[0].eventId, "b");
  assert.equal(laid[0].slots[8].hits[0].eventId, "c");
  assert.equal(laid[0].slots[2].hits.length, 0);
  assert.equal(laid[1].slots.flatMap((slot) => slot.hits).length, 0);
  assert.equal(slotTimeSeconds(laid[0], 8), 1.0);
  assert.equal(snapToSlot(1.06, laid[0]), 1.0);
});

test("a bar-boundary hit belongs to the bar that starts there", () => {
  const laid = buildStaffBars(
    [
      { id: "edge", time_seconds: 2.0, instrument: "kick", velocity: 100 },
      { id: "before", time_seconds: 1.99, instrument: "snare", velocity: 100 },
      { id: "end", time_seconds: 6.0, instrument: "crash", velocity: 100 },
    ],
    BARS,
  );
  assert.equal(laid[0].slots.flatMap((slot) => slot.hits).length, 1);
  assert.equal(laid[0].slots[15].hits[0].eventId, "before");
  assert.equal(laid[1].slots[0].hits[0].eventId, "edge");
  assert.equal(laid[2].slots[15].hits[0].eventId, "end");
});

test("same-slot hits of different drums form one chord, same drum collapses", () => {
  const laid = buildStaffBars(
    [
      { id: "k", time_seconds: 0.5, instrument: "kick", velocity: 100 },
      { id: "h", time_seconds: 0.51, instrument: "closed_hihat", velocity: 70 },
      { id: "k2", time_seconds: 0.52, instrument: "kick", velocity: 60 },
      { id: "s", time_seconds: 0.52, instrument: "snare", velocity: 90 },
    ],
    BARS,
  );
  const slot = laid[0].slots[4];
  assert.deepEqual(
    slot.hits.map((hit) => hit.eventId),
    ["h", "s", "k"],
  );
  assert.equal(slot.hits.length, 3);
});

test("cross-bar: a groove keeps its bar numbers and slot times", () => {
  const laid = buildStaffBars(
    [
      { id: "b1", time_seconds: 0.25, instrument: "kick", velocity: 100 },
      { id: "b2", time_seconds: 2.25, instrument: "kick", velocity: 100 },
      { id: "b3", time_seconds: 4.25, instrument: "kick", velocity: 100 },
    ],
    BARS,
  );
  assert.equal(laid[0].bar.number, 1);
  assert.equal(laid[0].slots[2].hits[0].eventId, "b1");
  assert.equal(laid[1].bar.number, 2);
  assert.equal(laid[1].slots[2].hits[0].eventId, "b2");
  assert.equal(laid[2].bar.number, 3);
  assert.equal(laid[2].slots[2].hits[0].eventId, "b3");
  assert.equal(slotTimeSeconds(laid[2], 2), 4.25);
});
