#!/bin/bash
#SBATCH --job-name=tcad-field-probe-api
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_field_probe_api_%j.out
#SBATCH --error=logs/tcad_field_probe_api_%j.err
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=field_probe_api
: "${PCB_TCAD_EXECUTION_ROOT:?set the frozen field probe API worktree}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_field_probe_api.py"
