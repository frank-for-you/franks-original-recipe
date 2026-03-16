#!/bin/bash
# Frank's Original Recipe — Workspace Audit Script
# Run this BEFORE and AFTER optimization to compare.
# Usage: bash audit.sh
# Output: file sizes, estimated token counts, total injected context

WORKSPACE="${OPENCLAW_WORKSPACE:-$HOME/.openclaw/workspace}"

echo "======================================================"
echo " Frank's Original Recipe — Workspace Audit"
echo " Workspace: $WORKSPACE"
echo " $(date)"
echo "======================================================"
echo ""
echo "FILE SIZES (injected every message):"
echo "------------------------------------------------------"

total_bytes=0
total_tokens=0

for f in "$WORKSPACE"/*.md; do
  [ -f "$f" ] || continue
  bytes=$(wc -c < "$f")
  lines=$(wc -l < "$f")
  tokens=$(python3 -c "t=open('$f').read(); print(round(len(t)/3.8))" 2>/dev/null || echo "?")
  total_bytes=$((total_bytes + bytes))
  [ "$tokens" != "?" ] && total_tokens=$((total_tokens + tokens))
  printf "  %-20s %6d bytes  %4d lines  ~%5d tokens\n" "$(basename $f)" "$bytes" "$lines" "$tokens"
done

echo "------------------------------------------------------"
printf "  %-20s %6d bytes            ~%5d tokens\n" "TOTAL" "$total_bytes" "$total_tokens"
echo ""

# Targets from Frank's Original Recipe
echo "TARGETS (from Frank's Original Recipe):"
echo "------------------------------------------------------"
echo "  SOUL.md              < 1,024 bytes  (< 270 tokens)"
echo "  AGENTS.md            < 2,048 bytes  (< 540 tokens)"
echo "  MEMORY.md            < 3,072 bytes  (< 810 tokens)"
echo "  TOOLS.md             < 1,024 bytes  (< 270 tokens)"
echo "  Total workspace      < 8,192 bytes  (<2,100 tokens)"
echo ""

# Status
echo "STATUS:"
echo "------------------------------------------------------"
check_file() {
  local file="$WORKSPACE/$1"
  local target=$2
  local name=$1
  if [ -f "$file" ]; then
    bytes=$(wc -c < "$file")
    if [ "$bytes" -le "$target" ]; then
      printf "  ✅ %-20s %d bytes (under %d target)\n" "$name" "$bytes" "$target"
    else
      over=$((bytes - target))
      printf "  ❌ %-20s %d bytes (%d over target)\n" "$name" "$bytes" "$over"
    fi
  fi
}

check_file "SOUL.md" 1024
check_file "AGENTS.md" 2048
check_file "MEMORY.md" 3072
check_file "TOOLS.md" 1024

echo ""
if [ "$total_bytes" -le 8192 ]; then
  echo "  ✅ TOTAL: $total_bytes bytes — under 8KB target"
else
  over=$((total_bytes - 8192))
  echo "  ❌ TOTAL: $total_bytes bytes — ${over} bytes over 8KB target"
fi

echo ""
echo "VAULT DIRECTORY:"
echo "------------------------------------------------------"
vault="$WORKSPACE/vault"
if [ -d "$vault" ]; then
  vault_files=$(find "$vault" -name "*.md" | wc -l)
  vault_bytes=$(find "$vault" -name "*.md" -exec cat {} \; | wc -c)
  echo "  ✅ vault/ exists: $vault_files files, $vault_bytes bytes"
  find "$vault" -name "*.md" | sort | while read f; do
    bytes=$(wc -c < "$f")
    rel="${f#$WORKSPACE/}"
    printf "     %-45s %6d bytes\n" "$rel" "$bytes"
  done
else
  echo "  ❌ vault/ not created yet"
fi

echo ""
echo "LOSSLESS-CLAW:"
echo "------------------------------------------------------"
config="${OPENCLAW_CONFIG:-$HOME/.openclaw/openclaw.json}"
if [ -f "$config" ]; then
  if python3 -c "import json; c=json.load(open('$config')); print(c.get('plugins',{}).get('entries',{}).get('lossless-claw',{}).get('enabled','not installed'))" 2>/dev/null | grep -q "True\|true"; then
    echo "  ✅ lossless-claw: installed and enabled"
    lcm_db="${LCM_DATABASE_PATH:-$HOME/.openclaw/lcm.db}"
    if [ -f "$lcm_db" ]; then
      db_size=$(wc -c < "$lcm_db")
      echo "  ✅ LCM database: $lcm_db ($db_size bytes)"
    else
      echo "  ⚠️  LCM database not yet created (will appear after first session)"
    fi
  else
    echo "  ❌ lossless-claw: not installed"
    echo "     Run: openclaw plugins install @martian-engineering/lossless-claw"
  fi
fi

echo ""
echo "======================================================"
