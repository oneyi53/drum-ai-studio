from __future__ import annotations

import os
import tempfile
from xml.etree import ElementTree as ET
from pathlib import Path
import sys

from fastapi.testclient import TestClient
from pypdf import PdfReader
import pypdfium2 as pdfium

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from engine_smoke import make_synthetic_full_mix  # noqa: E402

with tempfile.TemporaryDirectory(prefix="drumai-api-e2e-") as data_dir:
    os.environ["DRUMAI_DATA_DIR"] = data_dir
    from app.main import app  # noqa: E402

    audio_path = Path(data_dir) / "synthetic_full_mix.wav"
    make_synthetic_full_mix(audio_path)

    with TestClient(app) as client:
        with audio_path.open("rb") as audio_file:
            uploaded = client.post(
                "/api/projects",
                files={"audio": ("synthetic_full_mix.wav", audio_file, "audio/wav")},
            )
        if uploaded.status_code != 201:
            raise RuntimeError(f"API upload failed: {uploaded.status_code} {uploaded.text}")
        project_id = uploaded.json()["id"]

        started = client.post(f"/api/projects/{project_id}/analyze")
        if started.status_code != 202:
            raise RuntimeError(f"API job creation failed: {started.status_code} {started.text}")
        job_id = started.json()["job_id"]

        job = client.get(f"/api/analysis-jobs/{job_id}")
        job_data = job.json()
        if job.status_code != 200 or job_data.get("status") != "completed":
            raise RuntimeError(f"API engine job did not complete: {job_data}")

        result = client.get(f"/api/projects/{project_id}/performance")
        if result.status_code != 200:
            raise RuntimeError(f"Canonical result fetch failed: {result.status_code} {result.text}")
        performance = result.json()["performance"]
        events = performance.get("events", [])
        if not events:
            raise RuntimeError("API completed but returned no canonical drum events")

        midi = client.get(f"/api/projects/{project_id}/midi")
        if midi.status_code != 200 or not midi.content:
            raise RuntimeError("API did not return a non-empty generated MIDI download")

        musicxml = client.get(f"/api/projects/{project_id}/musicxml")
        if musicxml.status_code != 200 or not musicxml.content:
            raise RuntimeError(
                f"API MusicXML export failed: {musicxml.status_code} {musicxml.text}"
            )
        score = ET.fromstring(musicxml.content)
        if score.tag != "score-partwise" or not score.findall(".//note"):
            raise RuntimeError("MusicXML export did not contain a populated partwise drum score")

        pdf = client.get(f"/api/projects/{project_id}/pdf")
        if pdf.status_code != 200 or not pdf.content.startswith(b"%PDF"):
            raise RuntimeError(f"API PDF export failed: {pdf.status_code} {pdf.text}")
        pdf_reader = PdfReader(__import__("io").BytesIO(pdf.content))
        if not pdf_reader.pages:
            raise RuntimeError("PDF export contains no pages")
        for page in pdf_reader.pages:
            if (
                abs(float(page.mediabox.width) - 841.89) >= 1.0
                or abs(float(page.mediabox.height) - 595.28) >= 1.0
            ):
                raise RuntimeError("PDF export page is not landscape A4")
        output_dir = Path(os.getenv("DRUMAI_E2E_OUTPUT_DIR", data_dir))
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / "drumai-api-e2e-score.pdf"
        pdf_path.write_bytes(pdf.content)

        # Render the first page in-process so visual smoke does not depend on
        # Poppler/system package mirrors in the GitHub runner.
        pdf_document = pdfium.PdfDocument(pdf.content)
        try:
            pdf_page = pdf_document[0]
            bitmap = pdf_page.render(scale=120 / 72)
            rendered_image = bitmap.to_pil()
            png_path = output_dir / "drumai-score-page-1.png"
            rendered_image.save(png_path, format="PNG")
            # Keep the footer/engraver mark out of the measurement: the score
            # itself must occupy a meaningful vertical area on landscape A4.
            grayscale = rendered_image.convert("L")
            score_region = grayscale.crop((0, 0, grayscale.width, int(grayscale.height * 0.80)))
            ink_mask = score_region.point(lambda pixel: 255 if pixel < 210 else 0)
            score_bounds = ink_mask.getbbox()
            if score_bounds is None:
                raise RuntimeError("PDF visual check found no score notation")
            score_height_ratio = (score_bounds[3] - score_bounds[1]) / rendered_image.height
            if score_height_ratio < 0.15:
                raise RuntimeError(
                    "PDF score notation is too vertically compressed: "
                    f"ink height is {score_height_ratio:.1%} of the page; expected at least 15%"
                )
            score_width_ratio = (score_bounds[2] - score_bounds[0]) / rendered_image.width
            if score_width_ratio < 0.72:
                raise RuntimeError(
                    "PDF score notation is too horizontally compressed: "
                    f"ink width is {score_width_ratio:.1%} of the page; expected at least 72%"
                )
            if not png_path.is_file() or png_path.stat().st_size < 1024:
                raise RuntimeError("PDF rasterization produced an empty or implausibly small PNG")
            if png_path.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise RuntimeError("PDF rasterization output is not a valid PNG")
        finally:
            pdf_document.close()

        print(
            "API_ENGINE_E2E_OK "
            f"job_id={job_id} events={len(events)} "
            f"duration_seconds={performance['duration_seconds']:.3f} "
            f"midi_bytes={len(midi.content)} musicxml_bytes={len(musicxml.content)} "
            f"pdf_bytes={len(pdf.content)} pdf_pages={len(pdf_reader.pages)} "
            f"pdf_path={pdf_path} png_path={png_path} png_bytes={png_path.stat().st_size}"
        )
