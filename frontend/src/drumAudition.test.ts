import assert from "node:assert/strict";
import test from "node:test";

import {
  drumVoiceForInstrument,
  normalizedAuditionVelocity,
} from "./lib/drumAudition";

test("drum audition maps kick, snare, hats, toms and cymbals to five synth voices", () => {
  assert.equal(drumVoiceForInstrument("kick"), "kick");
  assert.equal(drumVoiceForInstrument("snare"), "snare");
  assert.equal(drumVoiceForInstrument("closed_hihat"), "hat");
  assert.equal(drumVoiceForInstrument("open_hihat"), "hat");
  assert.equal(drumVoiceForInstrument("pedal_hihat"), "hat");
  assert.equal(drumVoiceForInstrument("high_tom"), "tom");
  assert.equal(drumVoiceForInstrument("mid_tom"), "tom");
  assert.equal(drumVoiceForInstrument("low_tom"), "tom");
  assert.equal(drumVoiceForInstrument("crash"), "crash");
  assert.equal(drumVoiceForInstrument("ride"), "crash");
});

test("audition velocity is clamped to a safe normalized gain", () => {
  assert.equal(normalizedAuditionVelocity(0), 1 / 127);
  assert.equal(normalizedAuditionVelocity(96), 96 / 127);
  assert.equal(normalizedAuditionVelocity(200), 1);
});
