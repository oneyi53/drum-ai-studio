# Technology radar

Living notes on upstream engines and adjacent projects. Re-check on every
work session on this project; add new entries with date, license, and a
one-line verdict. Nothing here is adopted until it is installed, run, and
measured against the project's own benchmark (see `KICK_RECALL_RESEARCH.md`).

Last sweep: 2026-11-21.

## Selection principle (user decision, 2026-11-13)

Pick engines by **measured success rate on the same benchmark**, not by
hype. Manual editing stays first-class: the editor and human corrections
are never removed, re-analysis must not overwrite manually corrected
events, and corrections carry provenance (`manually_corrected`).

## Verdict 2026-11-21: five engines fail in the same place

Five new engines (STRUM, ADTOF, ADT_STR, STAR, MuScriptor-small) were
each installed, run, and measured on the same real songs; all fail in the
same place — real-song kick, worst on electronic and blues — while the
production engine DrumScript fails there too (directional kick F1 rock
0.334 / electronic 0.379). The bottleneck is real-song training data,
not the engine. **Do not look for a sixth engine.** The way forward is
human-annotated references (Phase 2) and training from pseudo-labels
(five-way voting: 2,579 pseudo-labels from 7,977 clusters, 32.3%),
not another off-the-shelf model. Details per engine below; the full
evaluation reports live under `~/workspace/.ds-scratch/` (local only).

## Engines in play

### DrumScript (current engine, Apache-2.0)
- v0.3.0, alpha since June 2026; beta targeted late 2026–2027 on API
  stability and benchmark validation. History rewritten 8 Oct 2026.
- Deterministic rule-based classifier (no ML); Demucs full-song stem
  extraction is optional. Known weak point in this project: post-onset
  kick classification — candidate recall ~98% but final kick recall
  5.3% / 17.2% / 57.1% (RealDrum / WaveDrum / TechnoDrum, IDMT-SMT-Drums).
- Verdict: still engine #1. Phase 1 landed 2026-11-16 (pipeline
  reorder: Demucs on the raw mix, EQ only on the drums stem; crash
  decay suppression, 1.5 s window): IDMT kick F1 0.8395 with zero
  regression; real-song directional kick F1 rock 0.334, electronic
  0.379 (first-pass references, not true accuracy). The per-style
  thresholds, kick guard, EQ-on-mix, kick dual-channel, single-label
  rule, and tom HFER gate were all measured and rolled back.
- Measured 2026-11-13 (IDMT-SMT-Drums, 50 ms tolerance, 55 tracks):
  retuning the kick LFER gate 0.32 -> 0.10 lifts pooled kick F1
  0.395 -> 0.838 (recall 0.254 -> 0.838, precision 0.885 -> 0.837);
  held-out WaveDrum F1 0.366 -> 0.643. Cost: TechnoDrum precision
  0.773, low-tom trade-off unmeasured. Fix lives in
  `backend/app/engine_adapter.py` (`KickClassificationConfig`, runtime
  override with restore, fail-closed on upstream changes).

### STRUM (evaluated 2026-11-14 — DO NOT SWAP)
- arXiv May 2026: Demucs HTDEMUCS_6S separation, two-stage CRNN onset
  detector, six-model ensemble drum classifier. Reports drums onset
  F1 0.838 on a 30-song benchmark (Clone Hero charting, 7-channel drum
  vocabulary). Claims a complete open-source pipeline.
- Measured: IDMT kick F1 0.866; real-song directional kick F1 rock
  0.378, electronic 0.003. Verdict: DO NOT SWAP.

### ADTOF-pytorch (evaluated 2026-11-14 — DO NOT SWAP)
- Code MIT-ish; model weights CC BY-NC-SA 4.0 (non-commercial).
  Demucs → ADTOF is proven end-to-end (DrumLab wraps it, AGPL-3.0).
- Measured: IDMT kick F1 0.974; real-song directional kick F1 rock
  0.249, electronic 0.006, blues 0 events. Verdict: DO NOT SWAP.
  Fine-tune-for-personal-use only; the NC-SA weights never enter the
  public repo.

### ADT_STR (evaluated 2026-11-16 — falsified, DO NOT SWAP)
- Measured: IDMT kick F1 0.952; real-song directional kick F1 rock
  0.348, electronic 0.007. CC BY-SA 4.0. Verdict: falsified,
  DO NOT SWAP.

