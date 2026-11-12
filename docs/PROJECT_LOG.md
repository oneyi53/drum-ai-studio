## 2026-11-12 — PDF engraving readability correction

- Visual inspection of the API-generated PDF confirmed two concrete defects:
  the Verovio metronome-note glyph rendered as a missing-font square, and the
  notation scale left the score unusually small on landscape A4.
- Updated the PDF-only Verovio input to render tempo as explicit readable text
  (for example, "Tempo: 120 BPM") while preserving the semantic metronome
  markings in the downloadable MusicXML. Increased Verovio notation scale from
  40 to 52 to use more of the printable page area.
- This is a targeted layout correction, not yet visually accepted. The next
  engine-validation run must regenerate the PDF and PNG; inspect the rendered
  page for clipped notes, collisions, tempo readability, and balanced margins
  before treating the PDF export as ready.

## 2026-11-12 — portable engine CI passes; kick and PDF visual blockers measured

- Replaced the Ubuntu apt-installed media tools with a Python-managed static
  FFmpeg/ffprobe distribution and in-process PDFium rendering. On commit
  7b9debbb7aebab6e862545e6907053b9667f9b15, the engine-validation workflow,
  backend test workflow, and repository CI all completed successfully.
- Engine validation completed upstream non-slow tests, the synthetic mix,
  both repository MP3 smoke tests, and API-to-engine export smoke. The two
  repository tracks produced 1,041 and 1,127 normalized drum events and
  non-empty MIDI files. API E2E produced MIDI, MusicXML, a 40,550-byte PDF,
  and a rendered 42,185-byte PNG page.
- The PNG was visually inspected rather than treating file existence as
  acceptance. The Verovio page has a tempo/metronome glyph rendered as a
  missing-font box and places a very short two-bar score in a small area at
  the top of a mostly empty A4 landscape page. PDF geometry and generation
  pass, but visual acceptance remains blocked. Next: inspect Verovio scale,
  page layout, and SMuFL font/resource handling; add a visual regression
  fixture with a multi-system score before marking PDF export production-ready.
- Expanded IDMT-SMT-Drums stage diagnostics (50 ms tolerance) evaluated 14
  RealDrum, 15 WaveDrum, and 11 TechnoDrum tracks. Candidate onset recall was
  98.3%, 96.3%, and 99.0%, while final kick recall was only 5.3%, 17.2%, and
  57.1%, respectively. Matched candidate features show the current LFER rule
  (minimum 0.32) is the dominant filter: only 16/297 RealDrum, 75/364
  WaveDrum, and 165/286 TechnoDrum matched candidates pass the LFER threshold.
  Peak-frequency eligibility is much higher (291/297, 312/364, 236/286).
- Do not lower the LFER threshold globally based on these aggregates. The
  next classifier task is to inspect per-track and per-instrument feature
  distributions, compare isolated kick stems where available, and tune or
  replace the hard gate with a calibrated/adaptive decision while measuring
  precision and recall on held-out tracks. IDMT use remains evaluation-only
  under its dataset terms; no audio is committed.
- PR #4 remains the sole integration path to main. Keep it open until the PDF
  visual issue and kick-classification regression strategy are reviewed; all
  three current CI workflows are green, but CI success is not product-quality
  acceptance.


## 2026-11-11 — non-destructive quantization preview

- Added a two-step quantization flow: generate a preview without persisting,
  inspect how many events will move, then explicitly confirm application.
- Changing the grid or strength invalidates the previous preview. Only the
  confirmed apply action creates a revision and synchronizes MIDI.
- This exposes the existing backend preview mode in the workspace and avoids
  accidental destructive quantization. Backend tests run #149 passed all 56
  tests plus Ruff; repository CI run #238 passed frontend build and backend
  tests. The subsequent CSS layout update also passed backend run #150 and
  repository CI run #239.


## 2026-11-11 — A–B loop range guard

- Prevented enabling A–B practice looping when the selected range is zero or
  reversed. Setting A after an existing B now restores B to the track end;
  setting B before A is disabled in the UI.
- This avoids a silently enabled loop that never wraps playback.


## 2026-11-11 — saved-project retry and recovery

- Improved workspace recovery so uploaded projects with no analysis job can be
  started directly, and projects whose latest analysis failed can be retried
  without uploading the audio again.
- Existing completed projects still restore the latest canonical performance;
  queued/running jobs remain resumable after a browser refresh.
- Added API coverage for the saved-project listing endpoint and documented the
  retry flow in the user guide. Frontend/backend CI for this increment pending.


## 2026-11-11 — saved project recovery (implementation, CI pending)

- Added `GET /api/projects?limit=...` to list recent local projects with their
  latest analysis-job state. The API clamps the requested list size to 1–100.
