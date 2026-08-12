# Historical IMPACT manuscript

This directory restores the original public manuscript blobs from commit
`54e617e` without editing their contents:

- `IMPACT2026_FullPaper_v6.tex` — blob `ccffa2a4c030f2e6e9658ba0a45c7f1ccc4e9106`;
- `IMPACT2026_FullPaper_v6.pdf` — blob `7b9edebb5f487b665d077e101da936bb455c03da`.

The suffix `v6` means revision 6. The archived PDF contains four US-Letter pages;
 This note records that distinction rather than modifying the
historical source to manufacture a different page count.

The historical TeX retained its development-tree figure path. To rebuild it
against the public `figures/` directory without changing the archived source:

```bash
bash paper/build.sh
```

The generated copy and PDF are written under `paper/build/`; the restored TeX and
PDF blobs remain byte-identical to commit `54e617e`.

The proof-backed post-submission extension lives in [`../Paper_Full/`](../Paper_Full/).
It is a separate manuscript package and does not supersede or rewrite these files.
