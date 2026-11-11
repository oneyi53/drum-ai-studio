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
`TempoChange`, and `evaluate_performance`.

## Single-pair accuracy evaluation

`evaluate_performance(reference, predicted, tolerance_ms=50)` compares
predictions to a human-reviewed reference:

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
pip install -e ".[dev]"
drumai-evaluate --reference reference.json --predicted predicted.json --tolerance-ms 50
```

## Batch benchmark manifest

A batch runner now evaluates a manifest of reviewed cases and emits per-case
and aggregate event metrics:

```bash
cd backend
drumai-benchmark --manifest benchmarks/manifest.json --tolerance-ms 50 > benchmark-report.json
```

Start from `backend/benchmarks/manifest.example.json`. Each case must provide:

- Unique case ID and stable source-recording ID.
- Split: `development` or `evaluation`.
- Relative paths to the source audio, canonical reference JSON, and predicted
  canonical JSON (resolved relative to the manifest), plus declared audio
  duration and sample rate.
- Permission basis: `public_domain`, `licensed`, or `written_permission`.
- `annotation_status: "reviewed"`, reviewer, and annotation revision.

The runner requires a declared permission basis and reviewed-annotation
metadata, and refuses missing files, duplicate case IDs, and source recordings
that leak across development/evaluation splits. These metadata declarations are
not a legal or independent verification of the underlying rights or annotation quality.
The report includes per-case metrics, pooled micro-aggregates across all cases,
and separate development/evaluation aggregates. Pooled metrics count matched
events, not an unweighted mean of track scores. Preserve the manifest and
report with the engine revision/configuration used to generate predictions.

The example manifest is intentionally empty. Permission/reviewer fields are
attestations supplied by the dataset owner, not automated rights verification.
Do not add private or copyrighted
audio, annotations, or predictions to Git without explicit redistribution
permission. A valid manifest is not itself evidence that the annotations are
accurate; human review remains required.


## Manual event editing and MIDI synchronization

The analysis API exposes manual event editing on the latest completed project
performance:

- `POST /api/projects/{project_id}/events`: add a manual event with
  `time_seconds`, `instrument`, and optional `velocity`.
- `PATCH /api/projects/{project_id}/events/{event_id}`: update one or more
  of those fields. Omitted fields are unchanged; null values are rejected.
- `DELETE /api/projects/{project_id}/events/{event_id}`: remove an event.

All changes are validated against the performance duration. New and edited
events are marked `source: "manual"` and `manually_corrected: true`.
Updates are serialized with SQLite write transactions. Each successful edit
regenerates the downloadable MIDI from the canonical performance, so the
JSON result and MIDI artifact stay in sync.

The MIDI writer emits GM percussion channel 10, tempo changes, time signatures,
velocities, and the full performance duration (via the end-of-track event). The `other` canonical category is exported as GM side-stick
key 37 as a fallback; that category therefore cannot preserve an arbitrary
unmapped source pitch through a round trip.

## Ground-truth dataset policy

Do not use copyrighted recordings unless the project has permission to process
and retain them. Each benchmark case should include audio provenance and usage
permission, duration/sample rate, a manually reviewed event list, annotator and
revision, and the engine revision/configuration used for predictions.

Start with short, permission-cleared excerpts spanning sparse and dense
arrangements. Split excerpts by source recording, not by random event, to
avoid leakage between development and evaluation sets.

## Current limitations

- DrumScript MIDI output has passed a compatibility smoke on synthetic audio
  and two repository MP3s; this verifies conversion, not transcription accuracy.
- No human-annotated golden dataset is checked in and no accuracy result is
  claimed.
- Benchmark cases still need permission-cleared audio and independently
  reviewed reference annotations.
- Tempo-map-aware bar/beat derivation and editor/export adapters remain future
  work.
