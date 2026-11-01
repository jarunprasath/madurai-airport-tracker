"""Make decks display identically on every device.

Phone and messaging previewers (WhatsApp, iOS Quick Look, some Android/Drive viewers) often drop text boxes,
shape text or slide backgrounds from PowerPoint files, leaving white boxes. Pictures always display.

flatten("X.pptx") therefore produces:
  X.pptx           – every slide is one full-size picture of the finished slide (shows the same everywhere);
                     the slide's text is kept in the speaker notes so it can still be searched and copied
  X.pdf            – the same pages as a PDF
  X_editable.pptx  – the original, editable deck (text boxes, tables, pictures)
Rendering uses LibreOffice + poppler (pdftoppm). If they are missing, the editable deck is left as X.pptx.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WIDTH_PX = 1920


def available() -> bool:
    return bool(shutil.which("soffice") and shutil.which("pdftoppm"))


def _slide_texts(pptx: Path) -> list[str]:
    from pptx import Presentation
    out = []
    for s in Presentation(str(pptx)).slides:
        parts = []
        for sh in s.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                parts.append(sh.text_frame.text.strip())
            elif getattr(sh, "has_table", False) and sh.has_table:
                for row in sh.table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
        out.append("\n".join(parts))
    return out


def flatten(pptx_path: str | Path) -> dict:
    p = Path(pptx_path)
    if not available():
        print("flatten: LibreOffice/pdftoppm not found – keeping the editable deck only", file=sys.stderr)
        return {"pptx": str(p)}
    from pptx import Presentation
    from pptx.util import Emu

    editable = p.with_name(p.stem + "_editable.pptx")
    shutil.copy2(p, editable)
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(t), str(editable)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        pdf = t / (editable.stem + ".pdf")
        subprocess.run(["pdftoppm", "-png", "-scale-to-x", str(WIDTH_PX), "-scale-to-y", "-1", str(pdf), str(t / "s")],
                       check=True, timeout=600)
        pages = sorted(t.glob("s-*.png"), key=lambda q: int(q.stem.split("-")[-1]))
        src = Presentation(str(editable))
        texts = _slide_texts(editable)
        if len(pages) != len(src.slides):
            raise RuntimeError(f"flatten: {len(pages)} rendered pages for {len(src.slides)} slides")
        out = Presentation()
        out.slide_width, out.slide_height = src.slide_width, src.slide_height
        blank = out.slide_layouts[6]
        for img, text in zip(pages, texts):
            s = out.slides.add_slide(blank)
            pic = s.shapes.add_picture(str(img), 0, 0, width=Emu(out.slide_width), height=Emu(out.slide_height))
            pic.name = "Slide picture"
            if text:
                s.notes_slide.notes_text_frame.text = text
        out.core_properties.title = src.core_properties.title
        out.core_properties.author = src.core_properties.author
        out.save(str(p))
        shutil.copy2(pdf, p.with_suffix(".pdf"))
    return {"pptx": str(p), "pdf": str(p.with_suffix(".pdf")), "editable": str(editable)}