- Added a workspace project picker that loads saved projects on startup,
  restores completed canonical performances and edit history after reload,
  can resume polling queued/running jobs, and supports manual list refresh.
- Project switching resets playback/selection state; event-row inputs remount
  when canonical event values change so undo/redo visibly restores the editor.
- Added API integration coverage for project metadata and latest completed job
  state. Backend tests run #140 passed all 56 tests and Ruff; repository CI
  run #227 passed frontend build and backend tests. DrumScript engine validation
  run #131 remains in progress.


## 2026-11-11 — editable MusicXML drum score export (implementation, CI pending)

- Added a MusicXML 4.0 partwise exporter for canonical drum events, with a
  percussion staff, instrument-specific voices/noteheads, GM percussion
  metadata, velocity playback hints, tempo directions, time-signature-aware
  measure boundaries, note values inferred from successive hit spacing, and
  explicitly marked implicit measures for partial bars or mid-bar time-signature
  changes.
- Added `GET /api/projects/{project_id}/musicxml` and a frontend download link
  beside MIDI export. The endpoint exports the latest canonical state, so
  manual edits, quantization, undo, and redo are reflected.
- Added XML structure, tempo/time-signature, velocity, empty-score, and API
  download tests. Extended the real DrumScript API-to-engine smoke to fetch and
  parse a populated MusicXML score from an actual inferred performance.
  Import into notation software is supported; final engraving remains the
  notation application's responsibility.
- Backend tests run #140 passed all 56 tests and Ruff; repository CI run #227
  passed both frontend build and backend tests on the current branch head.
  DrumScript engine validation run #131 is running the synthetic/repository MP3
  smoke stage before the expanded real-inference MusicXML export check. This
  is integration validation, not an accuracy claim.


## 2026-11-11 — tempo-synchronized practice metronome (implementation, CI pending)

- Added a browser metronome that follows the rendered tempo-map beat positions,
  including bar accents, so BPM changes use the same timeline as the drum events.
- Metronome clicks are generated locally with Web Audio and do not upload or
  persist audio. Seeking backward and A–B loop restarts reset beat tracking.
- The metronome is opt-in and can be toggled independently of A–B looping.
  Its animation-frame scheduler follows the audio element clock and stops while
  playback is paused. Repository CI run #202 passed frontend build and backend
  tests; DrumScript engine validation run #104 remains in progress.


## 2026-11-11 — A–B loop practice playback (implementation, CI pending)

- Added A/B loop markers to the synchronized audio player. Users can set the
  loop start and end from the current playback position, enable/disable looping,
  and reset the range to the full track.
- Looping is evaluated against the audio element's playback clock; drum-event
  positions and the timeline remain anchored to absolute seconds.
- Invalid or zero-length ranges do not trigger a loop. A–B range shading is
  shown across the drum lanes while looping is active. Repository CI run #202
  passed frontend build and backend tests; engine validation remains pending.

## 2026-11-11 — interactive drum arrangement timeline (implementation, CI pending)

- Added a full-song, instrument-lane timeline to the editor with a time ruler,
  tempo readout, velocity-weighted hit markers, and horizontally scrollable
  layout on smaller screens.
- Clicking a hit selects it and scrolls the corresponding editable event row
  into view. The timeline is driven directly by the canonical performance,
  so edits and quantization refresh the visualization from the saved source.
- Uses the performance tempo-map's initial BPM when available and a clearly
  labelled 120 BPM fallback when no tempo metadata exists; horizontal event
  positions remain absolute audio seconds.
- Frontend CI is pending for this commit; no build result is claimed yet.

## 2026-11-11 — persistent undo/redo for drum editing (implementation, CI pending)

- Added SQLite-backed performance revision snapshots and a current-revision
  cursor. Initial analysis output is revision zero; every manual event edit,
  deletion, and applied quantization creates a new revision.
- Added project history inspection plus undo/redo endpoints. Undo and redo
  restore canonical performance JSON and regenerate the downloadable MIDI;
  creating a new edit after undo truncates the abandoned redo branch.
- Added editor undo/redo controls with disabled states driven by server history.
- Added API integration coverage for baseline state, undo/redo, synchronized
  MIDI export, and redo-branch invalidation.
- CI is pending for this commit; no validation result is claimed yet.

# DrumAI Studio project log

## 2026-11-11 — tempo-aware drum quantization (implementation, CI pending)

- Added a pure canonical-performance quantizer with 1/4, 1/8, 1/16, and
  1/32-note grids, local BPM-aware spacing, tempo-change segment anchors, and
  adjustable 0–100% interpolation strength. Event identity, instrument,
  velocity, confidence, and provenance remain unchanged.
