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
