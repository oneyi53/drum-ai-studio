import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

type DrumEvent = {
  id: string;
  time_seconds: number;
  instrument: string;
  velocity: number;
  manually_corrected: boolean;
};

type Performance = {
  duration_seconds: number;
  events: DrumEvent[];
  tempo_map?: { time_seconds: number; bpm: number; numerator: number; denominator: number }[];
};

type AnalysisSummary = {
  jobId: string;
  projectId: string;
  durationSeconds: number;
  totalEvents: number;
  instruments: Record<string, number>;
  events: DrumEvent[];
  bpm: number;
  tempoMap: NonNullable<Performance["tempo_map"]>;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const INSTRUMENTS = [
  "kick", "snare", "closed_hihat", "open_hihat", "pedal_hihat",
  "ride", "crash", "high_tom", "mid_tom", "low_tom", "other",
];

function responseError(data: Record<string, unknown>, fallback: string): string {
  if (typeof data.detail === "string") return data.detail;
  if (data.detail) return JSON.stringify(data.detail);
  return fallback;
}

function summarizePerformance(
  jobId: string,
  projectId: string,
  performance: Performance,
): AnalysisSummary {
  const instruments: Record<string, number> = {};
  for (const event of performance.events) {
    instruments[event.instrument] = (instruments[event.instrument] ?? 0) + 1;
  }
  return {
    jobId,
    projectId,
    durationSeconds: performance.duration_seconds,
    totalEvents: performance.events.length,
    instruments,
    events: [...performance.events].sort((a, b) => a.time_seconds - b.time_seconds),
    bpm: performance.tempo_map?.[0]?.bpm ?? 120,
    tempoMap: performance.tempo_map ?? [],
  };
}

type TimelineBeat = { time: number; isBar: boolean };

function buildTimelineBeats(duration: number, tempoMap: AnalysisSummary["tempoMap"]): TimelineBeat[] {
  const changes = [...tempoMap].sort((a, b) => a.time_seconds - b.time_seconds);
  const boundaries = [0, ...changes.filter((change) => change.time_seconds > 0).map((change) => change.time_seconds)];
  const beats: TimelineBeat[] = [];
  for (let segment = 0; segment < boundaries.length; segment += 1) {
    const start = boundaries[segment];
    const end = boundaries[segment + 1] ?? duration;
    const active = [...changes].reverse().find((change) => change.time_seconds <= start);
    const bpm = active?.bpm ?? 120;
    const numerator = active?.numerator ?? 4;
    const denominator = active?.denominator ?? 4;
    const beatSeconds = 60 / bpm;
    const beatsPerBar = numerator * 4 / denominator;
    const segmentBeatCount = Math.max(0, Math.ceil((end - start) / beatSeconds));
    for (let beat = 0; beat < segmentBeatCount; beat += 1) {
      const time = start + beat * beatSeconds;
      if (time >= end - 0.000001 || time > duration) break;
      beats.push({ time, isBar: beat % beatsPerBar === 0 });
    }
  }
  if (beats.length === 0 || beats[0].time > 0.000001) beats.unshift({ time: 0, isBar: true });
  return beats;
}

function App() {
  const [file, setFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState("选择一首完整歌曲，上传后启动鼓谱分析。");
  const [busy, setBusy] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [summary, setSummary] = React.useState<AnalysisSummary | null>(null);
  const [newTime, setNewTime] = React.useState("0");
  const [newInstrument, setNewInstrument] = React.useState("kick");
  const [newVelocity, setNewVelocity] = React.useState("96");
  const [quantizeSubdivision, setQuantizeSubdivision] = React.useState("1/16");
  const [quantizeStrength, setQuantizeStrength] = React.useState(100);
  const [history, setHistory] = React.useState({ current_revision: 0, can_undo: false, can_redo: false });
  const [selectedEventId, setSelectedEventId] = React.useState<string | null>(null);
  const [audioTime, setAudioTime] = React.useState(0);
  const [audioDuration, setAudioDuration] = React.useState(0);
  const [activeEventId, setActiveEventId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const timelineBeats = React.useMemo(
    () => summary ? buildTimelineBeats(summary.durationSeconds, summary.tempoMap) : [],
    [summary],
  );

  async function uploadAndAnalyze() {
    if (!file) return;
    setBusy(true);
    setSummary(null);
    setMessage("正在上传音频…");
    try {
      const body = new FormData();
      body.append("audio", file);
      const uploadResponse = await fetch(`${API_BASE}/api/projects`, {
        method: "POST",
        body,
      });
      const project = await uploadResponse.json() as Record<string, unknown>;
      if (!uploadResponse.ok) throw new Error(responseError(project, "上传失败"));
      const projectId = String(project.id);

      setMessage("上传完成，正在创建分析任务…");
      const startResponse = await fetch(
        `${API_BASE}/api/projects/${projectId}/analyze`,
        { method: "POST" },
      );
      const started = await startResponse.json() as Record<string, unknown>;
      if (!startResponse.ok) throw new Error(responseError(started, "无法启动分析"));
      const jobId = String(started.job_id);
      setMessage("分析任务已排队，正在识别鼓件…");

      let completed = false;
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const jobResponse = await fetch(`${API_BASE}/api/analysis-jobs/${jobId}`);
        const job = await jobResponse.json() as {
          status?: string;
          error_message?: string | null;
        };
        if (!jobResponse.ok) throw new Error("无法读取分析任务状态");
        if (job.status === "failed") {
          throw new Error(job.error_message ?? "鼓谱分析失败，请检查后端引擎配置。");
        }
        if (job.status === "completed") {
          completed = true;
          break;
        }
        setMessage(
          job.status === "running"
            ? "正在运行 DrumScript，生成标准鼓事件…"
            : "分析任务已排队，等待引擎处理…",
        );
      }
      if (!completed) throw new Error("分析耗时较长，任务仍在后台运行；请稍后刷新项目结果。");

      await refreshPerformance(projectId, jobId);
      setMessage(`分析完成：项目 ${projectId}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "处理失败，请检查后端服务。");
    } finally {
      setBusy(false);
    }
  }

  async function refreshPerformance(projectId: string, jobId: string) {
    const response = await fetch(`${API_BASE}/api/projects/${projectId}/performance`);
    const result = await response.json() as { performance?: Performance };
    if (!response.ok || !result.performance) {
      throw new Error("无法读取标准鼓事件结果。");
    }
    setSummary(summarizePerformance(jobId, projectId, result.performance));
    const historyResponse = await fetch(`${API_BASE}/api/projects/${projectId}/history`);
    if (historyResponse.ok) setHistory(await historyResponse.json());
  }

  async function moveHistory(direction: "undo" | "redo") {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/${direction}`, { method: "POST" });
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, `${direction} 操作失败`));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage(direction === "undo" ? "已撤销上一步，MIDI 已同步。" : "已重做上一步，MIDI 已同步。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "历史操作失败");
    } finally {
      setSaving(false);
    }
  }

  async function editEvent(eventId: string, changes: Partial<Pick<DrumEvent, "time_seconds" | "instrument" | "velocity">>) {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/projects/${summary.projectId}/events/${eventId}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(changes),
        },
      );
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "无法保存鼓事件"));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage("鼓事件已更新，MIDI 下载也已同步。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "保存鼓事件失败");
    } finally {
      setSaving(false);
    }
  }

  async function addEvent() {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/projects/${summary.projectId}/events`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            time_seconds: Number(newTime),
            instrument: newInstrument,
            velocity: Number(newVelocity),
          }),
        },
      );
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "无法添加鼓事件"));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage("已添加手动鼓事件。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "添加鼓事件失败");
    } finally {
      setSaving(false);
    }
  }

  async function removeEvent(eventId: string) {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/projects/${summary.projectId}/events/${eventId}`,
        { method: "DELETE" },
      );
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "无法删除鼓事件"));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage("鼓事件已删除，MIDI 下载也已同步。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除鼓事件失败");
    } finally {
      setSaving(false);
    }
  }

  async function applyQuantization() {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/quantize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subdivision: quantizeSubdivision, strength: quantizeStrength, apply: true }),
      });
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "量化失败"));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage(`量化已应用：${quantizeSubdivision} 网格，强度 ${quantizeStrength}%，MIDI 已同步。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "量化失败");
    } finally {
      setSaving(false);
    }
  }
  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-mark">D</div>
        <div><strong>DrumAI Studio</strong><span>从整曲到可编辑鼓谱</span></div>
        <span className="status">P2 · 鼓事件编辑</span>
      </header>
      <section className="hero">
        <p className="eyebrow">AI DRUM TRANSCRIPTION WORKSPACE</p>
        <h1>把一首歌，拆解成<br /><em>看得懂、改得动的鼓谱。</em></h1>
        <p className="intro">导入完整混音，启动异步鼓谱分析，并在统一的标准鼓事件上进行人工修订。</p>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">NEW PROJECT</p><h2>导入并分析音频</h2></div><span className="step">01 / 04</span></div>
        <label className="dropzone">
          <input type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,.aac,audio/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <span className="upload-icon">↑</span>
          <strong>{file ? file.name : "选择音频文件"}</strong>
          <small>支持 WAV、MP3、FLAC、M4A、OGG、AAC · 当前上传上限 100 MB</small>
        </label>
        <div className="actions"><span>{message}</span><button disabled={!file || busy} onClick={uploadAndAnalyze}>{busy ? "分析中…" : "上传并分析"}</button></div>
      </section>
      {summary && (
        <section className="result-panel">
          <div className="panel-heading"><div><p className="eyebrow">CANONICAL PERFORMANCE</p><h2>标准鼓事件编辑器</h2></div><span className="complete">可编辑</span></div>
          <div className="history-controls">
            <button disabled={saving || !history.can_undo} onClick={() => void moveHistory("undo")}>↶ 撤销</button>
            <button disabled={saving || !history.can_redo} onClick={() => void moveHistory("redo")}>↷ 重做</button>
            <small>历史版本 {history.current_revision}</small>
          </div>
          <div className="metrics">
            <div><strong>{summary.totalEvents.toLocaleString()}</strong><small>鼓事件</small></div>
            <div><strong>{summary.durationSeconds.toFixed(1)}s</strong><small>音频时长</small></div>
            <div><strong>{Object.keys(summary.instruments).length}</strong><small>鼓件类别</small></div>
          </div>
          <div className="instrument-list">
            {Object.entries(summary.instruments).sort((a, b) => b[1] - a[1]).map(([name, count]) => (
              <span key={name}><strong>{name}</strong><small>{count}</small></span>
            ))}
          </div>
          <div className="quantize-panel">
            <div><p className="eyebrow">RHYTHM TOOLS</p><h3>节奏网格量化</h3><small>按速度变化分段对齐鼓点；预览不会修改原始事件。</small></div>
            <label>网格<select value={quantizeSubdivision} onChange={(event) => setQuantizeSubdivision(event.target.value)}>
              <option value="1/4">1/4 · 四分音符</option>
              <option value="1/8">1/8 · 八分音符</option>
              <option value="1/16">1/16 · 十六分音符</option>
              <option value="1/32">1/32 · 三十二分音符</option>
            </select></label>
            <label className="strength-control">量化强度 <strong>{quantizeStrength}%</strong>
              <input type="range" min="0" max="100" step="5" value={quantizeStrength} onChange={(event) => setQuantizeStrength(Number(event.target.value))} />
            </label>
            <button disabled={saving || quantizeStrength === 0} onClick={applyQuantization}>应用量化并同步 MIDI</button>
          </div>
          <div className="editor-heading">
            <div><p className="eyebrow">EVENT EDITOR</p><h3>添加鼓点</h3></div>
          </div>
          <div className="event-add">
            <label>时间（秒）<input type="number" min="0" max={summary.durationSeconds} step="0.001" value={newTime} onChange={(event) => setNewTime(event.target.value)} /></label>
            <label>鼓件<select value={newInstrument} onChange={(event) => setNewInstrument(event.target.value)}>{INSTRUMENTS.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>
            <label>力度<input type="number" min="1" max="127" value={newVelocity} onChange={(event) => setNewVelocity(event.target.value)} /></label>
            <button disabled={saving} onClick={addEvent}>添加事件</button>
          </div>
          <section className="audio-player">
            <div className="audio-player-heading">
              <div><p className="eyebrow">AUDIO PLAYBACK</p><h3>原音频同步播放</h3></div>
              <span>{audioTime.toFixed(2)}s / {(audioDuration || summary.durationSeconds).toFixed(2)}s</span>
            </div>
            <audio ref={audioRef} controls preload="metadata"
              src={API_BASE + "/api/projects/" + summary.projectId + "/audio"}
              onLoadedMetadata={(event) => setAudioDuration(event.currentTarget.duration || summary.durationSeconds)}
              onDurationChange={(event) => setAudioDuration(event.currentTarget.duration || summary.durationSeconds)}
              onTimeUpdate={(event) => {
                const time = event.currentTarget.currentTime;
                setAudioTime(time);
                let nearest: DrumEvent | null = null;
                let distance = Number.POSITIVE_INFINITY;
                for (const item of summary.events) {
                  const delta = Math.abs(item.time_seconds - time);
                  if (delta < distance) { distance = delta; nearest = item; }
                }
                setActiveEventId(nearest && distance <= 0.14 ? nearest.id : null);
              }}
            />
            <input className="audio-seek" aria-label="音频播放位置" type="range" min="0"
              max={audioDuration || summary.durationSeconds} step="0.01"
              value={Math.min(audioTime, audioDuration || summary.durationSeconds)}
              onChange={(event) => {
                const nextTime = Number(event.target.value);
                if (audioRef.current) audioRef.current.currentTime = nextTime;
                setAudioTime(nextTime);
              }}
            />
            <small>播放时播放头会跟随时间轴移动；点击任一鼓点可跳转到对应音频位置。</small>
          </section>
          <div className="timeline-panel">
            <div className="timeline-heading">
              <div><p className="eyebrow">ARRANGEMENT VIEW</p><h3>鼓点时间轴</h3></div>
              <span>{summary.bpm.toFixed(1)} BPM · {summary.durationSeconds.toFixed(1)} 秒</span>
            </div>
            <div className="tempo-map-labels">
              {(summary.tempoMap.length ? summary.tempoMap : [{ time_seconds: 0, bpm: 120, numerator: 4, denominator: 4 }]).map((change, index) => (
                <span key={change.time_seconds + "-" + index} style={{ left: (change.time_seconds / summary.durationSeconds) * 100 + "%" }}>
                  {change.bpm.toFixed(1)} BPM
                </span>
              ))}
            </div>
            <div className="timeline-ruler"><span>0:00</span><span>{(summary.durationSeconds * 0.25).toFixed(1)}s</span><span>{(summary.durationSeconds * 0.5).toFixed(1)}s</span><span>{(summary.durationSeconds * 0.75).toFixed(1)}s</span><span>{summary.durationSeconds.toFixed(1)}s</span></div>
            <div className="timeline-scroll"><div className="timeline-grid">
              {["kick", "snare", "closed_hihat", "open_hihat", "ride", "crash", "high_tom", "mid_tom", "low_tom", "pedal_hihat", "other"].map((lane) => {
                const laneEvents = summary.events.filter((event) => event.instrument === lane);
                return <div className="timeline-lane" key={lane}><span className="timeline-lane-name">{lane.replace(/_/g, " ")}</span><div className="timeline-track">
                  {timelineBeats.map((beat, index) => <span key={beat.time + "-" + index} className={"timeline-beat " + (beat.isBar ? "bar" : "")} style={{ left: (beat.time / summary.durationSeconds) * 100 + "%" }} />)}
                  <span className="timeline-playhead" style={{ left: `${(audioTime / summary.durationSeconds) * 100}%` }} />
                  {laneEvents.map((event) => <button key={event.id} type="button" className={`timeline-hit ${selectedEventId === event.id ? "selected" : ""} ${activeEventId === event.id ? "active" : ""}`} style={{ left: `${(event.time_seconds / summary.durationSeconds) * 100}%`, opacity: 0.45 + (event.velocity / 127) * 0.55 }} title={`${lane} · ${event.time_seconds.toFixed(3)}s · velocity ${event.velocity}`} aria-label={`选择 ${lane} ${event.time_seconds.toFixed(3)} 秒鼓点`} onClick={() => { setSelectedEventId(event.id); if (audioRef.current) audioRef.current.currentTime = event.time_seconds; setAudioTime(event.time_seconds); document.getElementById(`event-${event.id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }} />)}
                </div></div>;
              })}
            </div></div>
            <small className="timeline-help">点击鼓点可跳转音频并定位事件；绿色播放头随音频移动，标记亮度反映力度。</small>
          </div>
          <div className="event-table-wrap">
            <table className="event-table">
              <thead><tr><th>时间（秒）</th><th>鼓件</th><th>力度</th><th>来源</th><th>操作</th></tr></thead>
              <tbody>
                {summary.events.map((event) => (
                  <tr id={`event-${event.id}`} key={event.id} className={selectedEventId === event.id ? "selected-event-row" : ""}>
                    <td><input aria-label="事件时间" type="number" min="0" max={summary.durationSeconds} step="0.001" defaultValue={event.time_seconds} onBlur={(input) => { const value = Number(input.currentTarget.value); if (value !== event.time_seconds) void editEvent(event.id, { time_seconds: value }); }} /></td>
                    <td><select aria-label="鼓件" defaultValue={event.instrument} onChange={(input) => void editEvent(event.id, { instrument: input.target.value })}>{INSTRUMENTS.map((name) => <option key={name} value={name}>{name}</option>)}</select></td>
                    <td><input aria-label="力度" type="number" min="1" max="127" defaultValue={event.velocity} onBlur={(input) => { const value = Number(input.currentTarget.value); if (value !== event.velocity) void editEvent(event.id, { velocity: value }); }} /></td>
                    <td>{event.manually_corrected ? "人工修订" : "模型"}</td>
                    <td><button className="delete-event" disabled={saving} onClick={() => void removeEvent(event.id)}>删除</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <a className="download-link" href={`${API_BASE}/api/projects/${summary.projectId}/midi`} download>下载最新鼓谱 MIDI</a>
          <small className="job-id">任务 ID：{summary.jobId} · {saving ? "正在保存…" : "编辑自动保存到标准事件和 MIDI"}</small>
        </section>
      )}
      <section className="pipeline">
        {["音频导入", "鼓轨分离 / 转录", "标准鼓事件", "编辑与导出"].map((item, index) => (
          <div className="pipeline-item" key={item}><span>0{index + 1}</span><strong>{item}</strong><small>{index === 0 || index === 2 ? "已接入" : index === 1 ? "引擎运行时依赖" : "编辑器开发中"}</small></div>
        ))}
      </section>
      <footer>提示：分析服务需要在后端安装 DrumScript、CPU PyTorch 与 FFmpeg。模型输出未经人工校对；手动编辑会同步更新标准事件和 MIDI 文件。</footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
