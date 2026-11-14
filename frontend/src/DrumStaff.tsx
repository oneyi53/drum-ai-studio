/**
 * Editable drum staff (VexFlow 5, MIT), sharing the canonical event
 * model with the piano roll.
 *
 * Layout: one system per bar, four bars per page — a long song is never
 * drawn in one go. Each bar is a 4/4 voice of 16 sixteenth slots
 * (see drumStaff.ts for the slot layout); empty slots are rests.
 * Cymbal-only slots get x noteheads; a slot mixing cymbals and drums
 * renders with normal heads (VexFlow carries one head type per note).
 *
 * v1 interactions (same commit interface as the roll — add / PATCH /
 * batch / DELETE through onCommit, never a local model write):
 * - Click a notehead: select that event (synced with the roll and the
 *   event table). Click empty staff: seek the audio to that time.
 * - Drag a note: horizontally moves it in time (snapped to the 16th
 *   grid of its bar), vertically reclassifies it to the nearest lane.
 *   A ghost shows the drop target; the commit lands on release.
 * - Delete / Backspace: delete the selected events.
 * The staff only renders the visible lanes; hidden lanes keep their
 * events in the model and stay editable in the roll/table.
 */
import React from "react";
import { BarlineType, Formatter, Renderer, Stave, StaveNote, Voice } from "vexflow";

import {
  SLOTS_PER_BAR,
  buildStaffBars,
  instrumentAtStep,
  positionForInstrument,
  type StaffBar,
} from "./drumStaff";
import type { RollCommit } from "./drumRoll";
import { INSTRUMENT_COLORS } from "./WaveformPanel";

export type DrumEventLike = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
};

// VexFlow 把 Bravura / Academico 以 base64 data: URL 嵌在包里，入口模块
// 在 import 时就用 FontFace 加载（不依赖 CDN、不断网也能画）。首绘前等
// 字体就绪，避免字体晚到导致第一页符头空白；3 秒超时后照常画。
let musicFontsReady = false;
async function ensureMusicFonts(): Promise<void> {
  if (musicFontsReady || typeof document === "undefined" || !("fonts" in document)) return;
  try {
    await Promise.race([
      Promise.all([
        document.fonts.load('30px "Bravura"', "\uE084"),
        document.fonts.load('10px "Academico"', "4"),
      ]),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ]);
  } catch {
    // 字体没等到也照常画：VexFlow 的 FontFace 是 display:block，
    // 浏览器会在阻塞期后用已加载的字体画出来。
  }
  musicFontsReady = true;
}

export type StaffBarInput = StaffBar;

type DrumStaffProps = {
  events: DrumEventLike[];
  bars: StaffBarInput[];
  /** Lanes currently shown (solo wins over hidden). */
  visibleInstruments: string[];
  selectedEventId: string | null;
  selectedEventIds: string[];
  onSelectEvent: (eventId: string | null) => void;
  onSelectEvents: (eventIds: string[]) => void;
  onCommit: (commit: RollCommit) => void;
  onSeek: (timeSeconds: number) => void;
};

const BARS_PER_PAGE = 4;
const STAVE_HEIGHT = 120;
const STAVE_TOP = 14;
const STAVE_X = 12;

type RenderedHit = {
  eventId: string;
  instrument: string;
  step: number;
  /** Notehead left edge, px inside the SVG. */
  x: number;
  /** Notehead centre y, px inside the SVG. */
  y: number;
  barIndex: number;
  slotIndex: number;
  time: number;
};

type BarGeometry = {
  bar: StaffBar;
  x0: number;
  x1: number;
  y: number;
  sixteenthSeconds: number;
};

type StaffGeometry = {
  hits: RenderedHit[];
  bars: BarGeometry[];
  /** px per diatonic step, calibrated from rendered notes (fallback 5). */
  pxPerStep: number;
  stepRef: number;
  yRef: number;
};

type DragState = {
  eventId: string;
  barIndex: number;
  startTime: number;
  startStep: number;
  startX: number;
  startY: number;
  moved: boolean;
  targetTime: number;
  targetInstrument: string;
} | null;

