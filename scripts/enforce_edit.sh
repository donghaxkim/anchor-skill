#!/usr/bin/env bash
# PreToolUse hook for Edit/Write/MultiEdit — blocks operations on anchored files.
# Reads JSON from stdin, checks file_path/path against .anchors entries.
# Exit 0 = allow, Exit 2 = block.

set -euo pipefail

# Read JSON from stdin
INPUT=$(cat)

# Extract the file path from tool input (Write uses file_path, Edit uses file_path too)
FILE_PATH=$(python3 -c "
import json, sys
data = json.loads(sys.argv[1])
ti = data.get('tool_input', {})
# Try file_path first (Edit, Write), then path as fallback
p = ti.get('file_path') or ti.get('path') or ''
print(p)
" "$INPUT" 2>/dev/null) || true

# If no file path found, allow
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Find .anchors file by walking up from cwd
find_anchors() {
    local dir="$PWD"
    while true; do
        if [ -f "$dir/.anchors" ]; then
            echo "$dir/.anchors"
            return 0
        fi
        local parent
        parent=$(dirname "$dir")
        if [ "$parent" = "$dir" ]; then
            return 1
        fi
        dir="$parent"
    done
}

ANCHORS_FILE=$(find_anchors) || exit 0  # No .anchors = allow

# Get the project root (directory containing .anchors)
PROJECT_ROOT=$(dirname "$ANCHORS_FILE")

# Make the file path relative to project root
REL_PATH=$(python3 -c "
import os, sys
fpath = sys.argv[1]
root = sys.argv[2]
# If absolute, make relative
if os.path.isabs(fpath):
    print(os.path.relpath(fpath, root))
else:
    # Already relative — normalize
    print(os.path.normpath(fpath))
" "$FILE_PATH" "$PROJECT_ROOT" 2>/dev/null) || exit 0

# Check each anchor entry
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ -z "$line" || "$line" == \#* ]] && continue

    # Parse: type | target | hash | description
    entry_type=$(echo "$line" | cut -d'|' -f1 | xargs)
    entry_target=$(echo "$line" | cut -d'|' -f2 | xargs)
    entry_desc=$(echo "$line" | cut -d'|' -f4- | xargs)

    case "$entry_type" in
        file)
            if [ "$REL_PATH" = "$entry_target" ]; then
                echo "ANCHOR VIOLATION: $entry_target is protected (reason: $entry_desc). Work around this region." >&2
                exit 2
            fi
            ;;
        lines)
            # Extract file portion from target (file.py:45-80 -> file.py)
            anchor_file="${entry_target%%:*}"
            if [ "$REL_PATH" = "$anchor_file" ]; then
                echo "ANCHOR VIOLATION: $entry_target is protected (reason: $entry_desc). Work around this region." >&2
                exit 2
            fi
            ;;
        folder)
            # Check if the file path starts with the folder path
            case "$REL_PATH" in
                "${entry_target}"*)
                    echo "ANCHOR VIOLATION: $entry_target is protected (reason: $entry_desc). Work around this region." >&2
                    exit 2
                    ;;
            esac
            ;;
    esac
done < "$ANCHORS_FILE"

# No match — allow
exit 0
