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
- Extended the DrumScript smoke workflow to install this adapter and require each generated MIDI to normalize into non-empty canonical events; PR engine run #27 is in progress.
- DrumScript's published MIDI exporter documents General MIDI Level 1 percussion mapping and a drum track routed to MIDI channel 10. The current smoke run checks that the actual generated files satisfy this contract.
- Overall metrics aggregate per-instrument matches so an instrument substitution cannot be counted as a correct hit.
- Updated README and architecture documentation.

### Validation state

- Backend CI run #5 completed successfully: 17 tests passed and Ruff reported all checks passed. The repository CI run #111 also completed both backend and frontend jobs successfully.
- Engine validation run #27 is currently installing the upstream engine and will next test canonical MIDI conversion on the synthetic signal and repository MP3s.
- No human-annotated golden dataset has been committed.
- The generic GM MIDI-to-canonical adapter exists; actual DrumScript MIDI output compatibility is being verified by engine run #27.
- The analysis endpoint remains HTTP 501; it must not be enabled until the
  engine adapter and end-to-end outputs are validated.
- Event metrics are an evaluation tool, not evidence of current transcription
  accuracy.

## In progress / next engineering milestones

1. Complete engine run #27 and fix any real DrumScript MIDI compatibility issues it reveals.
2. Create a permission-cleared, manually reviewed reference set and benchmark manifest.
3. Run event-level scoring against those references; report per-instrument
   metrics and timing tolerance without inventing thresholds.
4. Integrate the adapter behind an explicit analysis-job boundary.
5. Add editor operations and MIDI/MusicXML/PDF exporters against the same
   canonical model.

## 2026-11-10/11 — engine integration spike (PR #2)

- Added isolated Python 3.12 GitHub Actions validation for CPU PyTorch,
  DrumScript import/CLI, upstream non-slow tests, synthetic full-mix smoke,
  and repository-root MP3 smoke.
- Engine validation run #6 completed successfully: synthetic full-mix MIDI and
  both repository MP3 files produced non-empty MIDI outputs. The logs show
  765 classified events for `Creep (Album Version)_Radiohead.mp3` and 755 for
  `Psycho_Muse(1).mp3`. This verifies pipeline execution only, not event-level
  accuracy.
- A non-empty MIDI artifact is only an integration smoke result; it is not an
  accuracy benchmark.
