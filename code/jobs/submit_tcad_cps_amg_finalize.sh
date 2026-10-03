#!/bin/bash
#SBATCH --job-name=tcad-amg-final
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_amg_finalize_%j.out
#SBATCH --error=logs/tcad_amg_finalize_%j.err
set -euo pipefail
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=finalize
: "${PCB_TCAD_EXECUTION_ROOT:?set the clean frozen AMG feasibility worktree}"
: "${PCB_TCAD_SMOKE_JOB_ID:?require the new terminal validated smoke}"
: "${PCB_TCAD_FEASIBILITY_JOB_ID:?set the single feasibility job ID}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_amg_feasibility.py" --phase finalize
