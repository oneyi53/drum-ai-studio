import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

function App() {
  const [file, setFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState("选择一首完整歌曲，创建分析项目。");
  const [busy, setBusy] = React.useState(false);

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

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-mark">D</div>
        <div><strong>DrumAI Studio</strong><span>从整曲到可编辑鼓谱</span></div>
        <span className="status">P0 · 基础框架</span>
      </header>
      <section className="hero">
        <p className="eyebrow">AI DRUM TRANSCRIPTION WORKSPACE</p>
        <h1>把一首歌，拆解成<br /><em>看得懂、改得动的鼓谱。</em></h1>
        <p className="intro">导入完整混音，后续将逐步完成鼓轨分离、鼓件识别、节奏校正与多格式导出。</p>
      </section>
      <section className="panel">
        <div className="panel-heading"><div><p className="eyebrow">NEW PROJECT</p><h2>导入音频</h2></div><span className="step">01 / 04</span></div>
        <label className="dropzone">
          <input type="file" accept=".wav,.mp3,.flac,.m4a,.ogg,.aac,audio/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          <span className="upload-icon">↑</span>
          <strong>{file ? file.name : "选择或拖入音频文件"}</strong>
          <small>支持 WAV、MP3、FLAC、M4A、OGG、AAC · 当前上传上限 100 MB</small>
        </label>
        <div className="actions"><span>{message}</span><button disabled={!file || busy} onClick={upload}>{busy ? "处理中…" : "创建项目"}</button></div>
      </section>
      <section className="pipeline">
        {["音频导入", "鼓轨分离", "鼓件与节奏识别", "编辑与导出"].map((item, index) => (
          <div className="pipeline-item" key={item}><span>0{index + 1}</span><strong>{item}</strong><small>{index === 0 ? "当前可用" : "开发中"}</small></div>
        ))}
      </section>
      <footer>提示：当前版本只实现项目上传与基础 API。自动转录尚未接入，不会生成未经验证的鼓谱。</footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