export default function DrumStaff({
  events,
  bars,
  visibleInstruments,
  selectedEventId,
  selectedEventIds,
  onSelectEvent,
  onSelectEvents,
  onCommit,
  onSeek,
}: DrumStaffProps) {
  const outerRef = React.useRef<HTMLDivElement | null>(null);
  const svgRef = React.useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = React.useState(960);
  const [page, setPage] = React.useState(0);
  const [geometry, setGeometry] = React.useState<StaffGeometry | null>(null);
  const [ghost, setGhost] = React.useState<{ x: number; y: number; label: string } | null>(null);
  const dragRef = React.useRef<DragState>(null);
  const seekCandidateRef = React.useRef<{ x: number; y: number } | null>(null);

  const pageCount = Math.max(1, Math.ceil(bars.length / BARS_PER_PAGE));
  const safePage = Math.min(page, pageCount - 1);
  const pageBars = bars.slice(safePage * BARS_PER_PAGE, (safePage + 1) * BARS_PER_PAGE);
  const visibleSet = React.useMemo(() => new Set(visibleInstruments), [visibleInstruments]);

  React.useEffect(() => {
    const el = outerRef.current;
    if (!el) return;
    const update = () => setContainerWidth(el.clientWidth || 960);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      await ensureMusicFonts();
      if (!cancelled) draw();
    })();
    return () => {
      cancelled = true;
    };
    function draw() {
      const host = svgRef.current;
      if (!host || pageBars.length === 0) {
        setGeometry(null);
        return;
      }
    const visibleEvents = events.filter((event) => visibleSet.has(event.instrument));
    const laid = buildStaffBars(visibleEvents, pageBars);
    host.innerHTML = "";
    const width = Math.max(320, containerWidth - 4);
    const height = STAVE_TOP + pageBars.length * STAVE_HEIGHT + 8;
    const renderer = new Renderer(host, Renderer.Backends.SVG);
    renderer.resize(width, height);
    const context = renderer.getContext();
    // VexFlow 默认黑字黑线，在深色背景上看不见：改成浅色再画。
    context.setFillStyle("#dbe4f0");
    context.setStrokeStyle("#9fb0cc");
    const hits: RenderedHit[] = [];
    const barGeometry: BarGeometry[] = [];
    laid.forEach((barNotes, barIndex) => {
      const y = STAVE_TOP + barIndex * STAVE_HEIGHT;
      const stave = new Stave(STAVE_X, y, width - STAVE_X * 2);
      if (barIndex === 0) stave.setClef("percussion");
      if (safePage === 0 && barIndex === 0) stave.setTimeSignature("4/4");
      if (barIndex === pageBars.length - 1) stave.setEndBarType(BarlineType.END);
      stave.setMeasure(barNotes.bar.number);
      stave.setContext(context).draw();
      // Keep the StaveNote refs: notehead geometry (getAbsoluteX / getYs)
      // is only valid after the voice is formatted and drawn.
      const noteRefs: { note: StaveNote; slotIndex: number; hits: { eventId: string; instrument: string }[] }[] = [];
      const tickables = barNotes.slots.map((slot) => {
        if (slot.hits.length === 0) {
          return new StaveNote({
            keys: ["b/4"],
            duration: "16r",
            clef: "percussion",
          });
        }
        const ascending = [...slot.hits].sort(
          (a, b) =>
            positionForInstrument(a.instrument).step - positionForInstrument(b.instrument).step,
        );
        const allCymbal = ascending.every(
          (hit) => positionForInstrument(hit.instrument).noteType === "x",
        );
        const note = new StaveNote({
          keys: ascending.map((hit) => positionForInstrument(hit.instrument).key),
          duration: "16",
          clef: "percussion",
          autoStem: true,
          ...(allCymbal ? { type: "x" as const } : {}),
        });
        noteRefs.push({
          note,
          slotIndex: slot.index,
          hits: ascending.map((hit) => ({ eventId: hit.eventId, instrument: hit.instrument })),
        });
        return note;
      });
      const voice = new Voice({ numBeats: 4, beatValue: 4 })
        .setStrict(false)
        .addTickables(tickables);
      const formatWidth =
        width - STAVE_X * 2 - (stave.getNoteStartX() - stave.getX()) - 12;
      new Formatter().joinVoices([voice]).format([voice], Math.max(100, formatWidth));
      voice.draw(context, stave);
      for (const ref of noteRefs) {
        const ys = ref.note.getYs();
        ref.hits.forEach((hit, keyIndex) => {
          hits.push({
            eventId: hit.eventId,
            instrument: hit.instrument,
            step: positionForInstrument(hit.instrument).step,
            x: ref.note.getAbsoluteX(),
            y: ys[keyIndex] ?? y + 40,
            barIndex,
            slotIndex: ref.slotIndex,
            time: barNotes.slots[ref.slotIndex].time,
          });
        });
      }
      barGeometry.push({
        bar: barNotes.bar,
        x0: stave.getNoteStartX(),
        x1: stave.getX() + stave.getWidth(),
        y,
        sixteenthSeconds: barNotes.sixteenthSeconds,
      });
    });
    // Calibrate px-per-step from two rendered notes at different steps;
    // fall back to VexFlow's default 5 px per diatonic step.
    let pxPerStep = 5;
    let stepRef = 1;
    let yRef = 0;
    const byStep = new Map<number, number>();
    for (const hit of hits) if (!byStep.has(hit.step)) byStep.set(hit.step, hit.y);
    const steps = [...byStep.keys()];
    if (steps.length >= 2) {
      const a = steps[0];
      const b = steps[1];
      const derived = Math.abs(byStep.get(a)! - byStep.get(b)!) / Math.abs(a - b);
      if (derived > 0.5 && derived < 20) pxPerStep = derived;
      stepRef = a;
      yRef = byStep.get(a)!;
    } else if (steps.length === 1) {
      stepRef = steps[0];
      yRef = byStep.get(steps[0])!;
    }
    setGeometry({ hits, bars: barGeometry, pxPerStep, stepRef, yRef });
    }
  }, [events, pageBars, safePage, visibleSet, containerWidth]);

  const yForStep = (step: number, geo: StaffGeometry) =>
    geo.yRef - (step - geo.stepRef) * geo.pxPerStep;

  const hitAt = (x: number, y: number, geo: StaffGeometry): RenderedHit | null => {
    let best: RenderedHit | null = null;
    let bestScore = Number.POSITIVE_INFINITY;
    for (const hit of geo.hits) {
      const dx = Math.abs(x - (hit.x + 7));
      const dy = Math.abs(y - hit.y);
      if (dx > 14 || dy > 10) continue;
      const score = dx * dx + dy * dy;
      if (score < bestScore) {
        bestScore = score;
        best = hit;
      }
    }
    return best;
  };

  const barAtX = (x: number, y: number, geo: StaffGeometry): BarGeometry | null => {
    for (const bar of geo.bars) {
      if (x >= bar.x0 - 4 && x <= bar.x1 + 4 && y >= bar.y - 4 && y <= bar.y + STAVE_HEIGHT) return bar;
    }
    return null;
  };

  const localPoint = (clientX: number, clientY: number) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return null;
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    const geo = geometry;
    if (!geo || event.button !== 0) return;
    const point = localPoint(event.clientX, event.clientY);
    if (!point) return;
    const hit = hitAt(point.x, point.y, geo);
    if (hit) {
      onSelectEvent(hit.eventId);
      onSelectEvents([hit.eventId]);
      dragRef.current = {
        eventId: hit.eventId,
        barIndex: hit.barIndex,
        startTime: hit.time,
        startStep: hit.step,
        startX: point.x,
        startY: point.y,
        moved: false,
        targetTime: hit.time,
        targetInstrument: hit.instrument,
      };
      seekCandidateRef.current = null;
      (event.currentTarget as HTMLDivElement).setPointerCapture(event.pointerId);
    } else {
      dragRef.current = null;
      seekCandidateRef.current = { x: point.x, y: point.y };
    }
  };

  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const geo = geometry;
    const drag = dragRef.current;
    if (!geo || !drag) return;
    const point = localPoint(event.clientX, event.clientY);
    if (!point) return;
    const dx = point.x - drag.startX;
    const dy = point.y - drag.startY;
    if (!drag.moved && Math.abs(dx) < 3 && Math.abs(dy) < 3) return;
    drag.moved = true;
    const barGeo = geo.bars[drag.barIndex];
    if (!barGeo) return;
    const pxPerSecond = (barGeo.x1 - barGeo.x0) / (barGeo.bar.end - barGeo.bar.start);
    const rawTime = drag.startTime + dx / pxPerSecond;
    const snapped =
      barGeo.bar.start +
      Math.max(
        0,
        Math.min(
          SLOTS_PER_BAR - 1,
          Math.round((rawTime - barGeo.bar.start) / barGeo.sixteenthSeconds),
        ),
      ) *
        barGeo.sixteenthSeconds;
    const targetStep = drag.startStep + Math.round(-dy / geo.pxPerStep);
    const targetInstrument = instrumentAtStep(targetStep);
    drag.targetTime = snapped;
    drag.targetInstrument = targetInstrument;
    setGhost({
      x: barGeo.x0 + (snapped - barGeo.bar.start) * pxPerSecond,
      y: yForStep(positionForInstrument(targetInstrument).step, geo),
      label: `${targetInstrument} · ${snapped.toFixed(2)}s`,
    });
  };

  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    const geo = geometry;
    const drag = dragRef.current;
    dragRef.current = null;
    setGhost(null);
    if (!geo) return;
    const point = localPoint(event.clientX, event.clientY);
    if (!point) return;
    if (drag) {
      if (!drag.moved) return;
      const original = events.find((item) => item.id === drag.eventId);
      if (!original) return;
      const changes: { time_seconds?: number; instrument?: string } = {};
      if (Math.abs(drag.targetTime - original.time_seconds) > 0.001) {
        changes.time_seconds = Math.max(0, drag.targetTime);
      }
      if (drag.targetInstrument !== original.instrument) {
        changes.instrument = drag.targetInstrument;
      }
      if (Object.keys(changes).length > 0) {
        onCommit({ added: [], changed: [{ eventId: drag.eventId, changes }], removed: [] });
      }
      return;
    }
    const seekFrom = seekCandidateRef.current;
    seekCandidateRef.current = null;
    if (!seekFrom) return;
    if (Math.abs(point.x - seekFrom.x) > 3 || Math.abs(point.y - seekFrom.y) > 3) return;
    const barGeo = barAtX(point.x, point.y, geo);
    if (!barGeo) return;
    const pxPerSecond = (barGeo.x1 - barGeo.x0) / (barGeo.bar.end - barGeo.bar.start);
    const time = Math.max(
      barGeo.bar.start,
      Math.min(barGeo.bar.end, barGeo.bar.start + (point.x - barGeo.x0) / pxPerSecond),
    );
    onSeek(time);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if ((event.key === "Delete" || event.key === "Backspace") && selectedEventIds.length > 0) {
      event.preventDefault();
      onCommit({ added: [], changed: [], removed: [...selectedEventIds] });
    }
  };

  const selectedHits = (geometry?.hits ?? []).filter((hit) =>
    selectedEventIds.includes(hit.eventId),
  );

  return (
    <div className="drum-staff-panel">
      <div className="drum-staff-heading">
        <div>
          <p className="eyebrow">DRUM STAFF · EDITABLE</p>
          <h3>鼓谱 · 可直接改</h3>
        </div>
        <span>
          {bars.length} 个小节 · 点符头选中，拖动移时间 / 改鼓件，Delete 删除
        </span>
      </div>
      <div className="drum-staff-toolbar">
        <button
          type="button"
          disabled={safePage <= 0}
          onClick={() => setPage((value) => Math.max(0, value - 1))}
        >
          ← 上一页
        </button>
        <span>
          第 {safePage + 1} / {pageCount} 页 · 第{" "}
          {pageBars.length ? pageBars[0].number : 0}–
          {pageBars.length ? pageBars[pageBars.length - 1].number : 0} 小节
        </span>
        <button
          type="button"
          disabled={safePage >= pageCount - 1}
          onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))}
        >
          下一页 →
        </button>
        <small>每页 {BARS_PER_PAGE} 小节；只画当前页，长歌不一次画全曲。</small>
      </div>
      {pageBars.length === 0 ? (
        <p className="drum-staff-empty">暂无小节网格，先完成一次分析。</p>
      ) : (
        <div
          ref={outerRef}
          className="drum-staff-page"
          tabIndex={0}
          role="application"
          aria-label="可编辑鼓谱"
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={() => {
            dragRef.current = null;
            seekCandidateRef.current = null;
            setGhost(null);
          }}
          onKeyDown={handleKeyDown}
        >
          <div ref={svgRef} className="drum-staff-svg" />
          {selectedHits.map((hit) => (
            <span
              key={hit.eventId}
              className="drum-staff-selected"
              style={{
                left: hit.x - 3,
                top: hit.y - 10,
                background: INSTRUMENT_COLORS[hit.instrument] ?? "#94a3b8",
              }}
              aria-hidden="true"
            />
          ))}
          {ghost && (
            <span className="drum-staff-ghost" style={{ left: ghost.x - 3, top: ghost.y - 10 }}>
              {ghost.label}
            </span>
          )}
        </div>
      )}
      <small className="drum-staff-note">
        与钢琴卷帘共用同一套鼓事件：在谱面上的改动会同步到卷帘、事件表与 MIDI。
        混和弦（底鼓 + 镲同在一拍）暂按普通符头画，鼓件信息仍在事件里。
        {selectedEventId
          ? "已选鼓点与卷帘 / 事件表同步。"
          : "点一个符头开始改。"}
      </small>
    </div>
  );
}
