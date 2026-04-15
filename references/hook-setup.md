# Hook Setup — Anchor Enforcement

## What Hooks Do

PreToolUse hooks intercept Claude's tool calls before they execute. The anchor enforcement scripts check if the target file is protected and block the operation if so. Two hooks are installed:

- **enforce_edit.sh** — Intercepts `Edit`, `Write`, and `MultiEdit` tool calls. Extracts the file path from the tool input and checks it against `.anchors` entries.
- **enforce_bash.sh** — Intercepts `Bash` tool calls. Scans the command for common file-writing patterns (`sed -i`, `echo >`, `rm`, `tee`, etc.) and checks extracted paths against `.anchors`.

## Automatic Setup

Run the setup command from the skill's scripts directory:

```bash
python <skill-path>/scripts/anchor.py setup
```

This will:
1. Create `.claude/settings.json` if it doesn't exist
2. Add PreToolUse hook entries for Edit/Write/MultiEdit and Bash
3. Add deny rules preventing Claude from editing `.anchors` itself
4. Preserve any existing hooks and settings (merges, doesn't overwrite)

## Manual Setup

If automatic setup fails, add the following to `.claude/settings.json` in your project root:

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

Replace `<absolute-path-to-skill>` with the actual absolute path to the anchor skill directory.

## Verifying Setup

Run `/hooks` in Claude Code to see all configured hooks. The anchor enforcement hooks should appear under PreToolUse with matchers for `Edit|Write|MultiEdit` and `Bash`.

## Self-Protection

The deny rules on `.anchors` prevent Claude from editing the anchors file itself. Only humans should modify anchors — either via the CLI commands (`anchor.py add/remove/update`) or by manually editing `.anchors`. This prevents Claude from circumventing protections by modifying the anchor registry.
