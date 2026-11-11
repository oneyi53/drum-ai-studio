# Architecture

## Current foundation

```
React + TypeScript
       |
       | HTTP / JSON
       v
FastAPI
       |
       +-- Project metadata + analysis jobs (SQLite)
       +-- Original audio + analysis artifacts (local storage)
       +-- Async job API (FastAPI BackgroundTasks; single worker)
       +-- Optional lazy DrumScript engine adapter
       +-- MIDI-to-canonical adapter (implemented and smoke-tested)
       +-- Canonical DrumPerformance (implemented)
       +-- Event evaluation + benchmark runner (implemented)
```

## Canonical event model

The versioned schema lives in `backend/app/drum_events.py`. A performance
contains absolute-time drum events and an ordered tempo map. Events carry a
stable ID, instrument, MIDI velocity, optional model confidence, provenance,
and manual-correction state. The schema rejects out-of-range values and
unknown fields so accidental contract drift is visible.

The current instrument vocabulary is kick, snare, closed/open/pedal hi-hat,
ride, crash, high/mid/low tom, and other. Event time is always seconds from
the start of the audio; bar/beat/subdivision are derived from tempo and meter
rather than stored as a competing source of truth.

See [DRUM_EVENT_EVALUATION.md](DRUM_EVENT_EVALUATION.md) for the full contract. Standard MIDI percussion files can be normalized with `backend/app/midi_adapter.py`; its General MIDI assumptions and limitations are documented in [MIDI_ADAPTER.md](MIDI_ADAPTER.md).

## Accuracy evaluation

A deterministic evaluator compares model events to human-reviewed references.
It performs one-to-one instrument-specific matching within a configurable
timing window (default +/-50 ms), reporting precision, recall, F1, counts,
and mean absolute timing error overall and per instrument.

The evaluator is independent of any particular transcription engine. This
lets the project compare engines without changing the scoring contract.
The generic General MIDI MIDI-to-canonical adapter is implemented. DrumScript output was smoke-tested on a synthetic mix and two repository MP3s; generated MIDI converted to non-empty canonical events. This verifies integration compatibility only, not transcription accuracy. There is no permission-cleared, human-annotated golden dataset; no accuracy claim is made.

## Engine boundary

The API invokes the lazy `DrumScriptEngine` adapter from an asynchronous analysis job. The adapter loads the optional engine at execution time, runs full-song transcription in an isolated temporary directory, validates the MIDI artifact, normalizes channel-10 percussion into canonical events, and persists the MIDI plus canonical JSON. The ordinary backend install does not install the heavy PyTorch/DrumScript runtime; the worker image must provide it along with FFmpeg/ffprobe.

The current queue uses FastAPI in-process background tasks and SQLite. It is intentionally limited to a single-worker development deployment. A durable queue and shared object storage/database are required before horizontal scaling.

## Notation and editing

OpenSheetMusicDisplay renders MusicXML. It is not, by itself, a complete
interactive drum notation editor. The editor will need its own event/grid
interaction layer and must update the canonical event model.

## Export

MusicXML is the interchange/notation representation. MIDI and PDF must be
generated from the same canonical events so edits remain consistent across
formats.

## Non-functional requirements

- Validate file extension, MIME type, and size.
- Generate server-side project IDs; never trust client paths.
- Keep uploaded audio outside the public frontend directory.
- Add cleanup, quotas, and authentication before public deployment.
- Do not expose arbitrary filesystem paths through API responses.
