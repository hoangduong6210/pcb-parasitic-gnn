#!/bin/bash
set -euo pipefail

printf 'SLURM_JOB_ID=%s\n' "$SLURM_JOB_ID"
printf 'SLURM_ARRAY_JOB_ID=%s\n' "$SLURM_ARRAY_JOB_ID"
printf 'SLURM_ARRAY_TASK_ID=%s\n' "$SLURM_ARRAY_TASK_ID"
printf 'SLURM_ARRAY_TASK_MIN=%s\n' "$SLURM_ARRAY_TASK_MIN"
printf 'SLURM_ARRAY_TASK_MAX=%s\n' "$SLURM_ARRAY_TASK_MAX"
printf 'SLURM_ARRAY_TASK_COUNT=%s\n' "$SLURM_ARRAY_TASK_COUNT"
printf 'SLURM_CPUS_PER_TASK=%s\n' "$SLURM_CPUS_PER_TASK"
printf 'SLURM_MEM_PER_NODE=%s\n' "$SLURM_MEM_PER_NODE"
printf 'SLURM_JOB_PARTITION=%s\n' "$SLURM_JOB_PARTITION"
printf '%s\n' 'QUERY_JOB_ID'
scontrol show job -o "$SLURM_JOB_ID"
printf '%s\n' 'QUERY_EXACT_COMPONENT'
scontrol show job -o "${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
printf '%s\n' 'QUERY_ARRAY_JOB_ID'
scontrol show job -o "$SLURM_ARRAY_JOB_ID"
