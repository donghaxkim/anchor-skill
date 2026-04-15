# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-04-15

### Added
- Core `anchor.py` CLI with `add`, `remove`, `list`, `check`, `update`, and `setup` commands
- `enforce_edit.sh` — PreToolUse hook blocking Edit/Write/MultiEdit on anchored files
- `enforce_bash.sh` — PreToolUse hook catching common bash bypass patterns (sed -i, echo >, rm, tee, etc.)
- `SKILL.md` with trigger phrases, intent parsing, command reference, and troubleshooting
- `.anchors` file format: human-readable, pipe-delimited, git-committable
- SHA-256 drift detection for files, line ranges, and folders
- Automatic setup command that merges hook config into `.claude/settings.json`
- Deny rules preventing Claude from editing `.anchors` or running `anchor.py remove/update` via Bash
- Project root auto-detection (walks up looking for `.anchors`, `.git`, or `.claude`)
- Rejection of targets outside the project root
- Reference docs for hook setup and `.anchors` file format
