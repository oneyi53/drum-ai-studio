# Engine validation runbook

The engine-validation workflow is intentionally separate from the lightweight web/API CI because Demucs downloads model weights and the PyTorch CPU wheels are large.

## Run it

1. Open the repository's [Actions tab](https://github.com/oneyi53/drum-ai-studio/actions).
2. Select **DrumScript engine validation**.
3. If no run is already queued or running, choose **Run workflow** on the `main` branch.

The workflow performs these checks in order:

1. Creates a clean Python 3.12 environment on Ubuntu.
2. Installs FFmpeg.
3. Installs CPU PyTorch 2.8.0 and the current DrumScript source from its public GitHub repository.
4. Checks the Python import and CLI help.
5. Runs DrumScript's upstream non-slow pytest suite.
6. Generates a deterministic, copyright-free synthetic full mix and calls `drumscript.transcribe(..., full_song=True, midi_only=True)`.
7. Verifies that a non-empty MIDI file was produced.

## Interpret results carefully

- **Install/import/CLI passed:** dependency and package startup are compatible in that runner environment.
- **Upstream tests passed:** the selected upstream test suite passed; this does not prove transcription accuracy.
- **Synthetic full-mix smoke passed:** Demucs separation plus DrumScript's full-song path completed for the generated test signal and produced a MIDI file.
- **Real-song accuracy:** still unverified. It requires permission-cleared real recordings and human review of instrument labels, timing, tempo, and exports.

The workflow logs print the exact DrumScript Git commit SHA used in the run. Record that SHA with any reported result. A later upstream `main` revision may behave differently.
