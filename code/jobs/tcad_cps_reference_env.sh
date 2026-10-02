#!/bin/bash
# Shared pinned setup; no scientific work before the Python allocation guard.
: "${PCB_TCAD_EXECUTION_ROOT:?set the clean, frozen execution worktree}"
: "${PCB_TCAD_SOURCE_COMMIT:?pin the remotely verified execution commit}"
: "${PCB_TCAD_LOCK_SHA256:?pin the execution lock SHA-256}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/slurm_job_env.sh"
cd "${PCB_TCAD_EXECUTION_ROOT}"
export BLIS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PCB_GNN_GMSH_THREADS=1 OMP_DYNAMIC=FALSE
export PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 CUDA_VISIBLE_DEVICES=""
unset GH_TOKEN GITHUB_TOKEN