### STAR (evaluated 2026-11-21 — DO NOT SWAP, Phase-2 re-score list only)
- Frame model benchmarked against IDMT (PR #16, merged 2026-11-21):
  IDMT kick F1 RealDrum 0.9768 / WaveDrum 0.9866 / TechnoDrum 0.9476
  (regression check only). Real-song directional kick F1 rock 0.3513,
  electronic 0.1943 (precision only 0.13), blues 0 kicks; recovered
  only 3 of 17 bass-hidden electronic kicks. AGPL-3.0, eval-only.
  Verdict: DO NOT SWAP.

### MuScriptor-small (evaluated 2026-11-21 — falsified, DO NOT SWAP)
- CC BY-NC 4.0, gated Hugging Face repo (license accepted for the
  small model only; weights ~412 MB, eval-only, never committed).
- Measured (Phase B): electronic kick directional F1 0.0000 — the
  model produced 0 drum events on the whole electronic track (an
  unconstrained rerun also produced 0 notes, so it is not the
  drums-only constraint and not the file: STAR got 185 kicks and
  DrumScript 448 on the same file); bass-hidden recovery 0/17; rock
  kick 0.4431 (the rock reference is circular, so the ranking does
  not count); inference 0.53x realtime on this VM. Verdict:
  falsified, DO NOT SWAP.

### Basic Pitch (Spotify, Apache-2.0)
- Free audio→MIDI, best on single instruments; no full-mix separation,
  no sheet music. Already the fallback in the project's earlier
  audio-to-score study.
- Verdict: keep as a per-stem fallback, not a drum engine.

### Beat This! (integrated — tempo/beat tracking)
- Neural beat and tempo estimation (CPJKU, ISMIR 2024, MIT code +
  weights, `final0.ckpt` ~81 MB). Evaluated 2026-11-14: the stock
  tempogram estimator octave-errors on real songs (rock 69.8 vs true
  ~140, electronic 215.3 vs ~108); Beat This! + a longest-strong-IOI-mode
  derivation is within 5% of the reference tempo on 18/18 tracks (6 real
  songs + 12 IDMT), vs 10/18 for the stock estimator.
- Integrated as the tempo source in `backend/app/beat_this_tempo.py`:
  `DrumScriptEngine` replaces the tempo map with the fused Beat This!
  tempo (single change at t=0) when the checkpoint is available, and
  falls back to the stock tempo — octave-folded into [60, 180] when Beat
  This! runs but finds no beat track — otherwise. The checkpoint is
  optional and never committed: set `BEAT_THIS_CHECKPOINT` to the
  `final0.ckpt` path. Weights provenance: the official CPJKU Nextcloud
  link is server-throttled, so the checkpoint used for evaluation came
  from the Hugging Face mirror `oulianov/beat_this` (verified by size
  and load test; not the official release).
- Verdict: adopted for tempo correction. The MIDI file on disk still
  carries DrumScript's own tempo (only the performance tempo map is
  corrected) — a follow-up if MIDI tempo matters to users.

## Separation

- **HTDemucs stays** as the project's separator. SCNet XL IHF,
  HTDemucs FT, MDX23C, BS-RoFormer-SW, and DrumSep 5+6 were each
  measured and rejected: none routes electronic kicks back into the
  drums stem. MVSep Mega 53 untried (MIT, >=16 GB VRAM, low priority).

## Adjacent projects (reference only, do not copy)

- **Aviv3434/DrumAI** (Oct 2026 PoC): same stack shape as this project
  (Demucs + STRUM + Beat This!, Python/PyTorch + React/TS). Tested on
  one song, no accuracy claims. Architecture reference only.
- **uapmd-mir**: carries a C++ port of DrumScript, off by default
  "because the results are not yet trustworthy" — independent
  confirmation that DrumScript accuracy is the weak link.
- **Paradiddle, GrooveSheet, notagen.ai**: commercial drum-transcription
  products (paid per song). Benchmarks for product quality only; no
  code reuse.
- **theDAW** (gantasmo/theDAW-Pinokio, free, FastAPI + React): its drum
  transcription is NOT a named model and was explicitly NOT adopted as
  an engine. Its editor UI was studied (plan in
  `~/workspace/.ds-scratch/thedaw-ui-study/PLAN.md`): P0 follow-playback
  / shared zoom / atomic undo and P1 note refinement / per-voice export
  are in main; P2 click-note audition is in draft PR #18.
- **dettato** (kobimusic/dettato on Hugging Face): self-reported
  composite 59.2 / drums 47.1, author claims unverified — follow-up
  candidate only, not evaluated.

## Commercial / closed (excluded)
- MVSEP, Klangio, Moises, Songscription: hosted/paid services. Not
  dependencies; may be used only as manual accuracy references.
- **Photon** (iZotope, launched 2026-11-03): Drums 5 Stems
  (kick/snare/hat/toms/cymbals) from a drum bus or full song; $349,
  $259 until 2026-12-07; free trial exists; macOS 14+ Apple Silicon.
  Closed, no CLI/API — manual reference use only, cannot enter the
  pipeline. A free-trial run (electronic + rock through Drums 5 Stems,
  checking the 17 bass-hidden kicks) is pending the user's decision;
  verify macOS >= 14 first.
