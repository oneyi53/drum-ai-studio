## 2026-11-14 — STRUM evaluation: complete, verdict DO NOT SWAP

- Repo `opria123/strum` HEAD 9f420cb, MIT (code + weights), arXiv
  2605.12135. Cloned locally (1.6 GB), CPU-runnable. Pipeline:
  Demucs htdemucs_ft → V14 two-stage CRNN onset detector → 7-model
  ensemble classifier → phase-3 multi-class model → tom CNN →
  64th-note quantization + phase align, 8 classes. Caveats: measured
  STRUM is STRUM-minus-tomcym (tom/cymbal CNN checkpoint missing
  locally) and minus-drumsep (arbiter assets absent); doc bug:
  `--onset-threshold` help says default 0.35, real default 0.50.
  Runtime ~7 min per 150 s stem, ~23 min full pipeline vs
  DrumScript app path ~5 min.
- Like-for-like IDMT (55 tracks, @50 ms): kick STRUM F1 0.866
  (P 0.972 / R 0.781) vs DrumScript (EQ+0.10) 0.840 (P 0.773 /
  R 0.919) — +0.026. Opposite error profiles: STRUM precision-first
  (misses ~22% of kicks), DrumScript recall-first. @100 ms STRUM
  kick F1 0.891, P 1.000. Snare 0.848; closed hat 0.782
  (P 0.949 / R 0.666 — hat recall is the weak spot; export enforces
  ≥100 ms between same-lane hat hits). Neither engine is near
  ADTOF-pytorch's reported IDMT kick F1 0.961.
- Real audio (6 tracks, @100 ms vs first-pass references): rock
  STRUM 0.378 vs DrumScript 0.320 (modestly better); electronic
  0.003 vs 0.183 (catastrophic — drums stem nearly empty, RMS
  0.015; V14 found 131 onsets vs funk 462); funk/latin tie; jazz
  STRUM over-fires cymbals (665 crash + 355 ride vs DS 30 + 3),
  under-fires hats (232 vs 747); blues under-detects (267 vs 1026
  events; kick 2, snare 5). Threshold experiment (done):
  electronic @0.35 → 694 onsets but events become crash 426 +
  low_tom 94, kick still 1, snare 0; F1 0.003→0.009. The failure
  is classifier-side, not tunable.
- Tempo: STRUM estimated rock at 139.99 BPM (true ~140) where
  DrumScript octave-errors to 69.8 — its grid-alignment tempo
  refinement works.
- Adoption: DO NOT SWAP THE ENGINE. STRUM is a lateral move: the
  +0.026 IDMT kick gain does not transfer to real songs, it makes
  the worst case (electronic) far worse, and integration costs
  1.6 GB weights + torch + 7-model ensemble for no net win. Take
  two things: (1) tempo refinement — cleanest adoption is Beat
  This! (MIT), not STRUM's code; (2) the precision-first kick
  lesson (P ~0.97–1.00 achievable) as a research direction — a
  precision-first classifier as filter/arbiter on DrumScript
  onsets — but only after a human-annotated benchmark exists. Do
  NOT adopt the V14 onset detector as-is.
- Two evaluator bugs found and fixed in the harness (STRUM Clone
  Hero hat names `closed_hihat`/`open_hihat` were missed, hats
  scored 0; `no_kick` double-counted overall TP). All numbers
  above are post-fix. Full write-up (local only):
  .ds-scratch/strum-eval/REPORT.md.

## 2026-11-14 — Per-style threshold tuning: swept, verdict NO

- User-proposed fix tested honestly: 8 configs (lfer {0.10, 0.15, 0.20,
  0.32} × EQ {off, on}) on the direct stem path for all 6 real tracks,
  @100 ms vs first-pass references. No production code changed.
- The best setting is IDENTICAL for both reference tracks (EQ off +
  lfer 0.10); EQ-on-stem never wins (rock hat-merged 0.689→0.499,
  electronic 0.633→0.516 at lfer 0.10). No per-track differentiation
  to exploit in this knob. lfer moves only the kick count; EQ adds
  kicks everywhere.
- Circularity correction (applies to ALL prior kick numbers): the rock
  kick reference is exactly the lfer-0.10 rule too — build_reference.py
  keeps the kick label whenever peak 40–140 AND LFER≥0.10;
  attack/bass-coincidence only set confidence, never filter. Kick
  P=R=1.000 at EQoff/lfer 0.10 on both tracks. So all kick P/R/F1 vs
  these references is circular, rock as well as electronic. The
  non-circular metrics (hat-merged ex-kick, hats+crash-only) are bad
  in every config (crash F1 0.008–0.021, closed-hat recall 0.07–0.50).
- Other 4 tracks: lfer 0.10 roughly doubles–triples kick counts vs
  0.32 (jazz 448 vs 40, blues 214 vs 23); 448 kicks in a slow jazz
  ballad is implausible. The IDMT-tuned 0.10 gate does not transfer
  to real stems. Auto-selection not validatable (only 2 reference
  tracks; stem features are Demucs-routing-dependent).
- Nuance: on the app path (EQ on the mix before Demucs) rock and
  electronic DO want different settings — but that is a Demucs-routing
  effect, not a threshold effect; proving it needs a full app-path
  sweep (~4 h Demucs per config) plus human-annotated references.
  Recommendation: do not implement per-style thresholds now. Full
  report (local only): .ds-scratch/real-audio/tuning/REPORT.md.

## 2026-11-14 — Ink-height smoke gate reworked to first-system height

- The old 15% whole-page ink-box gate false-failed correct short scores
  (2-bar 11.2%, sparse 9.7%, fresh smoke 12.6% — the stored smoke's
  16.0% pass depended on one low rest glyph). The gate now measures
  the first staff system's height (`scripts/score_geometry.py`,
  `first_system_height_ratio`, threshold 6%): first staff line found
  by full-width ink, system ends at the first blank band ≥2.5% of
  page height below it; returns `None` when no staff system can be
  located. Known-good renders measure 9.8–16.0% first-system height,
  so the 6% threshold has ~40% margin and still catches blank or
  squashed engraving. `scripts/api_engine_smoke.py` uses the new
  gate (width + no-ink checks untouched); CI evaluation job installs
  pillow for the new tests; `engine-validation.yml` triggers on the
  new helper. 8 new tests (synthetic images), scripts tests 19
  passed, backend 152 passed, full offline smoke `API_ENGINE_E2E_OK`,
  rendered score inspected unchanged.

## 2026-11-14 — Kick-precision guard: diagnosed, NOT shipped

- The attack/flux guard cannot fix the electronic blocker, so nothing
  was shipped. On the original-mix stems, bass-stem LF flux separates
  true from false kicks (AUC 0.83, keeps 93% of TPs while killing 65%
  of FPs); on the EQ'd-mix stems — the signal the classifier actually
  sees — it collapses (bass 0.69, drums 0.53), because the EQ boosts
  sustained bass into the kick band before Demucs. Even the best guard
  moves electronic F1 only 0.186→~0.20, and a mix-flux guard would cost
  rock 14–19% of its recovered kicks. The collapse is multi-instrument
  (crash 308 FPs, hats), not a single-gate problem.
- Reference circularity found: the electronic kick reference IS the
  direct lfer-0.10 rule (reproduced exactly, P/R 1.000) and the snare
  reference equals the production snare rule — neither can validate
  EQ-added kicks or snare recall. Hat/crash measurements are
  independent and real. A human-annotated benchmark is now the critical
  missing piece for any 1.0 accuracy claim.
- Proposed next lever (measured, not shipped): separate first, EQ only
  the drums stem, guard on the un-EQ'd bass stem — but its measured
  effect is kick P 0.214→0.249 with overall F1 flat, so it is
  architecture alignment, not a 1.0 unblocker.
- Evaluator fix shipped with this entry: `scripts/evaluate_midi.py`
  `normalize_instrument` had no alias for `hi_hat_closed`/`hi_hat_open`
  (raw classifier labels), so raw output evaluated with hat recall 0.
  Two aliases added + test; scripts tests 11 passed. (Pre-existing
  ruff EXE001 on the file's shebang is untouched.)

## 2026-11-14 — App path (EQ+0.10) measured on real audio; MIDI duplicates fixed

- First measurement of the app engine on the 6 real tracks (EQ + lfer
  0.10, full Demucs re-run per track): rock improves — overall F1
  0.261→0.320 @100 ms (hat-merged 0.461→0.519), kick F1 0.263→0.524;
  electronic collapses — F1 0.515→0.183 (hat-merged 0.696→0.277),
  kick precision 0.078 (374 predicted vs 62 reference candidates).
  Verdict is split: the IDMT-measured EQ+0.10 gain does not transfer
  to real electronic mixes. Kick counts explode everywhere (blues
  23→144, electronic 4→374, jazz 40→364); snare falls on rock
  (539→282) and electronic (324→193).
- MIDI exact-duplicate fix (`backend/app/midi_adapter.py`): upstream
  DrumScript emits byte-identical duplicate note-ons; `midi_to_performance`
  now collapses (channel, instrument, time) duplicates and
  `performance_to_midi` skips (tick, pitch) re-emissions, chords kept.
  319 extra notes removed across the 6 tracks (rock −136). 2 regression
  tests; backend suite 152 passed, ruff clean. F1 effect is neutral
  (rock 0.320→0.310, electronic 0.183→0.186) — the fix stands on
  correctness, not F1.
- 1.0 NOT READY on accuracy grounds: electronic regression is the
  biggest blocker (kick-precision guard needed), crash classification
  is broken on real audio (electronic 308 crash FPs), snare recall fell
  on rock (0.676→0.430), tempo octave errors persist (rock 69.8 vs
  ~140, electronic 215.3 vs ~108), and no human-annotated benchmark
  exists yet.

## 2026-11-14 — MusicXML note element order fixed (XSD)

- The exporter wrote `<instrument>` before `<duration>` in every note;
  the MusicXML XSD (`note` complexType) requires `duration`, `tie*`,
  `instrument?`, `voice`, … — fixed with one move in `_add_note`
  (`backend/app/musicxml_adapter.py`): `<instrument>` now emits after
  `<duration>`/`<tie>`, before `<voice>`. Rests were already in the
  correct order; `_add_note`/`_add_rest` are the only note emitters
  (no grace/cue notes). 1 new test
  (`test_note_children_follow_xsd_element_order`) asserts the full XSD
  child order for every note in a mixed export. Backend suite 150
  passed, ruff clean. Independent stdlib checker: 32 order problems
  before, 0 after; Verovio render unchanged.
- Pre-existing follow-up found, not fixed here: `<play>` is not in the
  XSD `note` sequence at all. It carries the MIDI velocity and an
  existing test asserts it — dropping it loses velocity, so it needs
  its own decision (drop vs move velocity somewhere schema-legal).

## 2026-11-14 — MusicXML ties (Phase 2)

- Ties split at barlines only (decision: within-bar beat-group crossings
  stay single notes, standard drum-score practice). Fragment-first per
  the 2026-11-12 review boundary: the gap now runs to the next hit of
  the same voice globally (`_next_voice_beat`), so `_choose_hit_duration`
  may pick a duration crossing the barline; `_split_duration_at_barline`
  splits it via `decompose_rhythmic_duration` on each side and returns
  `None` when either side isn't exactly representable (falls back to the
  old truncated duration, no inexact tie). Segments carry paired
  `<tie>`/`<tied>` (first `start`, last `stop`, middle both); chord
  tones tie the parent pitch only. Continuation fragments are carried
  to the next measure (`pending_ties`, loud `ValueError` if ever left
  unemitted). Non-crossing durations are byte-identical to before.
- Tests: 8 new in `backend/tests/test_musicxml_adapter.py` (crossing
  split with conserved duration, no tie in-measure or ending exactly on
  the barline, unrepresentable-split fallback, continuation-only voice,
  multi-fragment chain, chord tie). Backend suite 149 passed, ruff
  clean. Independent check: tie/`tied` mirror exactly, no unclosed
  chains; Verovio render inspected by eye — the tie arc visibly crosses
  the barline, hats beamed, no collisions. Dotted notes verified
  read-only: dotted-eighth hats in a beamed group validate strictly and
  beam correctly, no defect found. Untested edge: a tie spanning a meter
  change (tick-based fragments + strict validator on every export, so a
  bad case fails loudly).

## 2026-11-14 — MusicXML beaming generation (Phase 1)

- Beaming now computed from the shared-cursor reconstruction (the
  2026-11-12 review boundary held up): `_apply_beams` runs on the
  finished MusicXML tree in `backend/app/musicxml_adapter.py`, groups
  are maximal runs of beamable notes (eighth or shorter) contiguous in
  time inside one beat group; rests, forwards, tuplets, longer notes
  and beat-group boundaries break a run; single notes stay flagged.
  Secondary beams break per eighth-note unit, lone ones become forward /
  backward hooks. `_beat_group_boundaries` is the single source of truth
  for beat-group ticks (4/4 halves, compound dotted-quarter pulses,
  7/8 as 3+2+2); `decompose_meter_aware_gap` now uses it (6/8 and 7/8
  rest decompositions verified unchanged). Hooked into
  `performance_to_musicxml`, so the MusicXML download and the PDF print
  path share the same beamed output. Strict validation still runs on
  every export.
