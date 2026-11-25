/**
 * Unit tests for the shared playback helpers (playback.ts) and the
 * staff follow-playback helpers (drumStaffUtils.ts additions).
 * Run with: npm run test:roll
 * (esbuild bundles the test files to /tmp and node --test runs them;
 * no test runner dependency is added to the repo.)
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_ZOOM_PX_PER_S,
  MIN_ZOOM_PX_PER_S,
  clampZoom,
  fitZoom,
  wheelZoomFactor,
  zoomByFactor,
  zoomIn,
  zoomOut,
} from "./playback";
import {
  findBarIndexAtTime,
  pageIndexForBar,
  updateTrail,
  type StaffBar,
  type TrailHit,
} from "./drumStaffUtils";

test("zoom clamps to 1–240 px/s and null (fit) passes through", () => {
  assert.equal(clampZoom(null), null);
  assert.equal(clampZoom(0.2), MIN_ZOOM_PX_PER_S);
  assert.equal(clampZoom(9999), MAX_ZOOM_PX_PER_S);
  assert.equal(clampZoom(42), 42);
  assert.equal(clampZoom(Number.NaN), null);
  assert.equal(clampZoom(Number.POSITIVE_INFINITY), null);
});

test("fit zoom is width over duration, zoom steps multiply by 1.5", () => {
  assert.equal(fitZoom(960, 120), 8);
  assert.equal(fitZoom(0, 120), 8);
  assert.equal(zoomIn(null, 8), 12);
  assert.equal(zoomOut(null, 8), 8 / 1.5);
  assert.equal(zoomIn(160, 8), 240);
  assert.equal(zoomOut(1.2, 8), 1);
});

test("wheel zoom factor is smooth and direction-correct", () => {
  assert.ok(wheelZoomFactor(-100) > 1);
  assert.ok(wheelZoomFactor(100) < 1);
  assert.equal(wheelZoomFactor(0), 1);
  assert.equal(zoomByFactor(10, 8, 2), 20);
  assert.equal(zoomByFactor(null, 8, 0.5), 4);
});

const BARS: StaffBar[] = [
  { number: 1, start: 0, end: 2 },
  { number: 2, start: 2, end: 4 },
  { number: 3, start: 4, end: 6 },
];

test("follow finds the bar containing a time, boundaries go to the next bar", () => {
  assert.equal(findBarIndexAtTime(BARS, 0), 0);
  assert.equal(findBarIndexAtTime(BARS, 1.99), 0);
  assert.equal(findBarIndexAtTime(BARS, 2), 1);
  assert.equal(findBarIndexAtTime(BARS, 5.5), 2);
  assert.equal(findBarIndexAtTime(BARS, 6), 2);
  assert.equal(findBarIndexAtTime(BARS, 99), 2);
  assert.equal(findBarIndexAtTime([], 1), -1);
  assert.equal(pageIndexForBar(0, 4), 0);
  assert.equal(pageIndexForBar(3, 4), 0);
  assert.equal(pageIndexForBar(4, 4), 1);
  assert.equal(pageIndexForBar(7, 4), 1);
});

const HITS: TrailHit[] = [
  { eventId: "a", time: 0.5 },
  { eventId: "b", time: 1.0 },
  { eventId: "c", time: 1.5 },
];

test("trail Hold accumulates played hits and clears on a backward seek", () => {
  let trail = updateTrail({ ids: [], time: -1 }, HITS, 0.6, "hold");
  assert.deepEqual(trail.ids, ["a"]);
  trail = updateTrail(trail, HITS, 1.2, "hold");
  assert.deepEqual(trail.ids, ["a", "b"]);
  // Same time twice adds nothing; time standing still is not a new note.
  trail = updateTrail(trail, HITS, 1.2, "hold");
  assert.deepEqual(trail.ids, ["a", "b"]);
  // Seeking back before the last time clears the trail (theDAW rule).
  trail = updateTrail(trail, HITS, 0.4, "hold");
  assert.deepEqual(trail.ids, []);
  // Advancing a little past the seek point inks nothing: notes before
  // the seek point do not refill the trail on their own.
  trail = updateTrail(trail, HITS, 0.45, "hold");
  assert.deepEqual(trail.ids, []);
  // …but notes that sound again on the new pass are inked as they play.
  trail = updateTrail(trail, HITS, 1.6, "hold");
  assert.deepEqual(trail.ids, ["a", "b", "c"]);
});

test("trail Flash only shows hits sounding right now", () => {
  const trail = updateTrail({ ids: [], time: -1 }, HITS, 1.02, "flash");
  assert.deepEqual(trail.ids, ["b"]);
  assert.deepEqual(updateTrail(trail, HITS, 1.3, "flash").ids, []);
  assert.deepEqual(updateTrail(trail, HITS, 0.5, "flash").ids, ["a"]);
});
