# MusicXML export

## Current behavior

The editor's **Export MusicXML** action downloads `drumai-transcription.musicxml` as MusicXML 4.0 partwise. The preview and exporter use the same project event list.

- One percussion part named "Drum set" with a percussion clef.
- MIDI percussion instruments are assigned to MIDI channel 10.
- A 4/4 time signature and one fixed tempo, taken from the grid BPM control.
- Nine declared drum instruments with General MIDI percussion pitch assignments:
  - kick 36; snare 38
  - closed hat 42; open hat 46
  - low tom 41; mid tom 45; high tom 48
  - crash 49; ride 51
- Simultaneous hits are emitted as chord notes.
- Empty intervals are represented by rests.
- Events are mapped to the nearest sixteenth-note tick: `round(onset_seconds * BPM / 60 * 4)`.
- The measure count grows to include the latest event.

## Important limitations

This is an initial interchange export, not a lossless representation of the source event timeline.

- A single constant BPM and 4/4 meter are assumed.
- Events are quantized to sixteenths; original sub-grid timing is not preserved in MusicXML.
- Swing, tuplets, tempo changes, time-signature changes, note duration, sticking, and expressive articulation are not represented.
- MIDI velocity is retained in the project database and annotation model but is not currently encoded in this MusicXML output.
- The SVG staff preview is a compact visual aid, not a full engraving engine. Its vertical placement is a simplified drum-set layout and should be checked against the target notation application's rendering.

The original onset seconds and velocity remain available in project reference events and the reference CSV export. Do not overwrite or discard those source values when importing/exporting MusicXML.

## Validation

The browser E2E flow exports a score containing all nine supported drum instruments, simultaneous kick and snare hits, rests, and an event in measure five. It parses the downloaded document with the browser's XML parser and checks parser errors, chord notation, channel 10, all nine GM percussion pitches, fixed tempo, staff display position, measure count, and the required duration-before-instrument note element order. The same downloaded artifact is then validated in CI against the W3C MusicXML 4.0 XSD (with its imported XML and XLink schemas resolved locally), then imported and rendered to PDF by the Ubuntu-packaged MuseScore 3 CLI in a virtual display. The render check verifies that this independent notation application can import and paginate the fixture; it does not establish that every drumhead, staff position, or articulation is visually correct, and it does not cover MuseScore 4.

Before treating the export as production-ready, manually inspect the rendered score in a current notation application (including drumhead placement and instrument mapping) and verify playback/MIDI round-trip behavior. CI's MuseScore 3 PDF render is an import-and-pagination smoke test, not a visual sign-off.