- Added `POST /api/projects/{project_id}/quantize` with preview-only mode
  (`apply=false`) and persistent apply mode. Applied quantization uses the
  existing atomic JSON/MIDI save path so downloads remain synchronized.
- Added editor controls for grid resolution and strength, plus a one-click
  apply action. Preview remains available through the API for clients that
  need a non-mutating comparison.
- Added unit coverage for all supported grids, strength interpolation,
  zero-strength no-op, tempo changes, invalid parameters, API preview/apply,
  and MIDI round-trip synchronization.
- DrumScript engine validation run #52 passed all steps, including upstream
  tests, synthetic/repository MP3 smoke tests, and API-to-engine end-to-end.
  This is engine integration evidence, not a transcription accuracy claim.
- Quantization backend tests run #71 passed all 48 backend tests and Ruff
  (`ruff check app tests`). Repository CI run #158 passed backend tests and
  the frontend TypeScript/Vite production build. The initial run #157 exposed
  a missing frontend action handler; that was added and the next build passed.
- DrumScript engine validation run #62 passed package/CLI verification and
  upstream non-slow tests; synthetic/repository MP3 smoke and API E2E were
  still running when this log entry was prepared. Do not mark engine validation
  complete until those remaining steps pass.

## 2026-11-11 — canonical drum-event editor

- Added project-scoped event create, patch, and delete endpoints for the latest
  completed canonical performance. Manual changes are marked with manual
  provenance and validated against the audio duration.
- Added canonical-to-GM MIDI export, preserving event timing, velocity, tempo,
  and time signatures. Every successful edit regenerates the project's MIDI
  download so it remains synchronized with canonical JSON.
- Added a browser editor for adding events and changing time, instrument, and
  velocity, plus deleting events. Enabled PATCH/DELETE in API CORS policy.
- Added API integration coverage for CRUD behavior, validation, MIDI download
  synchronization, and MIDI adapter round-trip coverage for tempo and velocity.
- DrumScript engine validation run #34 passed, including synthetic + repository
  MP3 smoke tests and the API-to-engine end-to-end upload/inference/result/MIDI
  download path. This run predates the event-editor changes and does not
  validate those new endpoints.
- Backend tests run #60 passed: 35 tests and Ruff, including CRUD, synchronized
  MIDI download, and MIDI round-trip checks for tempo, velocity, timing, and
  full performance duration. Repository CI run #146 passed frontend build and
  backend tests.
- DrumScript engine validation run #51 is still running against the latest
  head; its end-to-end steps remain pending. No accuracy claim is made; model predictions still require
  human review.

## 2026-11-11 — CI regression fixes

- The first fresh backend run for the asynchronous API changes exposed two stale
  health-test assumptions: the tests still expected the removed HTTP 501 route,
  and they instantiated TestClient without entering its lifespan, so SQLite
  storage initialization never ran.
- Updated the health tests to use TestClient as a context manager, accept the
  actual engine installation states, and assert that an unknown project returns
  HTTP 404. The next backend run passed all 32 tests.
- That same run then exposed six Ruff findings in the API module (import order,
  modern typing/time APIs, environment default typing, and intentional FastAPI
  dependency/catch patterns). These were corrected in follow-up commits.
- Follow-up backend tests run #42 passed, including all unit tests and Ruff.
  Repository CI run #128 also passed both frontend build and backend tests.
  Engine validation run #33 was still running at the time of this update; its
  synthetic/MP3 and API-to-engine E2E steps are not yet verified.

This log records repository milestones and verified boundaries. Update it when
code or validation state changes; do not infer completion from plans.

## 2026-11-11 — asynchronous analysis API integration (implementation, CI pending)

### Implemented in PR #3

- Added a lazy-loaded `DrumScriptEngine` adapter. It invokes full-song
  transcription, requires a usable exported MIDI, converts GM percussion
  channel 10 into the canonical event model, and persists a normalized MIDI
  artifact plus canonical performance JSON.
- Replaced the placeholder HTTP 501 analysis route with a job-creation endpoint
  returning HTTP 202, SQLite-backed job status, job polling, and canonical
  performance retrieval.
- Added explicit `queued`, `running`, `completed`, and `failed` states,
  duplicate-active-job protection, restart recovery for interrupted jobs, and
  concise failure reporting.
- Added API and engine-adapter unit tests; backend CI now runs Ruff across the
  application and test tree.
- Connected the frontend upload flow to job creation, status polling, canonical
  event summary display, and generated MIDI download.
- Added a guarded MIDI download endpoint that serves only the latest completed
  job artifact for the requested project.
- Added an engine-validation workflow step that exercises the complete API path
  against a synthetic mix: upload, enqueue, real DrumScript inference, canonical
  performance retrieval, and MIDI download.
- Added `docs/ANALYSIS_API.md` with endpoint contracts, runtime requirements,
  and the single-worker deployment limitation.

