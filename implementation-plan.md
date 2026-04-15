# Anchor — Implementation Plan

> This document is a complete implementation spec for the `anchor` Claude Code skill. It is designed to be handed to Claude Code as a single instruction file. Build everything described below.

---

## Overview

Build a Claude Code skill called `anchor` that lets users protect specific parts of their codebase from AI modification. Users can "anchor" files, line ranges, functions/symbols, or folders. Once anchored, Claude is mechanically blocked from editing those regions via PreToolUse hooks. Claude can still read and understand anchored code — it just can't modify it.

The skill has three layers:
1. **SKILL.md** — Instructions that teach Claude the anchoring workflow
2. **scripts/** — Python and Bash scripts that handle anchoring logic and enforcement
3. **references/** — Setup guides and format specs loaded only when needed

---

## File Structure

Create this exact directory structure:

```
anchor/
├── SKILL.md
├── scripts/
│   ├── anchor.py
│   ├── enforce_edit.sh
│   └── enforce_bash.sh
├── references/
│   ├── hook-setup.md
│   └── anchor-format.md
└── assets/
    └── settings-template.json
```

---

## File 1: SKILL.md

This is the main skill file. It must have YAML frontmatter followed by markdown instructions.

### Frontmatter

```yaml
---
name: anchor
description: >
  Protect specific code regions from AI modification. Lets users "anchor"
  files, line ranges, functions/symbols, or folders so Claude mechanically
  cannot edit them while still being able to read and understand the code.
  Use this skill whenever a user says "anchor", "lock", "protect", "freeze",
  "don't touch", "hands off", "do not modify", or refers to code that
  should not be changed. Also use when a user asks to "check anchors",
  "verify protected code", "show what's locked", or wants to manage
  protected regions. Use this even for implicit requests like "be careful
  with auth.py" or "leave the payment logic alone". Do NOT use for HTML
  anchor tags or unrelated uses of the word "anchor".
---
```

### Body Content

The SKILL.md body should cover these sections in this order. Write it in clear, imperative markdown. Keep it under 400 lines.

#### Section 1: What this skill does
- One paragraph explaining that anchor protects code from AI modification
- Clarify that anchored code can still be read/understood, just not edited
- Mention that enforcement is mechanical (hooks), not instruction-based

#### Section 2: Parsing user intent
Explain how to interpret different user requests:
- `"anchor src/auth.py"` → whole file
- `"protect lines 45-80 in billing.py"` → line range
- `"don't touch the validateToken function"` → symbol-based (resolve the function name to its line range in the file first, then anchor those lines)
- `"lock down the migrations folder"` → folder (all files recursively)
- `"be careful with the billing logic"` → implicit request, ask the user to clarify which specific file/region they mean before anchoring

#### Section 3: Running anchor commands
Document how to call the anchor.py script. Include exact command examples:

```bash
# Add anchors (always provide a description)
python <skill-path>/scripts/anchor.py add <target> --desc "reason"

# Target formats:
#   src/auth.py                    → whole file
#   src/billing.py:45-80           → line range  
#   src/middleware.ts:validateToken → symbol (Claude must first find the
#                                    function's line range, then anchor those lines)
#   src/migrations/                → folder (trailing slash required)

# List all anchors with status
python <skill-path>/scripts/anchor.py list

# Check for drift (hash mismatches)
python <skill-path>/scripts/anchor.py check

# Remove an anchor
python <skill-path>/scripts/anchor.py remove <target>

# Update hash after intentional human change
python <skill-path>/scripts/anchor.py update <target>

# First-time setup: install enforcement hooks
python <skill-path>/scripts/anchor.py setup
```

Important instruction: When the user asks to anchor a symbol/function name, Claude should FIRST read the file to find the function's start and end lines, THEN call `anchor.py add file.py:startline-endline --desc "function_name: description"`. Do not pass symbol names directly to anchor.py — always resolve to line ranges first.

#### Section 4: When an edit is blocked
Explain what happens when the PreToolUse hook blocks an edit and how Claude should respond:

1. Claude will receive a stderr message like: `"ANCHOR VIOLATION: Lines 45-80 of src/billing.py are protected (reason: audited tax calculation). Work around this region."`
2. Do NOT attempt the edit again or try alternative tools (sed, echo, python) to bypass
3. Acknowledge the anchor to the user
4. Re-plan the approach. Suggest alternatives:
   - Add new code above or below the anchored region
   - Modify calling code instead of the anchored code
   - Create a wrapper function
   - Ask the user if they want to temporarily remove the anchor
5. Explain the alternative approach before proceeding

#### Section 5: First-time setup
Tell Claude to read `references/hook-setup.md` when a user needs to set up enforcement hooks for the first time. The `anchor.py setup` command handles this automatically, but the reference doc explains what it does.

#### Section 6: Troubleshooting
Cover these cases:
- **"File not found"**: Check the path. Use `find . -name "filename"` to locate it.
- **"Hash mismatch on check"**: Someone modified anchored code outside the AI session. Review the change with `git diff`. If intentional, run `anchor.py update`. If not, restore with `git checkout`.
- **"Hook not firing"**: Run `/hooks` in Claude Code to verify hooks are installed. Re-run `anchor.py setup` if needed.
- **"Anchor on wrong lines after code was added above"**: Line-range anchors track by content hash, not just line numbers. Run `anchor.py check` to detect drift, then `anchor.py update` if the content is still correct but lines shifted.

---

## File 2: scripts/anchor.py

This is the core CLI script. It must be a single Python file with zero external dependencies (stdlib only). Use `argparse` for the CLI interface.

### Commands to implement:

#### `add <target> [--desc DESCRIPTION]`
- Parse the target string:
  - `path/to/file.py` → type="file"
  - `path/to/file.py:45-80` → type="lines", extract start_line and end_line
  - `path/to/dir/` → type="folder" (trailing slash)
- Validate the target exists on the filesystem
- Compute SHA-256 hash of the content:
  - For files: hash the entire file content
  - For line ranges: read the file, extract lines start through end (1-indexed, inclusive), hash that substring
  - For folders: hash a sorted concatenation of all file paths within the folder (this is a lightweight check that the folder structure hasn't changed — individual files within an anchored folder are each protected from edits by path prefix matching in the hook, not by hash)
- Write an entry to `.anchors` file at the project root (create if doesn't exist)
- Print confirmation: `Anchored <target> (<type>) — "<description>"`
- If the target is already anchored, print a message and do nothing

#### `remove <target>`
- Find the matching entry in `.anchors` and remove it
- Print confirmation: `Removed anchor: <target>`
- If not found, print error and exit 1

#### `list`
- Read `.anchors` and print all entries in a readable table format
- For each entry, show: target, type, description, and status (OK or DRIFTED)
- Status is determined by re-hashing current content and comparing
- If `.anchors` doesn't exist or is empty, print "No anchors set."

#### `check`
- Like `list` but only reports problems
- For each entry, re-hash and compare
- Print mismatches with the target and what changed
- Exit 0 if all OK, exit 1 if any drift detected

#### `update <target>`
- Find the entry in `.anchors`
- Re-hash the current content
- Update the stored hash
- Print: `Updated hash for <target>`

#### `setup`
- Check if `.claude/settings.json` exists at the project root
- If it exists, read it and merge the hook configuration (don't overwrite existing hooks)
- If it doesn't exist, create it with the hook configuration
- The hook configuration should add PreToolUse hooks for both Edit/Write and Bash tools pointing to the enforce scripts
- Also add deny rules for editing the `.anchors` file itself
- Print what was configured
- See the settings-template.json asset for the exact structure

### `.anchors` file format

One entry per line. Fields separated by ` | ` (space-pipe-space). Lines starting with `#` are comments.

```
# .anchors — managed by anchor skill
# Format: type | target | hash | description
file | src/auth.py | a8f3c2e1 | authentication module, security-critical
lines | src/billing.py:45-80 | 7b2e1d4f | audited tax calculation logic
folder | db/migrations/ | c9d0e3a2 | production migrations, append-only
```

Hash values should be the first 8 characters of the SHA-256 hex digest (for readability in the file, but use the full hash internally for comparison).

### Important implementation details:
- All paths should be stored relative to the project root (where `.anchors` lives)
- The script should auto-detect the project root by looking for `.anchors`, `.git`, or `.claude` directory, walking up from cwd
- Use `#!/usr/bin/env python3` shebang
- All output should go to stdout for normal messages, stderr for errors
- Exit codes: 0 = success, 1 = error or drift detected

---

## File 3: scripts/enforce_edit.sh

This is the PreToolUse hook script for Edit and Write tool calls. It receives JSON on stdin from Claude Code's hook system.

### Behavior:

1. Read JSON from stdin
2. Extract `tool_input.file_path` (for Write tool) or `tool_input.path` (for Edit tool) from the JSON using `jq` or python
3. If no file path found, exit 0 (allow — not a file operation)
4. Find the `.anchors` file by walking up from the current directory
5. If no `.anchors` file exists, exit 0 (allow — no anchors configured)
6. Read each entry in `.anchors`:
   - For `file` type entries: check if the edit target path matches the anchored path
   - For `lines` type entries: check if the edit target path matches the file portion. If it does, this is a violation (we block the entire file if any line range within it is anchored, because determining the exact lines being edited from the tool input is unreliable)
   - For `folder` type entries: check if the edit target path starts with the folder path
7. If a match is found:
   - Write to stderr: `ANCHOR VIOLATION: <target> is protected (reason: <description>). Work around this region.`
   - Exit 2 (blocking error)
8. If no match: exit 0 (allow)

### Implementation notes:
- Use `#!/usr/bin/env bash`
- Use python3 inline (via `python3 -c "..."`) for JSON parsing since `jq` may not be installed everywhere. Alternatively, write a small python one-liner that reads stdin JSON and extracts the path.
- Keep it fast — this runs on every edit/write operation
- Make paths relative before comparing (both the tool input path and the anchored paths)

---

## File 4: scripts/enforce_bash.sh

This is the PreToolUse hook script for Bash tool calls. It catches attempts to modify anchored files via shell commands instead of the Edit/Write tools.

### Behavior:

1. Read JSON from stdin
2. Extract `tool_input.command` from the JSON
3. Check if the command contains file-writing patterns that target anchored files:
   - `sed -i` or `sed --in-place` followed by a path
   - `echo ... >` or `echo ... >>` followed by a path (but not `echo ... | something`)
   - `cat ... >` followed by a path
   - `cp ... <destination>` where destination is an anchored file
   - `mv ... <destination>` where destination is an anchored file
   - `tee` followed by a path
   - `python3 -c` or `python -c` containing `open(` with `'w'` and an anchored path
   - `rm` followed by an anchored path
4. For each pattern match, extract the target file path from the command
5. Check the extracted path against `.anchors` entries (same logic as enforce_edit.sh)
6. If a match is found:
   - Write to stderr: `ANCHOR VIOLATION: Bash command targets protected file <path> (reason: <description>). Do not attempt to bypass anchor protections via shell commands.`
   - Exit 2 (blocking error)
7. If no match: exit 0 (allow)

### Implementation notes:
- This does NOT need to be perfect — it's a best-effort catch for common bypass patterns
- Use regex matching for the command patterns
- False negatives are acceptable (some exotic bypass might slip through)
- False positives are NOT acceptable (don't block legitimate bash commands)
- When in doubt, allow the command (exit 0)
- Keep it fast

---

## File 5: references/hook-setup.md

A reference document explaining how the enforcement hooks work and how to set them up manually. This is only loaded when Claude needs to help a user with setup.

### Content:

Explain the following:

1. **What hooks do**: PreToolUse hooks intercept Claude's tool calls before they execute. The enforce scripts check if the target file is anchored and block the operation if so.

2. **Automatic setup**: Running `python <skill-path>/scripts/anchor.py setup` will configure everything automatically. It modifies `.claude/settings.json` to add the hook entries.

3. **Manual setup**: If automatic setup fails, explain how to manually add the following to `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Edit(.anchors)",
      "Write(.anchors)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-skill>/scripts/enforce_edit.sh"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to-skill>/scripts/enforce_bash.sh"
          }
        ]
      }
    ]
  }
}
```

4. **Verifying setup**: Run `/hooks` in Claude Code to see all configured hooks. The anchor enforcement hooks should appear under PreToolUse.

5. **Self-protection**: The deny rules on `.anchors` prevent Claude from editing the anchors file itself. Only humans should modify anchors (via the CLI commands or manual editing).

---

## File 6: references/anchor-format.md

A reference document explaining the `.anchors` file format in detail. Only loaded when debugging.

### Content:

Document the file format:
- Location: project root (same directory as `.git` or `.claude`)
- One entry per line
- Fields separated by ` | ` (space-pipe-space)
- Lines starting with `#` are comments
- Fields: `type | target | hash | description`
- Types: `file`, `lines`, `folder`
- Target format: relative path from project root, with optional `:start-end` for line ranges
- Hash: first 8 characters of SHA-256 hex digest of the protected content
- Description: human-readable reason for the anchor (freeform text, no pipe characters)

Include examples of each entry type and explain what gets hashed for each.

---

## File 7: assets/settings-template.json

A JSON template showing the Claude Code settings needed for enforcement. The `setup` command in anchor.py reads this as a reference.

```json
{
  "permissions": {
    "deny": [
      "Edit(.anchors)",
      "Write(.anchors)"
    ]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "SKILL_PATH/scripts/enforce_edit.sh"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "SKILL_PATH/scripts/enforce_bash.sh"
          }
        ]
      }
    ]
  }
}
```

Note: `SKILL_PATH` is a placeholder that `anchor.py setup` replaces with the actual absolute path to the skill's scripts directory.

---

## Testing

After building everything, test these scenarios:

### Test 1: Anchor a whole file
```bash
echo "def secret(): pass" > /tmp/test_auth.py
python anchor/scripts/anchor.py add /tmp/test_auth.py --desc "auth module"
python anchor/scripts/anchor.py list
```
Expected: Entry appears in `.anchors`, list shows it with status OK.

### Test 2: Anchor a line range
```bash
python anchor/scripts/anchor.py add src/billing.py:10-25 --desc "tax logic"
python anchor/scripts/anchor.py list
```
Expected: Entry with type `lines` appears.

### Test 3: Check drift detection
```bash
python anchor/scripts/anchor.py add /tmp/test_auth.py --desc "test"
echo "modified" >> /tmp/test_auth.py
python anchor/scripts/anchor.py check
```
Expected: Reports hash mismatch, exits with code 1.

### Test 4: Hook enforcement
```bash
echo '{"tool_input":{"path":"src/auth.py"}}' | bash anchor/scripts/enforce_edit.sh
```
Expected: If src/auth.py is in `.anchors`, exits 2 with violation message. Otherwise exits 0.

### Test 5: Setup command
```bash
python anchor/scripts/anchor.py setup
cat .claude/settings.json
```
Expected: Settings file contains the hook configuration with correct paths.

---

## Key Design Decisions

1. **Line-range anchors block the entire file in the hook**, not just the specific lines. This is because reliably determining which exact lines an Edit tool call modifies is fragile. The SKILL.md instructions tell Claude which lines are protected so it can plan around them — the hook is the safety net that catches everything.

2. **Symbol/function anchoring resolves to line ranges at anchor-time.** The anchor.py script does NOT do AST parsing. Instead, the SKILL.md instructs Claude to read the file, find the function's line range, and then call `anchor.py add file:start-end`. This keeps the script simple and language-agnostic.

3. **The `.anchors` file is human-readable and git-committable.** Teams can share anchors via version control.

4. **Hash truncation to 8 chars in the file** is for readability only. The full SHA-256 is used internally for comparison. The 8-char prefix is sufficient for detecting drift (collision probability is negligible for this use case).

5. **enforce_bash.sh is best-effort.** It catches common patterns but cannot catch every possible way to write to a file via bash. This is acceptable — it's defense in depth, not a security boundary.

6. **The skill does NOT add CLAUDE.md instructions.** Enforcement is entirely mechanical via hooks. This avoids the well-documented problem of Claude ignoring CLAUDE.md rules after context compaction.

---

## Build Order

Build the files in this order:
1. `scripts/anchor.py` — Core logic, test it standalone
2. `scripts/enforce_edit.sh` — Hook script, test with piped JSON
3. `scripts/enforce_bash.sh` — Bash hook, test with piped JSON
4. `SKILL.md` — Instructions referencing the scripts
5. `references/hook-setup.md` — Setup documentation
6. `references/anchor-format.md` — Format documentation
7. `assets/settings-template.json` — Settings template

Make all `.sh` files executable (`chmod +x`).