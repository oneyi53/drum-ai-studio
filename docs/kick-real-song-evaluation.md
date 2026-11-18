# Real-song kick evaluation

## Why this is a separate evaluation tier

IDMT-SMT-DRUMS-V2 is useful for annotated drum-hit checks, but its 40-file CI subset is made from isolated/loop-based drum recordings and is not a representative full-song corpus. Its labels do not include independent bass-guitar or bass-synth events. Do not treat the IDMT benchmark as proof that kick detection works in complete mixes.

## Openly licensed real-song sources

### OnAir Music Dataset V4 — stem-backed reference candidates

- Repository and source: https://github.com/sevagh/OnAir-Music-Dataset
- Dataset licence: CC BY-SA 4.0. Preserve attribution and share-alike obligations; do not redistribute audio outside the licence terms.
- V4 lists 11 tracks: Autumn in NY, Bouncin Around, Ramen Rain, Vibin Vibin, Yaku, Action, Ronin, Set Me Free, Under My Skin, Aurora Borealis, and Reflections.
- The source `onair-py/onair/config.py` provides the actual per-track stem map. It confirms only **two** tracks with dedicated `Kick.wav` and separate `Bass.wav`: **Under My Skin** and **Set Me Free**. These are the only automatic kick-reference candidates.
- **Ronin** has grouped Drums plus a separate 808 stem; **Yaku**, **Ramen Rain**, and **Bouncin Around** have grouped drum/percussion stems plus separate bass stems. They are valuable bass-confusion listening cases, but are not kick-only ground truth.
- **Autumn in NY** is omitted from the loader due to stem length mismatch. **Vibin Vibin** is commented out in the loader. **Action**, **Aurora Borealis**, and **Reflections** are omitted because bass/drums are not provided separately.

The CI preparation script downloads the V4 archives, records local paths and SHA-256 hashes, and generates onset proposals from the two isolated kick stems. These are explicitly marked `needs_human_review`; they are not accepted ground truth until a reviewer approves each onset. This prevents automated onset detection from being presented as human annotation.

### Kaino CC0 Music Library — full-mix pressure tests

- Library: https://kaino.dev/library/music
- 492 instrumental tracks across 57 genres; CC0 1.0. The site provides MP3/WAV downloads and states that commercial use is allowed without attribution.
- The pipeline queries the public Kaino Library MCP tools and selects tracks from acoustic folk, Afrobeat, hip hop, jazz, ambient/electronic, and cinematic/orchestral searches. Selected WAVs are recorded with source IDs and SHA-256 hashes.
- Kaino tracks have no kick-onset ground truth. They are full-mix robustness/smoke tests only; no precision/recall/F1 is reported until independent human annotations exist.

## Automated pipeline and annotation protocol

1. `scripts/prepare_real_song_kick_corpus.py` downloads OnAir V4, inspects per-track stem availability, writes the manifest, and proposes kick onsets from dedicated Kick stems.
2. `scripts/download_kaino_cc0_music.py` resolves public Kaino MCP search results into WAV downloads and writes a licence/checksum manifest.
3. `scripts/score_real_song_kick.py` runs the STAR frame CNN and DrumScript LFER 0.10 / 0.32 against the **same raw full-mix file**, with no Demucs/EQ on any arm. It exports prediction timestamps for every track.
4. For OnAir kick-reference candidates, provisional matches are calculated at 50 ms only to help review. The JSON explicitly marks them `PROVISIONAL_NOT_FOR_ACCEPTANCE` until the CSV rows are manually changed to `approved`.
5. For Kaino and grouped-drum OnAir tracks, report prediction counts/timestamps only. Do not fabricate labels or accuracy metrics.
6. Human reviewers must inspect each isolated kick stem and its full mix, approve/remove/add kick timestamps, and annotate false-positive causes separately: bass guitar, bass synth/808, snare/hat, other percussion, or unknown. Low-frequency energy alone is not evidence of a bass instrument.
7. Keep audio out of Git. Preserve source URL, title, licence, source ID where available, download date, checksum, sample rate, duration, and annotation provenance in benchmark artifacts.

## Acceptance gate

No production threshold/model change based only on IDMT or provisional stem-onset F1. Require human-approved kick references on real songs, identical pipeline conditions, per-track metrics, and verified bass/bass-synth false-positive review. The STAR reference model is AGPL-3.0 and remains evaluation-only unless a separate deployment licence review or independently trained replacement is completed.
