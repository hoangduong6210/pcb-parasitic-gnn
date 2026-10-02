#!/bin/bash
#SBATCH --job-name=tcad-cps-pilot
#SBATCH --account=pgs0407
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=160G
#SBATCH --time=03:00:00
#SBATCH --array=0-2%1
#SBATCH --no-requeue
#SBATCH --output=logs/tcad_cps_pilot_%A_%a.out
#SBATCH --error=logs/tcad_cps_pilot_%A_%a.err
set -euo pipefail
export PCB_TCAD_EXECUTED_BATCH_SCRIPT="${BASH_SOURCE[0]}" PCB_TCAD_BATCH_PHASE=pilot
: "${PCB_TCAD_EXECUTION_ROOT:?set the frozen execution root}"
: "${PCB_TCAD_SMOKE_JOB_ID:?require a successful terminal smoke job}"
source "${PCB_TCAD_EXECUTION_ROOT}/code/jobs/tcad_cps_reference_env.sh"
exec "${PCB_GNN_PYTHON}" "${PCB_TCAD_EXECUTION_ROOT}/code/experiments/proofs/run_tcad_cps_reference.py" --phase pilot