- Tests: 7 new in `backend/tests/test_musicxml_adapter.py` (8th group,
  16th group + second beam, no beam across rest / beat-group boundary /
  barline, secondary hooks, 7/8 rest decomposition). Backend suite 141
  passed, ruff clean. Independent check: 25 beam elements on a mixed
  2-bar 4/4 + 16th fill + 3/4 groove, strict validator accepts, Verovio
  render inspected by eye — hats beamed in half-measure groups, fill
  double-beamed, no collisions.
- Pre-existing follow-up found, not fixed here: the exporter writes
  `<instrument>` before `<duration>` in every note, while the MusicXML
  XSD requires duration first. Verovio accepts it; fixing it touches
  every note, so it stays a separate small task.
- Phase 2 (ties, dotted notes) still open: ties split at barlines only
  (decision: within-bar beat-group crossings stay single notes, standard
  drum-score practice); dotted values already emitted, need verification
  that they survive shared-cursor validation and beam correctly.

## 2026-11-14 — Issue #6: PDF engraving fixed after first visual inspection (3 blocking defects)

- First rendered score ever inspected by eye (16-bar groove, 237 events):
  every bar started with "4/4" (MusicXML emits `<time>` per measure),
  `breaks=auto` ignored the configured 4-measure grouping ([3,4,4,4,1]
  with an orphan final bar), and short scores stayed narrow (2 bars 50%,
  sparse 22% vs the 72% width gate). Fixed in `backend/app/pdf_adapter.py`
  (print path only; the MusicXML download is untouched): redundant
  `<time>` stripped except in measure 1 and on meter change, `"breaks":
  "line"` when explicit breaks exist, `minLastJustification=0` for
  single-system scores. Tempo text rounded to one decimal ("60.0927" ->
  "60.1 BPM", integer tempos unchanged) in both the Verovio and fallback
  paths. Post-fix: systems [4,4,4,4] / [4,4], width 95.8% on all renders,
  no collisions; the 300-dpi bar-16 fill crop is clean.
- Tests: 5 new in `backend/tests/test_pdf_adapter.py` (time-signature
  strip incl. meter-change case, Verovio options, real-geometry systems
  via Verovio SVG, tempo rounding). Backend suite 134 passed, ruff clean,
  offline API smoke `API_ENGINE_E2E_OK`.
- Open follow-up (not changed): the 15% ink-height gate is a fragile
  proxy for single-system scores — correct short scores measure 9.8–11.3%
  and the smoke passes at 16.0% only because one low rest glyph extends
  the bbox. Rework it to measure first-system height rather than the
  whole-page bbox before it false-fails a correct short score.

## 2026-11-14 — Salvaged real-audio evaluation toolchain from `feat/real-audio-evaluation-harness` (PR #1 closed as do-not-merge)

- Content merge onto main, no merge commit (same snapshot pattern as the
  PR #10/#11/#15 landings). Branch deleted after salvage; only `main`
  remains besides this work.
- Taken as-is: `scripts/evaluate_midi.py` (CSV-reference vs MIDI-prediction
  evaluator, one-to-one onset matching, per-instrument P/R/F1),
  `scripts/audit_prediction_csv.py` (structural prediction diagnostics),
  and their tests (`scripts/tests/test_evaluate_midi.py`,
  `test_audit_prediction_csv.py`, `test_repository_audio_export.py`).
  The file evaluator complements the in-app canonical evaluator
  (`drum_events.evaluate_performance` / `drumai-evaluate`): it works from
  hand-annotated CSVs and DrumScript MIDI files, the canonical one from
  `DrumPerformance` JSON.
- Adapted: `scripts/validate_repository_audio.py` — the hardcoded
  copyrighted MP3 filenames are gone; audio paths are now CLI arguments
  and the run skips cleanly (`REAL_AUDIO_VALIDATION_SKIPPED`, exit 0)
  when no audio is given or found, following the `engine_smoke.py` skip
  pattern. `docs/REAL_AUDIO_EVALUATION.md` rewritten to match: no
  workflow/MP3 references, and the accuracy gate now applies to reporting
  metrics (the analysis API is enabled since the EQ landing).
- CI: `ci.yml` gains the branch's `evaluation` job (`pytest scripts/tests`
  with pretty-midi). The branch's `browser-e2e` job was not taken (heavy
  Playwright + MuseScore run tied to the dropped old-frontend spec).
- Dropped deliberately: `backend/app/main.py` reference-events
  table/endpoints and `test_reference_events.py` — superseded by main's
  canonical `DrumEvent` (`source: model/manual/imported`,
  `manually_corrected`) and its events API; `test_project_library.py` —
  covered by `test_analysis_api.py` (list + audio); `frontend/src/main.tsx`
  / `style.css` / `e2e/project-library.spec.ts` /
  `playwright.config.ts` — old reference-annotation/grid UI, superseded by
  main's canonical editor; `docs/MUSICXML_EXPORT.md` — describes the old
  frontend exporter, main's backend `musicxml_adapter` is authoritative;
  `docs/ARCHITECTURE.md` hunks — predates main's canonical model;
  `.github/workflows/real-audio-validation.yml` — fetched the deleted
  copyrighted MP3s from main history; `engine-validation.yml` branch
  trigger — dead branch name; the branch's `PROJECT_LOG.md` content —
  stale (PR #1 draft, HTTP 501); the README status/notation/limitations
  hunks — stale vs current main (only the doc link was taken).
- Verification: backend suite 129 passed, ruff clean (backend `app` +
  `tests` and the salvaged scripts); scripts tests 11 passed
  (6 evaluate + 3 audit + 2 export); `validate_repository_audio.py`
  with no args and with a missing path both skip with exit 0;
  `evaluate_midi.py` CLI smoke on synthetic CSV+MIDI gives F1 1.0.
  No Hugging Face or other downloads; `pretty_midi` for the local
  scripts-test run came from the existing local `.scorepipe` env
  (CI installs it via pip in the evaluation job).
- No human-annotated benchmark exists yet; no accuracy claim is made.

## 2026-11-14 — EQ preprocessing integrated into production adapter; local API e2e passes

- EQ (from the 2026-11-14 experiment, ADOPT): 2nd-order Butterworth
  high-pass 30 Hz + RBJ low-shelf +6 dB @ 120 Hz, causal sosfilt, applied
  in `engine_adapter.analyze()` before `transcribe()` (writes
  `work_dir/source-eq.wav`); `KickClassificationConfig.eq_preprocessing`
  defaults True (new behaviour), explicit False restores the old path;
  stock upstream = lfer_min 0.32 + EQ off; fail-closed on missing/changed
  DrumScript interfaces or missing scipy. `scipy>=1.14,<2.0` added to the
  backend `dev` extra. `engine-validation.yml` now also triggers on
  `backend/app/engine_adapter.py` (push + PR paths).
- Verification: production `_apply_kick_eq` bit-identical to the experiment
  harness (max abs diff 0.0 on 8 s composite); sine gains 10 Hz 0.215,
  60 Hz 2.027, 1000 Hz 0.995. Small-sample IDMT check with the production
  function (6 tracks, lfer 0.10, 50 ms): pooled kick F1 0.790 -> 0.840
  with EQ (recall 0.743 -> 0.850, precision 0.844 -> 0.830), direction
  matches the experiment report (pooled 0.792 -> 0.840; held-out WaveDrum
  0.643 -> 0.783).
- Backend suite 129 passed (121 + 8 new adapter tests), ruff clean.
  Frontend `npm run build` passes locally (tsc + vite).
- Local API e2e (`scripts/api_engine_smoke.py`, offline network namespace,
  `HF_HUB_OFFLINE=1`, no Hugging Face download, no approval card):
  `API_ENGINE_E2E_OK` — upload -> analyze -> 39 events over 8.0 s ->
  MIDI 312 B, MusicXML 22,573 B (parsed + validated), PDF 40,112 B /
  1 page, PNG 54,668 B; visual gates passed. Demucs separation ran from
  the locally cached legacy torch-hub checkpoint (`source-eq.wav`
  confirms the EQ'd file reaches Demucs). The full-song Demucs path in CI
  engine-validation remains the cloud verification route.
- Hugging Face: no downloads attempted in this landing; the one needed
  weight (`955717e8.safetensors`, ~84 MB, `adefossez/HTDemucs`) is
  inventoried in `~/workspace/.ds-scratch/hf-inventory.md` for a single
  batched approval / GitHub Actions cloud download, not local direct
  download.
- Still open: Issue #5 (CI engine-validation Demucs e2e pending on this
  push); copyrighted MP3s remain in git history (removed from main only);
  PR #1 salvage files for later if wanted.

## 2026-11-14 — merged PR #15 (MusicXML explicit rests + exact rhythm); PR #1 closed

- Merged PR #15 locally (branch `feat/musicxml-explicit-rhythmic-rests`
  + fixes commit 67a198d) after the review's three fixes: (1) barline-rounding
  guard in `musicxml_adapter.py` — a hit rounding onto the barline is skipped
  instead of failing the whole export via `_choose_hit_duration(0)`,
  with a regression test (hit at 1.9999999s, 4/4 @120bpm; verified the test
  fails without the guard); (2) kick diagnostics scope split out
  (`kick_stage_diagnostics.py` and `engine-validation.yml` reverted to main,
  `kick_stage_aggregate.py` removed); (3) stale `docs/HANDOFF.md` deleted.
- Merge conflicts resolved keep-both (`docs/PROJECT_LOG.md`,
  `backend/tests/test_analysis_api.py`); also removed a duplicate
  `test_pdf_renderer_trims_silent_tail_measures_only` and a duplicate
  `_trim_trailing_empty_measures` call — the same trim had landed both via
  the PR #10 squash and via the branch.
- Verification on the merged tree: backend suite 121 passed (113 main + 8
  net new), ruff clean. PR #1 closed as do-not-merge (value already in main
  in newer form); PR #15 closed after this push (snapshot push, so GitHub
  shows it closed rather than merged).
- Still open: Issue #5 end-to-end Demucs-path verification (CI
  engine-validation), EQ preprocessing experiment result (30 Hz high-pass +
  120 Hz lowshelf +6 dB, F1 0.792 -> 0.840 pooled) awaiting a decision on
  integration, and deletion of the 8 stale branches (no delete tool; manual
  GitHub step).

## 2026-11-13 — kick detection (Issue #5): adapter-level threshold override, merged (cdb3b82)

- Root cause confirmed against upstream DrumScript source (HEAD e3c4707):
  the kick classifier lives upstream only, in
  `drumscript/drum_classifier/classify.py::classify_events`. The live kick
  rule is `lfer >= KICK_LFER_MIN (0.32)` and `40 Hz <= peak_freq <= 140 Hz`;
  no threshold was changed upstream or vendored. Onset-candidate recall for
  kick is ~98% while final kick recall is 5.3% (RealDrum) / 17.2%
  (WaveDrum) / 57.1% (TechnoDrum), so the loss is at this classification
  gate, not at onset detection. Upstream `transcribe()` runs classification
  in-process, so a runtime override is possible without vendoring code.
- Change (branch `fix/kick-detection`, merged as cdb3b82): added
  `KickClassificationConfig` to `backend/app/engine_adapter.py`. It
  temporarily sets `KICK_LFER_MIN`/`KICK_FREQ_MIN`/`KICK_FREQ_MAX` on the
  upstream `drumscript.drum_classifier.classify` module (its own globals —
  patching the constants module alone would not work) and restores them
  after each call; a config equal to the stock upstream rule is a no-op and
  any other config fails closed if the installed DrumScript revision does
  not expose them. `scripts/kick_stage_diagnostics.py` gained `--lfer-min`,
  `--peak-freq-min-hz`, `--peak-freq-max-hz`, and `--offset` (held-out
  evaluation on tracks not used for threshold selection).
  `docs/ENGINE_VALIDATION.md` documents the override and the numbers below.
- Measured default (IDMT-SMT-Drums V2, 50 ms, DrumScript HEAD e3c4707,
  55 tuning tracks / 969 kick refs): `lfer_min=0.10` lifts pooled kick
  recall 0.25 -> 0.84 at precision 0.89 -> 0.84 (F1 0.39 -> 0.84); per
  subset F1 0.10 -> 0.90 (RealDrum), 0.29 -> 0.82 (WaveDrum),
  0.68 -> 0.80 (TechnoDrum). Held-out check on 15 untouched WaveDrum
  tracks (349 refs): recall 0.24 -> 0.55, precision 0.83 -> 0.77
  (F1 0.37 -> 0.64). `lfer_min=0.15` is the conservative alternative
  (pooled F1 0.79, held-out F1 0.51). The default is therefore 0.10, not
  the stock 0.32; pass an explicit `KickClassificationConfig(lfer_min=0.32)`
  to restore upstream behaviour.
