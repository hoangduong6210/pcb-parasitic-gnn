#!/bin/bash
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BUILD="$HERE/build"
SOURCE="$HERE/IMPACT2026_FullPaper_v6.tex"

mkdir -p "$BUILD"

# Preserve the historical source byte-for-byte. The public release stored its
# figures under repository-root figures/, while the TeX retained the original
# ../08_figures/ development path. Patch only a generated build copy.
sed 's|{../08_figures/}|{../../figures/}|' "$SOURCE" > "$BUILD/IMPACT2026_FullPaper_v6.tex"
cd "$BUILD"
pdflatex -interaction=nonstopmode -halt-on-error IMPACT2026_FullPaper_v6.tex
pdflatex -interaction=nonstopmode -halt-on-error IMPACT2026_FullPaper_v6.tex

echo "Built $BUILD/IMPACT2026_FullPaper_v6.pdf"
