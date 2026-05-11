#!/usr/bin/env bash
# update_handoff.sh
# Updates PROJECT_HANDOFF.md with current local git state.
# Run this after any meaningful change so the handoff stays current.
#
# Usage: bash scripts/update_handoff.sh
# Requires: git, bash/zsh, a text editor or sed

set -euo pipefail

cd "$(dirname "$0")/.."

TARGET="PROJECT_HANDOFF.md"
NOW=$(date +%Y-%m-%d)
BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")
COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_STATUS=$(git status --short 2>/dev/null || echo "unknown")
GIT_DIFF=$(git diff --stat 2>/dev/null | head -20 || echo "none")
GIT_DIFF_NAME=$(git diff --name-status 2>/dev/null | head -50 || echo "none")

echo "Updating PROJECT_HANDOFF.md..."
echo "  Branch: $BRANCH"
echo "  Commit: $COMMIT"
echo "  Date: $NOW"

TMP=$(mktemp)

# Update Last Updated
sed "s/^## Last Updated$/## Last Updated\n\n$NOW/" "$TARGET" > "$TMP"

# Update branch
sed -i "s/| Local branch.*$/| \`$BRANCH\` |/" "$TMP"

# Update commit
sed -i "s/| Local commit.*$/| \`$COMMIT\` |/" "$TMP"

# Update Changed files block
python3 -c "
import re

with open('$TARGET', 'r') as f:
    content = f.read()

# Find the Exact Files Changed section
pattern = r'(## Exact Files Changed\n\n```text\n).*?(\n```)'
replacement = r'\1' + '''git diff --name-status (not run — run manually)
Check git status below for actual changes:
''' + GIT_DIFF_NAME.strip() + r'''
\2'''

# Also update Commands Run section with current values
content = re.sub(
    r'(\| git branch --show-current \| )[^|]+',
    r'\1' + BRANCH,
    content
)
content = re.sub(
    r'(\| git rev-parse --short HEAD \| )[^|]+',
    r'\1' + COMMIT,
    content
)

with open('$TMP', 'w') as f:
    f.write(content)
"

if command -v python3 &> /dev/null; then
    python3 - <<'PYEOF'
import datetime, re, os, subprocess

target = "PROJECT_HANDOFF.md"
now = datetime.date.today().isoformat()

branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip() or "unknown"
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
diff_names = subprocess.run(["git", "diff", "--name-status"], capture_output=True, text=True).stdout.strip()[:2000] or "none"

with open(target, "r") as f:
    content = f.read()

content = re.sub(r"^(\\| Last Updated \\| )[^|]+", rf"\1{now}", content, flags=re.MULTILINE)
content = re.sub(r"(\\| Local branch \\| )`[^`]+`", rf"\1`{branch}`", content)
content = re.sub(r"(\\| Local commit \\| )`[^`]+`", rf"\1`{commit}`", content)

block = f"```text\n{diff_names}\n```"
content = re.sub(r"## Exact Files Changed\n\n```text\n```text\n```", f"## Exact Files Changed\n\n{block}", content)
content = re.sub(r"## Exact Files Changed\n\n```text\n[^`]*```", f"## Exact Files Changed\n\n{block}", content)

with open(target, "w") as f:
    f.write(content)

print("Updated PROJECT_HANDOFF.md")
PYEOF
else
    echo "Python3 not available — manual update needed in $TARGET"
fi

echo "Done. Review $TARGET and commit changes."