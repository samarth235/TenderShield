"""Document segmentation: split extracted tender text into numbered clauses with page locations."""

from __future__ import annotations

import re
from dataclasses import dataclass

CLAUSE_START = re.compile(r"^(\d+\.\d+)\s+(.*)$")
SECTION_HEADING = re.compile(r"^(\d+)\.\s+([A-Z][^.]{2,80})$")
PAGE_FOOTER = re.compile(r"^Page \d+ of \d+$")


@dataclass
class Clause:
    clause_id: str
    section: str
    page: int
    text: str

    def to_dict(self) -> dict:
        return {"clause_id": self.clause_id, "section": self.section, "page": self.page, "text": self.text}


def segment_clauses(pages: list[tuple[int, str]]) -> list[Clause]:
    """Group lines into clauses. Wrapped continuation lines are joined to their clause."""
    clauses: list[Clause] = []
    section = ""
    current: Clause | None = None
    for page_no, text in pages:
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            line = line.strip()
            if not line or PAGE_FOOTER.match(line) or (idx == 0 and not CLAUSE_START.match(line)):
                # First line of each page is the running header.
                continue
            heading = SECTION_HEADING.match(line)
            clause = CLAUSE_START.match(line)
            if clause:
                current = Clause(clause.group(1), section, page_no, clause.group(2))
                clauses.append(current)
            elif heading:
                section = heading.group(2).strip()
                current = None
            elif current is not None:
                current.text = f"{current.text} {line}"
    return clauses
