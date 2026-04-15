# anchor

Protect specific code regions from AI modification in Claude Code.

Anchor files, line ranges, functions, or entire folders — Claude can still **read** and reason about anchored code, but **cannot edit it**. Enforcement is mechanical via [PreToolUse hooks](https://docs.anthropic.com/en/docs/claude-code/hooks), not instruction-based.

## Why not just tell Claude "don't touch this file"?

Instructions in CLAUDE.md or conversation context can be forgotten after context compaction. Anchor uses Claude Code's hook system to **mechanically block** edits before they execute. No amount of context loss, prompt injection, or creative reinterpretation can bypass a hook that exits with code 2.

## Install

```bash
# Via Claude Code plugin marketplace
/plugin marketplace add donghaxkim/anchor

# Or manually
git clone https://github.com/donghaxkim/anchor-skill.git ~/.claude/plugins/anchor
```

Then run setup in your project:

```bash
python ~/.claude/plugins/anchor/scripts/anchor.py setup
```

This adds PreToolUse hooks to your project's `.claude/settings.json`.

## Usage

```bash
# Anchor a whole file
anchor add src/auth.py --desc "security-critical, do not modify"

# Anchor specific lines
anchor add src/billing.py:45-80 --desc "audited tax calculation"

# Anchor an entire folder
anchor add db/migrations/ --desc "production migrations, append-only"

# Anchor a function (Claude resolves the line range first)
# "don't touch the validateToken function"

# List all anchors with drift status
anchor list

# Check for unauthorized changes
anchor check

# Accept an intentional change
anchor update src/auth.py

# Remove an anchor
anchor remove src/auth.py
```

## How it works

```
User says "anchor src/auth.py"
        │
        ▼
  anchor.py add ──► Hashes file content (SHA-256)
        │            Writes entry to .anchors
        ▼
  .anchors file:
  file | src/auth.py | a8f3c2e1 | security-critical
        │
        ▼
  Claude tries to edit src/auth.py
        │
        ▼
  PreToolUse hook fires ──► enforce_edit.sh
        │                     Reads .anchors
        │                     Matches path
        ▼                     Exit 2 (BLOCK)
  Claude receives:
  "ANCHOR VIOLATION: src/auth.py is protected"
        │
        ▼
  Claude re-plans: suggests wrapper,
  modifies calling code, or asks user
  to remove the anchor
```

**Three layers of protection:**

| Layer | What it catches | How |
|-------|----------------|-----|
| `enforce_edit.sh` | All Edit/Write/MultiEdit tool calls | Path matching against `.anchors` |
| `enforce_bash.sh` | `sed -i`, `echo >`, `rm`, `tee`, `cp`, `mv` | Regex extraction + path matching |
| Deny rules | `anchor.py remove/update` via Bash | Claude Code permission system |

## Drift detection

Anchor tracks content by SHA-256 hash. When someone modifies anchored code outside Claude:

```bash
$ anchor check
DRIFTED: src/auth.py — hash was a8f3c2e1, now 5c47d694

$ git diff src/auth.py   # Review the change
$ anchor update src/auth.py   # Accept it
```

## Comparison with alternatives

| Feature | anchor | `.cursorignore` | CLAUDE.md rules | ai-guard |
|---------|--------|-----------------|-----------------|----------|
| Enforcement | Mechanical (hooks) | IDE-level | Instruction-based | Git hooks |
| Survives context compaction | Yes | N/A | No | N/A |
| Line-range granularity | Yes | No | No | No |
| Drift detection | Yes (SHA-256) | No | No | Yes |
| Works with Claude Code | Yes | No | Yes | Partial |
| Works with Cursor | Instruction-only | Yes | N/A | No |

## Cross-tool compatibility

The `SKILL.md` skill file works instruction-based on **Codex**, **Gemini CLI**, and **Cursor** too — Claude will respect anchor descriptions and avoid modifying protected regions. However, **mechanical hook enforcement** (the part that makes anchors unbypassable) only works in **Claude Code**, which is the only tool that supports PreToolUse hooks.

## Project structure

```
anchor/
├── SKILL.md                    # Skill definition (loaded by Claude Code)
├── scripts/
│   ├── anchor.py               # Core CLI (stdlib only, zero deps)
│   ├── enforce_edit.sh          # PreToolUse hook for Edit/Write
│   └── enforce_bash.sh          # PreToolUse hook for Bash
├── references/
│   ├── hook-setup.md            # Setup documentation
│   └── anchor-format.md         # .anchors file format spec
├── assets/
│   └── settings-template.json   # Hook config template
├── marketplace.json             # Plugin marketplace metadata
├── CHANGELOG.md
└── LICENSE                      # MIT
```

## License

MIT
