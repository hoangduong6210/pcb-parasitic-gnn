---
title: License and Asset Boundaries
status: canonical governance
last_updated: 2026-08-17
paper_source: false
---

# License and Asset Boundaries

Project-authored source is released under BSD-3-Clause. Dependency and solver
notices live in `THIRD_PARTY_NOTICES.md`. A package name in the documentation
does not imply that its source or binary is redistributed by this repository.

FastHenry, FastCap, FasterCap, Gmsh, scikit-fem, PyTorch, and other optional
tools retain their upstream licenses. Reproduction instructions require users
to obtain external executables through their authorized sources and record the
binary hash used for a result.

Manufacturer datasheets, STEP assemblies, simulation libraries, screenshots,
logos, and derived meshes require a separate redistribution review. Local access
for research does not automatically authorize committing the file, embedding it
in a paper package, or publishing a derivative asset. Until terms are confirmed,
the repository may track a filename and checksum manifest but not the vendor
payload.

Paper figures should be project-generated diagrams or plots from admitted
evidence. A third-party figure is included only with a verified license or
written permission and a clear attribution. Internal detector reports, private
paths, cluster logs, credentials, and access tokens never belong in publication
packages.
