# Project development log

This log records implemented work and evidence. A passing CI run demonstrates the checks listed in that run; it does not establish transcription accuracy or production readiness.

## Current status

- Active development branch: `feat/real-audio-evaluation-harness`
- Pull request: [#1](https://github.com/oneyi53/drum-ai-studio/pull/1) (Draft; not merged)
- Automatic transcription API: still intentionally disabled (HTTP 501).
- Human annotation, project persistence, drum-grid editing, velocity persistence, MusicXML export, and selected browser E2E coverage are implemented on the feature branch.
- No human-annotated benchmark has been completed; no precision, recall, or F1 accuracy claim is made.

## Delivered milestones

### Project and reference annotation foundation

- Upload original audio into a project and retain project metadata in SQLite.
- List projects and reopen the original audio.
- Create, edit, import, export, and persist human-confirmed drum reference events.
- Persist onset, instrument, and velocity per project; retain browser-local storage as a fallback for unassociated local audio.
- Keep model predictions separate from manually confirmed reference events.

### Evaluation harness and engine checks

- Added a MIDI-vs-reference CSV evaluator with one-to-one onset matching, instrument matching, per-instrument metrics, and configurable tolerance.
- Added a protocol describing rights-cleared data, independent human annotations, and metric interpretation.
- Added CI checks for the evaluator and a dedicated real-audio validation workflow using the two audio files already present on the repository's main branch.
- The repository-audio workflow produces model predictions and structural diagnostics only. Predictions are not ground truth.
- Upstream DrumScript pipeline smoke validation has passed in its Python 3.12 workflow; this proves that the tested pipeline can execute and emit MIDI, not that its output is accurate.

### Editing and export milestone

- Added a 4-bar, 4/4, 16th-note drum grid with adjustable fixed BPM and per-event velocity editing.
- Added a simplified five-line percussion-staff preview derived from the same event list.
- Added downloadable MusicXML 4.0 partwise output with percussion clef, a drum-set part, GM percussion pitch mapping, tempo marking, and events quantized to the nearest sixteenth note.
- Added browser E2E coverage for MusicXML download, XML parsing, simultaneous kick/snare chord notation, channel 10, instrument pitch mapping, and note element order.
- Corrected MusicXML note child ordering so duration precedes the instrument reference.
- MusicXML currently uses one fixed BPM and 4/4 time. It does not encode a tempo map, swing, tuplets, expressive microtiming, or the source event's velocity. Original onset seconds and velocity remain in the project's event records; CSV reference export remains available.
- The staff preview is intentionally a lightweight visual check, not a substitute for a dedicated notation engine or engraving review.

## Validation evidence

Latest previously confirmed baseline before the current MusicXML changes:
- Commit: `602f4d9fc69f8f7febef60a169da73ee6d7696f9`
- GitHub Actions run: [42846309942](https://github.com/oneyi53/drum-ai-studio/actions/runs/42846309942)
- Result: completed successfully; backend, frontend build, evaluation, and Playwright browser E2E jobs passed.

Latest MusicXML conformance-hardening changes:
- Current branch head: `3529b34440493ef4e627fb31a430bbf9287a04b4`
- Changes include the MusicXML note child-order correction and browser E2E parsing of downloaded XML with simultaneous kick/snare notes, chord marker, GM pitches, MIDI channel 10, and tempo checks.
- The prior green run does not cover these newer changes. No Actions run or local Playwright execution has yet been confirmed for this exact head; validation is pending.
- Browser XML parsing checks well-formedness and selected structural invariants only. It is not a complete MusicXML 4.0 DTD/XSD validation and does not replace opening the file in a notation application.

## Next engineering gates

1. Obtain a CI run for the current head and inspect every job, including the stricter MusicXML browser parsing assertion.
2. Validate the generated MusicXML with an independent MusicXML parser/notation application, then inspect rendered notation for all nine supported drum instruments.
3. Decide and document how tempo maps, swing/tuplets, and velocity should be represented before promising faithful score/MIDI round trips.
4. Add a rights-cleared, independently human-annotated evaluation set before reporting transcription metrics or enabling the analysis API.
5. Review upload security, authentication, quotas, cleanup, and deployment configuration before any public multi-user deployment.

## Change record

| Date | Change |
|---|---|
| 2026-11-10 | Added initial MusicXML export, simplified percussion staff preview, browser E2E coverage, and project documentation. |
| 2026-11-11 | Corrected MusicXML note element order and expanded browser checks to parse the downloaded XML and cover simultaneous kick/snare events on MIDI channel 10. CI validation pending. |
