#!/usr/bin/env bash
set -euo pipefail

# Regenerate .claude/CLAUDE.md by concatenating the global ~/.claude/CLAUDE.md
# with this repo's root CLAUDE.md. Docker sandboxes only read project-level
# config (not ~/.claude), so this keeps a self-contained copy in sync.
#
# Usage: scripts/refresh-sandbox-claude.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GLOBAL_CLAUDE_MD="${HOME}/.claude/CLAUDE.md"
ROOT_CLAUDE_MD="${PROJECT_ROOT}/CLAUDE.md"
OUTPUT="${PROJECT_ROOT}/.claude/CLAUDE.md"
TMP_OUTPUT="$(mktemp)"

trap 'rm -f "${TMP_OUTPUT}"' EXIT

echo "Global source: ${GLOBAL_CLAUDE_MD}"
echo "Repo source:   ${ROOT_CLAUDE_MD}"
echo "Output:        ${OUTPUT}"

if [[ ! -f "${GLOBAL_CLAUDE_MD}" ]]; then
  echo "error: ${GLOBAL_CLAUDE_MD} not found" >&2
  exit 1
fi

if [[ ! -f "${ROOT_CLAUDE_MD}" ]]; then
  echo "error: ${ROOT_CLAUDE_MD} not found" >&2
  exit 1
fi

cat "${GLOBAL_CLAUDE_MD}" > "${TMP_OUTPUT}"
printf '\n---\n\n' >> "${TMP_OUTPUT}"
cat "${ROOT_CLAUDE_MD}" >> "${TMP_OUTPUT}"

mv "${TMP_OUTPUT}" "${OUTPUT}"
trap - EXIT

echo "Regenerated $(wc -l < "${OUTPUT}") lines."
