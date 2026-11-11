import React from "react";
import ReactDOM from "react-dom/client";
import "./style.css";

type AnalysisSummary = {
  jobId: string;
  projectId: string;
  durationSeconds: number;
  totalEvents: number;
  instruments: Record<string, number>;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function responseError(data: Record<string, unknown>, fallback: string): string {
  if (typeof data.detail === "string") return data.detail;
  if (data.detail) return JSON.stringify(data.detail);
  return fallback;
}

function App() {
  const [file, setFile] = React.useState<File | null>(null);
  const [message, setMessage] = React.useState("选择一首完整歌曲，上传后启动鼓谱分析。");
  const [busy, setBusy] = React.useState(false);
  const [summary, setSummary] = React.useState<AnalysisSummary | null>(null);

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

      const resultResponse = await fetch(
        `${API_BASE}/api/projects/${projectId}/performance`,
      );
      const result = await resultResponse.json() as {
        performance?: {
          duration_seconds: number;
          events: Array<{ instrument: string }>;
        };
      };
      if (!resultResponse.ok || !result.performance) {
        throw new Error("分析已结束，但无法读取标准鼓事件结果。");
      }
      const instruments: Record<string, number> = {};
      for (const event of result.performance.events) {
        instruments[event.instrument] = (instruments[event.instrument] ?? 0) + 1;
      }
      setSummary({
        jobId,
        projectId,
        durationSeconds: result.performance.duration_seconds,
        totalEvents: result.performance.events.length,
        instruments,
      });
      setMessage(`分析完成：项目 ${projectId}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "处理失败，请检查后端服务。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-mark">D</div>
        <div><strong>DrumAI Studio</strong><span>从整曲到可编辑鼓谱</span></div>
        <span className="status">P1 · 分析链路</span>
      </header>
      <section className="hero">
        <p className="eyebrow">AI DRUM TRANSCRIPTION WORKSPACE</p>
        <h1>把一首歌，拆解成<br /><em>看得懂、改得动的鼓谱。</em></h1>
        <p className="intro">导入完整混音，启动异步鼓谱分析，并将引擎输出转换为统一的标准鼓事件。</p>
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
          <div className="panel-heading"><div><p className="eyebrow">CANONICAL PERFORMANCE</p><h2>标准鼓事件已生成</h2></div><span className="complete">完成</span></div>
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
          <a className="download-link" href={`${API_BASE}/api/projects/${summary.projectId}/midi`} download>下载鼓谱 MIDI</a>
          <small className="job-id">任务 ID：{summary.jobId}</small>
        </section>
      )}
      <section className="pipeline">
        {["音频导入", "鼓轨分离 / 转录", "标准鼓事件", "编辑与导出"].map((item, index) => (
          <div className="pipeline-item" key={item}><span>0{index + 1}</span><strong>{item}</strong><small>{index === 0 || index === 2 ? "已接入" : index === 1 ? "引擎运行时依赖" : "开发中"}</small></div>
        ))}
      </section>
      <footer>提示：分析服务需要在后端安装 DrumScript、CPU PyTorch 与 FFmpeg。当前输出是引擎转录结果，尚未经过人工校对，不代表已验证的准确率。</footer>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