- Verification on this branch: backend suite 110 passed (was 99; +11 new
  adapter tests, incl. apply-and-restore, measured-default application,
  stock no-op, fail-closed); ruff clean on all touched files. The override
  was also verified against the real upstream module on a synthetic mix:
  default gate finds 9/31 onsets as kick, `lfer_min=0.15` finds 31/31,
  threshold restored to 0.32 afterwards.
- Risk: lowering `lfer_min` recovers kicks diluted by bass/mix energy but
  risks bass-guitar and low-tom false positives — pooled precision fell
  0.89 -> 0.84, and on a bass-heavy synthetic mix the 0.15 gate already
  labels every onset as kick. Snare/hi-hat rules are independent of this
  gate, but a kick label now suppresses the low_tom label for the same
  onset, so low-tom recall is the unmeasured trade-off. Full-song
  `transcribe()` (Demucs path) was not run end-to-end locally; the
  diagnostic path exercises the same `classify_events` code directly.

## 2026-11-13 — DC-suppressed kick feature experiment added

- Grouped validation folds by the explicit `subset/track` key, not basename alone, to prevent same-named files from different IDMT subsets from leaking into each other's training folds.
- Added an offline feature path in `scripts/kick_stage_diagnostics.py` that recomputes each onset's short-window STFT from the normalized source audio and excludes the DC bin before calculating peak frequency and LFER. The original DrumScript features and production inference remain untouched.
- Added leave-one-track-out tuning over DC-excluded LFER and an HFER ceiling, with peak frequency constrained to 20–180 Hz. The report includes per-track held-out predictions and pooled TP/FP/FN, precision, recall and F1.
- Extended the cross-subset aggregator to calculate the same DC-suppressed experiment across all three IDMT subsets using the already extracted candidate rows; no additional audio transcription pass is introduced.
- Validation is pending on the next Engine Validation run. This experiment is still exploratory and must be checked for low-tom/bass false positives before any production classifier change.
- Latest completed Engine Validation run `43403116257`: all IDMT subset scoring, kick diagnostics, synthetic smoke and both repository MP3 smoke tests passed. The API E2E failed only its PDF visual-height gate (13.4% vs 15% minimum); PDF/MusicXML export and PNG generation completed.

## 2026-11-13 — kick spectral-gate failure analysis

- A second offline grouped sweep tested LFER, peak-frequency handling, and HFER together on the same 40-track IDMT candidate artifact. Leave-one-track-out validation selected LFER 0.09 or 0.11, an HFER ceiling of 0.80, and a peak-frequency rule that accepts the DC-dominated zero bin or 20–180 Hz.
- Held-out candidate-level totals were TP=882, FP=176, FN=65 (precision 0.834, recall 0.931, F1 0.880). By subset, candidate-level precision/recall were RealDrum 92.9%/87.5%, WaveDrum 82.4%/92.3%, and TechnoDrum 77.3%/100%. There were 22 annotated kicks with no matched onset candidate, so the corresponding end-to-end recall ceiling-adjusted figure is 882/969 = 91.0%; these 22 remain onset-stage misses, not classifier misses.
- The fixed 40–140 Hz gate excludes 50 matched TechnoDrum kicks whose measured peak is 172 Hz. WaveDrum also contains 27 matched kicks with peak_freq=0; inspection of upstream DrumScript shows peak frequency is the argmax of the mean STFT magnitude including the DC bin. A zero peak can therefore indicate DC-bin dominance, not a literal 0 Hz kick fundamental. Among these zero-peak candidates, HFER median was 0.59 for annotated kicks versus 0.90 for negatives.
- This points to two distinct classifier defects to investigate: a narrow fixed peak-frequency band and a peak-frequency feature that does not suppress DC. The HFER cap is a promising discriminator for the zero-peak cases, but this experiment reuses the same IDMT corpus and is not production validation. Do not deploy the proposed rule yet; next calculate DC-suppressed spectral features from the raw onset slices and test tom/bass false positives on independent audio.
- These numbers are exploratory grouped cross-validation over the existing candidate artifact, not a new CI run and not a change to DrumScript inference.

## 2026-11-13 — cross-subset kick threshold validation

- The latest IDMT diagnostic artifacts evaluated 14 RealDrum, 15 WaveDrum,
  and 11 TechnoDrum tracks (2,619 feature-bearing candidate events and 969
  annotated reference kick events (947 had matched onset candidates)). The existing full-song rule (LFER >=
  0.32 with a 40–140 Hz peak band) achieved pooled candidate-level F1 0.402.
- An additional offline leave-one-track-out experiment pooled all three
  subsets and selected the LFER threshold using only the other tracks. Its
  held-out aggregate was TP=812, FP=177, FN=135 (precision 0.821, recall
  0.857, F1 0.839). By subset, held-out recall/precision were RealDrum
  89.2%/90.8%, WaveDrum 85.4%/81.0%, and TechnoDrum 82.5%/75.4%.
- This is promising evidence that the fixed 0.32 LFER gate is too strict,
  but it is still an offline feature-rule experiment, not a production
  classifier change. False positives increased, and some individual tracks
  remain difficult. Do not deploy a lower threshold until negative-event
  errors (especially tom/bass overlap) and an independent evaluation split
  are reviewed.
- Extended the diagnostics artifact to report a second leave-one-track-out
  sweep trained across the other IDMT subsets. This explicitly tests whether
  a threshold transfers between drum-kit domains rather than tuning only
  within each subset. CI validation is pending for this instrumentation.
- The engine-validation job's final API-to-engine smoke failed for a separate
  PDF visual gate: notation ink occupied 13.4% of the page, below the 15%
  minimum. Earlier engine tests, IDMT diagnostics, and repository MP3 smoke
  tests completed; backend and frontend CI passed. This PDF issue is not a
  kick-classification failure.

## 2026-11-12 — review of revised rhythmic-beaming implementation proposal

- Reviewed the newly supplied `process_measure_rhythm_and_beams` patch and
  its proposed tests against the actual exporter and PDF adapter on the
  integration branch. The proposal is directionally aligned with the desired
  features, but is not safe to apply as written.
- The MusicXML measure cursor is a shared document-order cursor: `backup`
  rewinds that cursor and `forward` advances it. It is not a command to
  subtract from a voice-local cursor. Voice identity is recorded on notes;
  chord tones share the preceding non-chord note's onset and do not advance
  the cursor. The proposal's `active_voice` bookkeeping conflates these
  concepts and does not validate voice streams or per-voice totals.
- The proposed 6/8 beat grouping is arithmetically wrong for divisions=4:
  each dotted-quarter beat is 6 divisions, not 3. Its generic fallback also
  does not correctly derive denominator beat units or compound-meter groups.
- The split helper shortens the original note but never inserts continuation
  notes, never emits the matching `<tie type="stop"/>` on a continuation,
  and never preserves the original total duration. The beam helper groups
  every eligible note in a voice regardless of onset, beat group, intervening
  rest, or rhythmic discontinuity; skipping rests while collecting notes
  actually permits beams to bridge them. Chord tones are skipped rather than
  handled as members of their onset group.
- The proposed PDF test does not match the repository API: current
  `_render_with_verovio(performance, title, measures_per_system=...)`
  accepts a `DrumPerformance` and returns PDF bytes. It does not accept raw
  MusicXML plus an output path. The test also references `os` without
  importing it and never constructs the required performance or calls
  `performance_to_pdf()`.
- Correct implementation boundary: reconstruct the shared MusicXML document
  cursor first (including backup/forward and chord onset semantics), validate
  voice timelines from those absolute positions, and generate duration
  fragments before serializing voices. Tie splitting must create both
  continuation segments and paired sound/notation tie markers while
  conserving duration. Beam groups must be computed from voice + absolute
  onset + meter beat-group + uninterrupted eligible note runs.
- No production code changed and no test/CI result is claimed in this review.
  PR #4 remains open and unmerged.

## 2026-11-12 — MusicXML rhythmic-timeline implementation plan grounded in current exporter

- Re-read the current integration-branch exporter, canonical event schema, and
  PDF rendering path before changing production code. The exporter uses
  per-instrument voices with `backup`/`forward`, but derives each hit's
  duration only from the next hit in that instrument voice and selects the
  largest undotted binary note value that fits the gap.
- Confirmed the current generator does not emit explicit rests, beams, ties,
  dotted values, or tuplets. A hit whose spacing is not an exact supported
  binary value can therefore leave unrepresented time; the current final
  `min(note_duration, available_gap)` can also create a duration that does
  not match the emitted `<type>`. These are generator correctness issues,
  not merely engraving-style options.
- Confirmed the PDF renderer calls this same MusicXML generator, then inserts
  system breaks and renders with Verovio. The rhythmic fix must therefore be
  made in the shared MusicXML path and verified through the real PDF renderer,
  not a parallel PDF-only notation implementation.
- Next implementation slice is a measure/voice timeline validator and
  duration decomposition with exact divisions conservation. It must interpret
  MusicXML cursor movement (`backup`/`forward`), chord notes, voices, rests,
  and measure boundaries; validate each voice independently; and reject
  unsupported/invalid rhythmic constructs rather than silently accepting
  mismatched `duration` and `type`. Only after this foundation should
  notation generation add beat-group beaming and tie-preserving splits.
- No production code was changed in this review. No test or CI result is
  claimed. PR #4 remains open and unmerged.

## 2026-11-12 — kick feature diagnostics split by classifier outcome

- Reviewed the upstream DrumScript classifier implementation used by the
  engine workflow. For full-song IDMT mixes, each detected onset is retained
  with debug features; kick assignment is primarily the joint LFER and
  40–140 Hz peak-frequency rule (the special amplitude/debounce gate applies
  only to a single-loud-hit clip shorter than 30 seconds).
- The existing IDMT diagnostic already aligned detected onset events to
  annotated kick times, but it summarized all aligned features together.
  Extended it to label each reference-aligned candidate as predicted or missed
  and report LFER/peak-frequency quartiles separately for both outcomes.
  This is diagnostic-only: no classifier thresholds or production inference
  behavior were changed.
- The latest PDF experiment uses scale 180 with vertical justification off;
  the next engine run must validate its output dimensions and be manually
  inspected before acceptance.

## 2026-11-12 — PDF layout follow-up after visual-gate failure

- Engine run 43159750781 passed upstream tests, all three IDMT subset diagnostics,
  synthetic/repository MP3 smoke, and generated the API PDF/PNG. Its API E2E
  correctly failed the new whitespace assertion: the assertion was measuring
  the gap between the score and the page footer, not specifically between
  notation systems. The rendered page also showed notation occupying only
  about 70% of available width.
- Corrected the Verovio layout experiment: increased engraving scale from 140
  to 180 and disabled vertical justification, which can distribute sparse
  systems across an unnecessarily tall page. Replaced the false-positive
  gap assertion with a direct score-width minimum of 72%; the existing 15%
  score-height minimum remains in place.
- These are unverified layout changes until the next engine-validation run
  passes and its generated PNG is manually inspected. Do not treat PDF export
  as accepted based on CI alone.

## 2026-11-12 — PDF visual gate hardened; expanded kick benchmark completed

- The latest API-generated landscape-A4 PDF and PNG were inspected from engine
  validation run 43147002409 (commit 13cd7f8). Tempo and notation glyphs render,
  but the page still has an isolated, nearly empty second percussion system and
  a large vertical whitespace gap. The PDF is not visually accepted.
- The previous 15% ink-height gate could be fooled by that empty system because
  it enlarged the page-wide ink bounding box. Added a second visual assertion
  that measures the largest gap between rows containing substantial ink and
  rejects gaps above 20% of page height. This intentionally makes the next
  engine run fail until the layout itself is corrected; do not weaken the gate.
- The completed IDMT-SMT-Drums run evaluated 14 RealDrum, 15 WaveDrum, and 11
  TechnoDrum tracks (50 tracks total). Kick candidate recall was 98.3%, 96.3%,
  and 99.0%, while final kick recall was only 5.3%, 17.2%, and 57.1%;
  corresponding precision was 100%, 95.6%, and 85.1%. This confirms the main
  bottleneck remains post-onset kick classification, not onset candidate
  generation. No kick threshold was changed based on these aggregate results.
- CI, backend tests, and the engine workflow passed on 13cd7f8, including real
  MP3 smoke, IDMT diagnostics, and API export generation. The new whitespace
  assertion is a follow-up regression test and has not yet been validated.

## 2026-11-12 — PDF engraving readability correction

- Visual inspection of the API-generated PDF confirmed two concrete defects:
  the Verovio metronome-note glyph rendered as a missing-font square, and the
  notation scale left the score unusually small on landscape A4.
- Updated the PDF-only Verovio input to render tempo as explicit readable text
  (for example, "Tempo: 120 BPM") while preserving the semantic metronome
  markings in the downloadable MusicXML. Increased Verovio notation scale from
  40 to 52 to use more of the printable page area.
- This is a targeted layout correction, not yet visually accepted. The next
  engine-validation run must regenerate the PDF and PNG; inspect the rendered
  page for clipped notes, collisions, tempo readability, and balanced margins
  before treating the PDF export as ready.

## 2026-11-12 — portable engine CI passes; kick and PDF visual blockers measured

