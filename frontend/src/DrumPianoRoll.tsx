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
  nudgeRollNote,
  parseMidiVelocity,
  pitchToInstrument,
  type RollCommit,
  type RollNote,
} from "./drumRoll";
import { zoomIn as zoomStepIn, zoomOut as zoomStepOut } from "./playback";
import type { PlayheadSource } from "./playback";

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
  /** Live playhead time, published outside React: the Timeline follows
   * this source straight in the DOM, so a playhead moving every frame
   * never re-renders the roll. */
  playheadSource: PlayheadSource;
  /** Shared zoom in px/s (null = fit the whole song); owned by the parent
   * so the roll, staff and waveform zoom together. */
  zoom: number | null;
  onZoomChange: (zoom: number | null) => void;
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
  playheadSource,
  zoom,
  onZoomChange,
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
  const [reclassify, setReclassify] = React.useState(false);
  const [velocityDraft, setVelocityDraft] = React.useState("");
  const [contextMenu, setContextMenu] = React.useState<{ eventId: string; x: number; y: number } | null>(null);
  const [contextIndex, setContextIndex] = React.useState(0);
  const contextMenuRef = React.useRef<HTMLDivElement | null>(null);
  const velocityMenuRef = React.useRef<HTMLInputElement | null>(null);
  const bodyRef = React.useRef<HTMLDivElement | null>(null);

  /** px/s that fits the whole song in the visible grid width. */
  const fitZoom = () => {
    const width = bodyRef.current?.clientWidth ?? 0;
    return width > 0 ? width / Math.max(1, durationSeconds) : 8;
  };
  const zoomIn = () => onZoomChange(zoomStepIn(zoom, fitZoom()));
  const zoomOut = () => onZoomChange(zoomStepOut(zoom, fitZoom()));

  const isLaneVisible = (instrument: string) =>
    soloLane ? soloLane === instrument : !hiddenLanes.includes(instrument);

  React.useEffect(() => {
    const selected = events.find((event) => event.id === selectedEventId);
    setVelocityDraft(selected ? String(selected.velocity) : "");
  }, [selectedEventId, events]);

  React.useEffect(() => {
    const next = notesFromEvents(events);
    baselineRef.current = next;
    setDraftNotes(next);
  }, [events]);

  const selectedNote =
    draftNotes.find((note) => String(note.id) === selectedEventId) ?? null;
  const selectedIsRealEvent =
    selectedNote !== null && events.some((event) => event.id === selectedNote.id);


  const commitSingleNote = (eventId: string, changes: { time_seconds?: number; instrument?: string; velocity?: number }, nextNotes?: RollNote[]) => {
    if (!events.some((event) => event.id === eventId)) return;
    if (nextNotes) { baselineRef.current = nextNotes; setDraftNotes(nextNotes); }
    onCommit({ added: [], changed: [{ eventId, changes }], removed: [] });
  };

  React.useEffect(() => {
    if (!contextMenu) return;
    contextMenuRef.current?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !contextMenuRef.current?.contains(event.target)) setContextMenu(null);
    };
    const closeEscape = (event: KeyboardEvent) => { if (event.key === "Escape") setContextMenu(null); };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", closeEscape); };
  }, [contextMenu]);

  React.useEffect(() => {
    if (contextMenu && contextIndex === INSTRUMENTS.length + 1) velocityMenuRef.current?.focus();
  }, [contextMenu, contextIndex]);

  const commitVelocity = (eventId: string) => {
    const velocity = parseMidiVelocity(velocityDraft);
    const original = events.find((event) => event.id === eventId);
    const currentNote = draftNotes.find((item) => String(item.id) === eventId);
    if (velocity === null || !original || velocity === original.velocity || (currentNote?.velocity !== undefined && Math.round(currentNote.velocity * 127) === velocity)) {
      setVelocityDraft(String(original?.velocity ?? ""));
      return;
    }
    const next = draftNotes.map((item) => String(item.id) === eventId ? { ...item, velocity: velocity / 127 } : item);
    commitSingleNote(eventId, { velocity }, next);
  };

  const applyContextLane = (instrument: string) => {
    if (!contextMenu) return;
    const lane = DRUM_LANES.find((item) => item.instrument === instrument);
    const currentNote = draftNotes.find((item) => String(item.id) === contextMenu.eventId);
    if (!lane || !currentNote || currentNote.pitch === lane.pitch) { setContextMenu(null); return; }
    const next = draftNotes.map((item) => String(item.id) === contextMenu.eventId
      ? { ...item, pitch: lane.pitch } : item);
    commitSingleNote(contextMenu.eventId, { instrument }, next);
    setContextMenu(null);
  };

  const deleteContextNote = () => {
    if (!contextMenu) return;
    const id = contextMenu.eventId;
    if (!events.some((event) => event.id === id)) { setContextMenu(null); return; }
    const next = draftNotes.filter((item) => String(item.id) !== id);
    baselineRef.current = next;
    setDraftNotes(next);
    onCommit({ added: [], changed: [], removed: [id] });
    setContextMenu(null);
  };

  const handleRollKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (contextMenu) {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); setContextMenu(null); return; }
      if ((event.target as HTMLElement).closest("input")) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        event.stopPropagation();
        setContextIndex((current) => (current + (event.key === "ArrowDown" ? 1 : -1) + INSTRUMENTS.length + 2) % (INSTRUMENTS.length + 2));
      }
      if (event.key === "Enter") {
        event.preventDefault();
        event.stopPropagation();
        if (contextIndex < INSTRUMENTS.length) applyContextLane(INSTRUMENTS[contextIndex]);
        else if (contextIndex === INSTRUMENTS.length) deleteContextNote();
        else velocityMenuRef.current?.focus();
      }
      return;
    }
    if (event.ctrlKey || event.metaKey || event.altKey || !selectedEventId) return;
    const target = event.target as HTMLElement;
    if (target.closest("input, textarea, select")) return;
    const note = draftNotes.find((item) => String(item.id) === selectedEventId);
    if (!note || !selectedIsRealEvent) return;
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      event.stopPropagation();
      baselineRef.current = draftNotes.filter((item) => String(item.id) !== selectedEventId);
      setDraftNotes(baselineRef.current);
      onCommit({ added: [], changed: [], removed: [selectedEventId] });
      onSelectEvent(null);
      onSelectEvents([]);
      return;
    }
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
    if (target.closest("button") && !target.closest(".drum-roll-grid")) return;
    event.preventDefault();
    event.stopPropagation();
    const direction = ({ ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down" } as const)[event.key as "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown"];
    const moved = nudgeRollNote(note, direction, gridStepSeconds, durationSeconds, barMarks, event.shiftKey && (direction === "left" || direction === "right"));
    if (moved.start === note.start && moved.pitch === note.pitch) return;
    const next = draftNotes.map((item) => String(item.id) === selectedEventId ? moved : item);
    commitSingleNote(selectedEventId, {
      ...(moved.start !== note.start ? { time_seconds: moved.start } : {}),
      ...(moved.pitch !== note.pitch ? { instrument: pitchToInstrument(moved.pitch) } : {}),
    }, next);
  };

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
    <div className="drum-roll-panel" onKeyDownCapture={handleRollKeyDown} onContextMenu={(event) => event.preventDefault()} onPointerDownCapture={(event) => { if (event.button === 2) { event.stopPropagation(); return; } const target = event.target as HTMLElement; if (!target.closest("input, textarea, select, button")) event.currentTarget.focus(); }} tabIndex={0}>
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
        {selectedNote && selectedIsRealEvent && (
          <label className="drum-roll-velocity-input">
            选中力度
            <input aria-label="选中鼓点力度" type="number" min="1" max="127" step="1"
              value={velocityDraft || String(events.find((item) => item.id === selectedEventId)?.velocity ?? "")}
              onFocus={() => setVelocityDraft(String(events.find((item) => item.id === selectedEventId)?.velocity ?? ""))}
              onChange={(input) => setVelocityDraft(input.target.value)}
              onKeyDown={(input) => { if (input.key === "Enter") { input.preventDefault(); commitVelocity(selectedEventId!); input.currentTarget.blur(); } }}
              onBlur={() => commitVelocity(selectedEventId!)} />
          </label>
        )}
        <span className="drum-roll-zoom" role="group" aria-label="卷帘缩放">
          <button type="button" onClick={zoomOut} title="缩小（看到更长一段）">− 缩小</button>
          <button type="button" onClick={() => onZoomChange(null)} title="整首适配到窗口宽度">适应宽度</button>
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
          source={playheadSource}
          zoom={zoom ?? undefined}
          minZoom={1}
          maxZoom={240}
          onZoomChange={(value) => onZoomChange(value)}
          onPositionChange={(value) => {
            // Scrubbing writes back into the same source the playhead
            // follows, so the head tracks the drag instead of snapping
            // back to the audio time when the gesture ends.
            playheadSource.set(value);
          }}
          onPositionCommitted={(value) => {
            playheadSource.set(value);
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
                            onContextMenu={(event: React.MouseEvent) => {
                              event.preventDefault();
                              event.stopPropagation();
                              const id = String(note.id);
                              if (!events.some((item) => item.id === id)) return;
                              onSelectEvent(id);
                              onSelectEvents([id]);
                              setVelocityDraft(String(events.find((item) => item.id === id)?.velocity ?? ""));
                              setContextIndex(0);
                              setContextMenu({ eventId: id, x: event.clientX, y: event.clientY });
                            }}
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

      {contextMenu && (
        <div ref={contextMenuRef} tabIndex={-1} className="drum-roll-context-menu" role="menu" aria-label="鼓点编辑菜单"
          style={{ position: "fixed", left: contextMenu.x, top: contextMenu.y, zIndex: 1000 }}
          onMouseDown={(event) => event.stopPropagation()}>
          <strong>改类到鼓件</strong>
          {INSTRUMENTS.map((instrument, index) => (
            <button key={instrument} type="button" role="menuitem" className={contextIndex === index ? "active" : ""}
              onMouseEnter={() => setContextIndex(index)} onClick={() => applyContextLane(instrument)}>{instrument}</button>
          ))}
          <button type="button" role="menuitem" className={contextIndex === INSTRUMENTS.length ? "active" : ""} onClick={deleteContextNote}>删除</button>
          <button type="button" role="menuitem" className={contextIndex === INSTRUMENTS.length + 1 ? "active" : ""} onClick={() => velocityMenuRef.current?.focus()}>设力度</button>
          <label>力度数值
            <input ref={velocityMenuRef} aria-label="右键菜单力度" type="number" min="1" max="127" value={velocityDraft}
              onChange={(event) => setVelocityDraft(event.target.value)}
              onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); commitVelocity(contextMenu.eventId); setContextMenu(null); } }}
              onBlur={() => { if (contextMenu) commitVelocity(contextMenu.eventId); }} />
          </label>
        </div>
      )}
      <small className="drum-roll-gesture-help">
        点空白格 = 加音 · 点音符 = 选中 · 拖拽 = 移动 / 改类 · 方向键 = 微移（Shift 按小节）· Delete = 删除 · 右键 = 菜单 · Ctrl+滚轮 = 缩放 · A/D = 上一个/下一个鼓点
      </small>
      <small className="drum-roll-note">
        鼓点是时间点：拉伸只改显示长度，不写入模型；左缘拉伸移动鼓点时间。
        力度条在下方，拖动改力度。画下的新鼓点保存后即为人工修订。
      </small>
    </div>
  );
}
