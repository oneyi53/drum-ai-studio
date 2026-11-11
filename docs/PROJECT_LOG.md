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
- Added browser E2E coverage for MusicXML download, XML parsing, simultaneous kick/snare chord notation, channel 10, instrument pitch mapping, rests, a fifth measure, and note element order. The test saves the exact browser-generated artifact for a separate CI schema-validation step.
- Corrected MusicXML note child ordering so duration precedes the instrument reference.
- MusicXML currently uses one fixed BPM and 4/4 time. It does not encode a tempo map, swing, tuplets, expressive microtiming, or the source event's velocity. Original onset seconds and velocity remain in the project's event records; CSV reference export remains available.
- The staff preview is intentionally a lightweight visual check, not a substitute for a dedicated notation engine or engraving review.

## Validation evidence

Latest previously confirmed baseline before the current MusicXML changes:
- Commit: `602f4d9fc69f8f7febef60a169da73ee6d7696f9`
- GitHub Actions run: [42846309942](https://github.com/oneyi53/drum-ai-studio/actions/runs/42846309942)
- Result: completed successfully; backend, frontend build, evaluation, and Playwright browser E2E jobs passed.

Latest MusicXML conformance-hardening changes:
- Code commits: `28ab3f246ad8fd0df8af01c1fd329a3ba41a381c` (MusicXML note order) and `d92825506d5cb84e6b0319e918a39a77c0e0e0f9` (browser E2E coverage); documentation was updated afterward.
- Changes include the MusicXML note child-order correction and browser E2E parsing of downloaded XML with simultaneous kick/snare notes, chord marker, GM pitches, MIDI channel 10, and tempo checks.
- The prior green run does not cover these newer changes. No Actions run or local Playwright execution has yet been confirmed for this exact head; validation is pending.
- The browser XML parser check covers well-formedness and selected structural invariants. CI also validates the saved browser-generated artifact with lxml against the official W3C MusicXML 4.0 XSD and imported XML/XLink schemas. The first run exposed a Playwright download-event await bug, which was fixed. The next run passed browser E2E and the schema step failed because W3C listing-page URLs returned HTML. The workflow was corrected to download the exact v4.0 schema files from the official `w3c-cg/musicxml` GitHub repository, pinned to tag `v4.0`. CI run [42934628583](https://github.com/oneyi53/drum-ai-studio/actions/runs/42934628583) then passed all four jobs; its browser E2E job explicitly printed `MusicXML 4.0 XSD validation passed: frontend/test-results/drumai-transcription.musicxml`. This establishes schema validity for the exact artifact generated by that browser test, but does not replace opening the file in a notation application.


- Latest CI run for head `e59dad0f3abd8494e428e57b3d220184555a4173`: [42857592824](https://github.com/oneyi53/drum-ai-studio/actions/runs/42857592824) failed in browser E2E after project reopen. The assertion expected the transient “已连接项目服务器；已载入 2 条参考标注” message, but the app immediately replaces it with the subsequent “已保存到项目服务器” status. Backend tests, frontend build, and evaluation tests passed; the MusicXML XSD step was skipped because E2E failed. The test is being corrected to assert the durable restored event count and values instead of a transient status string. XSD conformance remains unverified.

## Next engineering gates

1. Validate the expanded all-instrument, rest, and fifth-measure MusicXML fixture in CI; then open the generated file in a notation application and inspect rendered notation for all nine supported drum instruments.
3. Decide and document how tempo maps, swing/tuplets, and velocity should be represented before promising faithful score/MIDI round trips.
4. Add a rights-cleared, independently human-annotated evaluation set before reporting transcription metrics or enabling the analysis API.
5. Review upload security, authentication, quotas, cleanup, and deployment configuration before any public multi-user deployment.

## Change record

| Date | Change |
|---|---|
| 2026-11-10 | Added initial MusicXML export, simplified percussion staff preview, browser E2E coverage, and project documentation. |
| 2026-11-11 | Corrected MusicXML note element order and expanded browser checks to parse the downloaded XML and cover simultaneous kick/snare events on MIDI channel 10. Added official W3C MusicXML 4.0 XSD validation. Browser E2E passed, but validation exposed that W3C listing URLs returned HTML; CI now downloads schemas from the official GitHub `v4.0` release tag. Awaiting rerun. |

- CI run [42859921687](https://github.com/oneyi53/drum-ai-studio/actions/runs/42859921687): browser E2E passed (1 test), as did backend, frontend build, and evaluation. The XSD step failed before validating the generated XML because the W3C listing URLs without trailing slashes returned HTML rather than raw schema XML; lxml reported a mismatched HTML `link` tag. The schema download URLs were corrected to the W3C listing file endpoints with trailing slashes. This run does **not** establish MusicXML schema conformance.

- CI run [42863319135](https://github.com/oneyi53/drum-ai-studio/actions/runs/42863319135) on the previous head: backend, frontend build, evaluator tests, and browser E2E all passed. The XSD step failed while parsing the downloaded `musicxml.xsd` because the W3C listing endpoint returned an HTML document (`Opening and ending tag mismatch: link ... head`); the MusicXML artifact itself was not evaluated. Corrected the download source to the official GitHub `w3c-cg/musicxml` tag `v4.0` in commit `6027d6fb797adc09a5c46a2522f676641bc03d0f`. Conformance remains unverified pending CI.

- CI run [42934628583](https://github.com/oneyi53/drum-ai-studio/actions/runs/42934628583): all four jobs passed (backend, frontend, evaluation, browser E2E). The browser E2E test passed, and the exact downloaded browser artifact passed official MusicXML 4.0 XSD validation. The schema step output was `MusicXML 4.0 XSD validation passed: frontend/test-results/drumai-transcription.musicxml`. This verifies XSD conformance of the tested export fixture, not visual engraving in a notation application or all possible event combinations.

- Expanded the Playwright MusicXML fixture to include all nine supported instruments, simultaneous kick/snare hits, rests, and an event at 8.25 seconds (measure five). The previous 16.25-second timestamp was actually in measure nine at 120 BPM; corrected the fixture rather than weakening the five-measure assertion. Added assertions for all nine GM percussion pitches, ten drum events, rests, and five measures. CI run [42946423501](https://github.com/oneyi53/drum-ai-studio/actions/runs/42946423501) passed all four jobs. Browser E2E passed and the generated five-measure MusicXML artifact passed the official MusicXML 4.0 XSD validation step.

- CI run [42946423501](https://github.com/oneyi53/drum-ai-studio/actions/runs/42946423501), head `1a5df69b20662d812aaeeaab4354c2c7ca39ccbc`: frontend build, backend tests, MIDI evaluation tests, browser E2E, and official MusicXML 4.0 XSD validation all passed. The expanded fixture covers nine GM drum pitches, ten events, simultaneous kick/snare, rests, and five measures. This does not establish visual engraving compatibility in a notation application or transcription accuracy on real audio.


- 2026-11-11: Added an independent notation-application import/render gate after the MusicXML 4.0 XSD check. CI installs Ubuntu's MuseScore 3 package, imports the exact browser-generated five-measure fixture, renders a PDF in a virtual display, and checks that the PDF has at least one page. This tests MuseScore 3 import and pagination only; it does not claim visual correctness or MuseScore 4 compatibility. The workflow change is commit 79abd2ac9e3ce6a0c4b5f5531b9529a4fc547f07; its CI result is pending.

- 2026-11-11: Diagnosed the first MuseScore CI failures from job logs: the version probe launched Qt without a display and aborted before attempting MusicXML import. Moved both the version probe and PDF render under `xvfb-run`; browser E2E and MusicXML XSD validation had passed in those runs. Fix commit: 2faf0d405beef2dea64cae5e3f54a2b4e8274910. MuseScore render result is pending.
- 2026-11-11: Added a seven-day GitHub Actions artifact for the MuseScore-rendered PDF so the exact CI output can be visually reviewed after a successful import/render. Workflow commit: 90a665bbefb871ed3ad2c37c3b059f8ff6077603. Awaiting the updated run before claiming MuseScore compatibility.
