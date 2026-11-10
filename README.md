# DrumAI Studio

A web-based workspace for turning a full mixed song into an editable drum transcription.

> **Status: P0 scaffold.** Upload/project plumbing and the UI foundation are being established. Automatic drum separation, event detection, notation editing, and exports are not yet integrated or validated.

## Product direction

1. Import a complete mixed audio file.
2. Separate the drum stem.
3. Detect drum events (kick, snare, hi-hat, cymbals, and toms).
4. Review and correct events in an editable drum-grid/notation editor.
5. Export PDF, MIDI, and MusicXML from one canonical event model.

## Architecture

- **Frontend:** React + TypeScript + Vite
- **Backend:** FastAPI
- **Initial persistence:** local filesystem + SQLite (project metadata)
- **Audio/transcription engine:** planned evaluation of DrumScript + Demucs
- **Notation display:** OpenSheetMusicDisplay (MusicXML rendering); a dedicated editor will be built separately

## Upstream audit and licensing

See [docs/P0_AUDIT.md](docs/P0_AUDIT.md) before adding or redistributing upstream code or model weights.

- [DrumScript](https://github.com/DrumScript/DrumScript) is Apache-2.0 according to its upstream license file. Its README describes an alpha-stage, rule-based drum classification workflow with optional Demucs-based drum-stem extraction. It is a candidate integration, not yet installed or tested in this repository.
- [Demucs](https://github.com/facebookresearch/demucs) is MIT-licensed according to its upstream license file. Model weights and third-party assets still require separate license review.
- [akaihola/drum-transcribe](https://github.com/akaihola/drum-transcribe) is currently treated as architecture reference only: no root LICENSE was found during the initial audit, and its README describes it as a prototype not intended for production use. Do not copy or redistribute its source unless licensing is clarified.

No upstream source code or model weights are bundled in this scaffold.

## Requirements

- Python **3.12** for the planned DrumScript compatibility range (DrumScript declares Python >=3.9,<3.13).
- Node.js 20+ and npm for the frontend.
- FFmpeg is recommended for local audio inspection/conversion.
- The current execution environment previously detected Python 3.13.5, which is outside DrumScript's declared range. A Python 3.12 environment is required before validating that integration.

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
- The analysis endpoint deliberately returns HTTP 501 until a transcription engine is integrated and validated.
- No automatic transcription accuracy is claimed.
- Local uploads are not yet authenticated or suitable for public multi-user deployment.
- Do not upload copyrighted recordings unless you have the right to do so.

## Project documents

- [P0 audit](docs/P0_AUDIT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Engine validation runbook](docs/ENGINE_VALIDATION.md)
- [Real-audio evaluation protocol](docs/REAL_AUDIO_EVALUATION.md)
