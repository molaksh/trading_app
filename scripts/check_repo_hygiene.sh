#!/bin/bash
#
# Lightweight CI hygiene check - fails if repo structure violates conventions
# Run: bash scripts/check_repo_hygiene.sh
#
# Prevents:
# - Temporary notebooks outside docs/archive/
# - Scratch files in project root
# - Audit/temp files scattered around
#
# Allows:
# - Legitimate docs in docs/
# - Legacy code in core/strategies/crypto/legacy/
# - Archive files in docs/archive/
#

set -e  # Exit on any error

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAILED=0

echo "=========================================="
echo "Repository Hygiene Check"
echo "=========================================="
echo ""

# Check 1: No notebooks in root (except in docs/archive/)
echo "[1/5] Checking for notebooks outside docs/archive/..."
NOTEBOOKS=$(find "$REPO_ROOT" -maxdepth 2 -type f -name "*.ipynb" \
  ! -path "*/docs/archive/*" \
  ! -path "*/.git/*" \
  ! -path "*/.venv/*" \
  ! -path "*/.pytest_cache/*" 2>/dev/null | grep -v ".venv" | grep -v ".git" || true)

if [ -n "$NOTEBOOKS" ]; then
  echo "❌ FAIL: Found notebooks outside docs/archive/:"
  echo "$NOTEBOOKS" | sed 's/^/  - /'
  FAILED=1
else
  echo "✅ PASS: No notebooks outside docs/archive/"
fi
echo ""

# Check 2: No root-level *audit* files
echo "[2/5] Checking for audit files in root..."
AUDIT_FILES=$(find "$REPO_ROOT" -maxdepth 1 -type f -name "*audit*" 2>/dev/null || true)

if [ -n "$AUDIT_FILES" ]; then
  echo "❌ FAIL: Found audit files in root:"
  echo "$AUDIT_FILES" | sed 's/^/  - /'
  FAILED=1
else
  echo "✅ PASS: No audit files in root"
fi
echo ""

# Check 3: No root-level *scratch* files
echo "[3/5] Checking for scratch files in root..."
SCRATCH_FILES=$(find "$REPO_ROOT" -maxdepth 1 -type f -name "*scratch*" 2>/dev/null || true)

if [ -n "$SCRATCH_FILES" ]; then
  echo "❌ FAIL: Found scratch files in root:"
  echo "$SCRATCH_FILES" | sed 's/^/  - /'
  FAILED=1
else
  echo "✅ PASS: No scratch files in root"
fi
echo ""

# Check 4: No root-level *tmp* files (allow .tmp directories)
echo "[4/5] Checking for temp files in root..."
TMP_FILES=$(find "$REPO_ROOT" -maxdepth 1 -type f -name "*tmp*" 2>/dev/null || true)

if [ -n "$TMP_FILES" ]; then
  echo "❌ FAIL: Found temp files in root:"
  echo "$TMP_FILES" | sed 's/^/  - /'
  FAILED=1
else
  echo "✅ PASS: No temp files in root"
fi
echo ""

# Check 5: Verify archive structure exists
echo "[5/5] Checking archive structure..."
if [ ! -d "$REPO_ROOT/docs/archive/internal" ]; then
  echo "⚠️  WARNING: docs/archive/internal/ directory missing"
  echo "    This is OK if no internal docs have been archived yet."
else
  echo "✅ PASS: docs/archive/internal/ exists"
fi
echo ""

# Summary
echo "=========================================="
if [ $FAILED -eq 0 ]; then
  echo "✅ All hygiene checks PASSED"
  echo "=========================================="
  exit 0
else
  echo "❌ Some hygiene checks FAILED"
  echo "=========================================="
  echo ""
  echo "How to fix:"
  echo "  1. Move temporary files to docs/archive/internal/"
  echo "  2. Move notebooks to docs/archive/"
  echo "  3. Commit with message: 'Chore: Clean up temp files'"
  echo ""
  exit 1
fi
