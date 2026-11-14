import React from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.js";

/**
 * Waveform + per-bar loop panel (wavesurfer.js, BSD-3-Clause).
 *
 * Data sources — no new bar model, no new backend endpoints:
 * - Audio: the project's existing audio URL (`/api/projects/:id/audio`), the
 *   same URL the built-in <audio> player uses. WaveSurfer fetches + decodes
 *   it once to draw the waveform; playback runs through its own media path.
 * - Bars: derived in main.tsx from the same tempo-map beats the copy-bar
 *   tool uses (bar-start beats + duration as the final boundary).
 * - Hit markers: the existing event list, coloured by instrument.
 *
 * Interactions:
 * - Click a bar region on the waveform (or a bar button below it) to loop
 *   that bar; click the same bar again (or "停止循环") to stop looping.
 * - Click a hit marker to seek the waveform to that hit and select the event
 *   (the event table scrolls to it, as with the timeline strip).
 * - Click anywhere else on the waveform to seek, as usual.
 * WaveSurfer owns its own playback, so when it starts playing the parent
 * pauses the built-in <audio> element (via onWaveformPlay), and the parent
 * pauses WaveSurfer through the forwarded ref when the <audio> plays.
 */

export type WaveformBar = {
  number: number;
  start: number;
  end: number;
};

export type WaveformHit = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
  manually_corrected: boolean;
};

export type WaveformPanelHandle = {
  pause: () => void;
  seek: (timeSeconds: number) => void;
};

type WaveformPanelProps = {
  audioUrl: string;
  durationSeconds: number;
  bars: WaveformBar[];
  events: WaveformHit[];
  selectedEventId: string | null;
  onSelectEvent: (eventId: string, timeSeconds: number) => void;
  onWaveformPlay: () => void;
};

export const INSTRUMENT_COLORS: Record<string, string> = {
  kick: "#e11d48",
  snare: "#2563eb",
  closed_hihat: "#059669",
  open_hihat: "#65a30d",
  pedal_hihat: "#2dd4bf",
  ride: "#7c3aed",
  crash: "#d97706",
  high_tom: "#0891b2",
  mid_tom: "#c026d3",
  low_tom: "#db2777",
  other: "#94a3b8",
};

const BAR_REGION_COLOR = "rgba(201, 243, 107, 0.10)";
const LOOPED_BAR_REGION_COLOR = "rgba(201, 243, 107, 0.28)";

function barAt(bars: WaveformBar[], number: number): WaveformBar | undefined {
  return bars.find((bar) => bar.number === number);
}

