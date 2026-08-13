#!/bin/bash
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
BUILD="$HERE/build"
SOURCE="$HERE/main.tex"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1786492800}"
export FORCE_SOURCE_DATE=1
export TZ=UTC

mkdir -p "$BUILD"

# Keep the packaged source unchanged. The TeX retains its development-tree
# ../08_figures/ path, so patch only the generated build copy.
sed 's|{../08_figures/}|{../../figures/}|' "$SOURCE" > "$BUILD/main.tex"
cd "$BUILD"
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf Conference_Submission_ARCHIVE.pdf

echo "Built $BUILD/Conference_Submission_ARCHIVE.pdf"
