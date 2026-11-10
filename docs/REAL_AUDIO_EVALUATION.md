# Real-audio evaluation protocol

This phase adds a reproducible way to score a transcription against human annotations. It does **not** enable the API analysis endpoint or claim that the current engine is accurate.

## 1. Prepare a rights-cleared test recording

Use a recording you own, have permission to process, or that is explicitly licensed for this use. Keep the original audio and annotations outside the public repository unless redistribution is permitted. Record the source, license/permission basis, duration, sample rate, channel count, genre, and any known tempo/time-signature changes in a local dataset manifest.

Start with three contrasting recordings:
- Straight pop/rock with a stable tempo.
- Dense rock/metal with fills and cymbal changes.
- Funk/jazz or swung material with ghost notes and offbeat accents.

Do not tune the evaluation set against the same song used for development. Keep at least one track held out.

## 2. Create the reference annotation

Annotate audible drum events by onset in seconds and instrument. Save a UTF-8 CSV with this header:

```csv
onset_seconds,instrument
0.000,kick
0.500,snare
0.750,closed_hat
1.000,kick
```

Supported canonical labels include `kick`, `snare`, `closed_hat`, `open_hat`, `low_tom`, `mid_tom`, `high_tom`, `crash`, and `ride`. Aliases such as `bass_drum` and `hihat` are normalized. Use one row per audible hit. Annotate the audible onset consistently; document uncertain or masked hits rather than silently omitting them.

## 3. Run the evaluator

The evaluator reads the reference CSV and a MIDI prediction with a percussion track (`is_drum=True`). It maps General MIDI percussion pitches to instrument labels and matches events one-to-one by instrument within a default 50 ms onset tolerance.

```bash
python scripts/evaluate_midi.py \
  --reference /path/to/reference.csv \
  --prediction /path/to/drumscript-output.mid \
  --tolerance-ms 50 \
  --output /path/to/report.json
```

The JSON report includes overall and per-instrument precision, recall, F1, false positives, false negatives, and mean absolute onset error for matched events.

## 4. Interpret metrics

- Precision answers: of the predicted hits, how many matched a reference hit?
- Recall answers: of the annotated hits, how many were found?
- F1 balances precision and recall.
- Onset error is reported only for matched events.
- Wrong-instrument predictions count as one false positive and one false negative. This avoids rewarding a snare mislabeled as a kick.

Always report the tolerance alongside metrics. Review 25 ms, 50 ms, and 100 ms tolerances if timing sensitivity matters. Do not compare scores produced with different annotation conventions or tolerance windows.

## 5. Known limitations

- The current evaluator assumes a General MIDI drum pitch mapping and a MIDI percussion track marked `is_drum=True`. Confirm the engine's output mapping before interpreting instrument scores.
- Matching is greedy and chronological within each instrument; it is intended for a first benchmark, not a formal MIR challenge scorer.
- It does not yet evaluate tempo maps, swing feel, note velocity, sticking, notation readability, or PDF/MusicXML export.
- Synthetic smoke tests establish pipeline execution, not real-song accuracy.

## Acceptance gate before enabling analysis

Do not enable `POST /api/projects/{project_id}/analyze` until the engine has been tested on a rights-cleared, human-annotated set; MIDI output has been inspected; failure cases and supported styles are documented; and the API can persist versioned analysis results without overwriting source audio.
