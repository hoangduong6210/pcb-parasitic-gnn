#!/bin/bash
: "${BASH_VERSION:?slurm_job_env.sh requires bash}"

# Resolve from the helper itself, not from the batch script: Slurm may execute a
# spool copy of the submitted script, while this sourced helper remains in the
# checked-out project/release tree.
_pcb_job_env_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${_pcb_job_env_dir}/gnn_baseline.py" ]]; then
    # Flat source layout: <project>/04_code/slurm_job_env.sh
    PCB_GNN_CODE="${_pcb_job_env_dir}"
    PCB_GNN_ROOT="$(cd "${_pcb_job_env_dir}/.." && pwd)"
elif [[ -f "${_pcb_job_env_dir}/../env.sh" ]]; then
    # Public layout: <release>/code/jobs/slurm_job_env.sh
    PCB_GNN_CODE="$(cd "${_pcb_job_env_dir}/.." && pwd)"
    PCB_GNN_ROOT="$(cd "${PCB_GNN_CODE}/.." && pwd)"
else
    echo "Cannot resolve PCB-GNN root from ${_pcb_job_env_dir}" >&2
    return 2
fi

PCB_GNN_PYTHON="${PCB_GNN_PYTHON:-/usr/bin/python3}"
if [[ ! -x "${PCB_GNN_PYTHON}" ]]; then
    echo "PCB_GNN_PYTHON is not executable: ${PCB_GNN_PYTHON}" >&2
    return 2
fi

if [[ -f "${PCB_GNN_CODE}/env.sh" ]]; then
    # Reorganized public release: add every themed module directory.
    source "${PCB_GNN_CODE}/env.sh"
else
    export PYTHONPATH="${PCB_GNN_CODE}${PYTHONPATH:+:${PYTHONPATH}}"
fi
export PCB_GNN_ROOT PCB_GNN_CODE PCB_GNN_PYTHON PYTHONPATH
unset _pcb_job_env_dir
