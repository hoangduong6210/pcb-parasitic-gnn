#!/usr/bin/env python3
"""Verify the self-contained Journal Snapshot 1 publication package."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from freeze_snapshot import publishable_files


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "SNAPSHOT_MANIFEST.json"
EXPECTED_CLAIMS = {
    "C-GEOM-001",
    "C-FEM-001",
    "C-FEM-002",
    "C-FEM-003",
    "C-FEM-004",
    "C-CPS-DISC-001",
    "C-E3-001",
    "C-ACC-001",
    "C-ACC-FEMV2-001",
    "C-LAT-FEMV2-001",
    "C-BASE-FEMV2-001",
    "C-E3-FEMV2-001",
}
BAD_LOG_PATTERNS = (
    "Overfull",
    "Underfull",
    "undefined references",
    "undefined citations",
    "multiply defined",
    "LaTeX Error",
    "BibTeX warning",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_checked(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout


def abstract_word_count(tex: str) -> int:
    match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if match is None:
        raise AssertionError("abstract environment is missing")
    return len(re.findall(r"[A-Za-z0-9]+(?:[-,][A-Za-z0-9]+)*", match.group(1)))


def citation_keys(tex: str) -> set[str]:
    groups = re.findall(r"\\cite\{([^}]+)\}", tex)
    return {key.strip() for group in groups for key in group.split(",")}


def verify_grayscale_pngs() -> None:
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - explicit environment gate
        raise AssertionError("Pillow is required for the grayscale figure check") from exc
    for path in sorted((ROOT / "figures").glob("*.png")):
        with Image.open(path).convert("RGB") as image:
            extrema = image.getextrema()
            if not (extrema[0] == extrema[1] == extrema[2]):
                raise AssertionError(f"non-monochrome raster channels: {path.name}")


def verify(regenerate: bool) -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["schema"] == "pcb-gnn.journal-snapshot-manifest.v1"
    assert set(data["claims"]) == EXPECTED_CLAIMS

    manifested = set(data["files"])
    publishable = publishable_files()
    assert manifested == publishable, (
        f"manifest coverage mismatch: missing={sorted(publishable - manifested)}, "
        f"extra={sorted(manifested - publishable)}"
    )

    if regenerate:
        run_checked([sys.executable, "generate_figures.py"])
        run_checked(["bash", "build.sh"])

    for relative, expected in data["files"].items():
        path = ROOT / relative
        assert path.is_file(), f"missing manifest file: {relative}"
        assert sha256(path) == expected["sha256"], f"hash mismatch: {relative}"
        assert path.stat().st_size == expected["bytes"], f"size mismatch: {relative}"

    tex = (ROOT / "main.tex").read_text(encoding="utf-8")
    count = abstract_word_count(tex)
    assert count == data["document"]["abstract_words"]
    assert count <= 250
    assert "--" not in tex, "raw double hyphen remains in manuscript prose"
    assert "confidence interval" not in tex.lower()
    assert "/users/" not in tex and "SLURM" not in tex
    assert not re.search(r"\bjob[_ -]?\d+\b", tex, re.I)
    assert "Department of Computer Science, Da-Yeh University, Taiwan" in tex
    assert "Auditable" not in re.search(r"\\title\{([^}]+)\}", tex).group(1)

    bib = (ROOT / "references.bib").read_text(encoding="utf-8")
    available = set(re.findall(r"^@\w+\{([^,]+),", bib, re.M))
    cited = citation_keys(tex)
    missing = cited - available
    assert not missing, f"undefined bibliography keys: {sorted(missing)}"
    unused = available - cited
    assert not unused, f"unused bibliography entries: {sorted(unused)}"
    assert len(cited) == data["document"]["rendered_references"]
    assert len(cited) >= 50, "journal snapshot requires at least 50 cited references"

    included_figures = set(
        re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", tex)
    )
    generated_figures = {path.name for path in (ROOT / "figures").glob("*.pdf")}
    assert included_figures == generated_figures
    assert len(included_figures) == data["document"]["figures"]

    pdf = ROOT / data["document"]["pdf"]
    pdf_info = run_checked(["pdfinfo", str(pdf)])
    pages = int(re.search(r"^Pages:\s+(\d+)$", pdf_info, re.M).group(1))
    assert pages == data["document"]["pages"]
    fonts = run_checked(["pdffonts", str(pdf)]).splitlines()[2:]
    # The type column may itself contain a space (for example, ``Type 1``),
    # while the final five tokens always begin with the embedded-font flag.
    assert fonts and all(line.split()[-5] == "yes" for line in fonts if line.split())

    log = ROOT / "build/main.log"
    if log.exists():
        log_text = log.read_text(encoding="utf-8", errors="replace")
        found = [pattern for pattern in BAD_LOG_PATTERNS if pattern in log_text]
        assert not found, f"build log warnings: {found}"

    verify_grayscale_pngs()
    print(
        f"snapshot verification passed: {len(data['files'])} files, "
        f"{len(data['claims'])} claims, {pages} pages, {count}-word abstract"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="regenerate all figures and the PDF before checking frozen hashes",
    )
    args = parser.parse_args()
    verify(args.regenerate)


if __name__ == "__main__":
    main()
