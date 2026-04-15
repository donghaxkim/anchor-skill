# .anchors File Format

## Location

The `.anchors` file lives at the project root — the same directory as `.git` or `.claude`. It is human-readable and designed to be committed to version control so teams can share anchors.

## Format

- One entry per line
- Fields separated by ` | ` (space-pipe-space)
- Lines starting with `#` are comments
- Empty lines are ignored

## Fields

```
type | target | hash | description
```

| Field | Description |
|-------|-------------|
| **type** | One of: `file`, `lines`, `folder` |
| **target** | Relative path from project root, with optional `:start-end` for line ranges |
| **hash** | First 8 characters of the SHA-256 hex digest of the protected content |
| **description** | Human-readable reason for the anchor (freeform text, avoid pipe characters) |

## Entry Types

### `file` — Whole file

```
file | src/auth.py | a8f3c2e1 | authentication module, security-critical
```

**What gets hashed**: The entire file content as a UTF-8 string.

### `lines` — Line range

```
lines | src/billing.py:45-80 | 7b2e1d4f | audited tax calculation logic
```

**What gets hashed**: Lines 45 through 80 (1-indexed, inclusive), joined as a single string. Only these lines are hashed, but the enforcement hook blocks edits to the **entire file** if any line range within it is anchored.

### `folder` — Directory (recursive)

```
folder | db/migrations/ | c9d0e3a2 | production migrations, append-only
```

**What gets hashed**: A sorted, newline-separated list of all relative file paths within the folder. This detects structural changes (files added or removed). Individual files within the folder are protected from edits by path-prefix matching in the hook, not by content hash.

## Example File

```
# .anchors — managed by anchor skill
# Format: type | target | hash | description
file | src/auth.py | a8f3c2e1 | authentication module, security-critical
lines | src/billing.py:45-80 | 7b2e1d4f | audited tax calculation logic
folder | db/migrations/ | c9d0e3a2 | production migrations, append-only
file | config/prod.yaml | 1f4e7a3b | production config, do not modify
```
