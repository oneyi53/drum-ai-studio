# Drum AI Studio — 开发交接文档

> 更新日期：2026-11-13  
> 仓库：`oneyi53/drum-ai-studio`  
> 当前工作分支：`feat/musicxml-explicit-rhythmic-rests`  
> 当前 PR：[#15 — feat(musicxml): emit exact drum hits and explicit rests](https://github.com/oneyi53/drum-ai-studio/pull/15)  
> PR 状态：Open / Draft / 未合并  
> 当前 HEAD：`bfcbdded69b9e6e95ffb0705dbc6c5e4be2284d4`

## 1. 项目总体目标

Drum AI Studio 的目标是把一首歌曲音频自动转换成**可编辑、可校正、可导出的架子鼓谱**，形成完整可用的工作流：

1. 导入 MP3/WAV 等歌曲音频。
2. 自动分析节拍、速度、拍号及鼓组事件，识别底鼓、军鼓、踩镲、通鼓、镲片等乐器。
3. 将识别结果转换为规范的内部鼓谱事件模型，并允许用户在时间轴/鼓谱编辑器中试听、移动、删除、增加和更改鼓件。
4. 自动生成可读的架子鼓记谱，正确处理节奏时值、休止符、小节线、连音/切分等。
5. 导出可编辑谱文件（优先 MusicXML），以及稳定、清晰、可打印的 PDF；同时支持 MIDI 和项目归档。
6. 通过真实歌曲、标准标注数据集和自动化回归测试持续提高识别质量，不能只以“文件生成成功”作为产品可用标准。

**最终验收标准：** 用户上传一首真实歌曲，系统能生成鼓点基本准确、节奏位置可信、谱面易读的架子鼓谱；用户能直接编辑并导出 MusicXML/PDF/MIDI，重新打开导出文件仍保持正确内容。

## 2. 当前开发进度

### 已完成或已落地

- **主线与编辑能力**
  - 已实现时间轴事件跨鼓件轨道移动；垂直拖动会实际修改事件乐器，而不仅是视觉移动。
  - 批量事件编辑支持更改鼓件、时间偏移或两者同时进行，并保留力度与历史记录语义。
  - 增加对应 API 回归测试。

- **MusicXML 生成与校验**
  - 增加共享游标重建/校验能力，处理 MusicXML 的 `backup`、`forward`、多声部、多谱表及和弦音符。
  - 使用精确分数表示时值，避免 divisions 变化导致历史偏移被错误缩放。
  - 增加严格音符时值校验：duration、type、附点及 time-modification/tuplet 比例。
  - 导出器不再把“下一次击打之间的全部间隔”错误地写成当前鼓点的音符时值；击打使用单个合理音符值，静音部分生成显式休止符。
  - 已处理常见 4/4、3/4、6/8 和常见 7/8 分组；无法用标准音符值准确表达的间隔使用精确 cursor skip，不伪造时值。
  - 极短击打间隔用精确 tuplet 比例表示。
  - PDF 导出前执行 MusicXML 预检，避免 PDF fallback 掩盖无效记谱。
  - PDF 打印渲染会裁掉最后一个有效击打之后的静默尾小节；该裁剪不改变可编辑 MusicXML。

- **测试与工程**
  - 最新已记录的标准 CI：Backend 106 tests passed、Ruff clean、Frontend checks passed（对应最新 exporter 代码验证记录）。
  - Engine Validation 已有成功运行：仓库两首 MP3（Creep、Psycho）成功转录并生成 MIDI。
  - Engine Validation workflow 已优化：文档/纯 workflow 改动不再无谓触发昂贵音频评测；同一 PR/ref 的重复运行会取消旧任务，减少重复跑数据集。
  - 关键过程与证据持续记录在 `docs/PROJECT_LOG.md`。

### 仍未达到产品验收的部分

- **底鼓识别仍是核心质量风险。** 当前离线证据显示 onset 候选检测较好，但候选被分类为 kick 的阶段漏检/误报明显；尚未修改上游生产分类器。
- **PDF 视觉质量未验收。** 过去一次 API E2E 的 PDF ink-height gate 为 13.4%，低于 15% 下限。PDF/MusicXML/PNG 文件曾成功生成，但生成成功不代表排版可读。
- **MusicXML 仍需跨软件验证。** 当前重点覆盖节奏语义和结构校验，仍需用 MuseScore 等实际记谱软件打开检查；跨小节连音线、beam grouping 等仍有后续工作。
- PR #15 仍为 Draft，尚未合并。

## 3. 底鼓识别：已知证据与正确解读

生产全曲分类逻辑来自上游 DrumScript（Engine Validation 中从上游仓库安装），本仓库的诊断脚本**不会自动改变生产推理行为**。

已审查上游 full-song kick 规则：
- LFER >= 0.32
- peak frequency 40–140 Hz

原始 IDMT 子集诊断显示候选 onset recall 高，但 kick 分类保留率低：
- RealDrum：候选 recall 0.983；kick recall 0.053；precision 1.000。
- WaveDrum：候选 recall 0.963；kick recall 0.172；precision 0.956。
- TechnoDrum：候选 recall 0.990；kick recall 0.571；precision 0.851。

在 40 tracks / 2,619 candidates 的 track-isolated 离线评估中：
- 上游原规则：TP=246、FP=32、FN=701，P=0.885、R=0.260、F1=0.402。
- 降低 LFER 阈值：TP=812、FP=177、FN=135，P=0.821、R=0.857、F1=0.839。
- 排除 DC bin、peak band 改为 20–180 Hz 并增加 HFER ceiling：TP=905、FP=188、FN=42，P=0.828、R=0.956、F1=0.887。
  - RealDrum P/R/F1=0.910/0.916/0.913
  - WaveDrum=0.828/0.953/0.886
  - TechnoDrum=0.763/1.000/0.865
- TechnoDrum 的 precision 只有 0.763（89 FP），因此该规则不能直接上线。
- 使用训练 fold precision floor=0.85 的探索性结果曾得到 TP=854、FP=141、FN=93（P=0.858、R=0.902、F1=0.880）。这是先前对保存样本的探索结果；新增可复现实现必须由当前 Engine Validation 重新运行并核实后，才能称为已验证结果。
- 另有 22 个标注 kick 没有匹配到 onset candidate，属于 onset 阶段漏检；分类器调阈值无法恢复这些事件。

以上全部是**特定 IDMT 候选事件上的离线 candidate-level 评估**，不是产品真实歌曲的端到端准确率，也不是生产 classifier 的性能承诺。

## 4. 当前正在验证的改动

最近三个提交均在当前主开发分支：
- `39b1ad782711e4ca50a4a489d07be71f999d47e0` — precision-guarded kick threshold evaluation
- `76ca1bd7d5807ddc3e249654416ae02ea5a95c47` — report precision-guarded cross-subset kick metrics
- `bfcbdded69b9e6e95ffb0705dbc6c5e4be2284d4` — document precision-guarded kick evaluation

新增逻辑：每个 held-out track 完全不参与该 fold 的阈值选择；训练 tracks 先筛选 training precision 达到 0.85 的 LFER/HFER 参数，再从符合条件的组合中选择 F1 最好的参数。若训练 fold 无法达到 precision floor，会显式记录 fallback，不会伪称达标。按 subset 和全数据集都会输出指标。

### 最新 Engine Validation 状态

- Run [43421181480](https://github.com/oneyi53/drum-ai-studio/actions/runs/43421181480)（Engine Validation）在本次状态检查时仍为 **in_progress**。
- DrumScript 安装、CLI 检查及 upstream non-slow tests 已通过。
- 当前正在下载 IDMT-SMT-Drums 标注评测子集；RealDrum/WaveDrum/TechnoDrum 评分、kick diagnostics、MP3 smoke、API E2E 尚未完成。
- 因此最新 precision-guarded 结果尚未得到这次 Engine Validation 的确认。
- PR #15 的 Backend/CI 最近记录为成功，但不能替代上述 Engine Validation。

## 5. 下一阶段优先级（按顺序执行）

### P0 — 完成当前验证闭环
1. 继续跟踪 Run 43421181480，直到 success/failure/cancelled。
2. 若成功，下载 artifact，检查全局及各 subset 的 precision-guarded TP/FP/FN、P/R/F1、每轨道阈值、fallback folds。
3. 对 TechnoDrum 和其他高 FP 曲目做逐事件误报归因；区分低音通鼓、其他低频打击、bass overlap、DC/peak/HFER 特征异常，结论必须能追溯到 artifact。
4. 若失败，依据 job logs 修复；若被新提交取消，检查当前 PR head 并跟踪最新 run，不能把 cancelled 当作失败测试或通过。

### P1 — 让底鼓识别真正可用
1. 扩大独立曲目/风格评估，防止在同一批 IDMT tracks 上反复调参。
2. 保持按 track 分组的 nested/leave-one-track-out 评估；不能在 held-out 结果上选阈值再报告同一批结果。
3. 为 false positives 和 onset misses 建立可读的逐事件诊断报告。
4. 与上游 DrumScript 的真实 API/feature schema 对齐；在证据充分前不修改上游生产阈值。
5. 加入真实歌曲人工标注小型验收集，报告事件级 precision/recall、时间偏差和每分钟误报数。

### P2 — 记谱与导出验收
1. 用 MuseScore 等实际软件打开代表性 MusicXML：稀疏节奏、密集节奏、跨小节、6/8、7/8、三连音、不同鼓件同时击打。
2. 对 PDF 做人工视觉检查：单页/多页、短曲/长曲、空白比例、谱表大小、鼓件位置、节奏符号和分页。
3. 修复 PDF visual-height gate 的真实版面问题，不通过降低门槛来“修绿”CI。
4. 补充跨小节 ties、beam grouping、复杂拍号分组与多系统分页测试。

### P3 — 产品完整性
1. 完整走通上传 → 转录 → 编辑 → 播放/试听 → MusicXML/PDF/MIDI 导出 → 项目重新打开。
2. 处理长音频耗时、任务状态、错误提示、取消/重试和资源限制。
3. 建立一套固定的真实歌曲回归集，每次模型/规则变更都能复现对比。
4. 只有核心识别与谱面质量过验收后，才将 PR 从 Draft 转为 Ready 并合并。

## 6. 重要技术边界与协作约定

- **不要新开平行分支。** 用户要求主线收敛；后续工作优先直接在 `feat/musicxml-explicit-rhythmic-rests` / PR #15 上继续。
- 不要另起一个与 PR #15 重复的 exporter、classifier 或 workflow 实现；先检查当前代码和 PR diff。
- 生产 kick classifier 属于上游 DrumScript；本仓库的 `scripts/kick_stage_diagnostics.py` 和 `scripts/kick_stage_aggregate.py` 是离线诊断工具。
- 不要把候选级指标写成端到端识别准确率；不把 exploratory sklearn 模型或未重跑的阈值结果当作已验证实现。
- 不要通过降低 PDF 视觉门槛、只检查文件非空或只检查 PNG 存在来宣称视觉验收通过。
- 新增功能必须有针对性回归测试；代码变更后看实际 CI/Engine Validation 结果。
- 先读 `docs/PROJECT_LOG.md` 和本交接文档，再开始修改；每个有意义的阶段把提交、测试、数据、未解决风险追加到项目日志。
- 用户希望看到真实进展和产物，不要只回复计划；避免反复运行同一批昂贵 benchmark，只有代码/诊断口径发生实质变化时才重跑。

## 7. 关键文件入口

- `docs/PROJECT_LOG.md`：按日期记录开发过程、实验结果与决策。
- `scripts/kick_stage_diagnostics.py`：IDMT onset/kick 候选事件特征、匹配、track-isolated sweep 与 precision-guarded sweep。
- `scripts/kick_stage_aggregate.py`：跨 RealDrum/WaveDrum/TechnoDrum 汇总与全局指标。
- `backend/app/pdf_adapter.py`：MusicXML 生成、记谱语义及 PDF 适配相关逻辑（以当前分支实际代码为准）。
- `.github/workflows/engine-validation.yml`：上游 DrumScript 安装、IDMT 评估、真实 MP3 smoke、API 导出 E2E。
- PR #15：当前主线所有变更、review 和验证入口。

## 8. 接手后的第一件事

先检查 PR #15 当前 head 与 Engine Validation 最新运行状态；优先完成 run 43421181480 的结果审阅。只有拿到该 run 的 artifact 和日志后，才更新 precision-guarded 结论。然后从 TechnoDrum false positives 逐事件归因开始，不要直接把离线规则推入生产。
