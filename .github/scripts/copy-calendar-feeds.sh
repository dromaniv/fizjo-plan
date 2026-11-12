#!/usr/bin/env bash
set -euo pipefail

shopt -s nullglob
files=("${FEED_DIR:?FEED_DIR is required}"/*.ics)
if [[ ${#files[@]} -eq 0 ]]; then
  echo "::error::No calendar artifacts found"
  exit 1
fi

# Validate the entire artifact before copying any file.
for file in "${files[@]}"; do
  name="${file##*/}"
  if [[ ! "$name" =~ ^[A-Za-z0-9_-]+\.ics$ || ! -f "$file" || -L "$file" ]]; then
    echo "::error::Invalid calendar artifact"
    exit 1
  fi
  if [[ $(wc -c < "$file") -gt 2097152 ]]; then
    echo "::error::Calendar artifact exceeds the size limit"
    exit 1
  fi
done

for file in "${files[@]}"; do
  cp -- "$file" "docs/${file##*/}"
done