### Validation boundary

- Backend tests run #42 passed the API/adapter unit tests and Ruff; repository
  CI run #128 passed both frontend and backend jobs.
- DrumScript engine validation run #34 passed synthetic and repository MP3
  conversion smoke tests plus the API-to-engine upload/inference/result/MIDI
  download path. This verifies the CI integration path, not deployed service
  readiness or transcription accuracy.
- The regular backend install deliberately does not install PyTorch/DrumScript.
  The analysis job will report a clear failure until the optional worker
  runtime and FFmpeg/ffprobe are installed.
- FastAPI in-process background tasks are single-process development plumbing,
  not a durable production queue.

## 2026-11-11 — canonical events, engine compatibility, and benchmark harness

### Implemented in PR #3

- Added `backend/app/drum_events.py` with schema version 1.0, absolute event
  times, instrument labels, velocity, confidence, provenance, manual-correction
  state, duration, and tempo/time-signature map.
- Added deterministic one-to-one instrument-aware event scoring with configurable
  timing tolerance and overall/per-instrument precision, recall, F1, counts,
  and matched-event timing error.
- Added `drumai-evaluate` for single-pair canonical JSON scoring.
- Added `backend/app/midi_adapter.py` and `drumai-midi-import` to normalize
  General MIDI percussion notes into canonical events while preserving tempo,
  time signatures, velocity, and absolute seconds.
- Added backend CI and unit tests for schema, evaluator, MIDI conversion, and
  CLI behavior.
- Extended the DrumScript engine smoke so each generated MIDI must convert to
  non-empty canonical events.
- Added `drumai-benchmark`, a manifest-driven batch evaluator that requires
  declared permission basis, audio metadata, and reviewed annotations, checks
  file existence and unique case IDs, prevents source-recording leakage across
  development/evaluation splits, and emits per-case, pooled, and split-specific micro-aggregate
  metrics. These declarations are not independent rights verification.
- Added benchmark manifest starter and batch-evaluation documentation.

### Verified validation

- Backend CI run #5 passed: 17 tests and Ruff checks.
- Repository CI run #111 passed both frontend and backend jobs.
- Engine validation run #27 passed all steps, including upstream tests
  (202 passed, 8 skipped, 11 deselected) and synthetic + both repository MP3
  smoke tests.
- Canonical MIDI conversion output from run #27:
  - Synthetic mix: 38 canonical events (closed hi-hat 31, kick 7).
  - Radiohead Creep: 1,040 canonical events (closed hi-hat 621, crash 62,
    kick 118, open hi-hat 81, ride 1, snare 157).
  - Muse Psycho: 1,124 canonical events (closed hi-hat 518, crash 68,
    kick 233, open hi-hat 119, ride 15, snare 171).
- The engine generated non-empty MIDI and canonical events for all three
  inputs. This is integration evidence only, not an accuracy benchmark.
- No human-annotated golden dataset is checked in. The benchmark manifest
  starter is empty by design; permission-cleared audio and reviewed reference
  events are still required.
- The asynchronous analysis API is implemented, but its new CI run and a live
  API-to-DrumScript job have not yet passed. Do not claim deployed end-to-end
  readiness until those validations succeed.

## Next engineering milestones

1. Populate a small permission-cleared development benchmark and separately
   reviewed evaluation set; never reuse the repository MP3s without explicit
   redistribution permission.
2. Run batch scoring against those references and record engine revision,
   configuration, per-instrument metrics, and timing tolerance.
3. Replace the in-process background task with a durable worker queue before
   multi-worker deployment; add artifact download and job cancellation.
4. Add canonical event editing operations and MIDI/MusicXML/PDF exporters.

## 2026-11-10/11 — engine integration spike (PR #2)

- Added isolated Python 3.12 GitHub Actions validation for CPU PyTorch,
  DrumScript import/CLI, upstream non-slow tests, synthetic full-mix smoke,
  and repository-root MP3 smoke.
- Engine validation run #6 completed successfully and produced non-empty MIDI
  outputs for the synthetic signal and both repository MP3s. That earlier
  smoke verified pipeline execution only, not event-level accuracy.


## 2026-11-11 — synchronized audio playback and timeline (implementation, CI pending)

- Added `GET /api/projects/{project_id}/audio` to stream the original project
  upload by project ID. Filesystem access uses the server-generated stored
  filename, resolves under the upload directory, and returns 404 for unknown
  projects or missing audio.
- Added API coverage for audio bytes, media type, inline disposition, and
  unknown-project handling.
- Added browser audio playback controls and a seek slider to the editor.
  Playback time moves a playhead across every timeline lane; nearby events are
  highlighted during playback, and clicking a hit seeks the audio and selects
  its corresponding event row.
