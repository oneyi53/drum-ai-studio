import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

type DrumEvent = { id: number; onset_seconds: number; instrument: string; velocity: number };
type Project = { id: string; filename: string; size_bytes: number; created_at: string; status: string };

const INSTRUMENTS = [
  "kick", "snare", "closed_hat", "open_hat",
  "low_tom", "mid_tom", "high_tom", "crash", "ride",
];


const GM_DRUM_PITCH: Record<string, number> = {
  kick: 36, snare: 38, closed_hat: 42, open_hat: 46,
  low_tom: 41, mid_tom: 45, high_tom: 48, crash: 49, ride: 51,
};
const STAFF_POSITION: Record<string, { step: string; octave: number; y: number }> = {
  kick: { step: "F", octave: 4, y: 94 },
  snare: { step: "C", octave: 5, y: 64 },
  closed_hat: { step: "G", octave: 5, y: 19 },
  open_hat: { step: "G", octave: 5, y: 19 },
  low_tom: { step: "A", octave: 4, y: 79 },
  mid_tom: { step: "D", octave: 5, y: 49 },
  high_tom: { step: "F", octave: 5, y: 34 },
  crash: { step: "A", octave: 5, y: 4 },
  ride: { step: "E", octave: 5, y: 34 },
};

function escapeXml(value: string): string {
  const entities: Record<string, string> = {
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;",
  };
  return value.replace(/[&<>"']/g, (character) => entities[character] ?? character);
}

function buildMusicXml(events: DrumEvent[], bpm: number): string {
  const ticksPerMeasure = 16;
  const totalTicks = Math.max(ticksPerMeasure, ...events.map((event) =>
    Math.round(event.onset_seconds * bpm / 60 * 4) + 1));
  const measureCount = Math.ceil(totalTicks / ticksPerMeasure);
  const grouped = new Map<number, DrumEvent[]>();
  for (const event of events) {
    const tick = Math.max(0, Math.round(event.onset_seconds * bpm / 60 * 4));
    grouped.set(tick, [...(grouped.get(tick) ?? []), event]);
  }
  const scoreInstruments = INSTRUMENTS.map((kind) => {
    const id = "I" + kind;
    return `      <score-instrument id="${id}"><instrument-name>${escapeXml(kind)}</instrument-name></score-instrument>`;
  }).join("\n");
  const midiInstruments = INSTRUMENTS.map((kind) => {
    const id = "I" + kind;
    return `      <midi-instrument id="${id}"><midi-channel>10</midi-channel><midi-program>1</midi-program><midi-unpitched>${GM_DRUM_PITCH[kind]}</midi-unpitched></midi-instrument>`;
  }).join("\n");
  const measures = Array.from({ length: measureCount }, (_, measureIndex) => {
    const start = measureIndex * ticksPerMeasure;
    const end = start + ticksPerMeasure;
    const ticks = [...grouped.keys()].filter((tick) => tick >= start && tick < end).sort((a, b) => a - b);
    let cursor = start;
    const body: string[] = [];
    for (const tick of ticks) {
      if (tick > cursor) body.push(`      <note><rest/><duration>${tick - cursor}</duration><voice>1</voice></note>`);
      const simultaneous = grouped.get(tick) ?? [];
      simultaneous.forEach((event, index) => {
        const position = STAFF_POSITION[event.instrument];
        body.push(`      <note>${index ? "<chord/>" : ""}<unpitched><display-step>${position.step}</display-step><display-octave>${position.octave}</display-octave></unpitched><duration>1</duration><instrument id="I${event.instrument}"/><voice>1</voice><type>16th</type><notehead>${event.instrument.includes("hat") || event.instrument === "crash" || event.instrument === "ride" ? "x" : "normal"}</notehead></note>`);
      });
      cursor = tick + 1;
    }
    if (cursor < end) body.push(`      <note><rest/><duration>${end - cursor}</duration><voice>1</voice></note>`);
    const attributes = measureIndex === 0
      ? `      <attributes><divisions>4</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>percussion</sign><line>2</line></clef></attributes>
      <direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit><per-minute>${bpm}</per-minute></metronome></direction-type><sound tempo="${bpm}"/></direction>`
      : "";
    return `    <measure number="${measureIndex + 1}">
${attributes}
${body.join("\n")}
    </measure>`;
  }).join("\n");
  return `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0"><work><work-title>DrumAI Studio drum transcription</work-title></work><identification><encoding><software>DrumAI Studio</software></encoding></identification>
  <part-list><score-part id="P1"><part-name>Drum set</part-name>
${scoreInstruments}\n${midiInstruments}
  </score-part></part-list>
  <part id="P1">
${measures}
  </part>
</score-partwise>
`;
}

function downloadMusicXml(events: DrumEvent[], bpm: number): void {
  const xml = buildMusicXml(events, bpm);
  const url = URL.createObjectURL(new Blob([xml], { type: "application/vnd.recordare.musicxml+xml;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "drumai-transcription.musicxml";
  link.click();
  URL.revokeObjectURL(url);
}

function App() {
  const [file, setFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState("选择一首完整歌曲，创建分析项目。");
  const [busy, setBusy] = React.useState(false);
  const [audioFile, setAudioFile] = React.useState<File | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [currentTime, setCurrentTime] = React.useState(0);
  const [manualTime, setManualTime] = React.useState("0");
  const [instrument, setInstrument] = React.useState("kick");
  const [velocity, setVelocity] = React.useState(100);
  const [tempo, setTempo] = React.useState(120);
  const [events, setEvents] = React.useState<DrumEvent[]>([]);
  const [nextId, setNextId] = React.useState(1);
  const [importMessage, setImportMessage] = React.useState("");
  const [saveMessage, setSaveMessage] = React.useState("");
  const [projectId, setProjectId] = React.useState<string | null>(null);
  const [serverReady, setServerReady] = React.useState(false);
  const [projects, setProjects] = React.useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = React.useState("");
  const [projectBusy, setProjectBusy] = React.useState(false);
  const saveQueueRef = React.useRef<Promise<void>>(Promise.resolve());
  const audioRef = React.useRef<HTMLAudioElement>(null);

  const annotationStorageKey = audioFile ? "drumai:annotations:" + audioFile.name + ":" + audioFile.size + ":" + audioFile.lastModified : null;

  React.useEffect(() => {
    if (!audioFile) {
      setAudioUrl("");
      return;
    }
    const url = URL.createObjectURL(audioFile);
    setAudioUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [audioFile]);

  React.useEffect(() => {
    if (!annotationStorageKey || projectId) return;
    try {
      window.localStorage.setItem(annotationStorageKey, JSON.stringify(events));
    } catch {
      setSaveMessage("浏览器存储不可用；请及时导出 CSV 备份。");
    }
  }, [annotationStorageKey, events, projectId]);

  async function refreshProjects() {
    try {
      const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
      const response = await fetch(`${base}/api/projects`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "读取项目列表失败");
      setProjects(Array.isArray(data.projects) ? data.projects as Project[] : []);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "读取项目列表失败。");
    }
  }

  React.useEffect(() => { void refreshProjects(); }, []);

  async function openProject() {
    if (!selectedProjectId) return;
    setProjectBusy(true);
    setMessage("正在重新打开项目并读取原始音频…");
    try {
      const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
      const project = projects.find((item) => item.id === selectedProjectId);
      if (!project) throw new Error("所选项目不存在于当前列表中。");
      const response = await fetch(`${base}/api/projects/${selectedProjectId}/audio`);
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? "读取项目音频失败");
      }
      const blob = await response.blob();
      const restoredFile = new File([blob], project.filename, { type: blob.type || "audio/mpeg" });
      setProjectId(project.id);
      setServerReady(false);
      setEvents([]);
      setNextId(1);
      setAudioFile(restoredFile);
      setFile(restoredFile);
      setCurrentTime(0);
      setManualTime("0");
      setMessage(`已重新打开项目：${project.filename}。正在载入服务器标注。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "重新打开项目失败。");
    } finally {
      setProjectBusy(false);
    }
  }

  React.useEffect(() => {
    if (!projectId) return;
    setServerReady(false);
    let cancelled = false;
    async function loadReferenceEvents() {
      try {
        const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
        const response = await fetch(`${base}/api/projects/${projectId}/reference-events`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail ?? "读取服务器标注失败");
        if (cancelled) return;
        const restored = Array.isArray(data.events) ? (data.events as Omit<DrumEvent, "velocity">[]).map((item) => ({ ...item, velocity: Number.isInteger((item as DrumEvent).velocity) ? (item as DrumEvent).velocity : 100 })) : [];
        if (!restored.every((item) => Number.isInteger(item.id) && item.id > 0 &&
          Number.isFinite(item.onset_seconds) && item.onset_seconds >= 0 &&
          INSTRUMENTS.includes(item.instrument))) {
          throw new Error("服务器返回的参考标注格式无效。");
        }
        setEvents(restored);
        setNextId(restored.reduce((max, item) => Math.max(max, item.id), 0) + 1);
        setServerReady(true);
        setSaveMessage("已连接项目服务器；已载入 " + restored.length + " 条参考标注");
      } catch (error) {
        if (!cancelled) setSaveMessage(error instanceof Error ? error.message : "读取服务器标注失败。");
      }
    }
    void loadReferenceEvents();
    return () => { cancelled = true; };
  }, [projectId]);

  React.useEffect(() => {
    if (!projectId || !serverReady) return;
    const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
    const snapshot = events.map(({ id, onset_seconds, instrument: kind, velocity: eventVelocity }) => ({
      id, onset_seconds, instrument: kind, velocity: eventVelocity,
    }));
    saveQueueRef.current = saveQueueRef.current.catch(() => undefined).then(async () => {
      const response = await fetch(`${base}/api/projects/${projectId}/reference-events`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events: snapshot }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "服务器保存失败");
      setSaveMessage("已保存到项目服务器 · " + data.saved_events + " 条参考标注");
    }).catch((error: unknown) => {
      setSaveMessage(error instanceof Error ? error.message + "；请导出 CSV 备份。" : "服务器保存失败；请导出 CSV 备份。");
    });
  }, [projectId, serverReady, events]);

  async function upload() {
    if (!file) return;
    setBusy(true);
    setMessage("正在上传音频…");
    try {
      const body = new FormData();
      body.append("audio", file);
      const base = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
      const response = await fetch(`${base}/api/projects`, { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "上传失败");
      setProjectId(data.id);
      setServerReady(false);
      setEvents([]);
      setNextId(1);
      setAudioFile(file);
      setCurrentTime(0);
      setManualTime("0");
      setSelectedProjectId(data.id);
      await refreshProjects();
      setMessage(`项目已创建：${data.id}。人工标注将保存到此项目。`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败，请检查后端服务。");
    } finally {
      setBusy(false);
    }
  }

  function syncTime() {
    const time = audioRef.current?.currentTime ?? 0;
    setCurrentTime(time);
    setManualTime(time.toFixed(3));
  }

  function addEvent() {
    const onset = Number(manualTime);
    const duration = audioRef.current?.duration;
    if (!Number.isFinite(onset) || onset < 0 || (duration !== undefined && Number.isFinite(duration) && onset > duration)) {
      setImportMessage("时间必须是非负数，且不能超过音频时长。");
      return;
    }
    setEvents((previous) => [...previous, { id: nextId, onset_seconds: onset, instrument, velocity }]
      .sort((a, b) => a.onset_seconds - b.onset_seconds || a.id - b.id));
    setNextId((value) => value + 1);
    setImportMessage("");
  }

  async function importReference(selected: File | undefined) {
    if (!selected) return;
    try {
      const content = (await selected.text()).replace(/^\uFEFF/, "");
      const lines = content.split(/\r?\n/).filter((line) => line.trim().length > 0);
      if (lines.length < 1 || lines[0].trim() !== "onset_seconds,instrument") {
        throw new Error("CSV 表头必须为 onset_seconds,instrument。");
      }
      const imported: DrumEvent[] = [];
      for (let index = 1; index < lines.length; index += 1) {
        const columns = lines[index].split(",");
        if (columns.length !== 2) throw new Error("第 " + (index + 1) + " 行格式错误。");
        const onset = Number(columns[0].trim());
        const kind = columns[1].trim();
        if (!Number.isFinite(onset) || onset < 0 || !INSTRUMENTS.includes(kind)) {
          throw new Error("第 " + (index + 1) + " 行时间或鼓件无效。");
        }
        imported.push({ id: index, onset_seconds: onset, instrument: kind, velocity: 100 });
      }
      imported.sort((a, b) => a.onset_seconds - b.onset_seconds || a.id - b.id);
      setEvents(imported);
      setNextId(imported.length + 1);
      setImportMessage("已载入 " + imported.length + " 条人工参考事件（替换当前列表）。");
    } catch (error) {
      setImportMessage(error instanceof Error ? error.message : "CSV 导入失败。");
    }
  }

  function exportReference() {
    const rows = ["onset_seconds,instrument", ...events.map((event) =>
      `${event.onset_seconds.toFixed(3)},${event.instrument}`)];
    const blob = new Blob([rows.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "drum-reference-annotations.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-mark">D</div>
        <div><strong>DrumAI Studio</strong><span>从整曲到可编辑鼓谱</span></div>
        <span className="status">P1 · 人工标注</span>
      </header>
      <section className="hero">
        <p className="eyebrow">AI DRUM TRANSCRIPTION WORKSPACE</p>
        <h1>把一首歌，拆解成<br /><em>看得懂、改得动的鼓谱。</em></h1>
        <p className="intro">导入完整混音，逐步完成鼓轨分离、鼓件识别、节奏校正与多格式导出。现在可以用人工标注建立独立的参考鼓点数据。</p>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">NEW PROJECT</p><h2>导入音频</h2></div><span className="step">01 / 04</span></div>
        <label className="dropzone">
          <input type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,.aac,audio/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <span className="upload-icon">↑</span>
          <strong>{file ? file.name : "选择音频文件"}</strong>
          <small>支持 WAV、MP3、FLAC、M4A、OGG、AAC · 当前上传上限 100 MB</small>
        </label>
        <div className="actions"><span>{message}</span><button disabled={!file || busy} onClick={upload}>{busy ? "处理中…" : "创建项目"}</button></div>
      </section>

      <section className="panel project-library">
        <div className="panel-heading"><div><p className="eyebrow">PROJECT LIBRARY</p><h2>已有项目</h2></div><span className="step">{projects.length} 个项目</span></div>
        <div className="actions">
          <select aria-label="选择已有项目" value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}>
            <option value="">选择一个已保存的项目</option>
            {projects.map((project) => <option key={project.id} value={project.id}>{project.filename} · {new Date(project.created_at).toLocaleString()}</option>)}
          </select>
          <button disabled={!selectedProjectId || projectBusy} onClick={() => void openProject()}>{projectBusy ? "正在打开…" : "打开项目"}</button>
        </div>
        {!projects.length && <p className="section-note">还没有已保存的项目。上传音频并创建项目后，会出现在这里。</p>}
      </section>

      <section className="panel annotation-panel">
        <div className="panel-heading"><div><p className="eyebrow">GROUND-TRUTH WORKBENCH</p><h2>人工鼓点标注</h2></div><span className="step">{projectId ? "PROJECT · " + projectId.slice(0, 8) : "REFERENCE CSV"}</span></div>
        <p className="section-note">播放项目原始歌曲，记录时间与鼓件。人工确认的参考事件会自动保存到当前项目服务器；未创建项目时暂存于此浏览器。模型预测不会自动混入参考数据。</p>
        <label className="audio-picker">
          <span>原始歌曲</span>
          <input type="file" accept="audio/*,.mp3,.wav,.flac,.m4a" onChange={(event) => {
            const selected = event.target.files?.[0] ?? null;
            setProjectId(null);
            setServerReady(false);
            setSelectedProjectId("");
            setAudioFile(selected);
            setCurrentTime(0);
            setManualTime("0");
            setImportMessage("");
            if (selected) {
              const key = "drumai:annotations:" + selected.name + ":" + selected.size + ":" + selected.lastModified;
              try {
                const stored = window.localStorage.getItem(key);
                const restoredRaw = stored ? JSON.parse(stored) as Partial<DrumEvent>[] : [];
                const restored = restoredRaw.map((item) => ({ ...item, velocity: Number.isInteger(item.velocity) ? item.velocity! : 100 })) as DrumEvent[];
                if (Array.isArray(restored) && restored.every((item) => Number.isFinite(item.id) && Number.isFinite(item.onset_seconds) && item.onset_seconds >= 0 && INSTRUMENTS.includes(item.instrument))) {
                  setEvents(restored);
                  setNextId(restored.reduce((max, item) => Math.max(max, item.id), 0) + 1);
                  setSaveMessage(stored ? "已恢复 " + restored.length + " 条本地标注" : "新音频：尚无本地标注");
                } else { setEvents([]); setNextId(1); setSaveMessage("本地标注数据格式异常，已清空当前列表"); }
              } catch { setEvents([]); setNextId(1); setSaveMessage("无法读取本地标注；请检查浏览器存储权限"); }
            } else { setEvents([]); setNextId(1); setSaveMessage(""); }
            event.currentTarget.value = "";
          }} />
        </label>
        {audioUrl ? (
          <div className="audio-workspace">
            <audio ref={audioRef} src={audioUrl} controls onLoadedMetadata={syncTime} onTimeUpdate={syncTime} onSeeked={syncTime} />
            <div className="time-readout"><span>播放位置</span><strong>{currentTime.toFixed(3)} s</strong></div>
          </div>
        ) : <div className="audio-empty">选择本地音频后即可播放并标注鼓点。</div>}
        <div className="annotation-controls">
          <label><span>时间（秒）</span><input type="number" min="0" step="0.001" value={manualTime} onChange={(event) => setManualTime(event.target.value)} /></label>
          <label><span>鼓件</span><select value={instrument} onChange={(event) => setInstrument(event.target.value)}>{INSTRUMENTS.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>
          <label><span>力度</span><input aria-label="默认力度" type="number" min="1" max="127" value={velocity} onChange={(event) => setVelocity(Math.min(127, Math.max(1, Number(event.target.value) || 1)))} /></label>
          <button className="add-event" disabled={!audioFile} onClick={addEvent}>＋ 记录鼓点</button>
        </div>
        <section className="drum-grid-panel" aria-label="节奏网格编辑器">
          <div className="grid-toolbar">
            <div><strong>节奏网格</strong><small>4 小节 · 4/4 · 十六分音符；点击格子添加或移除鼓点</small></div>
            <label>速度 BPM <input aria-label="网格速度 BPM" type="number" min="40" max="240" step="1" value={tempo} onChange={(event) => setTempo(Math.min(240, Math.max(40, Number(event.target.value) || 40)))} /></label>
          </div>
          <div className="drum-grid">
            <div className="grid-corner">鼓件</div>
            {Array.from({ length: 64 }, (_, step) => <div className={step % 16 === 0 ? "grid-step bar-start" : step % 4 === 0 ? "grid-step beat-start" : "grid-step"} key={step}>{step % 16 === 0 ? "小节 " + (step / 16 + 1) : step % 4 === 0 ? String((step % 16) / 4 + 1) : ""}</div>)}
            {INSTRUMENTS.map((kind) => <React.Fragment key={kind}>
              <div className="grid-instrument">{kind}</div>
              {Array.from({ length: 64 }, (_, step) => {
                const onset = step * 60 / tempo / 4;
                const active = events.some((item) => item.instrument === kind && Math.abs(item.onset_seconds - onset) < 0.025);
                return <button type="button" key={step} aria-label={kind + " 第" + (step + 1) + "格" + (active ? " 已有鼓点" : " 空")} aria-pressed={active} className={["grid-cell", step % 16 === 0 ? "bar-start" : "", active ? "active" : ""].join(" ")} onClick={() => {
                  const match = events.find((item) => item.instrument === kind && Math.abs(item.onset_seconds - onset) < 0.025);
                  if (match) setEvents((previous) => previous.filter((item) => item.id !== match.id));
                  else setEvents((previous) => [...previous, { id: nextId, onset_seconds: onset, instrument: kind, velocity }].sort((a, b) => a.onset_seconds - b.onset_seconds || a.id - b.id));
                  if (!match) setNextId((value) => value + 1);
                }}>{active ? "●" : ""}</button>;
              })}
            </React.Fragment>)}
          </div>
          <p className="grid-note">网格按当前 BPM 显示；已有非网格时间的标注仍保留在下方事件列表中。</p>
        </section>
        <section className="notation-panel" aria-label="鼓谱预览">
          <div className="grid-toolbar"><div><strong>五线谱预览</strong><small>按当前 BPM 将事件量化到最近的十六分音符；每小节 4/4</small></div><button className="export-button" disabled={!events.length} onClick={() => downloadMusicXml(events, tempo)}>导出 MusicXML</button></div>
          {events.length ? (() => {
            const ticksPerMeasure = 16;
            const maxTick = Math.max(15, ...events.map((item) => Math.round(item.onset_seconds * tempo / 60 * 4)));
            const measureCount = Math.floor(maxTick / ticksPerMeasure) + 1;
            const measureWidth = 240;
            const scoreWidth = measureCount * measureWidth + 24;
            return <div className="notation-scroll"><svg role="img" aria-label={`鼓谱预览，${measureCount} 小节，${events.length} 个事件`} viewBox={`0 0 ${scoreWidth} 116`} width={scoreWidth} height="116">
              {[24, 39, 54, 69, 84].map((y) => <line key={y} x1="12" x2={scoreWidth - 12} y1={y} y2={y} stroke="#778398" strokeWidth="1" />)}
              {Array.from({ length: measureCount + 1 }, (_, index) => <g key={index}><line x1={12 + index * measureWidth} x2={12 + index * measureWidth} y1="18" y2="90" stroke="#aab4c6" strokeWidth={index === 0 ? 2 : 1} /><text x={18 + index * measureWidth} y="12" fill="#9ba3b4" fontSize="9">{index + 1}</text></g>)}
              {events.map((item) => {
                const tick = Math.max(0, Math.round(item.onset_seconds * tempo / 60 * 4));
                const position = STAFF_POSITION[item.instrument];
                const x = 12 + Math.floor(tick / ticksPerMeasure) * measureWidth + 22 + (tick % ticksPerMeasure) * 12.2;
                return <g key={item.id}><ellipse cx={x} cy={position.y} rx="5" ry="3.5" fill={item.instrument.includes("hat") || item.instrument === "crash" || item.instrument === "ride" ? "none" : "#c9f36b"} stroke="#c9f36b" strokeWidth="1.5" /><line x1={x + 4} x2={x + 4} y1={position.y} y2={position.y - 24} stroke="#c9f36b" strokeWidth="1.5" /><title>{item.instrument} · {item.onset_seconds.toFixed(3)} 秒</title></g>;
              })}
            </svg></div>;
          })() : <p className="notation-empty">添加鼓点后，这里会显示对应的鼓谱预览。</p>}
          <p className="grid-note">当前预览为简化打击乐谱，不是完整制谱软件的排版结果。导出按固定 BPM、4/4 拍和十六分音符量化；原始秒级时间仍保存在项目事件中。</p>
        </section>
        <div className="event-toolbar"><div><strong>人工确认事件 · {events.length}</strong><small className="save-status">{saveMessage}</small></div><div className="event-actions"><label className="import-button">导入参考 CSV<input type="file" accept=".csv,text/csv" onChange={(event) => { void importReference(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label><button className="export-button" disabled={!events.length} onClick={exportReference}>导出参考 CSV</button></div></div>
        {importMessage && <p className="import-message" role="status">{importMessage}</p>}
        {events.length ? (
          <div className="event-table">
            <div className="event-row event-head"><span>时间（秒）</span><span>鼓件</span><span>力度</span><span>操作</span></div>
            {events.map((event) => <div className="event-row editable-event-row" key={event.id}>
              <input aria-label={`事件 ${event.id} 时间`} type="number" min="0" step="0.001" value={event.onset_seconds} onChange={(change) => setEvents((previous) => previous.map((item) => item.id === event.id ? { ...item, onset_seconds: Math.max(0, Number(change.target.value) || 0) } : item).sort((a, b) => a.onset_seconds - b.onset_seconds || a.id - b.id))} />
              <select aria-label={`事件 ${event.id} 鼓件`} value={event.instrument} onChange={(change) => setEvents((previous) => previous.map((item) => item.id === event.id ? { ...item, instrument: change.target.value } : item))}>{INSTRUMENTS.map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select>
              <input aria-label={`事件 ${event.id} 力度`} type="number" min="1" max="127" value={event.velocity} onChange={(change) => setEvents((previous) => previous.map((item) => item.id === event.id ? { ...item, velocity: Math.min(127, Math.max(1, Number(change.target.value) || 1)) } : item))} />
              <button aria-label={`删除 ${event.instrument} ${event.onset_seconds}`} onClick={() => setEvents((previous) => previous.filter((item) => item.id !== event.id))}>删除</button>
            </div>)}
          </div>
        ) : <div className="event-empty">尚无参考事件。建议先标注一段 10–20 秒的片段，确认标注习惯后再扩展到整首歌。</div>}
      </section>

      <section className="pipeline">
        {["音频导入", "鼓轨分离", "鼓件与节奏识别", "人工校对与导出"].map((item, index) => (
          <div className="pipeline-item" key={item}><span>0{index + 1}</span><strong>{item}</strong><small>{index === 0 || index === 3 ? "部分可用" : "开发中"}</small></div>
        ))}
      </section>
      <footer>自动转录尚未接入产品 API。人工标注 CSV 可作为独立参考数据，供后续 Precision、Recall、F1 与 onset timing 评测使用。</footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
