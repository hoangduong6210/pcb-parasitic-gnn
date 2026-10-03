#!/bin/bash
#SBATCH --job-name=tcad-support-feas
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=160G
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_support_feasibility_%j.out
#SBATCH --error=logs/tcad_support_feasibility_%j.err
set -euo pipefail
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=feasibility
: "${PCB_TCAD_EXECUTION_ROOT:?set the clean recovery execution root}"
: "${PCB_TCAD_SMOKE_JOB_ID:?require the terminal validated recovery smoke}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_support_recovery.py" --phase feasibility