- Replaced the Ubuntu apt-installed media tools with a Python-managed static
  FFmpeg/ffprobe distribution and in-process PDFium rendering. On commit
  7b9debbb7aebab6e862545e6907053b9667f9b15, the engine-validation workflow,
  backend test workflow, and repository CI all completed successfully.
- Engine validation completed upstream non-slow tests, the synthetic mix,
  both repository MP3 smoke tests, and API-to-engine export smoke. The two
  repository tracks produced 1,041 and 1,127 normalized drum events and
  non-empty MIDI files. API E2E produced MIDI, MusicXML, a 40,550-byte PDF,
  and a rendered 42,185-byte PNG page.
- The PNG was visually inspected rather than treating file existence as
  acceptance. The Verovio page has a tempo/metronome glyph rendered as a
  missing-font box and places a very short two-bar score in a small area at
  the top of a mostly empty A4 landscape page. PDF geometry and generation
  pass, but visual acceptance remains blocked. Next: inspect Verovio scale,
  page layout, and SMuFL font/resource handling; add a visual regression
  fixture with a multi-system score before marking PDF export production-ready.
- Expanded IDMT-SMT-Drums stage diagnostics (50 ms tolerance) evaluated 14
  RealDrum, 15 WaveDrum, and 11 TechnoDrum tracks. Candidate onset recall was
  98.3%, 96.3%, and 99.0%, while final kick recall was only 5.3%, 17.2%, and
  57.1%, respectively. Matched candidate features show the current LFER rule
  (minimum 0.32) is the dominant filter: only 16/297 RealDrum, 75/364
  WaveDrum, and 165/286 TechnoDrum matched candidates pass the LFER threshold.
  Peak-frequency eligibility is much higher (291/297, 312/364, 236/286).
- Do not lower the LFER threshold globally based on these aggregates. The
  next classifier task is to inspect per-track and per-instrument feature
  distributions, compare isolated kick stems where available, and tune or
  replace the hard gate with a calibrated/adaptive decision while measuring
  precision and recall on held-out tracks. IDMT use remains evaluation-only
  under its dataset terms; no audio is committed.
- PR #4 remains the sole integration path to main. Keep it open until the PDF
  visual issue and kick-classification regression strategy are reviewed; all
  three current CI workflows are green, but CI success is not product-quality
  acceptance.


## 2026-11-11 — non-destructive quantization preview

- Added a two-step quantization flow: generate a preview without persisting,
  inspect how many events will move, then explicitly confirm application.
- Changing the grid or strength invalidates the previous preview. Only the
  confirmed apply action creates a revision and synchronizes MIDI.
- This exposes the existing backend preview mode in the workspace and avoids
  accidental destructive quantization. Backend tests run #149 passed all 56
  tests plus Ruff; repository CI run #238 passed frontend build and backend
  tests. The subsequent CSS layout update also passed backend run #150 and
  repository CI run #239.


## 2026-11-11 — A–B loop range guard

- Prevented enabling A–B practice looping when the selected range is zero or
  reversed. Setting A after an existing B now restores B to the track end;
  setting B before A is disabled in the UI.
- This avoids a silently enabled loop that never wraps playback.


## 2026-11-11 — saved-project retry and recovery

- Improved workspace recovery so uploaded projects with no analysis job can be
  started directly, and projects whose latest analysis failed can be retried
  without uploading the audio again.
- Existing completed projects still restore the latest canonical performance;
  queued/running jobs remain resumable after a browser refresh.
- Added API coverage for the saved-project listing endpoint and documented the
  retry flow in the user guide. Frontend/backend CI for this increment pending.


## 2026-11-11 — saved project recovery (implementation, CI pending)

- Added `GET /api/projects?limit=...` to list recent local projects with their
  latest analysis-job state. The API clamps the requested list size to 1–100.
- Added a workspace project picker that loads saved projects on startup,
  restores completed canonical performances and edit history after reload,
  can resume polling queued/running jobs, and supports manual list refresh.
- Project switching resets playback/selection state; event-row inputs remount
  when canonical event values change so undo/redo visibly restores the editor.
- Added API integration coverage for project metadata and latest completed job
  state. Backend tests run #140 passed all 56 tests and Ruff; repository CI
  run #227 passed frontend build and backend tests. DrumScript engine validation
  run #131 remains in progress.


## 2026-11-11 — editable MusicXML drum score export (implementation, CI pending)

- Added a MusicXML 4.0 partwise exporter for canonical drum events, with a
  percussion staff, instrument-specific voices/noteheads, GM percussion
  metadata, velocity playback hints, tempo directions, time-signature-aware
  measure boundaries, note values inferred from successive hit spacing, and
  explicitly marked implicit measures for partial bars or mid-bar time-signature
  changes.
- Added `GET /api/projects/{project_id}/musicxml` and a frontend download link
  beside MIDI export. The endpoint exports the latest canonical state, so
  manual edits, quantization, undo, and redo are reflected.
- Added XML structure, tempo/time-signature, velocity, empty-score, and API
  download tests. Extended the real DrumScript API-to-engine smoke to fetch and
  parse a populated MusicXML score from an actual inferred performance.
  Import into notation software is supported; final engraving remains the
  notation application's responsibility.
- Backend tests run #140 passed all 56 tests and Ruff; repository CI run #227
  passed both frontend build and backend tests on the current branch head.
  DrumScript engine validation run #131 is running the synthetic/repository MP3
  smoke stage before the expanded real-inference MusicXML export check. This
  is integration validation, not an accuracy claim.


## 2026-11-11 — tempo-synchronized practice metronome (implementation, CI pending)

- Added a browser metronome that follows the rendered tempo-map beat positions,
  including bar accents, so BPM changes use the same timeline as the drum events.
- Metronome clicks are generated locally with Web Audio and do not upload or
  persist audio. Seeking backward and A–B loop restarts reset beat tracking.
- The metronome is opt-in and can be toggled independently of A–B looping.
  Its animation-frame scheduler follows the audio element clock and stops while
  playback is paused. Repository CI run #202 passed frontend build and backend
  tests; DrumScript engine validation run #104 remains in progress.


## 2026-11-11 — A–B loop practice playback (implementation, CI pending)

- Added A/B loop markers to the synchronized audio player. Users can set the
  loop start and end from the current playback position, enable/disable looping,
  and reset the range to the full track.
- Looping is evaluated against the audio element's playback clock; drum-event
  positions and the timeline remain anchored to absolute seconds.
- Invalid or zero-length ranges do not trigger a loop. A–B range shading is
  shown across the drum lanes while looping is active. Repository CI run #202
  passed frontend build and backend tests; engine validation remains pending.

## 2026-11-11 — interactive drum arrangement timeline (implementation, CI pending)

- Added a full-song, instrument-lane timeline to the editor with a time ruler,
  tempo readout, velocity-weighted hit markers, and horizontally scrollable
  layout on smaller screens.
- Clicking a hit selects it and scrolls the corresponding editable event row
  into view. The timeline is driven directly by the canonical performance,
  so edits and quantization refresh the visualization from the saved source.
- Uses the performance tempo-map's initial BPM when available and a clearly
  labelled 120 BPM fallback when no tempo metadata exists; horizontal event
  positions remain absolute audio seconds.
- Frontend CI is pending for this commit; no build result is claimed yet.

## 2026-11-11 — persistent undo/redo for drum editing (implementation, CI pending)

- Added SQLite-backed performance revision snapshots and a current-revision
  cursor. Initial analysis output is revision zero; every manual event edit,
  deletion, and applied quantization creates a new revision.
- Added project history inspection plus undo/redo endpoints. Undo and redo
  restore canonical performance JSON and regenerate the downloadable MIDI;
  creating a new edit after undo truncates the abandoned redo branch.
- Added editor undo/redo controls with disabled states driven by server history.
- Added API integration coverage for baseline state, undo/redo, synchronized
  MIDI export, and redo-branch invalidation.
- CI is pending for this commit; no validation result is claimed yet.

# DrumAI Studio project log

## 2026-11-11 — tempo-aware drum quantization (implementation, CI pending)

- Added a pure canonical-performance quantizer with 1/4, 1/8, 1/16, and
  1/32-note grids, local BPM-aware spacing, tempo-change segment anchors, and
  adjustable 0–100% interpolation strength. Event identity, instrument,
  velocity, confidence, and provenance remain unchanged.
- Added `POST /api/projects/{project_id}/quantize` with preview-only mode
  (`apply=false`) and persistent apply mode. Applied quantization uses the
  existing atomic JSON/MIDI save path so downloads remain synchronized.
- Added editor controls for grid resolution and strength, plus a one-click
  apply action. Preview remains available through the API for clients that
  need a non-mutating comparison.
- Added unit coverage for all supported grids, strength interpolation,
  zero-strength no-op, tempo changes, invalid parameters, API preview/apply,
  and MIDI round-trip synchronization.
- DrumScript engine validation run #52 passed all steps, including upstream
  tests, synthetic/repository MP3 smoke tests, and API-to-engine end-to-end.
  This is engine integration evidence, not a transcription accuracy claim.
- Quantization backend tests run #71 passed all 48 backend tests and Ruff
  (`ruff check app tests`). Repository CI run #158 passed backend tests and
  the frontend TypeScript/Vite production build. The initial run #157 exposed
  a missing frontend action handler; that was added and the next build passed.
- DrumScript engine validation run #62 passed package/CLI verification and
  upstream non-slow tests; synthetic/repository MP3 smoke and API E2E were
  still running when this log entry was prepared. Do not mark engine validation
  complete until those remaining steps pass.

## 2026-11-11 — canonical drum-event editor

- Added project-scoped event create, patch, and delete endpoints for the latest
  completed canonical performance. Manual changes are marked with manual
  provenance and validated against the audio duration.
- Added canonical-to-GM MIDI export, preserving event timing, velocity, tempo,
  and time signatures. Every successful edit regenerates the project's MIDI
  download so it remains synchronized with canonical JSON.
- Added a browser editor for adding events and changing time, instrument, and
  velocity, plus deleting events. Enabled PATCH/DELETE in API CORS policy.
- Added API integration coverage for CRUD behavior, validation, MIDI download
  synchronization, and MIDI adapter round-trip coverage for tempo and velocity.
- DrumScript engine validation run #34 passed, including synthetic + repository
  MP3 smoke tests and the API-to-engine end-to-end upload/inference/result/MIDI
  download path. This run predates the event-editor changes and does not
  validate those new endpoints.
- Backend tests run #60 passed: 35 tests and Ruff, including CRUD, synchronized
  MIDI download, and MIDI round-trip checks for tempo, velocity, timing, and
  full performance duration. Repository CI run #146 passed frontend build and
  backend tests.
- DrumScript engine validation run #51 is still running against the latest
  head; its end-to-end steps remain pending. No accuracy claim is made; model predictions still require
  human review.

## 2026-11-11 — CI regression fixes

- The first fresh backend run for the asynchronous API changes exposed two stale
  health-test assumptions: the tests still expected the removed HTTP 501 route,
  and they instantiated TestClient without entering its lifespan, so SQLite
  storage initialization never ran.
- Updated the health tests to use TestClient as a context manager, accept the
  actual engine installation states, and assert that an unknown project returns
  HTTP 404. The next backend run passed all 32 tests.
- That same run then exposed six Ruff findings in the API module (import order,
  modern typing/time APIs, environment default typing, and intentional FastAPI
  dependency/catch patterns). These were corrected in follow-up commits.
- Follow-up backend tests run #42 passed, including all unit tests and Ruff.
  Repository CI run #128 also passed both frontend build and backend tests.
  Engine validation run #33 was still running at the time of this update; its
  synthetic/MP3 and API-to-engine E2E steps are not yet verified.

This log records repository milestones and verified boundaries. Update it when
code or validation state changes; do not infer completion from plans.

## 2026-11-11 — asynchronous analysis API integration (implementation, CI pending)

### Implemented in PR #3

- Added a lazy-loaded `DrumScriptEngine` adapter. It invokes full-song
  transcription, requires a usable exported MIDI, converts GM percussion
  channel 10 into the canonical event model, and persists a normalized MIDI
  artifact plus canonical performance JSON.
- Replaced the placeholder HTTP 501 analysis route with a job-creation endpoint
  returning HTTP 202, SQLite-backed job status, job polling, and canonical
  performance retrieval.
- Added explicit `queued`, `running`, `completed`, and `failed` states,
  duplicate-active-job protection, restart recovery for interrupted jobs, and
  concise failure reporting.
- Added API and engine-adapter unit tests; backend CI now runs Ruff across the
  application and test tree.
- Connected the frontend upload flow to job creation, status polling, canonical
  event summary display, and generated MIDI download.
- Added a guarded MIDI download endpoint that serves only the latest completed
  job artifact for the requested project.
- Added an engine-validation workflow step that exercises the complete API path
  against a synthetic mix: upload, enqueue, real DrumScript inference, canonical
  performance retrieval, and MIDI download.
- Added `docs/ANALYSIS_API.md` with endpoint contracts, runtime requirements,
  and the single-worker deployment limitation.

### Validation boundary

- Backend tests run #42 passed the API/adapter unit tests and Ruff; repository
  CI run #128 passed both frontend and backend jobs.
