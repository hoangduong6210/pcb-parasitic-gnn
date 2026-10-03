#!/bin/bash
#SBATCH --job-name=tcad-jacobian-arithmetic
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_jacobian_arithmetic_%j.out
#SBATCH --error=logs/tcad_jacobian_arithmetic_%j.err
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=jacobian_arithmetic
: "${PCB_TCAD_EXECUTION_ROOT:?set the clean frozen arithmetic worktree}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_jacobian_arithmetic.py"
