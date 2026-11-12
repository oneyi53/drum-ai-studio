# DrumAI Studio test-audio datasets

Use external datasets as test inputs; do not commit their audio, annotations, or model outputs to Git. Store downloaded data outside the repository and retain the source URL, dataset version, checksum, licence, and attribution with each local benchmark manifest.

## Recommended acquisition order

### 1. IDMT-SMT-Drums — compact annotated starter set

- Source: https://zenodo.org/records/7544164
- Size: about 287 MB; 608 mono WAV files, approximately 2 h 10 min.
- Content: acoustic, sample-library, and synthesized drum loops; 104 polyphonic loops have manually annotated kick, snare, and hi-hat onsets. Selected subsets also provide isolated instrument tracks.
- Licence: CC BY-NC-ND 4.0; Fraunhofer states evaluation use. Keep this strictly to non-commercial research/evaluation, do not redistribute modified derivatives, and review the dataset terms before use.
- Best use: first labelled regression set for hit detection and instrument classification, not a substitute for full mixed-song evaluation.

### 2. Groove MIDI Dataset (GMD) — aligned human performances

- Source: https://magenta.withgoogle.com/datasets/groove
- Size: 13.6 hours, 1,150 MIDI performances and aligned synthesized audio.
- Content: expressive performances by 10 drummers, with train/validation/test splits, genre, tempo, beat/fill metadata, and audio aligned to MIDI within approximately 2 ms.
- Licence: CC BY 4.0. Preserve attribution and dataset citation.
- Best use: high-quality timing, velocity, fill, and groove evaluation. It contains drum performances rather than complete band mixes.

### 3. Expanded Groove MIDI Dataset (E-GMD) — scale and kit diversity

- Source: https://magenta.withgoogle.com/datasets/e-gmd
- Size: 444 hours across 43 drum kits; full audio archive is about 90 GB, with a much smaller MIDI-only archive.
- Content: re-recorded human performances with aligned MIDI and velocity annotations.
- Licence: CC BY 4.0. Preserve attribution and dataset citation.
- Best use: later large-scale robustness testing across drum kits. Start with GMD before pulling the 90 GB archive.

### 4. ENST-Drums — acoustic kit and playing-technique diversity

- Source: https://zenodo.org/records/21506051
- Size: about 9.6 GB; three professional drummers, roughly 75 minutes per drummer, eight audio channels, and detailed annotations.
- Content: different genres, kits, sticks/rods/brushes/mallets, and multi-microphone recordings.
- Licence: CC BY-NC-ND 4.0, research use only; no commercial use. Confirm terms and access conditions before downloading.
- Best use: later stress tests for acoustic timbre, bleed, and playing technique.

### 5. QUASI — real mixed music and source stems

- Source: https://records.sigmm.org/?open-source-item=quasi-database-for-the-evaluation-of-music-source-separation
- Content: 11 multitrack songs, professionally mixed in several ways; mixes and original sources are described as available under Creative Commons licences.
- Best use: full-mixture and drum-stem separation experiments. Verify the licence of each recording and retain per-track attribution before adding any item to a benchmark.

## Important limits

- GMD/E-GMD and IDMT/ENST primarily test drum-only transcription or drum-signal robustness. They do not alone measure transcription quality on arbitrary commercial songs with vocals, bass, guitars, and dense mixes.
- QUASI is a promising real-mix source, but track-level licence terms must be checked before use.
- Do not assume that a dataset being downloadable means it is cleared for commercial training, public demo hosting, or redistribution.
- The benchmark runner requires each case to have a declared permission basis and a human-reviewed canonical reference. Dataset-provided annotations must be converted and spot-checked before being treated as gold labels.
- Split by original recording/session, not by random excerpts, to prevent leakage between development and evaluation.

## Staged rollout

1. Start with a small IDMT subset for annotated kick/snare/hi-hat regression and parser validation.
2. Add a fixed GMD subset using the provided held-out test split for timing/velocity scoring.
3. Add selected QUASI items only after track-level rights review, to measure real-mixture robustness.
4. Expand to E-GMD and ENST when storage and runtime budgets permit.
5. Keep a separate human-reviewed evaluation split untouched during model/configuration tuning.

Every benchmark report must record dataset version, source identifier, licence/permission basis, audio checksum, annotation revision, engine commit/configuration, and timing tolerance.