const WaveformPanel = React.forwardRef<WaveformPanelHandle, WaveformPanelProps>(
  function WaveformPanel(
    { audioUrl, durationSeconds, bars, events, selectedEventId, onSelectEvent, onWaveformPlay },
    ref,
  ) {
    const containerRef = React.useRef<HTMLDivElement | null>(null);
    const wavesurferRef = React.useRef<WaveSurfer | null>(null);
    const regionsRef = React.useRef<InstanceType<typeof RegionsPlugin> | null>(null);
    const [ready, setReady] = React.useState(false);
    const [loadError, setLoadError] = React.useState<string | null>(null);
    const [playing, setPlaying] = React.useState(false);
    const [loopBar, setLoopBar] = React.useState<number | null>(null);
    const loopBarRef = React.useRef<number | null>(null);
    const barsRef = React.useRef(bars);
    const eventsRef = React.useRef(events);
    const onWaveformPlayRef = React.useRef(onWaveformPlay);
    const onSelectEventRef = React.useRef(onSelectEvent);
    barsRef.current = bars;
    eventsRef.current = events;
    onWaveformPlayRef.current = onWaveformPlay;
    onSelectEventRef.current = onSelectEvent;
    loopBarRef.current = loopBar;

    const rebuildRegions = React.useCallback(() => {
      const ws = wavesurferRef.current;
      const regions = regionsRef.current;
      if (!ws || !regions || ws.getDuration() <= 0) return;
      regions.clearRegions();
      for (const bar of barsRef.current) {
        const region = regions.addRegion({
          id: `bar-${bar.number}`,
          start: bar.start,
          end: bar.end,
          color: bar.number === loopBarRef.current ? LOOPED_BAR_REGION_COLOR : BAR_REGION_COLOR,
          drag: false,
          resize: false,
        });
        region.element?.setAttribute(
          "title",
          `第 ${bar.number} 小节 ${bar.start.toFixed(2)}s–${bar.end.toFixed(2)}s（点击循环）`,
        );
      }
      for (const event of eventsRef.current) {
        // Zero-length region: wavesurfer renders it as a 2px marker line.
        const region = regions.addRegion({
          id: `hit-${event.id}`,
          start: event.time_seconds,
          end: event.time_seconds,
          color: INSTRUMENT_COLORS[event.instrument] ?? INSTRUMENT_COLORS.other,
          drag: false,
          resize: false,
        });
        region.element?.setAttribute(
          "title",
          `${event.instrument} · ${event.time_seconds.toFixed(3)}s · velocity ${event.velocity}${event.manually_corrected ? " · 人工修订" : ""}`,
        );
      }
    }, []);

    const loopBarByNumber = React.useCallback((number: number) => {
      const ws = wavesurferRef.current;
      const bar = barAt(barsRef.current, number);
      if (!ws || !bar) return;
      if (loopBarRef.current === number) {
        setLoopBar(null);
        return;
      }
      setLoopBar(number);
      // The waveform's own click-to-seek runs after the region click handler
      // (bubbling), so defer our jump to the bar start past that dispatch.
      window.setTimeout(() => {
        const current = wavesurferRef.current;
        if (!current || loopBarRef.current !== number) return;
        current.setTime(bar.start);
        void current.play();
      }, 0);
    }, []);

    React.useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      setReady(false);
      setLoadError(null);
      setPlaying(false);
      setLoopBar(null);
      const regions = RegionsPlugin.create();
      regionsRef.current = regions;
      const ws = WaveSurfer.create({
        container,
        url: audioUrl,
        height: 128,
        waveColor: "#5b6b84",
        progressColor: "#c9f36b",
        cursorColor: "#f5f7ff",
        plugins: [regions],
      });
      wavesurferRef.current = ws;

      const onReady = () => {
        setReady(true);
        rebuildRegions();
      };
      const onPlay = () => {
        setPlaying(true);
        onWaveformPlayRef.current();
      };
      const onPause = () => setPlaying(false);
      const onFinish = () => {
        setPlaying(false);
        const bar = loopBarRef.current === null ? undefined : barAt(barsRef.current, loopBarRef.current);
        if (bar) {
          ws.setTime(bar.start);
          void ws.play();
        }
      };
      const onTimeUpdate = (time: number) => {
        const bar = loopBarRef.current === null ? undefined : barAt(barsRef.current, loopBarRef.current);
        if (bar && time >= bar.end - 0.02) ws.setTime(bar.start);
      };
      const onError = (error: Error) => {
        setLoadError(error?.message ?? "波形加载失败");
      };
      const onRegionClicked = (region: { id: string }) => {
        if (region.id.startsWith("bar-")) {
          loopBarByNumber(Number(region.id.slice(4)));
          return;
        }
        if (region.id.startsWith("hit-")) {
          const eventId = region.id.slice(4);
          const event = eventsRef.current.find((item) => item.id === eventId);
          if (!event) return;
          window.setTimeout(() => {
            wavesurferRef.current?.setTime(event.time_seconds);
          }, 0);
          onSelectEventRef.current(eventId, event.time_seconds);
        }
      };

      ws.on("ready", onReady);
      ws.on("play", onPlay);
      ws.on("pause", onPause);
      ws.on("finish", onFinish);
      ws.on("timeupdate", onTimeUpdate);
      ws.on("error", onError);
      regions.on("region-clicked", onRegionClicked);
      return () => {
        regions.un("region-clicked", onRegionClicked);
        ws.destroy();
        wavesurferRef.current = null;
        regionsRef.current = null;
      };
    }, [audioUrl, loopBarByNumber, rebuildRegions]);

    // Re-draw regions when the bars or the event list change (edits, undo,
    // copy-bar, quantize…). The WaveSurfer instance itself is untouched, so
    // the audio is not re-decoded.
    React.useEffect(() => {
      if (ready) rebuildRegions();
    }, [bars, events, ready, rebuildRegions]);

    React.useImperativeHandle(ref, () => ({
      pause: () => {
        wavesurferRef.current?.pause();
      },
      seek: (timeSeconds: number) => {
        wavesurferRef.current?.setTime(timeSeconds);
      },
    }), []);

    const barHitCounts = React.useMemo(() => {
      const counts = new Map<number, number>();
      for (const bar of bars) counts.set(bar.number, 0);
      for (const event of events) {
        for (const bar of bars) {
          if (event.time_seconds >= bar.start && event.time_seconds < bar.end) {
            counts.set(bar.number, (counts.get(bar.number) ?? 0) + 1);
            break;
          }
        }
      }
      return counts;
    }, [bars, events]);

    const legendInstruments = React.useMemo(() => {
      const present = new Set(events.map((event) => event.instrument));
      return Object.keys(INSTRUMENT_COLORS).filter((name) => present.has(name));
    }, [events]);

    const loopedBar = loopBar === null ? undefined : barAt(bars, loopBar);

    return (
      <div className="waveform-panel">
        <div className="waveform-heading">
          <div>
            <p className="eyebrow">WAVEFORM · BAR LOOP</p>
            <h3>波形与小节循环</h3>
          </div>
          <span>
            {loadError
              ? `波形加载失败：${loadError}`
              : !ready
                ? "正在解码音频，生成波形…"
                : loopedBar
                  ? `正在循环：第 ${loopedBar.number} 小节（${loopedBar.start.toFixed(2)}s–${loopedBar.end.toFixed(2)}s）`
                  : `${bars.length} 个小节 · ${events.length} 个鼓点标记`}
          </span>
        </div>
        <div ref={containerRef} className="waveform-container" />
        <div className="waveform-controls">
          <button
            type="button"
            disabled={!ready}
            onClick={() => {
              const ws = wavesurferRef.current;
              if (!ws) return;
              if (ws.isPlaying()) ws.pause();
              else void ws.play();
            }}
          >
            {playing ? "⏸ 暂停波形" : "▶ 播放波形"}
          </button>
          <button type="button" disabled={!ready || loopBar === null} onClick={() => setLoopBar(null)}>
            停止循环
          </button>
          <small>点波形任意处跳转；点小节区域循环该小节；点鼓点标记跳转到该鼓点。</small>
        </div>
        {ready && bars.length > 0 && (
          <div className="waveform-bars" aria-label="小节循环">
            {bars.map((bar) => (
              <button
                key={bar.number}
                type="button"
                className={loopBar === bar.number ? "waveform-bar-button looped" : "waveform-bar-button"}
                title={`第 ${bar.number} 小节 ${bar.start.toFixed(2)}s–${bar.end.toFixed(2)}s，${barHitCounts.get(bar.number) ?? 0} 个鼓点`}
                onClick={() => loopBarByNumber(bar.number)}
              >
                {bar.number} ({barHitCounts.get(bar.number) ?? 0})
              </button>
            ))}
          </div>
        )}
        {ready && legendInstruments.length > 0 && (
          <div className="waveform-legend" aria-label="鼓点标记颜色">
            {legendInstruments.map((name) => (
              <span key={name}>
                <i style={{ background: INSTRUMENT_COLORS[name] }} />
                {name.replace(/_/g, " ")}
              </span>
            ))}
            {selectedEventId && <em>已选鼓点已在下方表格中高亮</em>}
          </div>
        )}
        <small className="waveform-note">
          波形与下方时间轴共用同一份鼓事件与小节网格；循环只控制波形播放，不改动任何事件。
          时长 {durationSeconds.toFixed(1)}s。
        </small>
      </div>
    );
  },
);

export default WaveformPanel;