- Updated the API contract documentation. CI for this batch has not yet been
  observed; implementation status is not a CI pass.


### CI feedback and follow-up fixes

- The first CI attempt for the audio playback batch exposed two issues in the
  merge checkout: the WAV MIME type on the runner is `audio/x-wav` rather than
  the equally valid `audio/wav`, and the frontend TypeScript target does not
  include `String.replaceAll`.
- Relaxed the API assertion to require an audio media type and replaced the
  lane-label `replaceAll` call with an ES-compatible regular expression.
- These fixes are committed on the PR branch. A fresh CI result for the updated
  head is still pending; the earlier failed run is not counted as validation.


## 2026-11-11 — tempo-map-aware arrangement grid (implementation, CI pending)

- Replaced the fixed single-BPM timeline grid with beat positions generated
  from the canonical tempo map. Each tempo segment uses its own BPM and time
  signature; bar starts and quarter-note beat lines are rendered independently
  in absolute audio time.
- Tempo-change boundaries are marked on every instrument lane and BPM labels
  are placed at their corresponding audio timestamps. A 120 BPM, 4/4 fallback
  remains in effect when a performance has no tempo metadata.
- Event positions and playback synchronization remain based on absolute
  seconds, so tempo visualization does not shift the canonical event times.
- Frontend build and regression CI for this increment are pending; no pass is
  claimed until the latest branch head completes validation.


## 2026-11-11 — playback integration validation

- DrumScript engine validation run #77 passed all steps on the playback batch
  head, including upstream non-slow tests, synthetic and both repository MP3
  smoke tests, and API-to-engine end-to-end smoke.
- Repository CI run #173 passed frontend build and backend tests; backend
  tests run #86 also passed with Ruff. These runs validated the playback
  implementation and the runner compatibility fixes.
- The later tempo-map-aware timeline commits were added after run #173. They
  still require a fresh frontend build; do not extend the earlier pass claim
  to those commits.


## 2026-11-11 — timeline lane visibility filters

- Added per-instrument visibility checkboxes plus show-all/hide-all controls above the arrangement timeline.
- Filtering is presentation-only: it does not mutate canonical events, history, playback audio, or MIDI/MusicXML exports; the event table remains complete.
- This is a frontend-only increment. Latest repository CI and engine-validation status are tracked separately from this commit.


## 2026-11-11 — atomic bulk event editing

- Added batch event time shifting and batch deletion endpoints with unique-ID and full-selection validation under SQLite `BEGIN IMMEDIATE`.
- All changes are validated before persistence; invalid negative event times reject the entire batch. Each operation creates exactly one revision and regenerates MIDI from the canonical performance.
- Added frontend multi-select, select-all, time-offset input, batch move/delete actions, and Chinese user-guide coverage.
- Added API tests for one-revision semantics, MIDI synchronization, and atomic rejection.


## 2026-11-11 — selected drum-event repetition

- Added an atomic duplication endpoint that clones selected canonical drum events
  at one or more fixed interval offsets. New events receive unique IDs, retain
  instrument/velocity metadata, and are marked as manually corrected.
- Repeat count is bounded to 1–16; invalid selections and any clone beyond the
  track duration reject the entire request before persistence.
- Added editor controls for interval and repeat count. A successful action
  creates one undo/redo revision and regenerates MIDI from canonical events.
- Added API tests for metadata preservation, unique IDs, repeat timing, single
  history revision, MIDI synchronization, and out-of-duration atomic rejection.
- CI validation for this increment is pending until the latest branch head runs.


## 2026-11-11 — measure-based drum phrase copy and paste

- Added an atomic API that copies all canonical events in a source time range
  to a target measure, mapping normalized within-bar offsets when source and
  target measure lengths differ. Instrument, velocity, and confidence are
  preserved; clones receive new IDs and manual provenance.
- Added frontend source/target measure controls driven by the tempo-aware
  timeline beat/bar grid. Original events remain untouched.
- Empty source ranges, invalid ranges, and pasted events beyond track duration
  reject the operation before saving. Successful pastes create one history
  revision and regenerate MIDI from canonical events.
- Added API tests for relative timing, metadata preservation, one-revision
  semantics, MIDI synchronization, empty-source rejection, and overflow
  atomicity. CI validation is pending for this increment.


### Measure-copy validation update

- Backend tests run #171 passed: 62 tests; Ruff passed.
- DrumScript engine validation run #162 is queued/pending. This editor-only API change does not modify the inference engine; engine workflow completion is still tracked.
- A fresh repository frontend build result has not yet been confirmed for this head.


## 2026-11-11 — built-in printable PDF drum score export (implementation, CI pending)

