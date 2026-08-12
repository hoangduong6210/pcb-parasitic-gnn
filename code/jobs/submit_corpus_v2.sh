#!/bin/bash
#SBATCH --job-name=pcb-corpus-v2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=24G
#SBATCH --time=03:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

JOB_ENV="${PCB_GNN_JOB_ENV:-${SLURM_SUBMIT_DIR:?submit from repository root}/code/jobs/slurm_job_env.sh}"
source "$JOB_ENV"
cd "$PCB_GNN_ROOT"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="$OMP_NUM_THREADS"

: "${PCB_GNN_CORPUS_OUT:?set PCB_GNN_CORPUS_OUT to an empty staging path ending in synth_v2}"
if [[ -e "$PCB_GNN_CORPUS_OUT" ]]; then
    echo "Refusing to overwrite existing corpus path: $PCB_GNN_CORPUS_OUT" >&2
    exit 2
fi

"$PCB_GNN_PYTHON" -u code/data/gen_corpus_fh.py \
  --n 1500 --seed 42 --max_per_net 36 --out "$PCB_GNN_CORPUS_OUT"
"$PCB_GNN_PYTHON" code/quality/verify_corpora.py \
  --data-root "$(dirname "$PCB_GNN_CORPUS_OUT")" --corpus synth_v2 --require-layouts
