#!/bin/bash
# env.sh — put every code/ sub-directory on PYTHONPATH.
#
# Module files are grouped into themed directories for readability but their
# imports remain flat (`from gnn_baseline import ...`), so every directory has
# to be importable. Source this once per shell:
#
#     source code/env.sh
#
CODE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$CODE_DIR"
for d in "$CODE_DIR"/core "$CODE_DIR"/models/gnn "$CODE_DIR"/solvers \
         "$CODE_DIR"/data "$CODE_DIR"/figures "$CODE_DIR"/experiments/*/; do
    PYTHONPATH="$PYTHONPATH:${d%/}"
done
export PYTHONPATH
