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

type SavedProject = {
  id: string;
  original_filename: string;
  created_at: string;
  status: string;
  latest_job_id: string | null;
  latest_job_status: string | null;
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
const TIMELINE_LANES = [
  "kick", "snare", "closed_hihat", "open_hihat", "ride", "crash",
  "high_tom", "mid_tom", "low_tom", "pedal_hihat", "other",
];
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
  let beatsIntoBar = 0;
  let previousSignature = "";
  for (let segment = 0; segment < boundaries.length; segment += 1) {
    const start = boundaries[segment];
    const end = boundaries[segment + 1] ?? duration;
    const active = [...changes].reverse().find((change) => change.time_seconds <= start);
    const bpm = active?.bpm ?? 120;
    const numerator = active?.numerator ?? 4;
    const denominator = active?.denominator ?? 4;
    const signature = numerator + "/" + denominator;
    const beatSeconds = 60 / bpm;
    const beatsPerBar = numerator * 4 / denominator;
    if (signature !== previousSignature) beatsIntoBar = 0;
    previousSignature = signature;
    const segmentBeatCount = Math.max(0, Math.ceil((end - start) / beatSeconds));
    for (let beat = 0; beat < segmentBeatCount; beat += 1) {
      const time = start + beat * beatSeconds;
      if (time >= end - 0.000001 || time > duration) break;
      beats.push({ time, isBar: beatsIntoBar < 0.000001 });
      beatsIntoBar += 1;
      if (beatsIntoBar >= beatsPerBar - 0.000001) beatsIntoBar = 0;
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
  const [projects, setProjects] = React.useState<SavedProject[]>([]);
  const [newTime, setNewTime] = React.useState("0");
  const [newInstrument, setNewInstrument] = React.useState("kick");
  const [newVelocity, setNewVelocity] = React.useState("96");
  const [quantizeSubdivision, setQuantizeSubdivision] = React.useState("1/16");
  const [quantizeStrength, setQuantizeStrength] = React.useState(100);
  const [quantizePreview, setQuantizePreview] = React.useState<Performance | null>(null);
  const [history, setHistory] = React.useState({ current_revision: 0, can_undo: false, can_redo: false });
  const [selectedEventId, setSelectedEventId] = React.useState<string | null>(null);
  const [audioTime, setAudioTime] = React.useState(0);
  const [audioDuration, setAudioDuration] = React.useState(0);
  const [audioPlaying, setAudioPlaying] = React.useState(false);
  const [loopEnabled, setLoopEnabled] = React.useState(false);
  const [loopStart, setLoopStart] = React.useState(0);
  const [loopEnd, setLoopEnd] = React.useState(0);
  const [metronomeEnabled, setMetronomeEnabled] = React.useState(false);
  const [activeEventId, setActiveEventId] = React.useState<string | null>(null);
  const [hiddenLanes, setHiddenLanes] = React.useState<string[]>([]);
  const [selectedEventIds, setSelectedEventIds] = React.useState<string[]>([]);
  const [batchTimeOffset, setBatchTimeOffset] = React.useState("0.010");
  const [duplicateInterval, setDuplicateInterval] = React.useState("1.000");
  const [duplicateRepeatCount, setDuplicateRepeatCount] = React.useState("1");
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const audioContextRef = React.useRef<AudioContext | null>(null);
  const lastMetronomeBeatRef = React.useRef(-1);
  const timelineBeats = React.useMemo(
    () => summary ? buildTimelineBeats(summary.durationSeconds, summary.tempoMap) : [],
    [summary],
  );
  const activeLoopEnd = loopEnd || audioDuration || summary?.durationSeconds || 0;
  const loopRangeValid = activeLoopEnd > loopStart;

  React.useEffect(() => {
    if (!audioPlaying || !loopEnabled || !loopRangeValid) return;
    let frame = 0;
    const enforceLoop = () => {
      const audio = audioRef.current;
      if (audio && !audio.paused && audio.currentTime >= activeLoopEnd) {
        audio.currentTime = loopStart;
        lastMetronomeBeatRef.current = -1;
      }
      frame = window.requestAnimationFrame(enforceLoop);
    };
    frame = window.requestAnimationFrame(enforceLoop);
    return () => window.cancelAnimationFrame(frame);
  }, [activeLoopEnd, audioPlaying, loopEnabled, loopRangeValid, loopStart]);
  React.useEffect(() => {
    if (!metronomeEnabled || !audioPlaying) return;
    let frame = 0;
    const tick = () => {
      const audio = audioRef.current;
      const context = audioContextRef.current;
      if (audio && !audio.paused && context && timelineBeats.length) {
        const time = audio.currentTime;
        let beatIndex = -1;
        for (let index = 0; index < timelineBeats.length; index += 1) {
          if (timelineBeats[index].time <= time + 0.005) beatIndex = index;
          else break;
        }
        if (beatIndex < lastMetronomeBeatRef.current) lastMetronomeBeatRef.current = -1;
        if (beatIndex >= 0 && beatIndex !== lastMetronomeBeatRef.current) {
          const beat = timelineBeats[beatIndex];
          const oscillator = context.createOscillator();
          const gain = context.createGain();
          oscillator.frequency.value = beat.isBar ? 1320 : 880;
          gain.gain.setValueAtTime(0.0001, context.currentTime);
          gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.004);
          gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.055);
          oscillator.connect(gain);
          gain.connect(context.destination);
          oscillator.start();
          oscillator.stop(context.currentTime + 0.06);
          lastMetronomeBeatRef.current = beatIndex;
        }
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(frame);
  }, [audioPlaying, metronomeEnabled, timelineBeats]);

  React.useEffect(() => () => {
    if (audioContextRef.current) void audioContextRef.current.close();
  }, []);

  function toggleMetronome() {
    if (!audioContextRef.current) audioContextRef.current = new window.AudioContext();
    if (audioContextRef.current.state === "suspended") void audioContextRef.current.resume();
    lastMetronomeBeatRef.current = -1;
    setMetronomeEnabled((enabled) => !enabled);
  }

  async function loadProjects() {
    try {
      const response = await fetch(`${API_BASE}/api/projects?limit=30`);
      if (!response.ok) return;
      const result = await response.json() as { projects?: SavedProject[] };
      setProjects(result.projects ?? []);
    } catch {
      // The API may not be running yet when the workspace first mounts.
    }
  }

  async function restoreProject(projectId: string) {
    if (!projectId) return;
    const project = projects.find((item) => item.id === projectId);
    if (!project) {
      setMessage("找不到该项目，请刷新项目列表。");
      return;
    }
    setSaving(true);
    setSummary(null);
    audioRef.current?.pause();
    setLoopEnabled(false);
    setMetronomeEnabled(false);
    setLoopStart(0);
    setLoopEnd(0);
    setAudioTime(0);
    setAudioDuration(0);
    setSelectedEventId(null);
    setActiveEventId(null);
    setSelectedEventIds([]);
    try {
      let jobId = project.latest_job_id;
      let completed = project.latest_job_status === "completed";
      if (!jobId || project.latest_job_status === "failed") {
        setMessage(project.latest_job_status === "failed" ? "上次分析失败，正在重新启动…" : "正在为该项目启动分析…");
        const startedResponse = await fetch(`${API_BASE}/api/projects/${projectId}/analyze`, { method: "POST" });
        const started = await startedResponse.json() as { job_id?: string; detail?: unknown };
        if (!startedResponse.ok || !started.job_id) {
          throw new Error(responseError(started as Record<string, unknown>, "无法重新启动分析任务。"));
        }
        jobId = started.job_id;
        completed = false;
      }
      for (let attempt = 0; attempt < 180 && !completed; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 1500));
        const response = await fetch(`${API_BASE}/api/analysis-jobs/${jobId}`);
        const job = await response.json() as { status?: string; error_message?: string | null };
        if (!response.ok) throw new Error("无法恢复分析任务状态。");
        if (job.status === "failed") throw new Error(job.error_message ?? "该项目的分析任务失败。");
        completed = job.status === "completed";
        setMessage(completed ? "分析完成，正在恢复鼓谱…" : "已恢复后台分析任务，等待引擎完成…");
      }
      if (!completed) throw new Error("分析仍在后台运行；请稍后刷新项目列表并重试。");
      await refreshPerformance(projectId, jobId);
      await loadProjects();
      setMessage(`已恢复项目：${project.original_filename}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "恢复项目失败");
    } finally {
      setSaving(false);
    }
  }

  React.useEffect(() => {
    void loadProjects();
  }, []);

  async function uploadAndAnalyze() {
    if (!file) return;
    setBusy(true);
    audioRef.current?.pause();
    setSummary(null);
    setAudioPlaying(false);
    setLoopEnabled(false);
    setLoopStart(0);
    setLoopEnd(0);
    setMetronomeEnabled(false);
    setAudioTime(0);
    setAudioDuration(0);
    setSelectedEventId(null);
    setActiveEventId(null);
    setSelectedEventIds([]);
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
      await loadProjects();
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
    setQuantizePreview(null);
    setSelectedEventIds([]);
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

  async function batchEditEvents() {
    if (!summary || !selectedEventIds.length) return;
    const offset = Number(batchTimeOffset);
    if (!Number.isFinite(offset) || offset === 0) { setMessage("请输入非零的时间偏移量。"); return; }
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/events/batch`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_ids: selectedEventIds, time_offset_seconds: offset }),
      });
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "批量移动失败"));
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage(`已批量移动 ${selectedEventIds.length} 个鼓点，生成一条历史记录并同步 MIDI。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "批量移动失败"); }
    finally { setSaving(false); }
  }

  async function duplicateSelectedEvents() {
    if (!summary || !selectedEventIds.length) return;
    const interval = Number(duplicateInterval);
    const repeatCount = Number(duplicateRepeatCount);
    if (!Number.isFinite(interval) || interval <= 0 || !Number.isInteger(repeatCount) || repeatCount < 1 || repeatCount > 16) {
      setMessage("重复间隔必须大于 0 秒，重复次数须为 1–16。"); return;
    }
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/events/duplicate`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_ids: selectedEventIds, interval_seconds: interval, repeat_count: repeatCount }),
      });
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "重复鼓点失败"));
      const count = Number(result.duplicated_count ?? 0);
      await refreshPerformance(summary.projectId, summary.jobId);
      setSelectedEventIds([]);
      setMessage(`已复制所选 ${selectedEventIds.length} 个鼓点并生成 ${count} 个新鼓点；仅创建一条历史记录，MIDI 已同步。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "重复鼓点失败"); }
    finally { setSaving(false); }
  }

  async function batchDeleteEvents() {
    if (!summary || !selectedEventIds.length) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/events/batch`, {
        method: "DELETE", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_ids: selectedEventIds }),
      });
      const result = await response.json() as Record<string, unknown>;
      if (!response.ok) throw new Error(responseError(result, "批量删除失败"));
      const count = selectedEventIds.length;
      await refreshPerformance(summary.projectId, summary.jobId);
      setMessage(`已批量删除 ${count} 个鼓点，生成一条历史记录并同步 MIDI。`);
    } catch (error) { setMessage(error instanceof Error ? error.message : "批量删除失败"); }
    finally { setSaving(false); }
  }

  async function previewQuantization() {
    if (!summary) return;
    setSaving(true);
    try {
      const response = await fetch(`${API_BASE}/api/projects/${summary.projectId}/quantize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subdivision: quantizeSubdivision, strength: quantizeStrength, apply: false }),
      });
      const result = await response.json() as { performance?: Performance } & Record<string, unknown>;
      if (!response.ok || !result.performance) throw new Error(responseError(result, "无法生成量化预览"));
      setQuantizePreview(result.performance);
      const changed = result.performance.events.filter((event) => {
        const original = summary.events.find((item) => item.id === event.id);
        return original !== undefined && Math.abs(original.time_seconds - event.time_seconds) > 0.001;
      }).length;
      setMessage(`量化预览已生成：${changed} 个鼓点将发生移动；原始鼓谱尚未修改。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "量化预览失败");
    } finally {
      setSaving(false);
    }
  }

  async function applyQuantization() {
    if (!summary || !quantizePreview) return;
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
        <div className="saved-projects">
          <label>恢复已保存项目<select value={summary?.projectId ?? ""} disabled={busy || saving} onChange={(event) => void restoreProject(event.target.value)}>
            <option value="">{projects.length ? "选择已保存项目" : "暂无已保存项目"}</option>
            {projects.map((project) => <option key={project.id} value={project.id} >
              {project.original_filename} · {project.latest_job_status ?? project.status}{project.latest_job_status === "failed" ? "（点击重试）" : ""}
            </option>)}
          </select></label>
          <button type="button" onClick={() => void loadProjects()} disabled={busy || saving}>刷新列表</button>
        </div>
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
            <label>网格<select value={quantizeSubdivision} onChange={(event) => { setQuantizeSubdivision(event.target.value); setQuantizePreview(null); }}>
              <option value="1/4">1/4 · 四分音符</option>
              <option value="1/8">1/8 · 八分音符</option>
              <option value="1/16">1/16 · 十六分音符</option>
              <option value="1/32">1/32 · 三十二分音符</option>
            </select></label>
            <label className="strength-control">量化强度 <strong>{quantizeStrength}%</strong>
              <input type="range" min="0" max="100" step="5" value={quantizeStrength} onChange={(event) => { setQuantizeStrength(Number(event.target.value)); setQuantizePreview(null); }} />
            </label>
            <button disabled={saving || quantizeStrength === 0} onClick={previewQuantization}>预览量化</button>
            <button disabled={saving || !quantizePreview} onClick={applyQuantization}>确认应用并同步 MIDI</button>
            {quantizePreview && <small className="quantize-preview-status">
              预览：{quantizePreview.events.filter((event) => {
                const original = summary.events.find((item) => item.id === event.id);
                return original !== undefined && Math.abs(original.time_seconds - event.time_seconds) > 0.001;
              }).length} / {summary.totalEvents} 个鼓点将移动；确认后才写入历史记录。
            </small>}
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
              onPlay={() => setAudioPlaying(true)}
              onPause={() => setAudioPlaying(false)}
              onEnded={() => setAudioPlaying(false)}
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
            <div className="loop-controls">
              <label className="loop-toggle"><input type="checkbox" checked={loopEnabled} disabled={!loopRangeValid} onChange={(event) => setLoopEnabled(event.target.checked)} /> A–B 循环</label>
              <button type="button" className={metronomeEnabled ? "metronome-on" : ""} onClick={toggleMetronome}>{metronomeEnabled ? "关闭节拍器" : "开启节拍器"}</button>
              <span>A：{loopStart.toFixed(2)}s</span>
              <button type="button" onClick={() => {
                const point = audioRef.current?.currentTime ?? audioTime;
                setLoopStart(point);
                if (loopEnd > 0 && loopEnd <= point) setLoopEnd(audioDuration || summary.durationSeconds);
              }}>设为 A 点</button>
              <span>B：{activeLoopEnd.toFixed(2)}s</span>
              <button type="button" disabled={(audioRef.current?.currentTime ?? audioTime) <= loopStart} onClick={() => setLoopEnd(audioRef.current?.currentTime ?? audioTime)}>设为 B 点</button>
              <button type="button" onClick={() => { setLoopStart(0); setLoopEnd(audioDuration || summary.durationSeconds); setLoopEnabled(false); }}>重置</button>
            </div>
            <small>播放时播放头会跟随时间轴移动；点击任一鼓点可跳转音频位置。设置 A/B 点可循环练习指定段落。</small>
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
            <div className="timeline-lane-filters" aria-label="时间轴轨道显示筛选">
              <span>显示轨道</span>
              <button type="button" onClick={() => setHiddenLanes([])} disabled={hiddenLanes.length === 0}>全部显示</button>
              <button type="button" onClick={() => setHiddenLanes(TIMELINE_LANES)} disabled={hiddenLanes.length === TIMELINE_LANES.length}>全部隐藏</button>
              {TIMELINE_LANES.map((lane) => <label key={lane}>
                <input type="checkbox" checked={!hiddenLanes.includes(lane)} onChange={(event) => setHiddenLanes((current) => event.target.checked ? current.filter((item) => item !== lane) : [...current, lane])} />
                {lane.replace(/_/g, " ")}
              </label>)}
            </div>
            <div className="timeline-scroll"><div className="timeline-grid">
              {TIMELINE_LANES.filter((lane) => !hiddenLanes.includes(lane)).map((lane) => {
                const laneEvents = summary.events.filter((event) => event.instrument === lane);
                return <div className="timeline-lane" key={lane}><span className="timeline-lane-name">{lane.replace(/_/g, " ")}</span><div className="timeline-track">
                  {loopEnabled && loopRangeValid && <span className="timeline-loop-range" style={{ left: (loopStart / summary.durationSeconds) * 100 + "%", width: ((activeLoopEnd - loopStart) / summary.durationSeconds) * 100 + "%" }} />}
                  {timelineBeats.map((beat, index) => <span key={beat.time + "-" + index} className={"timeline-beat " + (beat.isBar ? "bar" : "")} style={{ left: (beat.time / summary.durationSeconds) * 100 + "%" }} />)}
                  {summary.tempoMap.filter((change) => change.time_seconds > 0).map((change) => <span key={"tempo-" + change.time_seconds} className="timeline-tempo-change" style={{ left: (change.time_seconds / summary.durationSeconds) * 100 + "%" }} />)}
                  <span className="timeline-playhead" style={{ left: `${(audioTime / summary.durationSeconds) * 100}%` }} />
                  {laneEvents.map((event) => <button key={event.id} type="button" className={`timeline-hit ${selectedEventId === event.id ? "selected" : ""} ${activeEventId === event.id ? "active" : ""}`} style={{ left: `${(event.time_seconds / summary.durationSeconds) * 100}%`, opacity: 0.45 + (event.velocity / 127) * 0.55 }} title={`${lane} · ${event.time_seconds.toFixed(3)}s · velocity ${event.velocity}`} aria-label={`选择 ${lane} ${event.time_seconds.toFixed(3)} 秒鼓点`} onClick={() => { setSelectedEventId(event.id); if (audioRef.current) audioRef.current.currentTime = event.time_seconds; setAudioTime(event.time_seconds); document.getElementById(`event-${event.id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }} />)}
                </div></div>;
              })}
            </div></div>
            <small className="timeline-help">点击鼓点可跳转音频并定位事件；绿色播放头随音频移动，标记亮度反映力度。</small>
          </div>
          <div className="event-batch-controls">
            <label><input type="checkbox" checked={selectedEventIds.length === summary.events.length && summary.events.length > 0} onChange={(event) => setSelectedEventIds(event.target.checked ? summary.events.map((item) => item.id) : [])} /> 全选</label>
            <span>已选 {selectedEventIds.length} 个</span>
            <label>时间偏移（秒）<input type="number" step="0.001" value={batchTimeOffset} onChange={(event) => setBatchTimeOffset(event.target.value)} /></label>
            <button type="button" disabled={saving || selectedEventIds.length === 0 || !Number.isFinite(Number(batchTimeOffset)) || Number(batchTimeOffset) === 0} onClick={() => void batchEditEvents()}>批量移动</button>
            <button type="button" className="delete-event" disabled={saving || selectedEventIds.length === 0} onClick={() => void batchDeleteEvents()}>批量删除</button>
            <label>重复间隔（秒）<input type="number" min="0.001" step="0.001" value={duplicateInterval} onChange={(event) => setDuplicateInterval(event.target.value)} /></label>
            <label>重复次数<input type="number" min="1" max="16" step="1" value={duplicateRepeatCount} onChange={(event) => setDuplicateRepeatCount(event.target.value)} /></label>
            <button type="button" disabled={saving || selectedEventIds.length === 0 || Number(duplicateInterval) <= 0 || !Number.isInteger(Number(duplicateRepeatCount)) || Number(duplicateRepeatCount) < 1 || Number(duplicateRepeatCount) > 16} onClick={() => void duplicateSelectedEvents()}>复制/重复所选</button>
          </div>
          <div className="event-table-wrap">
            <table className="event-table">
              <thead><tr><th>选择</th><th>时间（秒）</th><th>鼓件</th><th>力度</th><th>来源</th><th>操作</th></tr></thead>
              <tbody>
                {summary.events.map((event) => (
                  <tr id={`event-${event.id}`} key={`${event.id}-${event.time_seconds}-${event.instrument}-${event.velocity}`} className={selectedEventId === event.id ? "selected-event-row" : ""}>
                    <td><input aria-label={`选择 ${event.instrument} 事件`} type="checkbox" checked={selectedEventIds.includes(event.id)} onChange={(input) => setSelectedEventIds((current) => input.target.checked ? [...current, event.id] : current.filter((id) => id !== event.id))} /></td>
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
          <a className="download-link musicxml-link" href={`${API_BASE}/api/projects/${summary.projectId}/musicxml`} download>下载可编辑 MusicXML 乐谱</a>
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
