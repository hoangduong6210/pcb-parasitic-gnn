#!/usr/bin/env python3
"""Freeze hashes and derived document metadata for the journal snapshot.

Run this only after the manuscript, figures, bibliography, and final PDF have
passed review. Scientific claim identities and evidence bindings are preserved
from the existing manifest; this utility updates publication-package identity.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SNAPSHOT_MANIFEST.json"
STATIC_FILES = {
    ".gitattributes",
    ".gitignore",
    "README.md",
    "VERSION",
    "build.sh",
    "figure_data.json",
    "freeze_snapshot.py",
    "generate_figures.py",
    "main.tex",
    "references.bib",
    "verify_snapshot.py",
    "vendor/IEEEtran.bst",
    "vendor/IEEEtran.cls",
    "vendor/README.md",
    "vendor/UPSTREAM_README",
    "build/PCB_Parasitic_GNN_Journal_Snapshot_1.pdf",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publishable_files() -> set[str]:
    figures = {
        path.relative_to(ROOT).as_posix()
        for suffix in ("*.pdf", "*.png")
        for path in (ROOT / "figures").glob(suffix)
    }
    return STATIC_FILES | figures


def citation_keys(tex: str) -> set[str]:
    groups = re.findall(r"\\cite\{([^}]+)\}", tex)
    return {key.strip() for group in groups for key in group.split(",")}


def abstract_word_count(tex: str) -> int:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if match is None:
        raise AssertionError("abstract environment is missing")
    return len(re.findall(r"[A-Za-z0-9]+(?:[-,][A-Za-z0-9]+)*", match.group(1)))


def pdf_pages(path: Path) -> int:
    info = subprocess.run(
        ["pdfinfo", str(path)], check=True, text=True, capture_output=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)$", info, re.M)
    if match is None:
        raise AssertionError("pdfinfo did not report a page count")
    return int(match.group(1))


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tex = (ROOT / "main.tex").read_text(encoding="utf-8")
    pdf = ROOT / "build/PCB_Parasitic_GNN_Journal_Snapshot_1.pdf"
    included_figures = set(re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex))
    generated_pdfs = {path.name for path in (ROOT / "figures").glob("*.pdf")}
    if included_figures != generated_pdfs:
        raise AssertionError(
            f"figure inclusion mismatch: included={sorted(included_figures)}, "
            f"generated={sorted(generated_pdfs)}"
        )

    data["version"] = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    data["document"].update(
        {
            "pages": pdf_pages(pdf),
            "abstract_words": abstract_word_count(tex),
            "rendered_references": len(citation_keys(tex)),
            "figures": len(included_figures),
        }
    )
    data["review"].update(
        {
            "technical_review_date": date.today().isoformat(),
            "prose_review_date": date.today().isoformat(),
            "visual_review_date": date.today().isoformat(),
            "visual_scope": (
                f"all {data['document']['pages']} PDF pages and all "
                f"{data['document']['figures']} monochrome figures"
            ),
        }
    )

    files: dict[str, dict[str, object]] = {}
    for relative in sorted(publishable_files()):
        path = ROOT / relative
        if not path.is_file():
            raise AssertionError(f"missing publishable file: {relative}")
        files[relative] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    data["files"] = files
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"froze {len(files)} files, {data['document']['pages']} pages, "
        f"{data['document']['rendered_references']} references, "
        f"{data['document']['figures']} figures"
    )


if __name__ == "__main__":
    main()
