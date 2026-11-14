/**
 * Mapping between the canonical DrumEvent model and @audio-ui/react
 * PianoRoll notes — the only place that knows how a drum lane becomes a
 * piano-roll row.
 *
 * The roll is pitch-based, so each drum lane gets a fixed pitch. The
 * pitches are consecutive and ordered to match the timeline's lane order
 * (kick on top, "other" at the bottom); they are row keys only, NOT GM
 * pitches — the MIDI export path uses the canonical DrumEvent model, never
 * the roll. Drum hits are points in time, so every note carries the same
 * short display length; only start, lane and velocity persist to the
 * model. A left-edge resize moves the hit (its start changes); a
 * right-edge resize only changes the display length and snaps back on
 * the next sync.
 */
import type { PianoRoll } from "@audio-ui/react";

export type RollNote = PianoRoll.Root.Note;

export type DrumEventLike = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
};

/** Display length of one hit on the roll, in seconds. */
export const HIT_NOTE_LENGTH = 0.2;

/** Lanes top-to-bottom: the same order as TIMELINE_LANES in main.tsx. */
export const DRUM_LANES: { instrument: string; pitch: number; label: string }[] = [
  { instrument: "kick", pitch: 46, label: "kick" },
  { instrument: "snare", pitch: 45, label: "snare" },
  { instrument: "closed_hihat", pitch: 44, label: "closed hihat" },
  { instrument: "open_hihat", pitch: 43, label: "open hihat" },
  { instrument: "ride", pitch: 42, label: "ride" },
  { instrument: "crash", pitch: 41, label: "crash" },
  { instrument: "high_tom", pitch: 40, label: "high tom" },
  { instrument: "mid_tom", pitch: 39, label: "mid tom" },
  { instrument: "low_tom", pitch: 38, label: "low tom" },
  { instrument: "pedal_hihat", pitch: 37, label: "pedal hihat" },
  { instrument: "other", pitch: 36, label: "other" },
];

export const MIN_PITCH = 36;
export const MAX_PITCH = 46;

const PITCH_BY_INSTRUMENT = new Map(DRUM_LANES.map((lane) => [lane.instrument, lane.pitch]));
const INSTRUMENT_BY_PITCH = new Map(DRUM_LANES.map((lane) => [lane.pitch, lane.instrument]));

export function instrumentToPitch(instrument: string): number {
  return PITCH_BY_INSTRUMENT.get(instrument) ?? PITCH_BY_INSTRUMENT.get("other")!;
}

export function pitchToInstrument(pitch: number): string {
  return INSTRUMENT_BY_PITCH.get(pitch) ?? "other";
}

export function velocityToMidi(velocity01: number | undefined): number {
  if (velocity01 === undefined) return 96;
  return Math.max(1, Math.min(127, Math.round(velocity01 * 127)));
}

export function notesFromEvents(events: DrumEventLike[]): RollNote[] {
  return [...events]
    .sort((a, b) => a.time_seconds - b.time_seconds)
    .map((event) => ({
      id: event.id,
      pitch: instrumentToPitch(event.instrument),
      start: event.time_seconds,
      length: HIT_NOTE_LENGTH,
      velocity: Math.max(1, Math.min(127, event.velocity)) / 127,
    }));
}

export type NotePatch = {
  eventId: string;
  changes: {
    time_seconds?: number;
    instrument?: string;
    velocity?: number;
  };
};

export type RollCommit = {
  /** Notes drawn on the roll that have no event yet. */
  added: { time_seconds: number; instrument: string; velocity: number }[];
  /** Existing events whose time, lane or velocity changed. */
  changed: NotePatch[];
  /** Event ids whose notes were removed from the roll. */
  removed: string[];
};

const TIME_EPSILON = 0.001;

/**
 * Diff a committed roll value against the pre-gesture notes and express
 * the difference as model operations. Length-only changes are ignored:
 * drum hits have no duration in the canonical model.
 */
export function diffNotes(
  before: RollNote[],
  after: RollNote[],
  events: DrumEventLike[],
): RollCommit {
  const beforeById = new Map(before.map((note) => [String(note.id), note]));
  const afterById = new Map(after.map((note) => [String(note.id), note]));
  const eventById = new Map(events.map((event) => [event.id, event]));

  const added: RollCommit["added"] = [];
  const changed: NotePatch[] = [];
  const removed: string[] = [];

  for (const note of after) {
    const id = String(note.id);
    const event = eventById.get(id);
    if (!event) {
      added.push({
        time_seconds: Math.max(0, note.start),
        instrument: pitchToInstrument(note.pitch),
        velocity: velocityToMidi(note.velocity),
      });
      continue;
    }
    const changes: NotePatch["changes"] = {};
    if (Math.abs(note.start - event.time_seconds) > TIME_EPSILON) {
      changes.time_seconds = Math.max(0, note.start);
    }
    const instrument = pitchToInstrument(note.pitch);
    if (instrument !== event.instrument) changes.instrument = instrument;
    const velocity = velocityToMidi(note.velocity);
    if (velocity !== event.velocity) changes.velocity = velocity;
    if (Object.keys(changes).length > 0) {
      changed.push({ eventId: id, changes });
    }
  }

  for (const note of before) {
    const id = String(note.id);
    if (eventById.has(id) && !afterById.has(id)) removed.push(id);
  }

  return { added, changed, removed };
}
