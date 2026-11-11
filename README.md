# DrumAI Studio

A web-based workspace for turning a full mixed song into an editable drum transcription.

> **Status: P2 transcription and editing workspace in progress.** Upload, asynchronous DrumScript analysis, canonical drum-event editing, quantization, undo/redo, synchronized playback, A–B practice looping, a tempo-map metronome, MIDI, editable MusicXML, and built-in printable PDF score export are implemented on the feature branch. Real analysis still requires the optional DrumScript/PyTorch/FFmpeg runtime. A durable production queue, authenticated multi-user storage, and full in-app notation engraving remain future work.

## Product direction

1. Import a complete mixed audio file.
2. Separate the drum stem.
3. Detect drum events (kick, snare, hi-hat, cymbals, and toms).
4. Review and correct events in an editable drum-grid/notation editor.
5. Export printable PDF, editable MusicXML, and MIDI from one canonical event model.

## Architecture

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI
- **Initial persistence:** local filesystem + SQLite (projects, analysis jobs, canonical performance JSON)
- **Audio/transcription engine:** optional lazy-loaded DrumScript adapter; worker runtime and deployment validation still required
- **Canonical data:** versioned Pydantic drum-event model with tempo map
- **MIDI normalization:** Standard MIDI File to canonical events, General MIDI percussion map, tempo/time-signature preservation
- **Accuracy evaluation:** event precision/recall/F1 with configurable timing tolerance
- **Score interchange:** MusicXML 4.0 percussion score export; final engraving is delegated to notation software

## Upstream audit and licensing

See [docs/P0_AUDIT.md](docs/P0_AUDIT.md) before adding or redistributing upstream code or model weights.

- [DrumScript](https://github.com/DrumScript/DrumScript) is Apache-2.0 according to its upstream license file. Its README describes an alpha-stage, rule-based drum classification workflow with optional Demucs-based drum-stem extraction. It is a candidate integration, not yet installed and validated in the application runtime.
- [Demucs](https://github.com/facebookresearch/demucs) is MIT-licensed according to its upstream license file. Model weights and third-party assets still require separate license review.
- [akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe) is currently treated as architecture reference only: no root LICENSE was found during the initial audit, and its README describes it as a prototype not intended for production use. Do not copy or redistribute its source unless licensing is clarified.

No upstream source code or model weights are bundled in this scaffold.

## Requirements

- Python **3.12** for the planned DrumScript compatibility range (DrumScript declares Python >=3.9,<3.13).
- Node.js 20+ and npm for the frontend.
- FFmpeg is recommended for local audio inspection/conversion.

## Development

### Backend

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check: `GET http://127.0.0.1:8000/api/health`

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend expects the API at `http://127.0.0.1:8000` by default. Set `VITE_API_BASE_URL` to override it.

## Current scope and limitations

- Audio upload creates a project record and stores the original file locally.
- The analysis endpoint creates an asynchronous job; the worker fails clearly if DrumScript or FFmpeg/ffprobe is not installed.
- The event evaluator is ready for reviewed reference annotations, but no golden dataset or accuracy result is claimed.
- PDF, MusicXML, and MIDI downloads reflect the latest canonical performance. PDF is engraved in-app through the Verovio notation engine; MusicXML can be imported into notation software for detailed editing and engraving.
- Analysis jobs use FastAPI in-process background tasks and are intended for single-worker development only; use a durable queue before multi-worker or multi-replica deployment.
- Local uploads are not yet authenticated or suitable for public multi-user deployment.
- Do not upload copyrighted recordings unless you have the right to do so.

- [Test dataset acquisition and licences](docs/TEST_DATASETS.md)
## Project documents

- [P0 audit](docs/P0_AUDIT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Engine validation runbook](docs/ENGINE_VALIDATION.md)
- [Canonical event schema and evaluation](docs/DRUM_EVENT_EVALUATION.md)
- [MIDI adapter and GM mapping assumptions](docs/MIDI_ADAPTER.md)
- [Asynchronous analysis API and engine runtime](docs/ANALYSIS_API.md)
- [User guide: analysis, editing, practice, and export](docs/USER_GUIDE.md)
