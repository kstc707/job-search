"""Upload a resume PDF to the presigned URL returned by `request-resume-upload`.

The bytes go straight to storage, never through the agent's context. Tsenta only
validates size and format later, at `check-custom-resume`, so check them here first.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024  # Tsenta's limit for custom resumes


def validate_pdf(data: bytes, max_bytes: int = MAX_BYTES) -> None:
    if not data.startswith(b"%PDF-"):
        raise ValueError("not a PDF (missing %PDF- header)")
    if len(data) > max_bytes:
        raise ValueError(f"PDF is {len(data)} bytes; limit is {max_bytes}")
    if b"%%EOF" not in data[-1024:]:
        raise ValueError("PDF looks truncated (no %%EOF trailer)")


def put_pdf(upload_url: str, pdf_path: str | Path, timeout: float = 60) -> int:
    """PUT the PDF with the content type the URL was signed for. Returns HTTP status."""
    data = Path(pdf_path).read_bytes()
    validate_pdf(data)
    req = urllib.request.Request(
        upload_url, data=data, method="PUT", headers={"Content-Type": "application/pdf"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status
