#!/bin/bash
#SBATCH --job-name=pcb-v4-cps-audit
#SBATCH --partition=nextgen
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

export PCB_GNN_EXECUTED_BATCH_SCRIPT="$(readlink -f "$0")"
JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"

"$PCB_GNN_PYTHON" -u \
  code/experiments/proofs/audit_corpus_v4_cps_fidelity_discrepancy.py \
  --protocol protocols/corpus_v4_cps_fidelity_discrepancy_v1.json \
  --output results/corpus_v4/cps_multifidelity/audits/r3_r4_discrepancy/v1/job_"$SLURM_JOB_ID" \
  --write
