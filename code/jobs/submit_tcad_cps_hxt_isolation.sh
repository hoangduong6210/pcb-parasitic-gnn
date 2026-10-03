#!/bin/bash
#SBATCH --job-name=tcad-hxt-isolate
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=160G
#SBATCH --time=00:55:00
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_hxt_isolation_%j.out
#SBATCH --error=logs/tcad_hxt_isolation_%j.err
set -euo pipefail
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=hxt_isolation
: "${PCB_TCAD_EXECUTION_ROOT:?set the clean frozen HXT-isolation worktree}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_hxt_isolation.py"
