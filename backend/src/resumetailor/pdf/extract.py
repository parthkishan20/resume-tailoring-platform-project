"""Reading text out of an uploaded PDF, with limits on how much of it there is."""

from __future__ import annotations

from resumetailor.core.errors import PDFExtractError

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50


class PyMuPDFAdapter:
    """Extracts plain text from a PDF, page by page."""

    _MAX_BYTES = MAX_BYTES
    _MAX_PAGES = MAX_PAGES

    async def extract(self, pdf_bytes: bytes) -> str:
        if len(pdf_bytes) > MAX_BYTES:
            msg = f"PDF exceeds 10 MB limit ({len(pdf_bytes) / 1_048_576:.1f} MB)"
            raise PDFExtractError(msg)
        try:
            import pymupdf  # lazy: pymupdf is slow to import

            # PyMuPDF ships partial stubs: `Document.__init__`, `.close()` and
            # iteration are all untyped or missing, though every one of them
            # works at runtime. The ignores are pinned to those three codes so
            # a real type error here still fails the build.
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")  # type: ignore[no-untyped-call]
        # Blind on purpose: PyMuPDF raises whatever MuPDF raised, and every one
        # of them means the same thing to the caller — this is not a PDF.
        except Exception as exc:
            msg = f"Cannot open PDF: {exc}"
            raise PDFExtractError(msg) from exc
        if doc.page_count > MAX_PAGES:
            doc.close()  # type: ignore[no-untyped-call]
            msg = f"PDF has {doc.page_count} pages (max {MAX_PAGES})"
            raise PDFExtractError(msg)
        pages = [page.get_text() for page in doc]  # type: ignore[attr-defined]
        doc.close()  # type: ignore[no-untyped-call]
        return "\n\n".join(pages)
