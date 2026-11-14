/**
 * Drum-lane piano-roll editor, built on @audio-ui/react PianoRoll
 * primitives (MIT, headless — all visuals come from style.css).
 *
 * Time runs on the X axis (seconds, Timeline units); drum instruments are
 * the rows on the Y axis (kick on top, "other" at the bottom — the same
 * order as the timeline). Click empty grid to draw a hit, drag a hit to
 * move it, drag it to another lane to reclassify it, Delete removes it,
 * arrow keys nudge it. The velocity lane below edits velocity by dragging
 * bars. Every gesture commits through the same backend interfaces as the
 * event table (add / PATCH / batch / DELETE); the roll never writes the
 * model itself. Drum hits are points in time: only start, lane and
 * velocity persist — a stretch that only changes display length snaps
 * back on the next sync, while a left-edge resize moves the hit.
 *
 * The component keeps a local draft of the notes so drags stay live; the
 * parent's event list is the source of truth and re-syncs the draft
 * whenever it changes (after a server round-trip).
 */
import React from "react";
import { PianoRoll, Timeline } from "@audio-ui/react";

import { INSTRUMENT_COLORS } from "./WaveformPanel";
import {
  DRUM_LANES,
  HIT_NOTE_LENGTH,
  MAX_PITCH,
  MIN_PITCH,
  diffNotes,
  notesFromEvents,
  pitchToInstrument,
  type RollCommit,
  type RollNote,
} from "./drumRoll";

export type DrumEventLike = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
};

const INSTRUMENTS = DRUM_LANES.map((lane) => lane.instrument);

type DrumPianoRollProps = {
  events: DrumEventLike[];
  durationSeconds: number;
  /** Grid step in seconds (a 16th note at the current tempo). */
  gridStepSeconds: number;
  /** Bar starts for the ruler labels ({value: seconds, label: bar number}). */
  barMarks: { value: number; label: string }[];
  /** Current audio time, in seconds — the playhead. */
  playheadSeconds: number;
  selectedEventId: string | null;
  selectedEventIds: string[];
  onSelectEvent: (eventId: string | null) => void;
  onSelectEvents: (eventIds: string[]) => void;
  /** Persist one committed gesture (add / move / reclassify / delete). */
  onCommit: (commit: RollCommit) => void;
  /** Seek the audio (and the waveform) to a time. */
  onSeek: (timeSeconds: number) => void;
  /** Lanes hidden by the track-header eye toggles (notes stay in the model). */
  hiddenLanes: string[];
  /** The soloed lane, if any (solo wins over hidden). */
  soloLane: string | null;
  onToggleLaneVisibility: (instrument: string) => void;
  onToggleLaneSolo: (instrument: string) => void;
};

