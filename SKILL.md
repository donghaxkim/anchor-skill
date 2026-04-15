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

# Anchor — Protect Code from AI Modification

Anchor protects specific code regions from AI modification. Anchored code can still be read and understood — Claude can reference it, reason about it, and use it as context — but Claude **cannot edit it**. Enforcement is mechanical: PreToolUse hooks intercept every Edit, Write, and Bash tool call and block operations targeting anchored files. This is not instruction-based (which can be forgotten after context compaction) — it's enforced by the Claude Code hook system.

## Parsing User Intent

Interpret user requests as follows:

| User says | Anchor type | Action |
|-----------|-------------|--------|
| `"anchor src/auth.py"` | Whole file | Anchor the entire file |
| `"protect lines 45-80 in billing.py"` | Line range | Anchor `billing.py:45-80` |
| `"don't touch the validateToken function"` | Symbol | Read the file, find the function's start and end lines, then anchor that range |
| `"lock down the migrations folder"` | Folder | Anchor `migrations/` (all files recursively) |
| `"be careful with the billing logic"` | Implicit | Ask the user to clarify which specific file or region they mean before anchoring |

For **symbol/function anchoring**: FIRST read the file to locate the function's exact start and end lines. THEN call `anchor.py add file.py:startline-endline --desc "functionName: reason"`. Never pass symbol names directly to anchor.py — always resolve to line ranges first.

## Running Anchor Commands

All commands use the `anchor.py` script in this skill's `scripts/` directory.

```bash
# Add anchors (always provide a description)
python <skill-path>/scripts/anchor.py add <target> --desc "reason"

# Target formats:
#   src/auth.py                    → whole file
#   src/billing.py:45-80           → line range
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

Replace `<skill-path>` with the absolute path to this skill's directory.

### First-time setup

Before anchors can be enforced, the user must run the setup command once per project. This installs PreToolUse hooks into `.claude/settings.json`. Read `references/hook-setup.md` for details on what the setup configures.

```bash
python <skill-path>/scripts/anchor.py setup
```

## When an Edit Is Blocked

When a PreToolUse hook blocks an edit, Claude receives a stderr message like:

```
ANCHOR VIOLATION: Lines 45-80 of src/billing.py are protected (reason: audited tax calculation). Work around this region.
```

When this happens:

1. **Do NOT** attempt the edit again or try alternative tools (`sed`, `echo`, `python -c`) to bypass the anchor.
2. **Acknowledge** the anchor to the user — explain which region is protected and why.
3. **Re-plan** the approach. Suggest alternatives:
   - Add new code above or below the anchored region
   - Modify calling code instead of the anchored code
   - Create a wrapper function that delegates to the anchored code
   - Ask the user if they want to temporarily remove the anchor
4. **Explain** the alternative approach before proceeding.

## Troubleshooting

**"File not found"**
Check the path. Use `find . -name "filename"` to locate the file. All paths in `.anchors` are relative to the project root.

**"Hash mismatch on check"**
Someone modified anchored code outside the AI session. Review the change with `git diff`. If the change was intentional, run `anchor.py update <target>` to accept the new content. If not, restore with `git checkout`.

**"Hook not firing"**
Run `/hooks` in Claude Code to verify hooks are installed. Re-run `anchor.py setup` if needed. Make sure the enforce scripts are executable (`chmod +x`).

**"Anchor on wrong lines after code was added above"**
Line-range anchors track by content hash, not just line numbers. Run `anchor.py check` to detect drift, then `anchor.py update <target>` if the content is still correct but lines shifted.
