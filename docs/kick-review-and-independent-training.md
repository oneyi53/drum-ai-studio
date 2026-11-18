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
