/**
 * Mapping between the canonical DrumEvent model and the editable drum
 * staff (DrumStaff.tsx, VexFlow 5, MIT).
 *
 * Staff positions follow the Weinberg/PAS drum-notation conventions
 * already recorded in the project memory: crash above the staff on a
 * ledger line, hi-hat in the space above the top line, ride on the top
 * line, snare in the 3rd space, high tom in the 4th space, mid tom on
 * the 3rd line, low tom in the 2nd space, kick in the bottom space,
 * pedal hi-hat below the staff.
 *
 * Positions are counted in diatonic steps above the bottom line (E4 =
 * 0): each step is half a staff-line gap (5 px at VexFlow's default
 * 10 px line spacing). Cymbals render with x noteheads, drums with
 * normal heads. A chord that mixes cymbals and drums renders with
 * normal heads — VexFlow's StaveNote carries one head type per note,
 * so the mixed case is a deliberate v1 simplification, not a bug.
 *
 * This module is pure: it knows nothing about VexFlow or the DOM, so
 * it is unit-testable on its own. The component only consumes the
 * slot layout it produces.
 */

export type DrumEventLike = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
};

export type StaffBar = {
  number: number;
  start: number;
  end: number;
};

export type StaffHit = {
  eventId: string;
  instrument: string;
  velocity: number;
  time: number;
};

export type StaffSlot = {
  /** 0-based 16th slot inside the bar. */
  index: number;
  /** Snapped slot time, in seconds. */
  time: number;
  hits: StaffHit[];
};

export type StaffBarNotes = {
  bar: StaffBar;
  /** Seconds per 16th inside this bar (bar length / 16). */
  sixteenthSeconds: number;
  slots: StaffSlot[];
};

/** One drum lane's place on the staff. `step` is diatonic steps above E4. */
export type StaffPosition = {
  instrument: string;
  /** VexFlow key on a treble/percussion staff. */
  key: string;
  step: number;
  /** "x" for cymbals (x notehead), undefined for drums (normal head). */
  noteType?: "x";
  label: string;
};

export const STAFF_POSITIONS: StaffPosition[] = [
  { instrument: "crash", key: "b/5", step: 11, noteType: "x", label: "crash" },
  { instrument: "open_hihat", key: "a/5", step: 10, noteType: "x", label: "open hihat" },
  { instrument: "closed_hihat", key: "g/5", step: 9, noteType: "x", label: "closed hihat" },
  { instrument: "ride", key: "f/5", step: 8, noteType: "x", label: "ride" },
  { instrument: "high_tom", key: "e/5", step: 7, label: "high tom" },
  { instrument: "snare", key: "c/5", step: 5, label: "snare" },
  { instrument: "mid_tom", key: "b/4", step: 4, label: "mid tom" },
  // 低落地嗵按 MuseScore 金标准放 G4（GM 41），不是 Weinberg 的 A4；
  // 与 MusicXML 导出（display-step/octave）保持同一显示位置。
  { instrument: "low_tom", key: "g/4", step: 2, label: "low tom" },
  { instrument: "kick", key: "f/4", step: 1, label: "kick" },
  { instrument: "pedal_hihat", key: "d/4", step: -1, noteType: "x", label: "pedal hihat" },
  { instrument: "other", key: "c/5", step: 5, label: "other" },
];

const POSITION_BY_INSTRUMENT = new Map(
  STAFF_POSITIONS.map((position) => [position.instrument, position]),
);
const FALLBACK = POSITION_BY_INSTRUMENT.get("other")!;

export function positionForInstrument(instrument: string): StaffPosition {
  return POSITION_BY_INSTRUMENT.get(instrument) ?? FALLBACK;
}

export function isCymbal(instrument: string): boolean {
  return positionForInstrument(instrument).noteType === "x";
}

/** Nearest lane for a dragged notehead, by diatonic step. */
export function instrumentAtStep(step: number): string {
  let best = FALLBACK;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const position of STAFF_POSITIONS) {
    if (position.instrument === "other") continue;
    const distance = Math.abs(position.step - step);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = position;
    }
  }
  return best.instrument;
}

/** 16th slots per bar (4/4). */
export const SLOTS_PER_BAR = 16;

/**
 * Lay events out on the bar grid: each bar gets 16 slots, each event
 * snaps to its nearest slot. Events on a bar boundary belong to the
 * bar that starts there; an event at the song end stays in the last
 * bar. Two hits of the same drum in one slot collapse to one note
 * (the earlier hit wins); different drums in one slot form a chord.
 */
export function buildStaffBars(
  events: DrumEventLike[],
  bars: StaffBar[],
): StaffBarNotes[] {
  const sorted = [...events].sort((a, b) => a.time_seconds - b.time_seconds);
  return bars.map((bar) => {
    const sixteenthSeconds = (bar.end - bar.start) / SLOTS_PER_BAR;
    const slots: StaffSlot[] = Array.from({ length: SLOTS_PER_BAR }, (_, index) => ({
      index,
      time: bar.start + index * sixteenthSeconds,
      hits: [],
    }));
    for (const event of sorted) {
      if (event.time_seconds < bar.start) continue;
      if (event.time_seconds > bar.end) continue;
      if (event.time_seconds === bar.end && bar !== bars[bars.length - 1]) continue;
      const raw = (event.time_seconds - bar.start) / sixteenthSeconds;
      const index = Math.max(0, Math.min(SLOTS_PER_BAR - 1, Math.round(raw)));
      const slot = slots[index];
      if (slot.hits.some((hit) => hit.instrument === event.instrument)) continue;
      slot.hits.push({
        eventId: event.id,
        instrument: event.instrument,
        velocity: event.velocity,
        time: event.time_seconds,
      });
    }
    for (const slot of slots) {
      slot.hits.sort(
        (a, b) => positionForInstrument(b.instrument).step - positionForInstrument(a.instrument).step,
      );
    }
    return { bar, sixteenthSeconds, slots };
  });
}

/** Snapped time of a slot inside its bar. */
export function slotTimeSeconds(barNotes: StaffBarNotes, slotIndex: number): number {
  const clamped = Math.max(0, Math.min(SLOTS_PER_BAR - 1, Math.round(slotIndex)));
  return barNotes.bar.start + clamped * barNotes.sixteenthSeconds;
}

/** Snap an arbitrary time to the nearest 16th slot of its bar. */
export function snapToSlot(time: number, barNotes: StaffBarNotes): number {
  const raw = (time - barNotes.bar.start) / barNotes.sixteenthSeconds;
  return slotTimeSeconds(barNotes, raw);
}