- DrumScript engine validation run #34 passed synthetic and repository MP3
  conversion smoke tests plus the API-to-engine upload/inference/result/MIDI
  download path. This verifies the CI integration path, not deployed service
  readiness or transcription accuracy.
- The regular backend install deliberately does not install PyTorch/DrumScript.
  The analysis job will report a clear failure until the optional worker
  runtime and FFmpeg/ffprobe are installed.
- FastAPI in-process background tasks are single-process development plumbing,
  not a durable production queue.

## 2026-11-11 — canonical events, engine compatibility, and benchmark harness

### Implemented in PR #3

- Added `backend/app/drum_events.py` with schema version 1.0, absolute event
  times, instrument labels, velocity, confidence, provenance, manual-correction
  state, duration, and tempo/time-signature map.
- Added deterministic one-to-one instrument-aware event scoring with configurable
  timing tolerance and overall/per-instrument precision, recall, F1, counts,
  and matched-event timing error.
- Added `drumai-evaluate` for single-pair canonical JSON scoring.
- Added `backend/app/midi_adapter.py` and `drumai-midi-import` to normalize
  General MIDI percussion notes into canonical events while preserving tempo,
  time signatures, velocity, and absolute seconds.
- Added backend CI and unit tests for schema, evaluator, MIDI conversion, and
  CLI behavior.
- Extended the DrumScript engine smoke so each generated MIDI must convert to
  non-empty canonical events.
- Added `drumai-benchmark`, a manifest-driven batch evaluator that requires
  declared permission basis, audio metadata, and reviewed annotations, checks
  file existence and unique case IDs, prevents source-recording leakage across
  development/evaluation splits, and emits per-case, pooled, and split-specific micro-aggregate
  metrics. These declarations are not independent rights verification.
- Added benchmark manifest starter and batch-evaluation documentation.

### Verified validation

- Backend CI run #5 passed: 17 tests and Ruff checks.
- Repository CI run #111 passed both frontend and backend jobs.
- Engine validation run #27 passed all steps, including upstream tests
  (202 passed, 8 skipped, 11 deselected) and synthetic + both repository MP3
  smoke tests.
- Canonical MIDI conversion output from run #27:
  - Synthetic mix: 38 canonical events (closed hi-hat 31, kick 7).
  - Radiohead Creep: 1,040 canonical events (closed hi-hat 621, crash 62,
    kick 118, open hi-hat 81, ride 1, snare 157).
  - Muse Psycho: 1,124 canonical events (closed hi-hat 518, crash 68,
    kick 233, open hi-hat 119, ride 15, snare 171).
- The engine generated non-empty MIDI and canonical events for all three
  inputs. This is integration evidence only, not an accuracy benchmark.
- No human-annotated golden dataset is checked in. The benchmark manifest
  starter is empty by design; permission-cleared audio and reviewed reference
  events are still required.
- The asynchronous analysis API is implemented, but its new CI run and a live
  API-to-DrumScript job have not yet passed. Do not claim deployed end-to-end
  readiness until those validations succeed.

## Next engineering milestones

1. Populate a small permission-cleared development benchmark and separately
   reviewed evaluation set; never reuse the repository MP3s without explicit
   redistribution permission.
2. Run batch scoring against those references and record engine revision,
   configuration, per-instrument metrics, and timing tolerance.
3. Replace the in-process background task with a durable worker queue before
   multi-worker deployment; add artifact download and job cancellation.
4. Add canonical event editing operations and MIDI/MusicXML/PDF exporters.

## 2026-11-10/11 — engine integration spike (PR #2)

- Added isolated Python 3.12 GitHub Actions validation for CPU PyTorch,
  DrumScript import/CLI, upstream non-slow tests, synthetic full-mix smoke,
  and repository-root MP3 smoke.
- Engine validation run #6 completed successfully and produced non-empty MIDI
  outputs for the synthetic signal and both repository MP3s. That earlier
  smoke verified pipeline execution only, not event-level accuracy.


## 2026-11-11 — synchronized audio playback and timeline (implementation, CI pending)

- Added `GET /api/projects/{project_id}/audio` to stream the original project
  upload by project ID. Filesystem access uses the server-generated stored
  filename, resolves under the upload directory, and returns 404 for unknown
  projects or missing audio.
- Added API coverage for audio bytes, media type, inline disposition, and
  unknown-project handling.
- Added browser audio playback controls and a seek slider to the editor.
  Playback time moves a playhead across every timeline lane; nearby events are
  highlighted during playback, and clicking a hit seeks the audio and selects
  its corresponding event row.
- Updated the API contract documentation. CI for this batch has not yet been
  observed; implementation status is not a CI pass.


### CI feedback and follow-up fixes

- The first CI attempt for the audio playback batch exposed two issues in the
  merge checkout: the WAV MIME type on the runner is `audio/x-wav` rather than
  the equally valid `audio/wav`, and the frontend TypeScript target does not
  include `String.replaceAll`.
- Relaxed the API assertion to require an audio media type and replaced the
  lane-label `replaceAll` call with an ES-compatible regular expression.
- These fixes are committed on the PR branch. A fresh CI result for the updated
  head is still pending; the earlier failed run is not counted as validation.


## 2026-11-11 — tempo-map-aware arrangement grid (implementation, CI pending)

- Replaced the fixed single-BPM timeline grid with beat positions generated
  from the canonical tempo map. Each tempo segment uses its own BPM and time
  signature; bar starts and quarter-note beat lines are rendered independently
  in absolute audio time.
- Tempo-change boundaries are marked on every instrument lane and BPM labels
  are placed at their corresponding audio timestamps. A 120 BPM, 4/4 fallback
  remains in effect when a performance has no tempo metadata.
- Event positions and playback synchronization remain based on absolute
  seconds, so tempo visualization does not shift the canonical event times.
- Frontend build and regression CI for this increment are pending; no pass is
  claimed until the latest branch head completes validation.


## 2026-11-11 — playback integration validation

- DrumScript engine validation run #77 passed all steps on the playback batch
  head, including upstream non-slow tests, synthetic and both repository MP3
  smoke tests, and API-to-engine end-to-end smoke.
- Repository CI run #173 passed frontend build and backend tests; backend
  tests run #86 also passed with Ruff. These runs validated the playback
  implementation and the runner compatibility fixes.
- The later tempo-map-aware timeline commits were added after run #173. They
  still require a fresh frontend build; do not extend the earlier pass claim
  to those commits.


## 2026-11-11 — timeline lane visibility filters

- Added per-instrument visibility checkboxes plus show-all/hide-all controls above the arrangement timeline.
- Filtering is presentation-only: it does not mutate canonical events, history, playback audio, or MIDI/MusicXML exports; the event table remains complete.
- This is a frontend-only increment. Latest repository CI and engine-validation status are tracked separately from this commit.


## 2026-11-11 — atomic bulk event editing

- Added batch event time shifting and batch deletion endpoints with unique-ID and full-selection validation under SQLite `BEGIN IMMEDIATE`.
- All changes are validated before persistence; invalid negative event times reject the entire batch. Each operation creates exactly one revision and regenerates MIDI from the canonical performance.
- Added frontend multi-select, select-all, time-offset input, batch move/delete actions, and Chinese user-guide coverage.
- Added API tests for one-revision semantics, MIDI synchronization, and atomic rejection.


## 2026-11-11 — selected drum-event repetition

- Added an atomic duplication endpoint that clones selected canonical drum events
  at one or more fixed interval offsets. New events receive unique IDs, retain
  instrument/velocity metadata, and are marked as manually corrected.
- Repeat count is bounded to 1–16; invalid selections and any clone beyond the
  track duration reject the entire request before persistence.
- Added editor controls for interval and repeat count. A successful action
  creates one undo/redo revision and regenerates MIDI from canonical events.
- Added API tests for metadata preservation, unique IDs, repeat timing, single
  history revision, MIDI synchronization, and out-of-duration atomic rejection.
- CI validation for this increment is pending until the latest branch head runs.


## 2026-11-11 — measure-based drum phrase copy and paste

- Added an atomic API that copies all canonical events in a source time range
  to a target measure, mapping normalized within-bar offsets when source and
  target measure lengths differ. Instrument, velocity, and confidence are
  preserved; clones receive new IDs and manual provenance.
- Added frontend source/target measure controls driven by the tempo-aware
  timeline beat/bar grid. Original events remain untouched.
- Empty source ranges, invalid ranges, and pasted events beyond track duration
  reject the operation before saving. Successful pastes create one history
  revision and regenerate MIDI from canonical events.
- Added API tests for relative timing, metadata preservation, one-revision
  semantics, MIDI synchronization, empty-source rejection, and overflow
  atomicity. CI validation is pending for this increment.


### Measure-copy validation update

- Backend tests run #171 passed: 62 tests; Ruff passed.
- DrumScript engine validation run #162 is queued/pending. This editor-only API change does not modify the inference engine; engine workflow completion is still tracked.
- A fresh repository frontend build result has not yet been confirmed for this head.


## 2026-11-11 — built-in printable PDF drum score export (implementation, CI pending)

- Added a ReportLab-based PDF renderer that lays canonical drum events onto a
  landscape percussion staff with measure boundaries/numbers, tempo and meter
  metadata, velocity-scaled noteheads, instrument-specific notehead styles,
  and a compact instrument legend. Long arrangements paginate by systems.
- Added `GET /api/projects/{project_id}/pdf`, which always renders the latest
  completed canonical performance, so manual corrections, quantization,
  undo, and redo are reflected in the printout.
- Added a PDF download link next to MIDI and editable MusicXML, declared the
  ReportLab runtime dependency, and updated the user guide/API/README.
- Added API tests for PDF signature/content type/download disposition and the
  missing-performance 404 path. CI is pending; no build or test pass is claimed
  until the workflow results are observed. MusicXML remains the editable score
  interchange format; PDF is the printable reading/printing format.


## 2026-11-11 — adopt Verovio for professional PDF engraving

- Replaced the hand-drawn PDF as the primary path with Verovio, a mature
  open-source notation engraving engine that imports MusicXML and renders
  vector SVG pages. CairoSVG converts each vector page to PDF and pypdf
  assembles multi-page output. ReportLab remains a minimal-install fallback.
- Added pinned-compatible runtime ranges for Verovio 6.4, CairoSVG, and pypdf.
  Verovio is LGPL-3.0; no Verovio source is vendored or modified.
- Strengthened the PDF API test to parse the returned PDF and require at least
  one real page. CI will validate MusicXML import, engraving, SVG-to-PDF
  conversion, and PDF assembly on the next run.
- OSS references: https://github.com/rism-digital/verovio and
  https://book.verovio.org/installing-or-building-from-sources/python.html .


## 2026-11-11 — timeline marquee selection and drag move

- Added pointer-based marquee selection across visible instrument lanes and a
  live selection rectangle. Dragging on empty timeline space selects events
  within both the time and lane range.
- Dragging a selected hit previews and applies a shared time offset to the
  whole selected group through the existing atomic batch-edit endpoint. The
  API still enforces song bounds, creates one history revision, and regenerates
  MIDI; click-to-seek behavior is preserved for non-drag clicks.
- Added visual marquee styling and updated the user guide. Frontend production
  build is pending for this increment.


### 2026-11-11 validation checkpoint — Verovio + timeline drag

