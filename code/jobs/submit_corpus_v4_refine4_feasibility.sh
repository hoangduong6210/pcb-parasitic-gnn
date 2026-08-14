#!/bin/bash
#SBATCH --job-name=pcb-v4-r4-feas
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=25
#SBATCH --mem=160G
#SBATCH --time=03:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
export PCB_GNN_EXECUTED_BATCH_SCRIPT="$(readlink -f "$0")"
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"; cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export BLIS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OMP_DYNAMIC=FALSE
export PCB_GNN_GMSH_THREADS=25
export PCB_GNN_MAX_MESH_NODES=10000000
export PCB_GNN_MAX_MESH_TETRAHEDRA=65000000
export PCB_GNN_MAX_RSS_KB=125829120
export PCB_GNN_MAX_OPERATOR_COMPLEXITY=1.25
: "${PCB_GNN_V3_CORPUS_DIR:?Set finalized source corpus-v3 directory}"
: "${PCB_GNN_PRIOR_CONVERGENCE_FINAL:?Set canonical failed convergence artifact}"
: "${PCB_GNN_REFINE4_LAYOUT_ID:?Set predeclared feasibility layout ID}"
EXTRA_ARGS=()
if [[ "$PCB_GNN_REFINE4_LAYOUT_ID" == "407" ]]; then
  : "${PCB_GNN_REFINE4_STAGE_A_149:?Layout 407 requires passing layout-149 evidence}"
  : "${PCB_GNN_REFINE4_STAGE_A_149_SHA256:?Layout 407 requires pinned stage-A SHA256}"
  EXTRA_ARGS+=(
    --prior-refine4-149 "$PCB_GNN_REFINE4_STAGE_A_149"
    --prior-refine4-149-sha256 "$PCB_GNN_REFINE4_STAGE_A_149_SHA256"
  )
fi
"$PCB_GNN_PYTHON" -u \
  code/experiments/proofs/experiments_corpus_v4_refine4_feasibility.py \
  --corpus "$PCB_GNN_V3_CORPUS_DIR" \
  --prior-convergence-final "$PCB_GNN_PRIOR_CONVERGENCE_FINAL" \
  --layout-id "$PCB_GNN_REFINE4_LAYOUT_ID" --timeout-s 7200 \
  "${EXTRA_ARGS[@]}"
