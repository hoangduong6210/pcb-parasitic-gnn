"""Release contracts for the first IEEE journal-format snapshot."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "Paper_Journal_Snapshot_1"

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


def test_snapshot_uses_ieee_journal_mode_and_covers_admitted_claims() -> None:
    manuscript = (PACKAGE / "main.tex").read_text(encoding="utf-8")
    data = json.loads((PACKAGE / "figure_data.json").read_text(encoding="utf-8"))

    assert r"\documentclass[journal]{IEEEtran}" in manuscript
    assert set(data["source_claim_ids"]) == EXPECTED_CLAIMS
    # Human-facing prose need not expose internal registry identifiers. The
    # package manifest is the machine-readable claim-to-paper bridge.
    manifest = json.loads(
        (PACKAGE / "SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8")
    )
    assert set(manifest["claims"]) == EXPECTED_CLAIMS


def test_snapshot_pins_current_headline_values() -> None:
    data = json.loads((PACKAGE / "figure_data.json").read_text(encoding="utf-8"))
    claims = data["claims"]

    assert claims["accuracy"]["mean_mape_pct"] == [12.550, 4.173, 3.964, 3.413]
    assert claims["latency"]["primary_ratio"] == 70099.076
    assert claims["latency"]["seconds"][0] == 0.00741936
    assert claims["latency"]["seconds"][3] == 522.98245
    assert claims["fidelity_discrepancy"]["median_pct"] == 8.479
    assert len(claims["coordinate_ablation"]["interval_low_pp"]) == 2
    assert len(claims["coordinate_ablation"]["interval_high_pp"]) == 2


def test_snapshot_package_contains_rebuildable_monochrome_figures_and_pdf() -> None:
    required = {
        "README.md",
        "VERSION",
        "build.sh",
        "generate_figures.py",
        "figure_data.json",
        "main.tex",
        "references.bib",
        "vendor/IEEEtran.cls",
        "vendor/IEEEtran.bst",
        "build/PCB_Parasitic_GNN_Journal_Snapshot_1.pdf",
    }
    for relative in required:
        assert (PACKAGE / relative).is_file(), relative

    for number in range(1, 10):
        matches = list((PACKAGE / "figures").glob(f"hoang{number}_*.pdf"))
        assert len(matches) == 1, number
        assert matches[0].read_bytes().startswith(b"%PDF")

    final_pdf = PACKAGE / "build/PCB_Parasitic_GNN_Journal_Snapshot_1.pdf"
    assert final_pdf.read_bytes().startswith(b"%PDF")


def test_snapshot_has_visible_affiliation_and_at_least_fifty_cited_sources() -> None:
    manuscript = (PACKAGE / "main.tex").read_text(encoding="utf-8")
    bibliography = (PACKAGE / "references.bib").read_text(encoding="utf-8")
    title = re.search(r"\\title\{([^}]+)\}", manuscript).group(1)
    cited = {
        key.strip()
        for group in re.findall(r"\\cite\{([^}]+)\}", manuscript)
        for key in group.split(",")
    }
    available = set(re.findall(r"^@\w+\{([^,]+),", bibliography, re.MULTILINE))

    assert "A License-Clean Graph Neural Network for Fast Parasitic Extraction" in title
    assert "Auditable" not in title
    assert "Department of Computer Science, Da-Yeh University, Taiwan" in manuscript
    assert len(cited) >= 50
    assert cited == available


def test_snapshot_excludes_operational_provenance_and_legacy_speed_claims() -> None:
    # Scan publication prose and declarative metadata. Executable verifier code
    # may contain a forbidden-token literal in the assertion that rejects it.
    public_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".tex", ".json"}
    )
    forbidden = (
        re.compile(r"/(?:users|home|scratch|tmp)/", re.IGNORECASE),
        re.compile(r"\b(?:job|slurm)[_ -]?(?:id[_ -]?)?\d{5,}\b", re.IGNORECASE),
        re.compile(r"(?:~|approximately|approx\.?)[ ]*4[,]?300(?:[ -]?fold|[x×])", re.IGNORECASE),
    )
    for pattern in forbidden:
        assert pattern.search(public_text) is None, pattern.pattern


def test_snapshot_abstract_is_one_paragraph_and_at_most_250_words() -> None:
    manuscript = (PACKAGE / "main.tex").read_text(encoding="utf-8")
    abstract = manuscript.split(r"\begin{abstract}", 1)[1].split(r"\end{abstract}", 1)[0]
    assert "\n\n" not in abstract.strip()
    words = re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", abstract)
    assert len(words) <= 250
