# DrumAI Studio project log

This log records repository milestones and verified boundaries. Update it when
code or validation state changes; do not infer completion from plans.

## 2026-11-11 — canonical event and evaluation foundation

### Implemented in PR #3

- Added `backend/app/drum_events.py` with schema version 1.0:
  - Drum instruments: kick, snare, closed/open/pedal hi-hat, ride, crash,
    high/mid/low tom, other.
  - Absolute event time, MIDI velocity, optional confidence, source,
    manual-correction flag, and unique event ID.
  - Performance duration and ordered tempo/time-signature map.
  - Strict validation for unknown fields, invalid values, and events outside
    the performance duration.
- Added deterministic event-level evaluator:
  - One-to-one instrument-aware matching.
  - Configurable timing tolerance (default 50 ms).
  - Overall and per-instrument precision, recall, F1, counts, and matched-event
    mean absolute timing error.
- Added unit tests, a `drumai-evaluate` JSON-report CLI, and `docs/DRUM_EVENT_EVALUATION.md`.
- Added `backend/app/midi_adapter.py` to normalize General MIDI percussion note-ons into canonical events, preserving velocity, tempo, time signatures, and absolute seconds.
- Added `drumai-midi-import` CLI, MIDI fixtures/tests, and `docs/MIDI_ADAPTER.md` documenting the channel-10 and GM pitch assumptions.
- Added a dedicated backend GitHub Actions workflow to install backend dev dependencies, run the complete backend test suite, and lint the touched pipeline modules.
- This is a generic GM adapter only: DrumScript-specific channel/pitch semantics remain unverified until its generated MIDI can be inspected.
- Overall metrics aggregate per-instrument matches so an instrument substitution cannot be counted as a correct hit.
- Updated README and architecture documentation.

### Validation state

- Unit tests are committed but PR CI result is not yet available at log time.
- No human-annotated golden dataset has been committed.
- The generic GM MIDI-to-canonical adapter exists, but DrumScript-specific channel and pitch mapping has not been verified.
- The analysis endpoint remains HTTP 501; it must not be enabled until the
  engine adapter and end-to-end outputs are validated.
- Event metrics are an evaluation tool, not evidence of current transcription
  accuracy.

## In progress / next engineering milestones

1. Verify PR #3 CI and correct any schema/test issues.
2. Inspect the DrumScript MIDI output format from the engine validation run and
   verify whether its channel and note numbers follow the General MIDI map; add
   a versioned engine mapping profile if they do not.
3. Add permission-cleared, manually reviewed reference annotations and a
   reproducible benchmark manifest.
4. Run event-level scoring against those references; report per-instrument
   metrics and timing tolerance without inventing thresholds.
5. Only then integrate the adapter behind an explicit analysis-job boundary.
6. Add editor operations and MIDI/MusicXML/PDF exporters against the same
   canonical model.

## 2026-11-10/11 — engine integration spike (PR #2)

- Added isolated Python 3.12 GitHub Actions validation for CPU PyTorch,
  DrumScript import/CLI, upstream non-slow tests, synthetic full-mix smoke,
  and repository-root MP3 smoke.
- The latest recorded engine run at the time of this log is still running its
  synthetic/repository audio smoke step. Its result must be checked before
  calling the engine validation complete.
- A non-empty MIDI artifact is only an integration smoke result; it is not an
  accuracy benchmark.
