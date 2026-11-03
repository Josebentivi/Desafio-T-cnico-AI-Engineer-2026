from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = ROOT / "data" / "políticas_da_loja.pdf"
OUT_PATH = ROOT / "data" / "policy_sections.json"

HEADER_RE = re.compile(r"^Empório da Música\s+Manual de Políticas e Procedimentos\s*$")
PAGE_RE = re.compile(r"^Página\s+\d+\s*$")
HEADING_RE = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?\s+(.+)$")


def is_heading(line: str) -> tuple[str, str] | None:
    match = HEADING_RE.match(line)
    if not match:
        return None
    number = int(match.group(1))
    subsection = match.group(2)
    title = match.group(3).strip()
    if number > 10 or len(title) > 100:
        return None
    if ":" in title:
        return None
    if not title or not title[0].isupper():
        return None
    section_id = f"{number}.{subsection}" if subsection else str(number)
    return section_id, f"{section_id} {title}"


def extract_lines() -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    with pdfplumber.open(PDF_PATH) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if HEADER_RE.match(line) or PAGE_RE.match(line):
                    continue
                lines.append((page_number, line))
    return lines


def build_sections() -> list[dict]:
    sections: list[dict] = []
    current = {
        "section_id": "0",
        "title": "Store information",
        "page": 1,
        "lines": [],
    }

    def flush() -> None:
        body = "\n".join(current["lines"]).strip()
        if not body:
            return
        sections.append(
            {
                "section_id": current["section_id"],
                "title": current["title"],
                "page": current["page"],
                "text": body,
            }
        )

    for page_number, line in extract_lines():
        heading = is_heading(line)
        if heading:
            flush()
            section_id, title = heading
            current = {
                "section_id": section_id,
                "title": title,
                "page": page_number,
                "lines": [],
            }
        else:
            current["lines"].append(line)
    flush()
    return sections


def main() -> int:
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}", file=sys.stderr)
        return 1
    sections = build_sections()
    payload = {
        "source": str(PDF_PATH.relative_to(ROOT)).replace("\\", "/"),
        "version": "2.1",
        "generated_at": datetime.now(UTC).isoformat(),
        "sections": sections,
    }
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(sections)} sections extracted to {OUT_PATH}")
    for section in sections:
        print(f"  {section['section_id']:>4}  {section['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