- Added a ReportLab-based PDF renderer that lays canonical drum events onto a
  landscape percussion staff with measure boundaries/numbers, tempo and meter
  metadata, velocity-scaled noteheads, instrument-specific notehead styles,
  and a compact instrument legend. Long arrangements paginate by systems.
- Added `GET /api/projects/{project_id}/pdf`, which always renders the latest
  completed canonical performance, so manual corrections, quantization,
  undo, and redo are reflected in the printout.
- Added a PDF download link next to MIDI and editable MusicXML, declared the
  ReportLab runtime dependency, and updated the user guide/API/README.
- Added API tests for PDF signature/content type/download disposition and the
  missing-performance 404 path. CI is pending; no build or test pass is claimed
  until the workflow results are observed. MusicXML remains the editable score
  interchange format; PDF is the printable reading/printing format.


## 2026-11-11 — adopt Verovio for professional PDF engraving

- Replaced the hand-drawn PDF as the primary path with Verovio, a mature
  open-source notation engraving engine that imports MusicXML and renders
  vector SVG pages. CairoSVG converts each vector page to PDF and pypdf
  assembles multi-page output. ReportLab remains a minimal-install fallback.
- Added pinned-compatible runtime ranges for Verovio 6.4, CairoSVG, and pypdf.
  Verovio is LGPL-3.0; no Verovio source is vendored or modified.
- Strengthened the PDF API test to parse the returned PDF and require at least
  one real page. CI will validate MusicXML import, engraving, SVG-to-PDF
  conversion, and PDF assembly on the next run.
- OSS references: https://github.com/rism-digital/verovio and
  https://book.verovio.org/installing-or-building-from-sources/python.html .


## 2026-11-11 — timeline marquee selection and drag move

- Added pointer-based marquee selection across visible instrument lanes and a
  live selection rectangle. Dragging on empty timeline space selects events
  within both the time and lane range.
- Dragging a selected hit previews and applies a shared time offset to the
  whole selected group through the existing atomic batch-edit endpoint. The
  API still enforces song bounds, creates one history revision, and regenerates
  MIDI; click-to-seek behavior is preserved for non-drag clicks.
- Added visual marquee styling and updated the user guide. Frontend production
  build is pending for this increment.


### 2026-11-11 validation checkpoint — Verovio + timeline drag

