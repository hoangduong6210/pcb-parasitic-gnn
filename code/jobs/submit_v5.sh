#!/bin/bash
#SBATCH -J job-v5-fhlabels
# #SBATCH -A <your-slurm-account>   # set via: sbatch -A <acct> ...
#SBATCH -p nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --time=05:00:00
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err
# Resolve the submitted checkout, not Slurm's spool copy of this script.
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:-$PWD}/code/jobs/slurm_job_env.sh}"
[[ -f "$JOB_ENV" ]] || JOB_ENV="${SLURM_SUBMIT_DIR:-$PWD}/slurm_job_env.sh"
source "$JOB_ENV"
REPO_ROOT="$PCB_GNN_ROOT"  # compatibility for the released legacy job bodies

set -euo pipefail
echo "=== this project v5: FastHenry labels + larger corpus + downstream ==="; hostname; date
cd ${REPO_ROOT}/code
source "${REPO_ROOT}/code/env.sh"   # composite PYTHONPATH
echo "=== pre-flight: gen 8 + filament + tiny train ==="
"$PCB_GNN_PYTHON" - <<'PY'
from gen_corpus_fh import big_layout, filament_total_Lm
from planar_to_graph import build_graph_from_planar_layout
lay=big_layout(1,12); g=build_graph_from_planar_layout(lay)
lm=filament_total_Lm(lay); assert lm>0, lm
print("preflight ok: nodes=%d Lm=%.2f nH"%(g.to_feature_matrices()[0].shape[0], lm))
PY
echo "=== gen corpus v2 (1500, larger boards, filament L_m) ==="
"$PCB_GNN_PYTHON" data/gen_corpus_fh.py --n 1500 --out ../datasets/synth_v2 --seed 42 --max_per_net 36
echo "=== experiments v5 ==="
"$PCB_GNN_PYTHON" core/experiments_v5.py
echo DONE; date
