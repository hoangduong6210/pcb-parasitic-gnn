#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p build
export SOURCE_DATE_EPOCH=1790899200
export FORCE_SOURCE_DATE=1
export TEXINPUTS="$PWD/vendor//:"
export BSTINPUTS="$PWD/vendor//:"
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
BIBINPUTS="$PWD:" bibtex build/main
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
pdflatex -interaction=nonstopmode -halt-on-error -output-directory=build main.tex
cp build/main.pdf build/PCB_Parasitic_GNN_TCAD_Draft.pdf
