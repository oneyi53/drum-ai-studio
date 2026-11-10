# P0 upstream audit

Audit date: 2026-11-10

This document records the initial source/license/dependency review. It is not a substitute for reviewing the exact upstream revision and all transitive assets at the time of integration.

## 1. DrumScript

Repository: https://github.com/DrumScript/DrumScript

Initial findings from upstream README, LICENSE, and pyproject metadata:

- Public repository; upstream license file identifies Apache License 2.0.
- README describes version 0.3.0 and labels the project alpha.
- README describes a full-song workflow that can use Demucs to extract a drum stem before drum analysis.
- Drum classification is described as deterministic/rule-based; do not describe it as an end-to-end neural drum-event model.
- README documents PDF, JSON, MIDI, and MusicXML outputs.
- Python constraint: >=3.9,<3.13.
- Declared dependencies include Demucs, librosa, matplotlib, music21, numpy<2, pretty-midi, pydub, reportlab, scipy, soundfile, torch>=2.4,<2.9, and torchaudio>=2.4,<2.9.

Decision: candidate engine for a controlled integration spike. It has **not** been cloned, installed, run, or tested in this environment. Network DNS prevented the earlier Git clone attempt. Do not claim otherwise.

## 2. Demucs

Repository: https://github.com/facebookresearch/demucs

- Upstream LICENSE file identifies MIT.
- Upstream README indicates the project is no longer actively maintained.
- Model checkpoints, downloaded assets, and third-party dependencies require their own review; the code license alone does not settle those rights.

Decision: candidate stem-separation dependency, subject to Python/PyTorch compatibility and model-asset review.

## 3. drum-transcribe

Repository: https://github.com/akaihola/drum-transcribe

Initial findings:

- README describes a prototype and explicitly says it is not intended for production use.
- The inspected project metadata references ADTOF, audio-separator, beat_this, Demucs, librosa, music21, pretty-midi, torch, and torchaudio.
- A root LICENSE file was not found in the initial inspection.

Decision: architecture/technical reference only. Do not copy, vendor, or redistribute its source until licensing is clarified.

## 4. Environment constraints

Previously detected in the available execution environment:

- Python 3.13.5
- Git 2.47.3
- uv 0.10.0
- FFmpeg 7.1.5

Python 3.13.5 is outside DrumScript's declared <3.13 range. A Python 3.12 environment is needed for a fair compatibility test.

The earlier attempt to clone DrumScript failed because the environment could not resolve github.com. Consequently, dependency installation, model download, pytest, and end-to-end audio transcription remain unverified.

## 5. Required checks before engine integration

- [ ] Obtain a pinned upstream revision and inspect its complete source tree.
- [ ] Re-check LICENSE and notices for all code and bundled assets.
- [ ] Create a clean Python 3.12 environment.
- [ ] Install dependencies from a reproducible lockfile.
- [ ] Run upstream tests and record exact command/output.
- [ ] Run a short known test audio through separation and transcription.
- [ ] Inspect event timing and instrument labels manually.
- [ ] Test pop, dense rock, and tempo-change examples.
- [ ] Verify export files open in target applications.
- [ ] Record model weight source, checksum, and license/terms.

No checkbox above should be marked complete without an actual recorded result.
