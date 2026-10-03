---
title: TCAD Saved-Packet Jacobian Arithmetic
status: VALIDATED; saved-packet arithmetic diagnostic only
last_updated: 2026-10-03
paper_source: false
---

# TCAD Saved-Packet Jacobian Arithmetic

The [rejected boundary-mesh attempt](../evidence/TCAD-Dielectric-Boundary-Mesh.md)
preserved raw and optimized toy packets but failed its native/reconstructed
Jacobian comparison. This separate diagnostic examines those identical arrays;
it does not regenerate a mesh, repair elements or alter the failed tolerance.

## Frozen question and scope

For every saved tetrahedron, compare the original NumPy scalar-triple-product
operation sequence and the saved native `minDetJac` with two independent exact
calculations: a rational scalar triple product and rational elimination of the
4-by-4 matrix whose rows are `[1,x,y,z]`. Convert each stored coordinate using
`Fraction.from_float` before any subtraction. Exactness refers to stored binary64
values, not intended decimals or the CAD continuum. The
[Python fractions documentation](https://docs.python.org/3.9/library/fractions.html)
explains this distinction. Never approximate using `limit_denominator`.

Retain all rows, native element/node/volume IDs, signed determinants, native
SICN, exact numerator/denominator pairs and the original `isclose` flags at
relative tolerance `1e-8`, absolute tolerance zero. A separate diagnostic error
uses the absolute exact determinant as denominator; its relative value is null
when that determinant is zero. Absolute rational error remains available.
Interesting rows also contain hexadecimal stored coordinates. No outlier is
removed, including degenerate or inverted tetrahedra.

The pinned Gmsh 4.15.2 source dispatches `minDetJac` to
`jacobianBasedQuality::minMaxJacobianDeterminant`; this API observation alone
does not establish its numerical accuracy or explain the rejection. Source:
[official versioned archive](https://gmsh.info/src/gmsh-4.15.2-source.tgz),
`src/common/gmsh.cpp`, `getElementQualities` branch. No Gmsh execution is needed
for this diagnosis.

## Execution and completion gates

Protocol: `protocols/tcad_cps_jacobian_arithmetic_v1.json`. One SLURM job uses
8 GiB, 15 minutes, one requested CPU and one scientific thread. Three fresh
workers process raw, final and repeat-final packets; each has a 180-second,
6-GiB ceiling and a 16-MiB report cap. All tetrahedra are covered, with a
4,096-element cap fixed before execution. Actual allocation/compute host,
source lock and pinned runtime are checked before numerical imports or packet
loading. Login-side verification reads bytes and report metadata only.

Completion requires agreement of the two exact algorithms for every element,
full input-hash/row coverage, successful bounded workers and byte-identical
final/repeat-final reports. An arithmetic diagnosis can complete even if every
mesh remains rejected. It cannot authorize field solving, reference labels,
training or a paper claim. Any new mesh policy or numerical admission criterion
requires a separately justified prospective protocol; this failure is retained.

Implementation was first tested with tiny synthetic inputs, then frozen and
published before SLURM execution. The same-packet diagnosis has now completed
with exact fresh-repeat reports and a checked terminal archive; outcomes and
per-element interpretation belong to the
[evidence owner](../evidence/TCAD-Jacobian-Arithmetic.md). Positive exact signs
did not remove the sliver/conditioning concern or admit the rejected mesh.
