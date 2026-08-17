#!/usr/bin/env python3
"""Audit publication-eligible wiki prose for deterministic style defects.

This tool does not classify authorship. It enforces the repository's public
prose contract before wiki content can be exported into a paper snapshot.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"

FLAGGED_PHRASES = (
    "as an ai",
    "delve into",
    "game-changing",
    "in today's rapidly evolving",
    "it is important to note",
    "it is worth noting",
    "paves the way",
    "seamlessly",
    "serves as a testament",
    "underscores the importance",
)
PLACEHOLDERS = ("lorem ipsum", "todo", "tbd", "insert citation", "citation needed")
PRIVATE_PATH = re.compile(
    r"(?<![\w.])/(?:users|home|tmp|scratch|var|opt|mnt|gpfs|fs|projects?)(?:/|\b)",
    re.IGNORECASE,
)
JOB_REFERENCE = re.compile(
    r"\b(?:slurm|array|batch|job)[_ -]?(?:id[_ -]?)?\d{5,}\b",
    re.IGNORECASE,
)
TABLE_SEPARATOR = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*$")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise ValueError("missing front matter")
    header, separator, body = text[4:].partition("\n---\n")
    if not separator:
        raise ValueError("unterminated front matter")
    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, colon, value = line.partition(":")
        if not colon:
            raise ValueError(f"invalid front-matter line: {line!r}")
        metadata[key.strip()] = value.strip()
    return metadata, body


def prose_only(body: str) -> str:
    """Remove fenced code, inline code, and Markdown table separators."""
    lines: list[str] = []
    fenced = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced or TABLE_SEPARATOR.match(line):
            continue
        lines.append(re.sub(r"`[^`]*`", "", line))
    return "\n".join(lines)


def repeated_paragraphs(body: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", prose_only(body))
    normalized = [re.sub(r"\s+", " ", paragraph).strip().lower() for paragraph in paragraphs]
    normalized = [paragraph for paragraph in normalized if len(paragraph) >= 120]
    return [paragraph for paragraph, count in Counter(normalized).items() if count > 1]


def audit_page(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        metadata, body = parse_front_matter(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]

    if metadata.get("paper_source") != "true":
        return errors
    if metadata.get("prose_reviewed") != "true":
        errors.append("paper_source page lacks prose_reviewed: true")
    if not metadata.get("claim_ids"):
        errors.append("paper_source page lacks a claim_ids export boundary")

    prose = prose_only(body)
    lowered = prose.lower()
    if "--" in prose:
        errors.append("raw double hyphen appears in prose")
    for phrase in FLAGGED_PHRASES:
        if phrase in lowered:
            errors.append(f"flagged templated phrase: {phrase!r}")
    for placeholder in PLACEHOLDERS:
        if re.search(rf"\b{re.escape(placeholder)}\b", lowered):
            errors.append(f"unresolved placeholder: {placeholder!r}")
    if PRIVATE_PATH.search(prose):
        errors.append("private absolute path appears in paper-source prose")
    if JOB_REFERENCE.search(prose):
        errors.append("raw scheduler identifier appears in paper-source prose")
    if repeated_paragraphs(body):
        errors.append("repeated long paragraph appears in page")
    return errors


def main() -> int:
    failures: list[str] = []
    for path in sorted(WIKI.rglob("*.md")):
        for error in audit_page(path):
            failures.append(f"{path.relative_to(ROOT)}: {error}")

    full_paper = ROOT / "Paper_Full/main.tex"
    if full_paper.is_file():
        tex = full_paper.read_text(encoding="utf-8")
        lowered = tex.lower()
        if "--" in tex:
            failures.append("Paper_Full/main.tex: raw double hyphen appears in LaTeX")
        for phrase in FLAGGED_PHRASES:
            if phrase in lowered:
                failures.append(
                    f"Paper_Full/main.tex: flagged templated phrase {phrase!r}"
                )
        for placeholder in PLACEHOLDERS:
            if re.search(rf"\b{re.escape(placeholder)}\b", lowered):
                failures.append(
                    f"Paper_Full/main.tex: unresolved placeholder {placeholder!r}"
                )
        if PRIVATE_PATH.search(tex) or JOB_REFERENCE.search(tex):
            failures.append(
                "Paper_Full/main.tex: internal path or scheduler identifier appears"
            )

    if failures:
        print("Research prose audit failed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("Research prose audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
