#!/usr/bin/env bash
# PreToolUse hook for Bash — catches common bypass patterns targeting anchored files.
# Best-effort: catches common patterns, false negatives acceptable, false positives NOT.
# Exit 0 = allow, Exit 2 = block.

set -euo pipefail

# Read JSON from stdin
INPUT=$(cat)

# Extract the command from tool input
COMMAND=$(python3 -c "
import json, sys
data = json.loads(sys.argv[1])
print(data.get('tool_input', {}).get('command', ''))
" "$INPUT" 2>/dev/null) || true

# If no command, allow
if [ -z "$COMMAND" ]; then
    exit 0
fi

# Find .anchors file
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

ANCHORS_FILE=$(find_anchors) || exit 0
PROJECT_ROOT=$(dirname "$ANCHORS_FILE")

# Collect all anchored targets into arrays
declare -a ANCHOR_FILES=()
declare -a ANCHOR_FOLDERS=()
declare -a ANCHOR_DESCS=()
declare -a ANCHOR_TARGETS=()

while IFS= read -r line; do
    [[ -z "$line" || "$line" == \#* ]] && continue

    entry_type=$(echo "$line" | cut -d'|' -f1 | xargs)
    entry_target=$(echo "$line" | cut -d'|' -f2 | xargs)
    entry_desc=$(echo "$line" | cut -d'|' -f4- | xargs)

    case "$entry_type" in
        file)
            ANCHOR_FILES+=("$entry_target")
            ANCHOR_DESCS+=("$entry_desc")
            ANCHOR_TARGETS+=("$entry_target")
            ;;
        lines)
            # Protect the whole file
            anchor_file="${entry_target%%:*}"
            ANCHOR_FILES+=("$anchor_file")
            ANCHOR_DESCS+=("$entry_desc")
            ANCHOR_TARGETS+=("$entry_target")
            ;;
        folder)
            ANCHOR_FOLDERS+=("$entry_target")
            ANCHOR_DESCS+=("$entry_desc")
            ANCHOR_TARGETS+=("$entry_target")
            ;;
    esac
done < "$ANCHORS_FILE"

# If no anchors, allow
if [ ${#ANCHOR_FILES[@]} -eq 0 ] && [ ${#ANCHOR_FOLDERS[@]} -eq 0 ]; then
    exit 0
fi

# Check if a path matches any anchor. Prints the matching anchor target and desc.
check_path() {
    local check_path="$1"

    # Normalize: make relative if absolute
    if [[ "$check_path" == /* ]]; then
        check_path=$(python3 -c "import os; print(os.path.relpath('$check_path', '$PROJECT_ROOT'))" 2>/dev/null) || return 1
    fi

    for i in "${!ANCHOR_FILES[@]}"; do
        if [ "$check_path" = "${ANCHOR_FILES[$i]}" ]; then
            echo "${ANCHOR_TARGETS[$i]}|${ANCHOR_DESCS[$i]}"
            return 0
        fi
    done

    for i in "${!ANCHOR_FOLDERS[@]}"; do
        case "$check_path" in
            "${ANCHOR_FOLDERS[$i]}"*)
                echo "${ANCHOR_TARGETS[$i]}|${ANCHOR_DESCS[$i]}"
                return 0
                ;;
        esac
    done

    return 1
}

# Use python to extract potential target paths from the command and check them
RESULT=$(python3 -c "
import re, sys

command = sys.argv[1]
anchor_files = sys.argv[2].split(':::') if sys.argv[2] else []
anchor_folders = sys.argv[3].split(':::') if sys.argv[3] else []

# Extract potential file paths from dangerous patterns
paths = set()

# sed -i / sed --in-place
for m in re.finditer(r'sed\s+(?:-[^i]*)?(?:-i|--in-place)\s+(?:\"[^\"]*\"|\'[^\']*\'|\S+)\s+([\w./\-]+)', command):
    paths.add(m.group(1))

# Also catch: sed -i'' 'pattern' file
for m in re.finditer(r'sed\s+-i\S*\s+(?:\"[^\"]*\"|\'[^\']*\'|\S+)\s+([\w./\-]+)', command):
    paths.add(m.group(1))

# echo/printf > or >> file (but not echo | something)
for m in re.finditer(r'(?:echo|printf)\s+.*?>{1,2}\s*([\w./\-]+)', command):
    paths.add(m.group(1))

# cat > file
for m in re.finditer(r'cat\s+.*?>\s*([\w./\-]+)', command):
    paths.add(m.group(1))

# cp ... dest (last arg)
for m in re.finditer(r'\bcp\s+(?:-\w+\s+)*\S+\s+([\w./\-]+)\s*$', command, re.MULTILINE):
    paths.add(m.group(1))

# mv ... dest (last arg)
for m in re.finditer(r'\bmv\s+(?:-\w+\s+)*\S+\s+([\w./\-]+)\s*$', command, re.MULTILINE):
    paths.add(m.group(1))

# tee file
for m in re.finditer(r'\btee\s+(?:-a\s+)?([\w./\-]+)', command):
    paths.add(m.group(1))

# rm file
for m in re.finditer(r'\brm\s+(?:-\w+\s+)*([\w./\-]+)', command):
    paths.add(m.group(1))

# python -c with open('file', 'w')
for m in re.finditer(r'(?:python3?)\s+-c\s+[\"\\'].*?open\([\"\\']([^\"\\']+ )[\"\\'].*?[\"w\\']', command):
    paths.add(m.group(1))

# Output paths one per line
for p in paths:
    print(p)
" "$COMMAND" "$(IFS=':::'; echo "${ANCHOR_FILES[*]:-}")" "$(IFS=':::'; echo "${ANCHOR_FOLDERS[*]:-}")" 2>/dev/null) || exit 0

# Check each extracted path against anchors
while IFS= read -r extracted_path; do
    [ -z "$extracted_path" ] && continue
    match=$(check_path "$extracted_path") && {
        target="${match%%|*}"
        desc="${match##*|}"
        echo "ANCHOR VIOLATION: Bash command targets protected file $target (reason: $desc). Do not attempt to bypass anchor protections via shell commands." >&2
        exit 2
    }
done <<< "$RESULT"

# No match — allow
exit 0
