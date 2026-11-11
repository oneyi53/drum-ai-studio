# Architecture

## Current foundation

```
React + TypeScript
       |
       | HTTP / JSON
       v
FastAPI
       |
       +-- Project metadata (SQLite)
       +-- Original audio (local storage)
       +-- Analysis adapter (not implemented yet)
       +-- Canonical DrumPerformance (implemented)
       +-- Event evaluation (implemented)
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

See [DRUM_EVENT_EVALUATION.md](DRUM_EVENT_EVALUATION.md) for the full contract.

## Accuracy evaluation

A deterministic evaluator compares model events to human-reviewed references.
It performs one-to-one instrument-specific matching within a configurable
timing window (default +/-50 ms), reporting precision, recall, F1, counts,
and mean absolute timing error overall and per instrument.

The evaluator is independent of any particular transcription engine. This
lets the project compare engines without changing the scoring contract.
There is not yet a DrumScript-to-canonical adapter or a permission-cleared,
human-annotated golden dataset; no accuracy claim is made.

## Engine boundary

The API must call an engine adapter rather than importing a specific
transcription implementation throughout the web layer. This allows controlled
comparison of candidate engines and makes it possible to replace a weak model
without rewriting project management or the editor.

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
