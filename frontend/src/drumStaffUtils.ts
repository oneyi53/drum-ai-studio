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

/** Index of the bar containing `time` (boundaries belong to the bar that
 * starts there; a time at/past the song end stays in the last bar). */
export function findBarIndexAtTime(bars: StaffBar[], time: number): number {
  if (bars.length === 0) return -1;
  let index = bars.length - 1;
  for (let i = 0; i < bars.length; i += 1) {
    if (time < bars[i].end) {
      index = i;
      break;
    }
  }
  return index;
}

/** Page (0-based) holding `barIndex` at `barsPerPage` bars per page. */
export function pageIndexForBar(barIndex: number, barsPerPage: number): number {
  if (barIndex < 0 || barsPerPage <= 0) return 0;
  return Math.floor(barIndex / barsPerPage);
}

/** How the follow-playback trail behaves (theDAW's TRAIL switch). */
export type TrailMode = "hold" | "flash";

export type TrailHit = { eventId: string; time: number };

export type TrailState = {
  /** Event ids the trail currently marks. */
  ids: string[];
  /** Playhead time the trail was last advanced to (-1 = never played). */
  time: number;
};

/** Window around the playhead that counts as "sounding now" in Flash. */
export const TRAIL_FLASH_WINDOW_SECONDS = 0.07;

/** Backward-jump threshold that counts as a seek (clears a Hold trail). */
export const TRAIL_SEEK_BACK_SECONDS = 0.1;

/**
 * Advance the follow-playback trail to `time` (pure: the component calls
 * this from its rAF loop and only re-renders when the ids change).
 *
 * - Hold: every hit the playhead passes stays inked. The window is
 *   (prev.time, time], so a hit is added exactly once.
 * - Flash: only hits sounding right now (|time - hit| <= 0.07s).
 * - A backward jump of more than 0.1s is a seek: the trail clears and
 *   re-accumulates from the seek point (theDAW rule), it does not refill
 *   with the notes before the seek point.
 */
export function updateTrail(
  prev: TrailState,
  hits: TrailHit[],
  time: number,
  mode: TrailMode,
): TrailState {
  if (time < prev.time - TRAIL_SEEK_BACK_SECONDS) {
    prev = { ids: [], time };
  }
  if (mode === "flash") {
    return {
      ids: hits
        .filter((hit) => Math.abs(hit.time - time) <= TRAIL_FLASH_WINDOW_SECONDS)
        .map((hit) => hit.eventId),
      time,
    };
  }
  const fresh = hits
    .filter((hit) => hit.time > prev.time && hit.time <= time)
    .map((hit) => hit.eventId);
  if (fresh.length === 0) return { ids: prev.ids, time };
  return { ids: [...prev.ids, ...fresh], time };
}
