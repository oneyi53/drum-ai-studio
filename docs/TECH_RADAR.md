# Technology radar

Living notes on upstream engines and adjacent projects. Re-check on every
work session on this project; add new entries with date, license, and a
one-line verdict. Nothing here is adopted until it is installed, run, and
measured against the project's own benchmark (see `KICK_RECALL_RESEARCH.md`).

Last sweep: 2026-11-13.

## Selection principle (user decision, 2026-11-13)

Pick engines by **measured success rate on the same benchmark**, not by
hype. Manual editing stays first-class: the editor and human corrections
are never removed, re-analysis must not overwrite manually corrected
events, and corrections carry provenance (`manually_corrected`).

## Engines in play

### DrumScript (current engine, Apache-2.0)
- v0.3.0, alpha since June 2026; beta targeted late 2026–2027 on API
  stability and benchmark validation. History rewritten 8 Oct 2026.
- Deterministic rule-based classifier (no ML); Demucs full-song stem
  extraction is optional. Known weak point in this project: post-onset
  kick classification — candidate recall ~98% but final kick recall
  5.3% / 17.2% / 57.1% (RealDrum / WaveDrum / TechnoDrum, IDMT-SMT-Drums).
- Verdict: keep as engine #1 while the fix in Issue #5 is measured.
  Watch upstream releases; do not vendor its code.
- Measured 2026-11-13 (IDMT-SMT-Drums, 50 ms tolerance, 55 tracks):
  retuning the kick LFER gate 0.32 -> 0.10 lifts pooled kick F1
  0.395 -> 0.838 (recall 0.254 -> 0.838, precision 0.885 -> 0.837);
  held-out WaveDrum F1 0.366 -> 0.643. Cost: TechnoDrum precision
  0.773, low-tom trade-off unmeasured. Fix lives in
  `backend/app/engine_adapter.py` (`KickClassificationConfig`, runtime
  override with restore, fail-closed on upstream changes).

### STRUM (candidate engine #2 — evaluate next)
- arXiv May 2026: Demucs HTDEMUCS_6S separation, two-stage CRNN onset
  detector, six-model ensemble drum classifier. Reports drums onset
  F1 0.838 on a 30-song benchmark (Clone Hero charting, 7-channel drum
  vocabulary). Claims a complete open-source pipeline.
- Verdict: highest-priority alternative. Next step is to find its code
  release, check license, and run it on the same IDMT tracks as
  DrumScript for a like-for-like kick recall comparison. The project's
  engine-independent evaluator (`DRUM_EVENT_EVALUATION.md`) already
  supports this comparison without changing the scoring contract.
- Status 2026-11-13: evaluation in progress (same IDMT tracks, same
  50 ms tolerance). Winner by measured kick F1 becomes the main engine;
  the loser stays as fallback/reference.

### ADTOF-pytorch (candidate engine #3 — license caution)
- Code MIT-ish; model weights CC BY-NC-SA 4.0 (non-commercial).
  Demucs → ADTOF is proven end-to-end (DrumLab wraps it, AGPL-3.0).
- Verdict: evaluate for accuracy only. The non-commercial weights
  rule out shipping it in any commercial distribution; treat as a
  measurement reference unless licensing is clarified.

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

## Commercial / closed (excluded)
- MVSEP, Klangio, Moises, Songscription: hosted/paid services. Not
  dependencies; may be used only as manual accuracy references.
