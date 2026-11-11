# Asynchronous analysis API

## Flow

1. Upload audio with `POST /api/projects`.
2. Start analysis with `POST /api/projects/{project_id}/analyze`. The response contains a job ID and HTTP 202.
3. Poll `GET /api/analysis-jobs/{job_id}` until status is `completed` or `failed`.
4. Fetch the canonical result with `GET /api/projects/{project_id}/performance`.
5. Stream the original uploaded audio with `GET /api/projects/{project_id}/audio`; the endpoint supports browser media playback and byte-range seeking through FastAPI's file response.

Job statuses: `queued`, `running`, `completed`, `failed`. A project moves through
`uploaded`, `queued`, `processing`, `analyzed`, or `failed`.

## Engine runtime

The API lazily imports DrumScript inside the analysis worker. The regular backend
install intentionally does not pull the large PyTorch runtime. The worker image
must include:

- Python 3.12 and the backend package (`pip install -e ./backend`)
- CPU-compatible PyTorch and torchaudio versions supported by the pinned
  DrumScript revision
- DrumScript installed from its upstream repository
- FFmpeg/ffprobe on PATH

The engine adapter runs full-song transcription in an isolated temporary
workspace, requires a non-empty exported MIDI, normalizes GM percussion channel
10 into canonical drum events, and stores both the MIDI and canonical JSON
under the configured data directory.

Set `DRUMAI_DATA_DIR` to a persistent writable volume. Do not expose the data
directory as a public static directory. SQLite and FastAPI in-process background
tasks are suitable for a single-worker development deployment, not a
multi-replica production queue. On API restart, interrupted queued/running jobs
are marked failed rather than remaining stuck. Before horizontal scaling,
replace BackgroundTasks with a durable worker queue and shared database/object
storage.

## API contract

### Start

```http
POST /api/projects/{project_id}/analyze
```

Returns `202 Accepted`:

```json
{"job_id":"...","project_id":"...","status":"queued"}
```

### Poll

```http
GET /api/analysis-jobs/{job_id}
```

### Result

```http
GET /api/projects/{project_id}/performance
```

The result contains the canonical `DrumPerformance` JSON and generated MIDI
filename. Download the MIDI artifact with `GET /api/projects/{project_id}/midi`.
Event create/update/delete operations are persisted as revisions. The editor exposes
persistent undo/redo through `POST /api/projects/{project_id}/undo` and
`POST /api/projects/{project_id}/redo`; query
`GET /api/projects/{project_id}/history` for the current revision and
`can_undo`/`can_redo` flags. Undo/redo restore canonical JSON and regenerate
the MIDI artifact in the same database transaction. A new edit after undo
discards the redo branch.

## Failure modes

- Engine package absent: job fails with an actionable runtime installation message.
- FFmpeg/ffprobe absent: job fails before inference.
- Missing or empty MIDI, or no channel-10 percussion events: job fails closed.
- Duplicate active job for a project: HTTP 409.
- Unknown project/job: HTTP 404.


### Original audio playback

`GET /api/projects/{project_id}/audio` streams the project's original upload
using its server-generated storage filename and the original media type. The
route resolves the stored path under the upload directory and returns 404 for
unknown projects or missing artifacts. The frontend uses the browser audio
element for playback, seeking, and timeline playhead synchronization; selecting
a drum event seeks the player to that event's absolute timestamp.
