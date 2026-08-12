# tools/ — external 3-D extractors (ceiling-break T1)

## fasthenry
FastHenry2 (FastFieldSolvers, MIT) — field-standard 3-D partial-element inductance
extractor (open-source equivalent of ANSYS Q3D for L; returns L(f), R(f)).

Build from the upstream source; binaries are intentionally not distributed:

```bash
git clone https://github.com/ediloren/FastHenry2.git
make -C FastHenry2 fasthenry
export FASTHENRY_BIN=/absolute/path/to/FastHenry2/bin/fasthenry
```

Validation (job 5700723, 24 layouts): our multi-filament reference matches
FastHenry to 1.6% median; the analytical Grover label is 56% off FastHenry.

## fastercap
FasterCap (FastFieldSolvers, LGPL-2.1, v6.0.7) — 3-D ADAPTIVE-mesh capacitance
solver (open-source counterpart of Q3D for C). Unlike the 1992 FastCap (uniform
mesh), FasterCap auto-refines panels near close surfaces, which is required for
thin planar inter-layer gaps (~0.1 mm) where uniform FastCap does NOT converge.

Build from source (needs sibling repos LinAlgebra + Geometry):

```bash
git clone https://github.com/ediloren/FasterCap.git
git clone https://github.com/ediloren/LinAlgebra.git
git clone https://github.com/ediloren/Geometry.git
cmake -S FasterCap -B FasterCap/build -DCMAKE_BUILD_TYPE=Release
cmake --build FasterCap/build -j8
export FASTERCAP_BIN=/absolute/path/to/fastercap
```
Links wxWidgets 3.0.5 (present on HPC). Runs HEADLESS via:
    xvfb-run -a ./fastercap -b <input.qui> -a<mesh_tol>
Reads FastCap-format .qui input. NOTE: sensitive to panel ORIENTATION (outward
normals) — inconsistent winding yields a non-diagonally-dominant (wrong-sign)
matrix; validate on a parallel-plate (C=eps0*A/d) before trusting windings.
Adaptive solves are heavy and must be submitted through SLURM.
