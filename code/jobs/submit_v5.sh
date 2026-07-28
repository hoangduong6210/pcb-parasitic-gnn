#!/bin/bash
#SBATCH -J job-v5-fhlabels
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH -N1 -n16 --mem=32G -t 05:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# --- portability shim added by build_release.py ---------------------------
# REPO_ROOT defaults to this script's parent repo; override to relocate.
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Set SLURM_ACCOUNT for your own allocation before submitting:
#   sbatch -A <your-account> <script>.sh
# --------------------------------------------------------------------------

set -euo pipefail
echo "=== this project v5: FastHenry labels + larger corpus + downstream ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: gen 8 + filament + tiny train ==="
/usr/bin/python3 - <<'PY'
from gen_corpus_fh import big_layout, filament_total_Lm
from planar_to_graph import build_graph_from_planar_layout
lay=big_layout(1,12); g=build_graph_from_planar_layout(lay)
lm=filament_total_Lm(lay); assert lm>0, lm
print("preflight ok: nodes=%d Lm=%.2f nH"%(g.to_feature_matrices()[0].shape[0], lm))
PY
echo "=== gen corpus v2 (1500, larger boards, filament L_m) ==="
/usr/bin/python3 data/gen_corpus_fh.py --n 1500 --out ../datasets/synth_v2 --seed 42 --max_per_net 36
echo "=== experiments v5 ==="
/usr/bin/python3 core/experiments_v5.py
echo DONE; date
