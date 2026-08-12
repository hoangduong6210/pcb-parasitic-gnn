# Third-party software

This repository contains project source under BSD-3-Clause. It does not vendor
FastHenry, FastCap, or FasterCap executables.

- FastHenry2 and FastCap2 are optional external solver dependencies. Obtain
  their source and license terms from their upstream FastFieldSolvers projects.
- FasterCap is an optional external LGPL-licensed solver used only by the
  documented negative/convergence study; it is not linked into this project.
- Python dependencies retain their respective upstream licenses. The exact
  proof environment is listed in `requirements-proof.txt`.

Users are responsible for reviewing and complying with upstream terms when they
install optional third-party software.