- Verovio PDF path is exercised by the API test: backend test suite reports
  64 passed, including parsing the returned PDF with pypdf (workflow run
  #180 / CI backend test job).
- Frontend production build passed on the commit containing marquee selection
  and drag-move (CI run #269).
- Ruff caught import-order-only issues in the PDF test imports on two workflow
  attempts. Both were corrected; latest fix commit
  `0953ebbf036ce47ea623ff363fa29db20b74a6ee` is awaiting its own lint result.
- DrumScript upstream test and repository MP3 end-to-end workflow is still
  running; do not treat the engine smoke test as passed until its final status
  is recorded.


## 2026-11-11 — PDF fallback layout correction and regression coverage

- Moved system labels and the initial time signature into a dedicated left
  gutter, separated bar numbers from the staff, and annotate later meter
  changes only where they occur instead of repeating the initial meter.
- Added fallback-renderer regression tests for single- and multi-system
  scores, PDF page readability, system labels, and time-signature repetition.
- CI is pending for this increment. Visual review of a freshly rendered PDF
  remains required before calling the layout fully accepted.


## 2026-11-11 — portable full-project backup export

- Added a ZIP endpoint and workspace download link bundling the original uploaded
  audio, latest canonical performance JSON, MIDI, editable MusicXML, printable
  PDF, and a short README manifest.
- The bundle reads the latest completed canonical performance so edits and
  history restores are reflected in the exported files. Added API coverage for
  archive contents and the not-yet-analyzed response. CI pending.


## 2026-11-11 — graceful PDF engraving fallback

- CI exposed that the Verovio Python package can be installed while its SMuFL
  font resources are unavailable, causing score loading to raise a ValueError.
- PDF export now falls back to the ReportLab renderer for that specific
  unusable-engraving condition, rather than failing the entire export and
  project backup. Added a regression test for this path.
- Full-project backup export is now covered by archive-content API tests;
  CI rerun pending.


## 2026-11-11 — PDF page geometry and external benchmark acquisition

- Corrected the Verovio SVG-to-PDF conversion to set an explicit landscape A4 output surface. CairoSVG otherwise interprets SVG pixel dimensions at 96 DPI, which can make the physical PDF page size differ from the intended paper size.
- Added PDF regression coverage for A4 media-box dimensions on both the Verovio primary renderer and the ReportLab fallback, in addition to existing text/layout checks. CI must confirm the new primary-renderer assertion before this fix is considered verified.
- Added `docs/TEST_DATASETS.md` with a staged, licence-aware acquisition plan for IDMT-SMT-Drums, GMD, E-GMD, ENST-Drums, and QUASI. Audio remains outside Git; each benchmark case must preserve provenance, licence, checksum, and reviewed annotation metadata.
- No external dataset has yet been downloaded into the repository or scored. The first practical target is a small IDMT subset plus a fixed GMD held-out subset; real mixed-song evaluation requires separate track-level rights review.


## 2026-11-11 — annotated IDMT regression benchmark added to engine CI

- Reused the upstream DrumScript IDMT-SMT-Drums V2 benchmark adapter rather than creating a second annotation parser. The upstream adapter already pairs `#MIX.wav` recordings with XML/SVL labels and scores kick, snare, and hi-hat onset events at a 50 ms tolerance.
- Added an engine-validation CI step that downloads the 287 MB IDMT archive from Zenodo, runs the first 10 annotated RealDrum mixes, and uploads metrics as a workflow artifact. Raw dataset audio stays outside Git; the run is an evaluation-only use under the dataset's non-commercial/no-derivatives terms.
- This is the first labelled regression benchmark in our pipeline. It does not measure full-band mixed-song separation; QUASI remains a later candidate pending per-track licence review.
- Latest PDF resource-path and A4 regression changes are awaiting the current CI run. Previous attempts exposed and corrected a missing `Path` import and an incorrect multi-page test expectation; those failed runs are not counted as passes.

## 2026-11-11 — CI acceleration: FFmpeg provisioning

- The IDMT engine-validation workflow's FFmpeg setup was spending excessive time in the Ubuntu package-manager path (apt-get update / apt-get install).
- Replaced that fallback with the pip-distributed imageio-ffmpeg binary when the runner does not already provide FFmpeg; the binary directory is added to GITHUB_PATH and verified with ffmpeg -version.
- This keeps the runner-provided FFmpeg fast path and removes the slow apt repository refresh from the fallback path.
- The previous benchmark run had not yet reached dataset download or scoring, so no IDMT accuracy result is claimed. The workflow will rerun on this commit.

- Follow-up CI correction: imageio-ffmpeg exposes a versioned executable name rather than a literal ffmpeg command. The workflow now creates a runner-temp ffmpeg symlink and adds that directory to PATH before verifying the binary. The first pip-based attempt failed at the verification command before any benchmark work ran; no accuracy result is available yet.

## 2026-11-11 — First labelled IDMT benchmark completed

- The CI workflow successfully downloaded the IDMT-SMT-DRUMS-V2 evaluation archive, ran the upstream adapter on 10/10 RealDrum mixes, and uploaded the metrics artifact (workflow run #213, artifact `idmt-drum-transcription-benchmark`).
- Macro-average at the upstream adapter's 50 ms onset tolerance: kick P=0.700 / R=0.070 / F1=0.123; snare P=0.706 / R=0.914 / F1=0.775; hi-hat P=0.907 / R=0.996 / F1=0.949.
- Interpretation: kick recall is the major quality blocker; the score is an initial 10-item baseline, not a production-accuracy claim. Expand the held-out sample before making broad claims.
- The same workflow passed synthetic full-mix separation/transcription and canonical MIDI normalization. Repository MP3 processing then failed during Demucs MP3 decoding because its loader could not locate/use FFmpeg in that subprocess, despite the workflow's FFmpeg verification step.
- Updated `scripts/engine_smoke.py` to explicitly decode repository MP3 samples to PCM WAV with the imageio-ffmpeg executable (or system FFmpeg fallback) before passing the audio into Demucs. This preserves real repository MP3 coverage while avoiding Demucs' optional MP3 decoder lookup path. CI must validate this correction.


## 2026-11-11 — kick recall research and cross-domain benchmark expansion

- Investigated public ADT research and open implementations: IDMT-SMT-Drums, MDB Drums, ADTOF, a Librosa-onset + CNN baseline, adaptive onset detection with spectral/tail templates, and the 2026 Separate-and-Detect five-stem approach.
- Added `docs/KICK_RECALL_RESEARCH.md` with cited sources, testable failure hypotheses, dataset/license notes, and a staged diagnostic plan. The causes are explicitly hypotheses, not asserted facts.
- Expanded IDMT CI evaluation from the first 10 RealDrum mixes to 15 examples each from RealDrum, WaveDrum, and TechnoDrum, with distinct run names and archived per-track metrics. This checks whether the low kick recall is domain-specific instead of extrapolating from one subset.
- Disabled cancellation of an in-progress engine-validation run when a new commit arrives; this long-running CPU benchmark should finish rather than repeatedly being cancelled by rapid pushes.
- The expanded benchmark and MP3-to-WAV smoke correction are awaiting CI execution. No accuracy improvement is claimed yet.


## 2026-11-11 — stage-wise kick miss diagnostics

- Added `scripts/kick_stage_diagnostics.py`. It evaluates each IDMT kick reference twice: first against all onset candidates before classification, then against events classified as kick. It reports candidate recall, final kick recall, kick precision, and candidate-to-kick match retention per subset and per track.
- The engine-validation workflow now runs this diagnostic on 15 tracks from each of RealDrum, WaveDrum, and TechnoDrum and uploads JSON/CSV alongside the upstream per-track benchmark archives.
- Interpretation rule: low candidate recall indicates the shared onset stage is missing kick opportunities; healthy candidate recall but low final kick recall points to classification/feature rules. This is a diagnostic decomposition, not a claim that either failure mode has already been observed.
- CI is running/pending for the new diagnostic script and workflow. The first output will determine which algorithm branch to change next.


## 2026-11-12 — API runtime dependency and export visual smoke coverage

- The first expanded stage-wise run evaluated 14 RealDrum, 15 WaveDrum, and 11 TechnoDrum tracks (the dataset contains fewer eligible files in two subsets). Candidate-onset recall was 0.983 / 0.963 / 0.990, while final kick recall was 0.053 / 0.172 / 0.571. These are subset-level diagnostic results, not production accuracy claims.
- The API-to-engine end-to-end smoke exposed a real worker-image dependency gap: the workflow had ffmpeg but not ffprobe, which the API uses to read source duration. Replaced the workflow provisioning step with system FFmpeg installation and explicit checks for both executables. Backend unit tests and frontend/backend CI passed on the dependency-fix commit; the full engine workflow is rerunning.
- Added feature-level diagnostics for IDMT reference kicks that already match an onset candidate. The archived JSON now includes per-candidate LFER, peak frequency, centroid, HFER, high-frequency energy, decay, and pass/fail against the current kick-rule thresholds. This measures which boundaries reject candidate kick events before any classifier changes are attempted.
- Extended the API end-to-end smoke to call the PDF endpoint, validate PDF signature/page count/landscape-A4 geometry, preserve the generated PDF, rasterize its first page with Poppler, and upload both PDF and PNG as a CI artifact. This creates a reviewable visual regression artifact rather than relying only on PDF metadata tests.
- The PDF raster/artifact step and expanded kick-feature diagnostics are pending on the current PR #4 engine-validation run. No PDF visual acceptance or kick-recall improvement is claimed until those artifacts and metrics are reviewed.



## 2026-11-12 — avoid unnecessary media-tool installation on CI runners

- The latest engine-validation run remained in the media-tool provisioning step
  even after removing the explicit apt repository refresh. The workflow now
  checks for ffmpeg, ffprobe, and pdftoppm first and installs FFmpeg/Poppler
  packages only when one or more tools are missing.
- This uses the preinstalled GitHub-hosted runner binaries when available and
  avoids a package-manager round trip on already-provisioned runners. The next
  run must still prove that all three tools are present and the full engine,
  benchmark, MP3, and PDF-render stages complete; no pass is inferred from this
  workflow change alone.


## 2026-11-12 — remove Ubuntu apt mirror dependency from engine validation

- Inspected the failed GitHub Actions job log: the runner did not have
  ffmpeg/ffprobe/pdftoppm preinstalled, and Ubuntu package downloads repeatedly
  failed DNS resolution against the Azure archive mirror. The install step
  spent about 33 minutes downloading most packages before apt exited 100.
- Replaced apt-based media provisioning with the Python ffmpeg-downloader
  package and its static FFmpeg build, exposing both ffmpeg and ffprobe on PATH.
  The workflow also installs pypdfium2 from PyPI for PDF rasterization.
- The API smoke now renders the first PDF page in-process, validates the PNG
  signature and non-trivial file size, and uploads the PDF plus rendered PNG.
  Poppler/pdfinfo are no longer required.
- This removes the failing Ubuntu mirror dependency, but the next CI run must
  still verify the binary download, full inference, repository MP3s, PDF
  generation, and raster output. No engine or visual pass is claimed yet.


## 2026-11-12 — PDF notation scale follow-up
- Re-inspected the regenerated API PDF artifact from engine run 43125687384. The tempo label is now readable, but the notation still occupies too little vertical space on landscape A4; visual acceptance remains blocked.
- The prior Verovio setting used `scale: 52`, although Verovio defines 100 as normal output size. Updated the engraving scale to 100 and enabled vertical justification with an 0.8 maximum vertical justification ratio.
- This is a targeted layout correction, not yet a visual pass. The next engine run must regenerate and inspect the page image before claiming PDF readability.
- Official reference: Verovio toolkit options document scale as a percentage with 100 normal size and describe vertical justification as filling page spacing.


## 2026-11-12 — PDF visual acceptance gate
- Re-inspected the PDF/PNG artifact from engine validation run 43134370764 after the Verovio scale/vertical-justification adjustment. Tempo text is readable, but the score remains vertically compressed near the top of the landscape A4 page; the blank lower page area is still unacceptable.
- Added a visual smoke assertion in `scripts/api_engine_smoke.py`: it measures dark-ink vertical coverage in the upper 80% of the rendered page (excluding the footer mark) and rejects notation occupying less than 15% of page height.
- This intentionally turns a visually poor export into a failing engine-validation check instead of reporting a misleading green result. The next run is expected to determine whether the current renderer clears this threshold; visual inspection remains required regardless.


## 2026-11-12 — sparse-score engraving scale follow-up

- The new API visual gate measured only 8.4% vertical ink coverage on the synthetic short-score PDF. The archived PNG confirmed that a single percussion staff was rendered legibly but too small and confined to the top of the A4 page.
- Increased Verovio engraving scale from 100 to 140 and the MEI unit from its default to the supported maximum of 12, aiming to enlarge staff spacing, noteheads, and stems while preserving vector output and A4 geometry.
- This is a measured layout experiment, not an accepted PDF fix. The 15% visual gate remains unchanged; the next engine run and a fresh PNG review must confirm whether the score now occupies the page appropriately without clipping or excessive pagination.


## 2026-11-12 — deterministic PDF measures per system

- Replaced reliance on Verovio's automatic horizontal line wrapping with explicit
  MusicXML `print new-system="yes"` markers at the configured measure interval.
- PDF export now defaults to four measures per system and accepts five via
  `GET /api/projects/{project_id}/pdf?measures_per_system=5`. Unsupported
  values are rejected with HTTP 422; the ReportLab fallback uses the same
  grouping setting.
- Added regression coverage for the exact 4-bar and 5-bar system-break
  positions and invalid settings. Fresh engine PDF artifact review is still
  required before visual acceptance.


## 2026-11-12 — editor keyboard history shortcuts

- Added standard editor shortcuts for persistent project history: Ctrl/Cmd+Z
  undoes, Ctrl/Cmd+Shift+Z and Ctrl/Cmd+Y redo.
- Shortcuts are ignored while typing in inputs, textareas, selects, or
  content-editable regions, and are disabled while a save/history operation is
  already running. The existing server-backed undo/redo remains the single
  source of truth.
- This improves editing speed without introducing a separate client-only
  history stack or changing event persistence semantics.


## 2026-11-12 — consistent export bundle layout

- The complete project ZIP now accepts the same `measures_per_system=4|5`
  option as the standalone PDF endpoint.
- The editor passes its selected line density to both standalone PDF and ZIP
  export, so the packaged score no longer silently falls back to four measures
  when the user selected five.
- ZIP contents remain canonical performance JSON, MIDI, editable MusicXML,
  printable PDF, and original uploaded audio.


## 2026-11-12 — project bundle layout regression coverage

- Extended the project archive API test to request five measures per system and
  assert that the selected value reaches the PDF renderer and is preserved in
  the ZIP's score PDF.
- Added a regression check that unsupported project-bundle PDF layouts return
  HTTP 422.


## 2026-11-12 — pipeline readiness copy

- Updated the pipeline summary so the implemented editor/export stage is no
  longer mislabeled as "in development".
- Kept the transcription runtime dependency explicit, avoiding the impression
  that a clean frontend install alone enables model inference.


## 2026-11-12 — kick classifier runtime audit and Gemini follow-up

- Confirmed the actual standard full-song classifier is in the external
  `DrumScript/DrumScript` runtime, not in a FastAPI `app.engine.classifier`
  module. DrumAI's `backend/app/engine_adapter.py` lazily imports
  `drumscript` and calls `engine.transcribe(..., full_song=True,
  midi_only=True)`.
- The engine-validation workflow currently shallow-clones upstream main
  without pinning a commit. The upstream source snapshot independently
  inspected during this audit is
  `e3c470787a3ec33221fcb18674e01fa5bdfd5de8`; this is not asserted to be the
  exact SHA used by the completed CI run. Pinning/recording the actual runtime
  SHA is required for reproducible classifier experiments.
- In upstream `drumscript/drum_classifier/classify.py`, standard
  `classify_events` extracts a 200 ms spectral slice plus 1.5 s decay slice.
  Its kick rule is `lfer >= KICK_LFER_MIN` and peak frequency within
  `KICK_FREQ_MIN..KICK_FREQ_MAX`. Current upstream constants inspected:
  LFER 0.32, frequency 40–140 Hz. Actual feature names are
  `peak_freq`, `centroid`, `decay`, `lfer`, `hfer`, `hfer_5k`.
  No `transient_strength` or `beater_attack_ratio` exists in this path.
- Low-tom classification follows the kick rule and requires low HFER plus
  resonant decay; when the kick condition fails, a low-frequency resonant
  candidate can be labeled `low_tom`. Standard full-song classification does
  not use the separate rudiment ADSR/lockout gates.
- Gemini received a follow-up task on Issue #5 to inspect the actual upstream
  source, reproduce IDMT results, and return a minimal opt-in candidate only
  if held-out track-isolated evidence justifies it. No code patch or threshold
  change is accepted yet.
- Integration head `f100c55b6bed2045b8598c7859fe4f51cd69eadc` passed backend
  tests (Actions run 43212702038) and engine validation (run 43212702034).
  The engine job completed IDMT benchmark/diagnostic steps for all three
  subsets and uploaded artifact `idmt-drum-transcription-benchmark` (artifact
  13942855863). These are successful workflow executions, not a claimed
  classifier accuracy improvement; raw artifact metrics still require review.
- No integration classifier code or threshold was changed. PR #4 remains
  unmerged pending review and user approval.


## 2026-11-12 — reject ungrounded Gemini kick patch proposal

- Reviewed the latest Issue #5 delivery against the actual integration branch.
  The claimed `backend/app/api/projects.py`,
  `backend/app/engine/features.py`, `backend/app/engine/classifier.py`,
  and `backend/app/engine/patches/kick_classifier_patch.py` paths do not
  exist. The real API adapter is `backend/app/engine_adapter.py`, which
  lazily imports DrumScript and calls its full-song `transcribe()` API.
- The proposal's `transient_strength`, `beater_attack_ratio`, and
  `decay_duration_ms` fields are not part of the real full-song classifier
  feature schema. The actual fields are `lfer`, `peak_freq`, `centroid`,
  `hfer`, `hfer_5k`, and `decay`; the current upstream kick rule uses
  LFER 0.32 and peak frequency 40–140 Hz. No evidence supports replacing
  this with a 0.65 threshold or invented millisecond decay gates.
- Rejected the submitted IDMT table as unauditable: no per-track source
  records, matching tolerance, raw metrics, runtime SHA, or reproducible
  command were supplied. Its 30-track/0.70–0.92 recall claims conflict with
  the project's previously archived stage-wise diagnostic baseline
  (14/15/11 tracks; final kick recall 0.053/0.172/0.571).
- The supplied "track-isolated" script only evaluates two hand-written mock
  samples. It does not load IDMT, isolate tracks, match event timestamps, or
  compare baseline and candidate on identical held-out tracks. The proposed
  unit tests exercise only a new synthetic helper, not the real classifier.
- Posted the complete evidence-based rejection and required resubmission
  criteria to Issue #5 comment
  https://github.com/oneyi53/drum-ai-studio/issues/5#issuecomment-6823552165.
- No classifier code, threshold, workflow, or production behavior changed.
  PR #4 remains unmerged and awaits explicit user approval.


## 2026-11-12 — re-review of revised kick metrics and rollback proposal

- Reviewed the revised Gemini delivery claiming paired IDMT baseline/candidate
  metrics and track-isolated evaluation. The displayed precision, recall, and
  F1 values are arithmetically consistent with the supplied aggregate counts,
  but no per-track raw metrics, track IDs, event timestamps, matching
  tolerance, runtime SHA, command log, or benchmark artifact was supplied.
  Arithmetic consistency is not evidence that the numbers were measured.
- The provided evaluation script remains a two-row hand-authored mock example;
  it does not load IDMT, implement leave-one-track-out, isolate tracks, match
  timestamps, or compare baseline and candidate on identical held-out tracks.
- The proposal still assumes nonexistent backend classifier paths and feature
  fields not emitted by the standard full-song DrumScript classifier.
- Its rollback example uses LFER 0.65, which does not restore the current
  upstream baseline (LFER 0.32 plus peak frequency 40–140 Hz); applying it
  would change behavior rather than roll back to the current rule.
- Posted the additional evidence requirements and rejection to Issue #5
  comment https://github.com/oneyi53/drum-ai-studio/issues/5#issuecomment-6823645441.
- No classifier, threshold, CI workflow, or production behavior was changed.
  PR #4 remains unmerged pending explicit user approval.


## 2026-11-12 — audit of newly supplied kick event-level metrics

- Reviewed the newly supplied IDMT table and five-row JSON excerpt. The
  aggregate TP/FP/FN arithmetic and derived precision/recall/F1 values are
  internally consistent. This validates only the arithmetic, not that the
  counts came from a real DrumScript execution.
- The submission labels the sample as 30 tracks (10 per subset), whereas the
  repository's completed expanded benchmark discovered 14 RealDrum, 15
  WaveDrum, and 11 TechnoDrum eligible tracks. The submitted cohort therefore
  needs explicit track IDs and inclusion/exclusion provenance before it can
  be compared with the archived run. The reported 0.70–0.92 subset recall
  also differs materially from the archived stage-wise final-kick recall
  0.053/0.172/0.571; differing cohort or scoring semantics may explain this,
  but no evidence currently reconciles them.
- The JSON fields `transient_strength`, `beater_attack_ratio`, and
  `decay_duration_ms` still do not match the standard full-song DrumScript
  feature schema (`lfer`, `peak_freq`, `centroid`, `hfer`,
  `hfer_5k`, `decay`). The stated default LFER threshold 0.65 also does
  not match the inspected upstream baseline of 0.32 plus the 40–140 Hz
  peak-frequency gate. No classifier change is justified by these records.
- The five examples are illustrative snippets, not a raw event-level
  evaluation artifact: they omit the complete per-track event population,
  predicted-event IDs/pitches, one-to-one matching assignments, duplicate
  handling, and the exact scoring command/runtime SHA. In particular, an FN
  row containing features but no predicted onset needs a documented method
  explaining how those features were measured at the reference time.
- The asserted 68% bass-masking and 72% tom/slap-bass attribution rates are
  not derivable from the five examples or aggregate TP/FP/FN table. They need
  per-event evidence and a reproducible attribution procedure.
- No code, threshold, or workflow was changed. Treat this submission as an
  unverified hypothesis/report, not measured benchmark evidence. Next
  acceptable evidence is the complete machine-generated JSON/CSV with
  per-track IDs and event-level assignments, the exact ±50 ms matcher and
  command, DrumScript runtime commit/package versions, and CI artifact/log
  proving the run. PR #4 remains unmerged.


## 2026-11-12 — review of proposed event matcher and artifact generator

- Reviewed the newly supplied environment declaration, greedy matcher, and
  machine-artifact generator against the integration branch's real diagnostic
  and engine adapter code. The environment limitation is appropriately stated;
  no measured accuracy claim is accepted from this delivery.
- Rejected the proposed global minimum-delta greedy matcher as the canonical
  scorer: it can fail to maximize one-to-one match cardinality. Counterexample
  at a 50 ms window: GT=[0.000, 0.050], Pred=[0.020, -0.040]. Global pair sorting
  consumes GT 0.050 / Pred 0.020 first and yields only one TP, although the
  alternative assignment yields two. Use the repository's chronological
  two-pointer matcher or a formally specified maximum-cardinality assignment,
  and add this adversarial regression test.
- The generator is not runnable against the actual DrumScript API. It calls
  `classify_events(audio_path)`, while the repository diagnostic loads and
  normalizes audio, calls `detect_onsets(audio, sample_rate)`, then calls
  `classify_events(audio, sample_rate, onsets)`. It also assumes event keys
  `time` and `pitch`; the real event shape used by the repository is
  `time_sec`, `instruments`, and optional `debug_features`.
- The proposed `idmt_manifest.json` is not the repository's dataset contract.
  Existing IDMT integration uses `find_mix_files`, `reference_onsets_for_file`,
  and the upstream XML/SVL annotation adapter. The proposed hard-coded fallback
  for `drumscript.__commit__` is not provenance: it can silently report a
  guessed SHA when the attribute is absent. Record the actual Git checkout SHA
  from the runtime installation and fail closed if it cannot be established.
- Kick pitch handling is underspecified: the task groups MIDI 35 and 36 as
  Kick, but the matcher requires exact pitch equality. Normalize both GT and
  predictions to a documented Kick class before matching, or explicitly score
  exact MIDI pitches as a separate metric.
- No evaluation code, classifier, or threshold was changed. The delivery is
  retained as a specification draft only; it is not an executable/reproducible
  evaluation artifact. PR #4 remains unmerged.


## 2026-11-12 — parallelized PDF engraving work with Gemini

- Created focused task Issue #6 for Gemini to reproduce and correct the Verovio PDF layout, add short-score and multi-system visual regression coverage, and submit a separate PR against the integration branch.
- The task explicitly forbids classifier/IDMT changes, fabricated artifacts or metrics, weakening visual gates, and merging the mainline integration PR.
- Rechecked current PDF implementation and tests: Verovio is configured at scale 180 with vertical justification disabled; tests cover A4 geometry and 4/5-measure break insertion, while API smoke checks first-page ink bounds. These checks do not yet establish visual acceptance for representative multi-system PDFs.
- Latest available engine-validation run #264 (run ID 43212702034) completed successfully on commit f100c55b6bed2045b8598c7859fe4f51cd69eadc. The integration branch has since advanced to ad6ae9401e25a43d65c15e5e3fc181eae23a8b3a, so this run is not validation of the current branch head. PDF artifact 13942911556 is available but its image has not yet been manually inspected in this environment.
- No production classifier or renderer code was changed in this documentation-only increment. PR #4 remains open and unmerged.


## 2026-11-12 — Issue #6 proposal review and CI PDF artifact inspection

- Reviewed Gemini's Issue #6 response. It supplied a plan/snippet only, not a branch, commit, PR, rendered output, or test logs. The proposed functions are not part of the current adapter API; it introduces a parallel `render_musicxml_to_pdf` path and uses toolkit method casing/API that does not match the existing implementation (`setOptions`, `loadData`, `renderToSVG` + CairoSVG/PyPDF). Its tests assert only non-empty output/options and do not exercise actual rendered multi-system geometry. Requested a real focused implementation and PR in Issue #6; comment 6823839834.
- Downloaded and visually inspected CI artifact 13942911556 from run 43212702034. The PNG is 1404x993 and shows the actual defect: the first system is rendered near the top, then a second almost-empty percussion staff appears below it, leaving most of the landscape page blank. This is concrete evidence that the PDF layout is not yet acceptable.
- Added this artifact reproduction to Issue #6 and asked Gemini to create a regression that fails on the extra near-empty system, then attach before/after PDF and PNG renders with the actual Verovio version/options; comment 6823850692.
- Artifact run commit is f100c55b6bed2045b8598c7859fe4f51cd69eadc, older than current integration head. No production code changed in this increment. PR #4 remains open and unmerged.


## 2026-11-13 — timeline cross-lane editing

- Fixed a functional mismatch in the piano-roll-style timeline: vertical pointer drags previously tracked the destination lane visually but only persisted horizontal time offsets, so a drum hit could not actually change instrument by dragging it to another lane.
- Extended the batch event API to accept an optional target instrument independently of an optional time offset. Selected events can now be reassigned to a drum lane, shifted in time, or both in one atomic history revision; edits retain velocity and are marked manual/corrected.
- Updated timeline pointer-up handling to persist the destination lane as well as time movement, and to allow a purely vertical move with zero time offset.
- Added API regression tests for instrument reassignment preserving event timing/velocity and for rejecting empty batch edits.
- No transcription classifier, benchmark thresholds, or PDF code changed.


## 2026-11-13 — MusicXML shared-cursor validation slice

- Started a mainline-based implementation slice after merging the timeline cross-lane editor fix.
- Added a MusicXML measure reconstructor that interprets `backup` and `forward` against the document-order shared cursor, resolves chord tones to their preceding non-chord onset, and validates non-overlapping events by (staff, voice).
- Tracks cursor positions as exact quarter-note fractions so a `divisions` change within a measure does not silently rescale earlier offsets; carries divisions and time signatures across measures in score-partwise documents.
- Adds regression coverage for 4/4, 6/8, additive meters, interleaved voices/staves, chord parent constraints, cursor underflow, overlap, overflow, and invalid durations.
- This slice validates existing MusicXML structure only. It does not yet change the event-to-MusicXML exporter to generate complete rests, dotted/tied durations, tuplets, or beat-aware beams, and it does not claim PDF visual acceptance. CI validation is pending.


- Follow-up validation: the first CI pass exposed two test-fixture/namespace-handling defects; both were corrected. The current backend CI reports 93 passed and Ruff clean, and the paired frontend CI is green. A regression now runs the validator against actual output from `performance_to_musicxml()`, not only hand-authored XML. PR #13 remains a validation-only slice; exporter notation semantics and PDF visual acceptance are still outstanding.


## 2026-11-13 — MusicXML note-value semantics validation

- Added an opt-in strict validator for MusicXML note `duration`, `type`, dot count, and `time-modification` ratios. The calculation uses exact fractions in quarter-note units.
- Added coverage for dotted and double-dotted values, triplet ratios, invalid tuplets, missing note types, and strict validation of actual output from the existing exporter.
- Kept strict validation opt-in to avoid silently breaking existing exports while the exporter is being upgraded to emit rests and duration fragments in a later slice.
- CI on the implementation commit: backend 99 tests passed and Ruff clean; frontend checks passed. This slice validates notation consistency but does not yet change exporter output or claim PDF visual acceptance.



## 2026-11-13 — PDF visual inspection and silent-tail correction

- Manually inspected the PDF/PNG from successful engine run 43222194461
  (artifact 13946229769). Notation and tempo are legible and horizontal score
  coverage improved, but the render still contains a nearly empty final
  staff/system and substantial lower-page whitespace. Automated ink bounds
  alone were insufficient for visual acceptance.
- Added a PDF-only trim of measures after the last measure containing a note,
  preserving direction markings from removed tail measures. Editable MusicXML
  remains unchanged and retains full duration. Added regression coverage for
  silent-tail removal and direction preservation. Fresh engine render review
  is required before accepting the correction.
- Latest kick diagnostics artifact 13947170566 shows aligned predicted/missed
  candidate LFER medians: RealDrum 0.523/0.184 (16/281), WaveDrum 0.499/0.186
  (65/299), TechnoDrum 0.437/0.209 (165/121). Peak-frequency distributions
  overlap more strongly. No classifier threshold or production behavior was
  changed; any adaptive LFER proposal still requires held-out track-level
  precision/recall validation.

## 2026-11-13 — project lifecycle management

- Added `DELETE /api/projects/{project_id}` to remove a saved project and its related analysis-job, revision-history, and history-state records. Original uploads and per-job analysis output directories are cleaned up using server-generated stored names only.
- Deletion is rejected with HTTP 409 while any analysis job is queued or running, preventing a background worker from racing filesystem cleanup or recreating orphaned output.
- Added API regression coverage for successful deletion (database rows and files) and the active-job guard, plus a delete action for the currently loaded project in the web editor with explicit destructive-action confirmation and UI state reset.
- This is a project-workflow increment; no PDF rendering, transcription classifier, or benchmark thresholds were changed.

## 2026-11-13 — takeover: merged PR #10 and PR #11, branch cleanup started

- Merged PR #10 (fix/pdf: trim silent tail measures before engraving) and
  PR #11 (feat/projects: safe project deletion with 409 guard) into main
  as one squashed snapshot: the PR branches conflicted with main on
  append-at-same-anchor spots (PROJECT_LOG, USER_GUIDE, test file), so the
  merges were resolved locally (keep both sides) instead of through the
  GitHub merge button. Backend suite on the merged tree: 102 passed
  (99 main + 1 PDF tail test + 2 delete tests). Frontend changes merged
  without conflict; frontend CI runs on push.
- PR #1 stays closed (do-not-merge): its evaluator/library work is already
  in main in newer form. Salvage-only: scripts/audit_prediction_csv.py and
  docs/REAL_AUDIO_EVALUATION.md, to cherry-pick later if wanted.
- Branch state after this push: 8 stale branches remain to delete
  (merged #2/#12/#13/#14, closed-unmerged #3/#7/#8/#9); they cannot be
  deleted through the available GitHub tools, so deletion is a manual
  GitHub step or a later cleanup. PR #15 (MusicXML explicit rests) and
  Issue #5 (kick detection) are still in review/fix, not in this push.
- Added docs/PROJECT_MANAGEMENT.md (one-branch-per-workstream, 7-day
  stale rule, PROJECT_LOG as the single progress record) and
  docs/TECH_RADAR.md (DrumScript / STRUM / ADTOF / Basic Pitch / Beat
  This!). Monthly tech-watch cron drum-ai-studio-tech-watch is set
  (1st of month, ~10:16).
## 2026-11-13 — Explicit MusicXML hits and rests

- Reworked the exporter so a drum hit is no longer assigned the entire gap to the next hit as its note value. Hits use a single standard/dotted note value (capped at a quarter note); representable silent spans are emitted as explicit rests.
- Added meter-aware rest grouping for 4/4, 3/4, 6/8, and common 7/8 groupings. Unspellable silent spans use exact MusicXML `forward` cursor skips instead of falsifying note values or shifting event onsets.
- Very short sub-128th hit intervals are represented by exact `time-modification` ratios. Every generated score is checked by the strict duration/type/dot/tuplet validator.
- PDF export performs the same MusicXML preflight before trying its fallback renderer, so the fallback cannot hide invalid notation.
- API/exporter regressions cover sparse voices, explicit rests, irregular intervals, sub-128th tuplets, and 4/4, 3/4, and 6/8 timing. Latest standard CI: 106 backend tests passed, Ruff clean, frontend checks passed. DrumScript/IDMT engine validation is still running; do not mark the change fully accepted until that result is reviewed.

## 2026-11-13 — validation review and mainline consolidation

- Both engine-validation runs for PR #15 completed successfully. Repository MP3 smoke results: `Creep` produced 1,035 canonical events including 114 kicks; `Psycho` produced 1,131 events including 229 kicks. Both completed MIDI generation. API end-to-end export produced MusicXML (22,021 bytes), PDF (41,082 bytes), and a rendered PNG (58,573 bytes); the artifact exists, but this log does not claim visual acceptance because the PNG has not been manually inspected.
- IDMT kick-stage diagnostics show candidate onset recall is high but kick classification retention is the bottleneck: RealDrum candidate recall 0.983 / kick recall 0.053 / precision 1.000; WaveDrum 0.963 / 0.172 / 0.956; TechnoDrum 0.990 / 0.571 / 0.851. The current feature-rule pass counts are 16/297, 65/364, and 165/286 respectively. Do not tune thresholds against these same tracks; use track-separated validation before changing production classification.
- Consolidated the previously separate PR #10 PDF-only silent-tail trim into this PR's PDF renderer. It removes measures after the last audible measure from the printable rendering only and preserves direction markings; the MusicXML download remains unchanged. Added the regression test for tail removal and direction preservation.
- Fixed engine-validation scheduling: docs-only changes no longer trigger the expensive audio workflow, and runs for the same PR/ref share one concurrency group with cancellation of superseded runs. This prevents duplicate full audio evaluations for sequential commits.
- The engine smoke and artifact-upload checks passed, but automated existence checks are not equivalent to manual visual acceptance of the PDF/PNG. The PDF layout still requires visual review.


## 2026-11-13 — kick classifier track-isolated experiment harness

- Audited the actual full-song DrumScript classifier source. Its kick decision is a fixed gate on the 200 ms onset slice: LFER >= 0.32 and peak frequency 40–140 Hz. The separate rudiment classifier has different gates and is not the production full-song path.
- Extended the IDMT kick diagnostic to retain feature rows for every classified onset candidate, including non-kick candidates, and label candidates with chronological one-to-one matching against annotated kick onsets at the configured tolerance.
- Added a leave-one-track-out LFER threshold sweep. Each held-out track is scored using a threshold selected only from the other tracks; the frequency band remains fixed. The report includes held-out baseline and tuned TP/FP/FN, precision, recall, F1, and per-track selected thresholds.
- This is an offline diagnostic experiment only. It does not change DrumScript production classification or claim an accuracy gain. A threshold change requires a consistent held-out improvement across subsets and review of low-tom/bass false positives.
- The workflow will rerun the IDMT diagnostics on this instrumentation change. This is a targeted reason to run the dataset once: it creates the missing candidate-level evidence needed to choose the next classifier experiment, rather than repeating the old aggregate smoke test.

## 2026-11-13 — DC-suppressed kick feature validation

- Completed Engine Validation run [43415917292](https://github.com/oneyi53/drum-ai-studio/actions/runs/43415917292) on PR #15 head `791fded11ae6a5c295f55aba37d81c94db07d9e5`. The three IDMT subset diagnostics, cross-subset aggregation, synthetic smoke, and both repository MP3 smoke tests completed successfully. Standard CI and backend tests also passed (runs 43415917253 and 43415917449).
- The 40-track / 2,619-candidate cross-subset leave-one-track-out artifact shows the original full-song gate (LFER >= 0.32, peak 40–140 Hz) at TP=246, FP=32, FN=701 (P=0.885, R=0.260, F1=0.402). Lowering LFER with the original peak feature improved held-out results to TP=812, FP=177, FN=135 (P=0.821, R=0.857, F1=0.839).
- Recomputing the onset spectrum with the DC bin excluded, widening the peak band to 20–180 Hz, and adding an HFER ceiling produced TP=905, FP=188, FN=42 (P=0.828, R=0.956, F1=0.887) in the same track-isolated evaluation. By subset: RealDrum P/R/F1=0.910/0.916/0.913; WaveDrum=0.828/0.953/0.886; TechnoDrum=0.763/1.000/0.865. This is a strong offline signal, not production accuracy: candidate-level false positives remain, and the subset mix is small/selected.
- Important interpretation: DC suppression + HFER recovered many WaveDrum/TechnoDrum kicks, but TechnoDrum precision remains 0.763 (89 false positives across that subset). RealDrum track 10 and some WaveDrum tracks still have substantial misses. The feature rule is therefore not safe to promote as-is; next work should inspect false-positive instrument overlap and validate on a broader independent set before changing upstream DrumScript.
- The Engine Validation job's only failure is the unrelated API PDF visual-height gate (13.4% ink height vs 15% minimum). Both repository MP3s still transcribed and generated MIDI; the failure occurred in the separate API PDF visual check. PDF visual acceptance remains open and is not a kick-classifier failure.
- No production classifier was changed. DrumScript is installed from its upstream repository in this workflow; these results currently validate an offline diagnostic rule only.

- Follow-up threshold-risk check on the same saved candidate artifact: selecting the DC-suppressed rule with a training-fold precision floor of 0.85 yielded held-out TP=854, FP=141, FN=93 (P=0.858, R=0.902, F1=0.880). This trims 47 false positives versus unconstrained F1 tuning while retaining 90.2% recall. Raising the training precision floor to 0.90 collapsed held-out recall to 0.304 (P=0.823), showing that a stricter training constraint did not generalize reliably. Treat 0.85 as a candidate operating point for further independent testing, not a production setting.

## 2026-11-13 — precision-guarded kick operating point

- Added a reproducible second operating-point evaluation to the existing candidate-feature diagnostic: each held-out track is excluded from threshold selection, and the training fold first filters candidate LFER/HFER thresholds to those meeting a configurable minimum training precision (currently 0.85), then selects the best F1 among eligible thresholds. If a fold cannot meet the floor, the artifact records an explicit fallback instead of silently claiming the constraint was met.
- The same precision-guarded sweep is now emitted per subset and across all subsets, including per-track selected thresholds, training precision, fallback flags, and held-out metrics. No scikit-learn dependency or production classifier change is introduced.
- Prior exploratory calculation on the saved 2,619-candidate artifact suggested this operating point could reduce false positives while retaining roughly 90% recall; the new committed implementation must reproduce that result in Engine Validation before it is treated as verified. Runs 43421128261 (backend), 43421128525 (CI), and 43421128350 (Engine Validation) were triggered by the implementation and are pending at log update time.

## 2026-11-13 — development handoff

- Added `docs/HANDOFF.md` as the current consolidated handover: project goals, implemented capabilities, open quality risks, kick-classifier evidence and its limitations, current PR/Engine Validation state, next priorities, technical boundaries, and key file entry points.
- Current handoff commit: `50a99a6fe0304711eeb623b326951ce3abed8ec1`.
- At handoff time PR #15 remains Draft and Engine Validation run `43421181480` remains in progress; precision-guarded results are not yet verified by that run.
