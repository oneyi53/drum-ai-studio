import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

type DrumEvent = { id: number; onset_seconds: number; instrument: string };

const INSTRUMENTS = [
  "kick", "snare", "closed_hat", "open_hat",
  "low_tom", "mid_tom", "high_tom", "crash", "ride",
];

function App() {
  const [file, setFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState("选择一首完整歌曲，创建分析项目。");
  const [busy, setBusy] = React.useState(false);
  const [audioFile, setAudioFile] = React.useState<File | null>(null);
  const [audioUrl, setAudioUrl] = React.useState("");
  const [currentTime, setCurrentTime] = React.useState(0);
  const [manualTime, setManualTime] = React.useState("0");
  const [instrument, setInstrument] = React.useState("kick");
  const [events, setEvents] = React.useState<DrumEvent[]>([]);
  const [nextId, setNextId] = React.useState(1);
  const [importMessage, setImportMessage] = React.useState("");
  const [saveMessage, setSaveMessage] = React.useState("");
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
    if (!annotationStorageKey) return;
    try {
      window.localStorage.setItem(annotationStorageKey, JSON.stringify(events));
      setSaveMessage("已在此浏览器自动保存 " + events.length + " 条标注");
    } catch {
      setSaveMessage("浏览器存储不可用；请及时导出 CSV 备份。");
    }
  }, [annotationStorageKey, events]);

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
      setMessage(`项目已创建：${data.id}。当前版本尚未接入自动鼓谱识别。`);
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
    setEvents((previous) => [...previous, { id: nextId, onset_seconds: onset, instrument }]
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
        imported.push({ id: index, onset_seconds: onset, instrument: kind });
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

      <section className="panel annotation-panel">
        <div className="panel-heading"><div><p className="eyebrow">GROUND-TRUTH WORKBENCH</p><h2>人工鼓点标注</h2></div><span className="step">REFERENCE CSV</span></div>
        <p className="section-note">选择原始歌曲，播放到鼓点出现的位置，记录时间与鼓件。此处只记录人工确认的参考事件，不会自动导入模型预测，避免把预测结果误当成标准答案。</p>
        <label className="audio-picker">
          <span>原始歌曲</span>
          <input type="file" accept="audio/*,.mp3,.wav,.flac,.m4a" onChange={(event) => {
            const selected = event.target.files?.[0] ?? null;
            setAudioFile(selected);
            setCurrentTime(0);
            setManualTime("0");
            setImportMessage("");
            if (selected) {
              const key = "drumai:annotations:" + selected.name + ":" + selected.size + ":" + selected.lastModified;
              try {
                const stored = window.localStorage.getItem(key);
                const restored = stored ? JSON.parse(stored) as DrumEvent[] : [];
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
          <button className="add-event" disabled={!audioFile} onClick={addEvent}>＋ 记录鼓点</button>
        </div>
        <div className="event-toolbar"><div><strong>人工确认事件 · {events.length}</strong><small className="save-status">{saveMessage}</small></div><div className="event-actions"><label className="import-button">导入参考 CSV<input type="file" accept=".csv,text/csv" onChange={(event) => { void importReference(event.target.files?.[0]); event.currentTarget.value = ""; }} /></label><button className="export-button" disabled={!events.length} onClick={exportReference}>导出参考 CSV</button></div></div>
        {importMessage && <p className="import-message" role="status">{importMessage}</p>}
        {events.length ? (
          <div className="event-table">
            <div className="event-row event-head"><span>时间（秒）</span><span>鼓件</span><span>操作</span></div>
            {events.map((event) => <div className="event-row" key={event.id}>
              <span>{event.onset_seconds.toFixed(3)}</span><span>{event.instrument}</span>
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
