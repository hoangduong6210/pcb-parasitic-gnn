#!/bin/bash
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/.." && pwd)
cd "$HERE"
export MPLCONFIGDIR="$HERE/.mplconfig"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1786492800}"
export FORCE_SOURCE_DATE=1
export TZ=UTC

python3 "$REPO/code/figures/make_paper_full_figures.py"
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
mkdir -p build
cp main.pdf build/Paper_Full.pdf
echo "Built $HERE/build/Paper_Full.pdf"
