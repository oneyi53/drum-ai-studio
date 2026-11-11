# MIDI to canonical drum events

The adapter in `app.midi_adapter` reads Standard MIDI Files and creates a
schema-version-1.0 `DrumPerformance`.

## Supported normalization

- Reads note-on messages with velocity 1..127; note-on velocity zero and
  note-off messages are not counted as hits.
- Defaults to MIDI channel 10 (zero-based channel 9), the General MIDI
  percussion channel. Set `percussion_channel_only=False` only when an
  upstream engine is known to put percussion on another channel.
- Maps standard General MIDI percussion pitches to kick, snare, hi-hat,
  cymbal, and tom instruments. Side stick and hand clap remain `other` rather
  than being mislabeled as snare. Unmapped pitches are retained as `other`
  unless `include_unmapped_notes=False`.
- Converts MIDI ticks to absolute seconds while applying tempo meta-events.
- Preserves tempo and time-signature changes in the canonical tempo map.
- Sets event provenance to `imported`; MIDI does not provide a trustworthy
  model confidence score, so confidence remains null.

## Usage

```python
from app.midi_adapter import midi_to_performance

performance = midi_to_performance("transcription.mid")
payload = performance.model_dump_json(indent=2)
```

The adapter intentionally follows the General MIDI Level 1 Percussion Key Map.
DrumScript's published MIDI exporter documents that it writes this GM map and
uses a drum track that pretty_midi marks as percussion (MIDI channel 10). The
engine smoke job now verifies that its actual output can be normalized into
non-empty canonical events. If a future engine revision changes its output
mapping, add an explicit, versioned mapping profile rather than silently
changing the GM interpretation.

## Limitations

- MIDI note numbers are treated as General MIDI percussion keys; a MIDI file
  using a custom drum map needs an explicit mapping profile.
- Only note-on attacks are represented; note durations, articulations beyond
  the GM pitch map, and expressive flam/roll semantics are not inferred.
- This adapter normalizes MIDI structure; it does not establish transcription
  accuracy. Compare output to reviewed reference annotations with
  `evaluate_performance`.
