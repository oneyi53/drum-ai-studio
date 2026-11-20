# Kick review, bass-confusion evaluation, and independent model training

## Human review pack

Run after the real-song comparison:
\`\`\`bash
python scripts/build_kick_review_pack.py --manifest-root /tmp/real-song-corpus --comparison-dir /tmp/real-song-comparison --output /tmp/kick-review-pack
\`\`\`

The CSV consolidates CNN and DrumScript predictions, isolated-kick onset proposals, and onset proposals from separate bass stems. Events within 35 ms are clustered, with model arms and source types retained. Labels and decisions are blank by design.

Review labels: \`kick\`, \`bass_guitar\`, \`bass_synth_808\`, \`snare\`, \`hat\`, \`percussion\`, \`other\`, \`uncertain\`. Set \`decision=accept\` only after listening to the full mix and relevant stem. Add missed kicks manually. Never infer an instrument from low-frequency energy alone.

## Bass-confusion reporting

Count a prediction as a bass false positive only when a reviewer labels it as \`bass_guitar\` or \`bass_synth_808\`. Keep uncertain and unreviewed events out of class-specific false-positive rates.

## Independent classifier training scaffold

\`scripts/train_kick_event_classifier.py\` trains a multi-class CNN from scratch. It does not load, distill, or initialize from STAR/AGPL weights. It consumes only accepted human-reviewed events and a source manifest with licence metadata.

Default training allowlist: CC0 1.0 and CC BY 2.0/3.0/4.0. CC BY-SA is rejected unless \`--allow-sharealike\` is explicitly supplied after separate rights review. Kaino full mixes have no labels until manually annotated. OnAir CC BY-SA examples remain evaluation-first and are not silently treated as permissively licensed training data.

The script requires at least 8 tracks and 20 accepted examples per class by default, uses a track-grouped validation split, and records audio hashes, source licences, track split and feature settings. This is experimental scaffolding, not a production-ready model. Require an untouched real-song test set, per-class metrics, calibration and legal review before deployment.

## Current limits

- OnAir currently provides only two dedicated kick-stem tracks; this is not enough for a general model.
- Four bass-confusion tracks have separate bass/808 stems but grouped drums, so they support bass-transient review, not kick-only ground truth.
- STAR CNN remains evaluation-only under AGPL-3.0. No STAR weights are copied into the independent model.
- Production inference, thresholds, MIDI mapping and exports are unchanged.


## Independent trainer hardening (2026-11-18)

The from-scratch trainer now refuses accepted annotations unless the source manifest explicitly marks `license_verified_per_track: true`, or the annotation row carries `license_verified=true`. A repository-wide CC0 badge is not sufficient. The trainer also checks any recorded audio SHA-256, rejects invalid/out-of-range annotation times, and requires each event class to occur in at least two distinct tracks before track-grouped holdout training.

The event crop was lengthened from 32 to 96 hops (about 1.115 seconds at 22,050 Hz / 256 hop). This gives the classifier more low-frequency sustain/context to distinguish kick transients from bass guitar and 808 notes. It remains an experimental event classifier, not a full-song deployed transcription model. A dedicated test file covers the per-track rights gate and is run in CI.


## Full-song corpus expansion and separated error accounting (2026-11-18)

The CI discovery pool is expanded to up to 60 candidates (five per each of 12 filename-derived genre buckets). A candidate is only marked as passing the full-song length screen when FFprobe confirms at least 60 seconds. This is not a musical-content or genre confirmation: actual drums, bass, style and per-track rights remain pending human/source review. Short loops remain recorded but are excluded from the full-song eligible count.

Use `scripts/evaluate_kick_bass_confusions.py` with reviewed CSV annotations and `real-song-events.csv` predictions to report, independently per model arm and track:
- kick reference events matched and missed (kick recall);
- bass-guitar events incorrectly matched by a kick prediction;
- bass-synth/808 events incorrectly matched by a kick prediction;
- unmatched kick predictions, kept as unknown rather than automatically called bass.

Only rows with `decision=accept` enter the reference set. Rejected and uncertain rows do not count as ground truth. The test suite explicitly checks that the three error categories remain separate.

The independent trainer now also requires every class to occur in both the train and track-held-out validation partitions. It writes a validation confusion matrix and per-class precision/recall/F1, in addition to the previous track-grouped split and source hashes. This prevents an apparently good aggregate accuracy from hiding an absent class in the holdout set.


## Wider open-song discovery and technical screening (2026-11-18)

The SoundSafari CC0 discovery pass now samples up to 120 full-song candidates (10 per each of 12 filename-derived style buckets), rather than 60. Each downloaded candidate records the immutable repository commit, path, blob SHA, local SHA-256, file size and duration. FFmpeg adds a non-destructive technical screen for peak/RMS level and long silence; these flags identify files needing review, not musical genre or instrument presence. A technical pass never means a song is accepted as a kick reference.

Rights remain a separate gate: SoundSafari's repository-level CC0 statement is recorded as discovery evidence, but `license_verified_per_track` remains false until original track provenance is checked. No candidate may enter supervised training on this basis alone.

Additional source leads screened for the next ingestion pass:
- Sound Atlas Stems (Hugging Face `kvnloo/sound-atlas-stems`): 2,740 stem-layer rows; dataset card describes source tracks as CC0 or CC BY and points to a per-track `CREDITS.md`. It includes separated drums and bass layers, useful for paired mixture/stem work, but the drum layer is not kick-isolated. Preserve artist credit for CC BY and verify each original track's credit/license before use.
- MTG-Jamendo: 55k+ full tracks with genre/instrument tags and individual Creative Commons audio licenses, but the dataset page restricts use to non-commercial research/academic use unless Jamendo grants written authorization. Therefore it is not treated as commercial-training-cleared material.
- MUSDB18: useful mix/drums/bass stem benchmark, but it has academic-use and non-commercial restrictions in its component sources; excluded from commercial-training data absent separate permission.

The ingestion policy is now explicit: source discovery -> per-track rights/provenance -> file integrity/duration/technical screen -> actual genre and instrument review -> event annotation. These are independent gates and cannot be collapsed into a single "CC0" label.


## Sound Atlas stem-source discovery (2026-11-18)

Added a metadata-only ingestion path for Hugging Face `kvnloo/sound-atlas-stems`. It reads the source stem index and full `CREDITS.md`, then identifies original track IDs that have both drum and bass layers. It records duration, layer file names and active fractions for prioritizing later downloads. It does not download the 2.61 GB collection in CI.

The dataset card reports 2,740 instrument-layer rows, not 2,740 unique songs. Its original tracks are described as CC0 or CC BY, but the source credit/license must be resolved for each track ID. All discovered rows therefore remain `license_verified_per_track=false`. The drum stem is Demucs-separated drums, not an isolated kick; it is useful for candidate mixes and bass-confusion listening, not direct kick ground truth. This discovery pass writes an auditable report and is not itself a training dataset.


## Song-level three-way model split (2026-11-18)

The independent three-class trainer now separates original songs into train, validation and untouched test partitions before any model fitting. The split is group-based by original track ID, requires every class (kick, bass guitar, 808) in all three partitions, and requires at least three distinct source tracks per class. Validation is used for epoch monitoring; the test partition is evaluated once after training and is never used for model selection. Checkpoints and JSON reports preserve all three track lists plus separate validation and untouched-test confusion matrices and per-class precision/recall/F1. This remains blocked until enough accepted, rights-verified event annotations exist.