export default function DrumPianoRoll({
  events,
  durationSeconds,
  gridStepSeconds,
  barMarks,
  playheadSeconds,
  selectedEventId,
  selectedEventIds,
  onSelectEvent,
  onSelectEvents,
  onCommit,
  onSeek,
  hiddenLanes,
  soloLane,
  onToggleLaneVisibility,
  onToggleLaneSolo,
}: DrumPianoRollProps) {
  const [draftNotes, setDraftNotes] = React.useState<RollNote[]>(() =>
    notesFromEvents(events),
  );
  const baselineRef = React.useRef<RollNote[]>(notesFromEvents(events));
  const draftIdRef = React.useRef(0);
  const playheadDragRef = React.useRef(false);
  const [playhead, setPlayhead] = React.useState(playheadSeconds);
  const [reclassify, setReclassify] = React.useState(false);
  /** Zoom in px per second; null = fit the whole song in the viewport. */
  const [zoom, setZoom] = React.useState<number | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);

  /** px/s that fits the whole song in the visible grid width. */
  const fitZoom = () => {
    const width = bodyRef.current?.clientWidth ?? 0;
    return width > 0 ? width / Math.max(1, durationSeconds) : 8;
  };
  const zoomIn = () =>
    setZoom((current) => Math.min(240, (current ?? fitZoom()) * 1.5));
  const zoomOut = () =>
    setZoom((current) => Math.max(1, (current ?? fitZoom()) / 1.5));

  const isLaneVisible = (instrument: string) =>
    soloLane ? soloLane === instrument : !hiddenLanes.includes(instrument);

  React.useEffect(() => {
    const next = notesFromEvents(events);
    baselineRef.current = next;
    setDraftNotes(next);
  }, [events]);

  React.useEffect(() => {
    if (!playheadDragRef.current) setPlayhead(playheadSeconds);
  }, [playheadSeconds]);

  const selectedNote =
    draftNotes.find((note) => String(note.id) === selectedEventId) ?? null;
  const selectedIsRealEvent =
    selectedNote !== null && events.some((event) => event.id === selectedNote.id);

  const handleCommitted = (value: readonly RollNote[]) => {
    const next = [...value];
    const commit = diffNotes(baselineRef.current, next, events);
    baselineRef.current = next;
    setDraftNotes(next);
    if (commit.added.length || commit.changed.length || commit.removed.length) {
      onCommit(commit);
    }
  };

  return (
    <div className="drum-roll-panel">
      <div className="drum-roll-heading">
        <div>
          <p className="eyebrow">DRUM LANES · PIANO ROLL</p>
          <h3>鼓 lane 钢琴卷帘</h3>
        </div>
        <span>
          {draftNotes.length} 个鼓点 · 点击空白处画音，拖动移音，拖到别的
          lane 改鼓件
        </span>
      </div>
      <div className="drum-roll-toolbar">
        <button
          type="button"
          className={reclassify ? "reclassify-on" : ""}
          aria-pressed={reclassify}
          onClick={() => setReclassify((value) => !value)}
        >
          {reclassify ? "重分类：开" : "重分类：关"}
        </button>
        {reclassify && selectedNote && (
          <label>
            选中鼓点改鼓件
            <select
              value={pitchToInstrument(selectedNote.pitch)}
              disabled={!selectedIsRealEvent}
              onChange={(input) => {
                if (!selectedIsRealEvent) return;
                onCommit({
                  added: [],
                  changed: [
                    {
                      eventId: String(selectedNote.id),
                      changes: { instrument: input.target.value },
                    },
                  ],
                  removed: [],
                });
              }}
            >
              {INSTRUMENTS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
        <small>
          方向键微调选中鼓点，Delete 删除；A / D 跳到上一个 / 下一个鼓点。
        </small>
        <span className="drum-roll-zoom" role="group" aria-label="卷帘缩放">
          <button type="button" onClick={zoomOut} title="缩小（看到更长一段）">− 缩小</button>
          <button type="button" onClick={() => setZoom(null)} title="整首适配到窗口宽度">适应宽度</button>
          <button type="button" onClick={zoomIn} title="放大（看清单个鼓点）">放大 +</button>
          <small>{zoom === null ? "适应宽度" : `${zoom.toFixed(0)} px/s`}</small>
        </span>
        {soloLane && (
          <small className="drum-roll-solo-note">
            独奏中：{soloLane}（点 lane 头的 S 取消）
          </small>
        )}
      </div>
      <div className="drum-roll-main">
        <Timeline.Root
          className="drum-roll-timeline"
          duration={durationSeconds}
          snapStep={gridStepSeconds}
          position={playhead}
          zoom={zoom ?? undefined}
          minZoom={1}
          maxZoom={240}
          onZoomChange={(value) => setZoom(value)}
          onPositionChange={(value) => {
            playheadDragRef.current = true;
            setPlayhead(value);
          }}
          onPositionCommitted={(value) => {
            playheadDragRef.current = false;
            onSeek(value);
          }}
        >
          <div className="drum-roll-corner" aria-hidden="true" />
          <Timeline.Viewport className="drum-roll-viewport">
            <Timeline.Ruler className="drum-roll-ruler">
              {barMarks.map((mark) => (
                <Timeline.Mark key={mark.value} value={mark.value} className="drum-roll-mark">
                  {mark.label}
                </Timeline.Mark>
              ))}
            </Timeline.Ruler>
            <div className="drum-roll-body" ref={bodyRef}>
              <PianoRoll.Root
                value={draftNotes}
                onValueChange={(value) => setDraftNotes([...value])}
                onValueCommitted={handleCommitted}
                onSelectionChange={(selection) => {
                  const ids = selection
                    .map((id) => String(id))
                    .filter((id) => events.some((event) => event.id === id));
                  onSelectEvents(ids);
                  onSelectEvent(ids[0] ?? null);
                }}
                selection={selectedEventIds}
                mode="draw"
                minPitch={MIN_PITCH}
                maxPitch={MAX_PITCH}
                minLength={HIT_NOTE_LENGTH}
                createNoteId={() => `draft-${Date.now()}-${draftIdRef.current++}`}
                getNoteLabel={(note) =>
                  `${pitchToInstrument(note.pitch)} · ${note.start.toFixed(2)}s`
                }
              >
                <PianoRoll.Grid className="drum-roll-grid">
                  <PianoRoll.Rows>
                    {(pitch) => <PianoRoll.Row key={pitch} pitch={pitch} />}
                  </PianoRoll.Rows>
                  <PianoRoll.Notes>
                    {(note) => {
                      const instrument = pitchToInstrument(note.pitch);
                      return (
                        <PianoRoll.Note
                          key={note.id}
                          note={note}
                          className={isLaneVisible(instrument) ? undefined : "drum-roll-hidden"}
                        >
                          <span
                            className="drum-note-fill"
                            style={{
                              background:
                                INSTRUMENT_COLORS[instrument] ?? "#94a3b8",
                            }}
                            title={`${instrument} · ${note.start.toFixed(3)}s`}
                          />
                          <PianoRoll.NoteHandle edge="start" />
                          <PianoRoll.NoteHandle edge="end" />
                        </PianoRoll.Note>
                      );
                    }}
                  </PianoRoll.Notes>
                  <PianoRoll.Marquee />
                  <Timeline.Playhead className="drum-roll-playhead" />
                </PianoRoll.Grid>
                <PianoRoll.VelocityLane className="drum-roll-velocity">
                  {draftNotes.map((note) => {
                    const instrument = pitchToInstrument(note.pitch);
                    return (
                      <PianoRoll.Velocity
                        key={note.id}
                        note={note}
                        className={
                          isLaneVisible(instrument)
                            ? "drum-velocity-bar"
                            : "drum-velocity-bar drum-roll-hidden"
                        }
                        style={{
                          background:
                            INSTRUMENT_COLORS[instrument] ?? "#94a3b8",
                        }}
                      />
                    );
                  })}
                </PianoRoll.VelocityLane>
              </PianoRoll.Root>
            </div>
          </Timeline.Viewport>
          <div className="drum-roll-labels">
            {DRUM_LANES.map((lane) => {
              const visible = isLaneVisible(lane.instrument);
              const solo = soloLane === lane.instrument;
              return (
                <div
                  key={lane.instrument}
                  className={
                    "drum-roll-label" +
                    (visible ? "" : " drum-roll-label-hidden") +
                    (solo ? " drum-roll-label-solo" : "")
                  }
                >
                  <i style={{ background: INSTRUMENT_COLORS[lane.instrument] ?? "#94a3b8" }} />
                  <span className="drum-roll-label-name">{lane.label}</span>
                  <button
                    type="button"
                    className="drum-roll-lane-toggle"
                    aria-pressed={visible}
                    title={visible ? `隐藏 ${lane.label}` : `显示 ${lane.label}`}
                    onClick={() => onToggleLaneVisibility(lane.instrument)}
                  >
                    {visible ? "👁" : "🚫"}
                  </button>
                  <button
                    type="button"
                    className={"drum-roll-lane-toggle" + (solo ? " drum-roll-lane-solo-on" : "")}
                    aria-pressed={solo}
                    title={solo ? `取消独奏 ${lane.label}` : `独奏 ${lane.label}（只看这一轨）`}
                    onClick={() => onToggleLaneSolo(lane.instrument)}
                  >
                    S
                  </button>
                </div>
              );
            })}
          </div>
        </Timeline.Root>
      </div>
      <small className="drum-roll-note">
        鼓点是时间点：拉伸只改显示长度，不写入模型；左缘拉伸移动鼓点时间。
        力度条在下方，拖动改力度。画下的新鼓点保存后即为人工修订。
      </small>
    </div>
  );
}
