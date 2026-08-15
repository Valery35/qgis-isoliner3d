#!/usr/bin/env bash
# Сборка руководства Isoliner3D: RU и EN.
# Лежит в manual/ рядом с manual.md, manual_en.md и папкой images/.
# Запускать из manual/. Готовые PDF кладутся в ../isoliner3d/doc/
# (только они уходят в плагин; сами manual.md и images/ в zip не попадают).
set -euo pipefail
cd "$(dirname "$0")"

OUT=../isoliner3d/doc
mkdir -p "$OUT"

PANDOC_COMMON=(--pdf-engine=xelatex --toc --toc-depth=3
  -V mainfont="DejaVu Serif" -V sansfont="DejaVu Sans"
  -V monofont="DejaVu Sans Mono"
  -V geometry:margin=2.2cm -V colorlinks=true
  -V header-includes='\usepackage{float}\floatplacement{figure}{H}')

build () {  # build <src.md> <lang> <out.pdf>
  local src="$1" lang="$2" out="$3" tmp="_raw_$3"
  echo ">> $src -> $OUT/$out  (lang=$lang)"
  pandoc "$src" -o "$tmp" "${PANDOC_COMMON[@]}" -V lang="$lang"
  gs -sDEVICE=pdfwrite -dCompatibilityLevel=1.5 -dPDFSETTINGS=/ebook \
     -dColorImageResolution=150 -dGrayImageResolution=150 \
     -dMonoImageResolution=150 \
     -dNOPAUSE -dQUIET -dBATCH -sOutputFile="$OUT/$out" "$tmp"
  rm -f "$tmp"
}

build manual.md    ru Isoliner3D.pdf
build manual_en.md en Isoliner3D_en.pdf
echo "Готово: $OUT/Isoliner3D.pdf, $OUT/Isoliner3D_en.pdf"
