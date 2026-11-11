# Canonical drum events and evaluation

## Purpose

The canonical event model is the shared contract between transcription, manual
correction, the editor, and all exporters. Engine-specific MIDI/JSON output
must be normalized into this model before it reaches product features.

## Event contract (schema version 1.0)

Each event contains:

- `id`: stable unique event identifier
- `time_seconds`: absolute time from the start of the source audio
- `instrument`: `kick`, `snare`, `closed_hihat`, `open_hihat`,
  `pedal_hihat`, `ride`, `crash`, `high_tom`, `mid_tom`, `low_tom`,
  or `other`
- `velocity`: MIDI velocity from 1 to 127
- `confidence`: optional model confidence in [0, 1]
- `source`: `model`, `manual`, or `imported`
- `manually_corrected`: whether a person has corrected the event

A performance also stores its duration and an ordered tempo map. Tempo changes
include time, BPM, and time-signature numerator/denominator. Event times are
absolute seconds; bar/beat positions are derived from the tempo map and must
not be treated as stable identifiers.

Python API: `app.drum_events.DrumPerformance`, `DrumEvent`,
`TempoChange`, and `evaluate_performance`. A CLI is also installed as
`drumai-evaluate` when the backend package is installed.

## Accuracy evaluation

`evaluate_performance(reference, predicted, tolerance_ms=50)` compares
predictions to a human-annotated reference:

- Instrument labels must match exactly.
- A prediction can match at most one reference event.
- A match is accepted when absolute timing error is within the configured
  tolerance (default +/-50 ms).
- Precision = TP / (TP + FP); recall = TP / (TP + FN); F1 is their harmonic
  mean.
- Mean absolute timing error is reported for matched events only.
- Results include overall and per-instrument metrics.

Run the evaluator against two serialized `DrumPerformance` JSON files:

```bash
cd backend
pip install -e .
drumai-evaluate --reference reference.json --predicted predicted.json --tolerance-ms 50
```

The command prints a JSON report suitable for saving as a benchmark artifact.
The evaluator is deterministic and does not claim that any engine meets a
quality threshold. Empty-vs-empty is reported as 1.0 for precision, recall,
and F1 because there are no errors; reports must still include event counts.

## Ground-truth dataset policy

Do not use copyrighted recordings unless the project has permission to process
and retain them. Each benchmark case should include:

1. Audio provenance and usage permission.
2. Audio duration and sample rate.
3. A manually reviewed reference event list in the canonical schema.
4. Annotator/reviewer and annotation revision.
5. Engine name, exact revision, and configuration for each prediction.
6. The tolerance used when reporting metrics.

Start with short, permission-cleared excerpts spanning sparse and dense
arrangements. Split excerpts by source recording, not by random event, to
avoid leakage between development and evaluation sets.

## Current limitations

- The evaluator scores canonical events; no DrumScript-to-canonical adapter is
  implemented yet.
- No human-annotated golden dataset is checked in.
- No accuracy result is claimed until predictions are normalized and scored
  against reviewed reference annotations.
- Tempo-map-aware bar/beat derivation and export adapters remain future work.
