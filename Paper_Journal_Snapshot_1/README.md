# IEEE journal snapshot 1

This is the first journal-format snapshot exported from the admitted research
wiki. It is an independent package; `Paper_Summary/` remains the immutable
conference submission and `Paper_Full/` remains a superseded historical draft.

The manuscript uses the IEEEtran journal class in two-column mode. The format
choice follows the IEEE Author Center article-template, article-structure and
graphics guidance. The bundled IEEEtran 1.8b class and bibliography style are
LPPL-licensed copies from the CTAN distribution; provenance is recorded in
`vendor/README.md`.

Format sources checked on 2026-09-15:

- [IEEE article templates](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/authoring-tools-and-templates/tools-for-ieee-authors/ieee-article-templates/)
- [IEEE article structure](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-the-text-of-your-article/structure-your-article/)
- [IEEE graphics guidance](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/)
- [IEEE graphics file formatting](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)

The package contains manuscript source, bibliography, deterministic figure
data, the figure generator, monochrome PDF/PNG figures, build tooling, the
built PDF and a snapshot manifest. It contains no scheduler identifiers,
private machine paths, raw logs or internal audit reports.

Build from this directory:

```bash
./build.sh
```

Regenerate figures before building:

```bash
/usr/bin/python3 generate_figures.py
```

Verify the frozen package, including hashes, claim coverage, bibliography
keys, embedded fonts, monochrome figures, build warnings, and the 250-word
abstract limit:

```bash
/usr/bin/python3 verify_snapshot.py
```

Use `--regenerate` to rebuild every figure and the PDF before checking that
their bytes match the snapshot manifest.

The scientific claim set is frozen in `SNAPSHOT_MANIFEST.json`. This snapshot
is a research handoff artifact, not a declaration that it has been submitted
to a particular IEEE journal.
