from pathlib import Path

SCRIPT = Path(__file__).with_name("prepare_real_song_kick_corpus.py")


def test_onair_zip_extraction_sanitizes_unsafe_paths_and_keeps_provenance():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "PurePosixPath(member.filename)" in source
    assert 'ch in \'<>:"|?*\'' in source
    assert '"source_member": member.filename' in source
    assert '"extracted_path": str(destination)' in source
    assert 'source_name.is_absolute() or ".." in source_name.parts' in source


def test_onair_zip_extraction_does_not_materialize_symlinks():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "mode == 0o120000" in source
