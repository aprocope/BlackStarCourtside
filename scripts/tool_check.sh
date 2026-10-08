#!/usr/bin/env bash
# P0.2: print versions of required tools. Docker is only needed from Phase 2.
for c in python3.13 terraform aws docker gh; do
  printf "%-10s " "$c"
  if command -v "$c" >/dev/null 2>&1; then "$c" --version 2>&1 | head -1; else echo "MISSING"; fi
done
