# Real-song kick evaluation plan

## Why this is a separate evaluation tier

IDMT-SMT-DRUMS-V2 is useful for annotated drum-hit checks, but its 40-file CI subset is made from isolated/loop-based drum recordings and is not a representative full-song corpus. Its labels do not include independent bass-guitar or bass-synth events. Do not treat the IDMT benchmark as proof that kick detection works in complete commercial-style mixes.

## Openly licensed real-song sources

### OnAir Music Dataset (primary stem-backed real-song source)

- Repository: https://github.com/sevagh/OnAir-Music-Dataset
- Licence stated by the dataset: Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0).
- The V4 public release lists 11 royalty-free songs: Autumn in NY, Bouncin Around, Ramen Rain, Vibin Vibin, Yaku, Action, Ronin, Set Me Free, Under My Skin, Aurora Borealis, and Reflections.
- Each released song folder contains a full mix and its component stems.
- The related `onair-py` loader documents that custom source stems are mapped into broad MUSDB targets and that not every song maps cleanly; some songs do not provide bass and kick separately.

Use this source to compare the full mix with the available isolated stems and inspect kick/bass interference. A broad `drums` stem is not a kick-only ground truth. Only calculate kick precision/recall for a track when a genuine kick-only stem or a manually reviewed kick-onset annotation is available. Keep attribution and share-alike obligations with any redistributed derivative; do not copy the audio into the application repository by default.

### Kaino CC0 Music Library (full-mix realism / application smoke tests)

- Library: https://kaino.dev/library/music
- The library currently lists 492 instrumental tracks and states CC0 1.0; its page offers MP3 and lossless WAV downloads and permits commercial use without attribution.
- Use varied genres and arrangements as realistic complete-song inputs for end-to-end transcription, robustness checks, and listening review.
- These tracks do not ship kick-onset ground truth. They must not be included in precision/recall aggregates until kick events have been independently annotated and reviewed.

## Evaluation protocol

1. Pin each downloaded track to its source URL, title, creator, licence, download date, file checksum, sample rate, and duration in a manifest. Do not commit copyrighted audio or large audio files to Git.
2. Keep source audio immutable. Run DrumScript production processing and any candidate classifier on the exact same full-mix file. Record the pipeline mode (raw mix vs Demucs+EQ) explicitly; never compare results from different paths as if they were identical.
3. For stem-backed songs, listen to and inspect the isolated drum and bass stems. Use the drum stem to locate candidate kick events, then manually verify each onset against the mix and waveform. If kick is inseparable from bass in the source, mark the track as unsuitable for kick-only scoring rather than inventing labels.
4. For CC0 full mixes, create a human-reviewed onset CSV with at least `track_id,time_seconds,label,reviewer,notes`. Annotate kick, snare, hi-hat, bass-only low-frequency transients, and ambiguous events separately. Have a second review pass for ambiguous events.
5. Score with a fixed tolerance (initially 50 ms) and report per-track TP/FP/FN, precision, recall, F1, plus false-positive timestamps. Break down false positives by verified bass/bass-synth, snare/hat, other percussion, and unknown. Never infer bass/synth labels from low frequency alone.
6. Publish the manifest and annotation provenance with the benchmark artifacts. Do not distribute source audio unless the source licence and attribution requirements explicitly allow it.

## Acceptance gate

No production threshold/model change based only on IDMT or aggregate F1. Require a reviewed real-song set with varied genres, genuine kick references, and a dedicated bass-confusion review. Keep the AGPL-3.0 STAR reference model evaluation-only unless a separate deployment licence review or independently trained replacement is completed.
