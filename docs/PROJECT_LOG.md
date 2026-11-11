# DrumAI Studio project log

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
- Fresh backend and frontend CI for the editor changes is pending. No accuracy
  claim is made; model predictions still require human review.

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

- The new API/adapter/frontend code and tests are committed, but fresh backend
  and frontend CI results for these changes are still pending. Do not report the new tests as passing yet.
- Existing Engine validation run #27 proves the underlying DrumScript-to-MIDI
  and MIDI-to-canonical conversion path on synthetic and repository audio. It
  does not by itself prove this new API worker has run successfully in a
  deployed application.
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
