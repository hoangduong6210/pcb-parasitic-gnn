#!/bin/bash
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BUILD="$HERE/build"
SOURCE="$HERE/main.tex"

mkdir -p "$BUILD"

# Keep the packaged source unchanged. The TeX retains its development-tree
# ../08_figures/ path, so patch only the generated build copy.
sed 's|{../08_figures/}|{../../figures/}|' "$SOURCE" > "$BUILD/main.tex"
cd "$BUILD"
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf GNN_Parasitic.pdf

echo "Built $BUILD/GNN_Parasitic.pdf"
