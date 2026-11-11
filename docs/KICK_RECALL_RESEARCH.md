# Kick-drum miss analysis and evidence-driven improvement plan

## Current measured symptom

The first labelled IDMT-SMT-Drums V2 baseline evaluated 10 RealDrum mixes at a 50 ms onset tolerance:

- Kick: precision 0.700, recall 0.070, F1 0.123
- Snare: precision 0.706, recall 0.914, F1 0.775
- Hi-hat: precision 0.907, recall 0.996, F1 0.949

This is a small initial sample, not a production accuracy estimate. The kick recall is nevertheless a severe blocker and must be debugged before parameter tuning.

## External research and reusable approaches

1. **IDMT-SMT-Drums (Fraunhofer IDMT)** — 608 mono 44.1 kHz WAV files, with 104 polyphonic loops and manually annotated kick/snare/hi-hat onsets. RealDrum, WaveDrum and TechnoDrum subsets allow domain comparison. WaveDrum02 and TechnoDrum02 also include isolated component tracks, enabling controlled mixture-vs-isolated diagnostics. Evaluation licence is CC BY-NC-ND 4.0; keep use within its terms.
   - https://www.idmt.fraunhofer.de/en/publications/datasets/drums.html
   - https://zenodo.org/records/7544164

2. **MDB Drums** — 23 real multitrack recordings with hand-checked annotations; the multitrack format permits different mixtures to be constructed (e.g. drums with/without bass). This is valuable for testing bass masking and real-world mix robustness. The dataset repository states CC BY-NC-SA 4.0; confirm terms before any redistribution or commercial use.
   - https://musicinformatics.gatech.edu/project/mdb-drums-dataset-for-automatic-drum-transcription/
   - https://github.com/CarlSouthall/MDBDrums

3. **Separate-and-Detect (ISMIR 2026)** — a five-stem kick/snare/toms/hi-hat/cymbals separation front-end followed by onset detection. The paper reports that an auxiliary onset branch during separator training provides stable transcription gains. This supports testing a kick-specific stem/detection path rather than forcing all instruments through one mixed-spectrum classifier.
   - https://arxiv.org/abs/2608.01093
   - https://github.com/ddman1101/Separate-and-detect

4. **ADTOF and drum-stem work** — published work explores combining multi-class drum transcription with separated instrument stems, including velocity estimation. This is a useful alternative model family to benchmark against a deterministic rules engine.
   - https://arxiv.org/abs/2509.24853
   - https://github.com/xavriley/ADTOF-pytorch

5. **Adaptive onset detection and spectral templates** — Eric Battenberg's dissertation describes adaptive causal thresholds to handle large dynamic swings, multiple spectral templates per drum, and decay-tail templates; the reported tail templates reduced detection errors by 42% in that system. This suggests checking dynamic-range sensitivity and kick decay/tail modelling rather than relying on a single fixed onset threshold.
   - https://escholarship.org/uc/item/6jf2g52n

6. **Open-source onset + CNN baseline** — drum-score-transcriber uses Librosa spectral-flux onset detection followed by a CNN over 200 ms mel-spectrogram windows, trained on IDMT. It is a practical comparison point for separating candidate generation from instrument classification.
   - https://github.com/connorgilchrist/drum-score-transcriber

## Engineering hypotheses to test (not yet established causes)

- **Candidate-onset loss:** low-frequency kick attacks may not trigger the shared onset detector strongly enough, especially with a soft beater, low velocity, or bass/guitar masking.
- **Classification loss:** a candidate onset may exist but be labelled as another instrument or rejected by fixed spectral/energy rules.
- **Masking and phase:** kick fundamentals and body commonly overlap bass fundamentals; phase cancellation and drum/bass overlap can weaken the kick signature in a mono mix.
- **Dynamic-range sensitivity:** a global peak normalization can leave quieter kick hits relatively weak when loud cymbals/snare dominate.
- **Window/timing mismatch:** a fixed analysis slice may miss the kick's short attack or confuse its longer low-frequency decay with neighbouring events.
- **Dataset/domain bias:** the first 10 RealDrum examples cannot establish whether the failure generalizes to sample-library and synthesized kits.

## Required diagnostic sequence

1. Preserve the current baseline and evaluator. Do not tune against the held-out evaluation split.
2. Run all three IDMT domains separately (RealDrum, WaveDrum, TechnoDrum), recording per-track counts and metrics.
3. On isolated-track subsets, compare kick detection on the isolated kick against the corresponding polyphonic mix. A large gap implicates masking/classification; failure on isolated kick points toward onset sensitivity or feature rules.
4. Instrument the pipeline to measure generic onset-candidate recall against kick references before classification, then final kick recall after classification. This identifies which stage loses events.
5. Inspect false negatives by kick level, spectral centroid/low-frequency energy, overlap with bass/snare/hat, and local dynamic range.
6. Compare controlled variants on the development split only: adaptive/local thresholds; low-frequency-band onset novelty; longer/multi-resolution analysis windows; kick-specific spectral templates; a small CNN/ADTOF classifier; and a separated-kick stem front-end.
7. Select a change only when it improves kick recall without unacceptable precision or snare/hi-hat regression, then verify once on the untouched held-out set.

## Guardrails

- Keep raw licensed audio outside Git and record source/version/licence/checksum.
- Never treat an unlabelled smoke test or a generated synthetic signal as transcription accuracy evidence.
- Record per-instrument precision, recall, F1, event counts, tolerance, engine revision and configuration for every run.
- Do not silently change canonical event semantics, MIDI export, or editor behavior while iterating on inference.