- Verovio PDF path is exercised by the API test: backend test suite reports
  64 passed, including parsing the returned PDF with pypdf (workflow run
  #180 / CI backend test job).
- Frontend production build passed on the commit containing marquee selection
  and drag-move (CI run #269).
- Ruff caught import-order-only issues in the PDF test imports on two workflow
  attempts. Both were corrected; latest fix commit
  `0953ebbf036ce47ea623ff363fa29db20b74a6ee` is awaiting its own lint result.
- DrumScript upstream test and repository MP3 end-to-end workflow is still
  running; do not treat the engine smoke test as passed until its final status
  is recorded.


## 2026-11-11 — PDF fallback layout correction and regression coverage

- Moved system labels and the initial time signature into a dedicated left
  gutter, separated bar numbers from the staff, and annotate later meter
  changes only where they occur instead of repeating the initial meter.
- Added fallback-renderer regression tests for single- and multi-system
  scores, PDF page readability, system labels, and time-signature repetition.
- CI is pending for this increment. Visual review of a freshly rendered PDF
  remains required before calling the layout fully accepted.


## 2026-11-11 — portable full-project backup export

- Added a ZIP endpoint and workspace download link bundling the original uploaded
  audio, latest canonical performance JSON, MIDI, editable MusicXML, printable
  PDF, and a short README manifest.
- The bundle reads the latest completed canonical performance so edits and
  history restores are reflected in the exported files. Added API coverage for
  archive contents and the not-yet-analyzed response. CI pending.


## 2026-11-11 — graceful PDF engraving fallback

- CI exposed that the Verovio Python package can be installed while its SMuFL
  font resources are unavailable, causing score loading to raise a ValueError.
- PDF export now falls back to the ReportLab renderer for that specific
  unusable-engraving condition, rather than failing the entire export and
  project backup. Added a regression test for this path.
- Full-project backup export is now covered by archive-content API tests;
  CI rerun pending.


## 2026-11-11 — PDF page geometry and external benchmark acquisition

- Corrected the Verovio SVG-to-PDF conversion to set an explicit landscape A4 output surface. CairoSVG otherwise interprets SVG pixel dimensions at 96 DPI, which can make the physical PDF page size differ from the intended paper size.
- Added PDF regression coverage for A4 media-box dimensions on both the Verovio primary renderer and the ReportLab fallback, in addition to existing text/layout checks. CI must confirm the new primary-renderer assertion before this fix is considered verified.
- Added `docs/TEST_DATASETS.md` with a staged, licence-aware acquisition plan for IDMT-SMT-Drums, GMD, E-GMD, ENST-Drums, and QUASI. Audio remains outside Git; each benchmark case must preserve provenance, licence, checksum, and reviewed annotation metadata.
- No external dataset has yet been downloaded into the repository or scored. The first practical target is a small IDMT subset plus a fixed GMD held-out subset; real mixed-song evaluation requires separate track-level rights review.


## 2026-11-11 — annotated IDMT regression benchmark added to engine CI

- Reused the upstream DrumScript IDMT-SMT-Drums V2 benchmark adapter rather than creating a second annotation parser. The upstream adapter already pairs `#MIX.wav` recordings with XML/SVL labels and scores kick, snare, and hi-hat onset events at a 50 ms tolerance.
- Added an engine-validation CI step that downloads the 287 MB IDMT archive from Zenodo, runs the first 10 annotated RealDrum mixes, and uploads metrics as a workflow artifact. Raw dataset audio stays outside Git; the run is an evaluation-only use under the dataset's non-commercial/no-derivatives terms.
- This is the first labelled regression benchmark in our pipeline. It does not measure full-band mixed-song separation; QUASI remains a later candidate pending per-track licence review.
- Latest PDF resource-path and A4 regression changes are awaiting the current CI run. Previous attempts exposed and corrected a missing `Path` import and an incorrect multi-page test expectation; those failed runs are not counted as passes.

## 2026-11-11 — CI acceleration: FFmpeg provisioning

- The IDMT engine-validation workflow's FFmpeg setup was spending excessive time in the Ubuntu package-manager path (apt-get update / apt-get install).
- Replaced that fallback with the pip-distributed imageio-ffmpeg binary when the runner does not already provide FFmpeg; the binary directory is added to GITHUB_PATH and verified with ffmpeg -version.
- This keeps the runner-provided FFmpeg fast path and removes the slow apt repository refresh from the fallback path.
- The previous benchmark run had not yet reached dataset download or scoring, so no IDMT accuracy result is claimed. The workflow will rerun on this commit.

- Follow-up CI correction: imageio-ffmpeg exposes a versioned executable name rather than a literal ffmpeg command. The workflow now creates a runner-temp ffmpeg symlink and adds that directory to PATH before verifying the binary. The first pip-based attempt failed at the verification command before any benchmark work ran; no accuracy result is available yet.

## 2026-11-11 — First labelled IDMT benchmark completed

- The CI workflow successfully downloaded the IDMT-SMT-DRUMS-V2 evaluation archive, ran the upstream adapter on 10/10 RealDrum mixes, and uploaded the metrics artifact (workflow run #213, artifact `idmt-drum-transcription-benchmark`).
- Macro-average at the upstream adapter's 50 ms onset tolerance: kick P=0.700 / R=0.070 / F1=0.123; snare P=0.706 / R=0.914 / F1=0.775; hi-hat P=0.907 / R=0.996 / F1=0.949.
- Interpretation: kick recall is the major quality blocker; the score is an initial 10-item baseline, not a production-accuracy claim. Expand the held-out sample before making broad claims.
- The same workflow passed synthetic full-mix separation/transcription and canonical MIDI normalization. Repository MP3 processing then failed during Demucs MP3 decoding because its loader could not locate/use FFmpeg in that subprocess, despite the workflow's FFmpeg verification step.
- Updated `scripts/engine_smoke.py` to explicitly decode repository MP3 samples to PCM WAV with the imageio-ffmpeg executable (or system FFmpeg fallback) before passing the audio into Demucs. This preserves real repository MP3 coverage while avoiding Demucs' optional MP3 decoder lookup path. CI must validate this correction.


## 2026-11-11 — kick recall research and cross-domain benchmark expansion

- Investigated public ADT research and open implementations: IDMT-SMT-Drums, MDB Drums, ADTOF, a Librosa-onset + CNN baseline, adaptive onset detection with spectral/tail templates, and the 2026 Separate-and-Detect five-stem approach.
- Added `docs/KICK_RECALL_RESEARCH.md` with cited sources, testable failure hypotheses, dataset/license notes, and a staged diagnostic plan. The causes are explicitly hypotheses, not asserted facts.
- Expanded IDMT CI evaluation from the first 10 RealDrum mixes to 15 examples each from RealDrum, WaveDrum, and TechnoDrum, with distinct run names and archived per-track metrics. This checks whether the low kick recall is domain-specific instead of extrapolating from one subset.
- Disabled cancellation of an in-progress engine-validation run when a new commit arrives; this long-running CPU benchmark should finish rather than repeatedly being cancelled by rapid pushes.
- The expanded benchmark and MP3-to-WAV smoke correction are awaiting CI execution. No accuracy improvement is claimed yet.


## 2026-11-11 — stage-wise kick miss diagnostics

- Added `scripts/kick_stage_diagnostics.py`. It evaluates each IDMT kick reference twice: first against all onset candidates before classification, then against events classified as kick. It reports candidate recall, final kick recall, kick precision, and candidate-to-kick match retention per subset and per track.
- The engine-validation workflow now runs this diagnostic on 15 tracks from each of RealDrum, WaveDrum, and TechnoDrum and uploads JSON/CSV alongside the upstream per-track benchmark archives.
- Interpretation rule: low candidate recall indicates the shared onset stage is missing kick opportunities; healthy candidate recall but low final kick recall points to classification/feature rules. This is a diagnostic decomposition, not a claim that either failure mode has already been observed.
- CI is running/pending for the new diagnostic script and workflow. The first output will determine which algorithm branch to change next.


## 2026-11-12 — API runtime dependency and export visual smoke coverage

- The first expanded stage-wise run evaluated 14 RealDrum, 15 WaveDrum, and 11 TechnoDrum tracks (the dataset contains fewer eligible files in two subsets). Candidate-onset recall was 0.983 / 0.963 / 0.990, while final kick recall was 0.053 / 0.172 / 0.571. These are subset-level diagnostic results, not production accuracy claims.
- The API-to-engine end-to-end smoke exposed a real worker-image dependency gap: the workflow had ffmpeg but not ffprobe, which the API uses to read source duration. Replaced the workflow provisioning step with system FFmpeg installation and explicit checks for both executables. Backend unit tests and frontend/backend CI passed on the dependency-fix commit; the full engine workflow is rerunning.
- Added feature-level diagnostics for IDMT reference kicks that already match an onset candidate. The archived JSON now includes per-candidate LFER, peak frequency, centroid, HFER, high-frequency energy, decay, and pass/fail against the current kick-rule thresholds. This measures which boundaries reject candidate kick events before any classifier changes are attempted.
- Extended the API end-to-end smoke to call the PDF endpoint, validate PDF signature/page count/landscape-A4 geometry, preserve the generated PDF, rasterize its first page with Poppler, and upload both PDF and PNG as a CI artifact. This creates a reviewable visual regression artifact rather than relying only on PDF metadata tests.
- The PDF raster/artifact step and expanded kick-feature diagnostics are pending on the current PR #4 engine-validation run. No PDF visual acceptance or kick-recall improvement is claimed until those artifacts and metrics are reviewed.



## 2026-11-12 — avoid unnecessary media-tool installation on CI runners

- The latest engine-validation run remained in the media-tool provisioning step
  even after removing the explicit apt repository refresh. The workflow now
  checks for ffmpeg, ffprobe, and pdftoppm first and installs FFmpeg/Poppler
  packages only when one or more tools are missing.
- This uses the preinstalled GitHub-hosted runner binaries when available and
  avoids a package-manager round trip on already-provisioned runners. The next
  run must still prove that all three tools are present and the full engine,
  benchmark, MP3, and PDF-render stages complete; no pass is inferred from this
  workflow change alone.


## 2026-11-12 — remove Ubuntu apt mirror dependency from engine validation

- Inspected the failed GitHub Actions job log: the runner did not have
  ffmpeg/ffprobe/pdftoppm preinstalled, and Ubuntu package downloads repeatedly
  failed DNS resolution against the Azure archive mirror. The install step
  spent about 33 minutes downloading most packages before apt exited 100.
- Replaced apt-based media provisioning with the Python ffmpeg-downloader
  package and its static FFmpeg build, exposing both ffmpeg and ffprobe on PATH.
  The workflow also installs pypdfium2 from PyPI for PDF rasterization.
- The API smoke now renders the first PDF page in-process, validates the PNG
  signature and non-trivial file size, and uploads the PDF plus rendered PNG.
  Poppler/pdfinfo are no longer required.
- This removes the failing Ubuntu mirror dependency, but the next CI run must
  still verify the binary download, full inference, repository MP3s, PDF
  generation, and raster output. No engine or visual pass is claimed yet.


## 2026-11-12 — PDF notation scale follow-up
- Re-inspected the regenerated API PDF artifact from engine run 43125687384. The tempo label is now readable, but the notation still occupies too little vertical space on landscape A4; visual acceptance remains blocked.
- The prior Verovio setting used `scale: 52`, although Verovio defines 100 as normal output size. Updated the engraving scale to 100 and enabled vertical justification with an 0.8 maximum vertical justification ratio.
- This is a targeted layout correction, not yet a visual pass. The next engine run must regenerate and inspect the page image before claiming PDF readability.
- Official reference: Verovio toolkit options document scale as a percentage with 100 normal size and describe vertical justification as filling page spacing.
