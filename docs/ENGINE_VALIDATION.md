# Engine validation runbook

The engine-validation workflow is intentionally separate from the lightweight web/API CI because Demucs downloads model weights and the PyTorch CPU wheels are large.

## Run it

1. Open the repository's [Actions tab](https://github.com/oneyi53/drum-ai-studio/actions).
2. Select **DrumScript engine validation**.
3. If no run is already queued or running, choose **Run workflow** on the `main` branch.

The workflow performs these checks in order:

1. Creates a clean Python 3.12 environment on Ubuntu.
2. Installs FFmpeg.
3. Installs CPU PyTorch 2.8.0 and the current DrumScript source from its public GitHub repository.
4. Checks the Python import and CLI help.
5. Runs DrumScript's upstream non-slow pytest suite.
6. Generates a deterministic, copyright-free synthetic full mix and calls `drumscript.transcribe(..., full_song=True, midi_only=True)`.
7. Runs the same full-song path for each MP3 located at the repository root.
8. Verifies that each run returns a non-empty MIDI file. Generated outputs are isolated in a temporary directory.

The workflow is triggered by changes to this workflow, the smoke-test script, or root-level MP3 samples. It can also be started manually.

## Interpret results carefully

- **Install/import/CLI passed:** dependency and package startup are compatible in that runner environment.
- **Upstream tests passed:** the selected upstream test suite passed; this does not prove transcription accuracy.
- **Synthetic full-mix smoke passed:** Demucs separation plus DrumScript's full-song path completed for the generated test signal and produced a MIDI file.
- **Repository MP3 smoke passed:** the engine accepted the supplied MP3 input and produced a non-empty MIDI file. This is an integration check only, not a measure of transcription quality.
- **Real-song accuracy:** still requires human review of instrument labels, timing, tempo, and exports against the audio. Use recordings you have permission to process.

The workflow logs print the exact DrumScript Git commit SHA used in the run. Record that SHA with any reported result. A later upstream `main` revision may behave differently.

## Kick classification threshold override

The kick classifier lives upstream in DrumScript (`drumscript.drum_classifier.classify.classify_events`); it is not vendored here. The live rule is `lfer >= KICK_LFER_MIN (0.32)` and `40 Hz <= peak_freq <= 140 Hz`. IDMT-SMT-Drums diagnostics show onset-candidate recall for kick near 98% while final kick recall is far lower, so missed kicks are lost at this classification gate, not at onset detection.

`backend/app/engine_adapter.py` exposes `KickClassificationConfig(lfer_min, peak_freq_min_hz, peak_freq_max_hz)` on `DrumScriptEngine`. It temporarily overrides the thresholds on the upstream classifier module (which binds them as its own globals at import time — patching the constants module alone would not work) and restores them after each call. A config equal to the stock upstream rule is a no-op; any other config fails closed if the installed DrumScript revision does not expose the expected attributes.

The default is `lfer_min=0.10`, measured 2026-11-13 on IDMT-SMT-Drums V2 (50 ms tolerance, DrumScript HEAD e3c4707): pooled over 55 tuning tracks (969 kick references) it lifts kick recall 0.25 → 0.84 at precision 0.89 → 0.84 (F1 0.39 → 0.84), and on 15 held-out WaveDrum tracks (349 references, never used for threshold selection) recall 0.24 → 0.55 at precision 0.83 → 0.77 (F1 0.37 → 0.64). `lfer_min=0.15` is the conservative alternative (pooled F1 0.79, held-out F1 0.51). Pass an explicit `KickClassificationConfig(lfer_min=0.32)` to restore the stock upstream rule.

Measure a candidate threshold before adopting it, using the same diagnostic that produced the baseline:

```bash
python scripts/kick_stage_diagnostics.py --root "$IDMT_ROOT" --subset RealDrum \
  --limit 15 --lfer-min 0.20 --output /tmp/kick-diagnostics/realdrum-lfer020.json
```

Compare `kick_recall` against `kick_precision` for each subset (RealDrum, WaveDrum, TechnoDrum). Lowering `lfer_min` recovers kicks whose low-frequency energy share is diluted by bass or mix energy, but risks bass-guitar and low-tom false positives; a threshold is only adopted when it improves kick recall without unacceptable precision loss or snare/hi-hat regression. The diagnostic also reports the LFER / peak-frequency quartiles of reference-aligned kicks split by predicted vs missed, which is the evidence for where the gate should move.
