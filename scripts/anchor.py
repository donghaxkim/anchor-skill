#!/usr/bin/env python3
"""anchor — protect code regions from AI modification.

CLI tool for managing anchored (protected) files, line ranges, and folders.
Zero external dependencies — stdlib only.
"""

import argparse
import hashlib
import json
import os
import sys

ANCHORS_FILE = ".anchors"
ANCHORS_HEADER = "# .anchors — managed by anchor skill\n# Format: type | target | hash | description\n"
SETTINGS_REL = os.path.join(".claude", "settings.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_project_root():
    """Walk up from cwd looking for .anchors, .git, or .claude."""
    d = os.getcwd()
    while True:
        for marker in (ANCHORS_FILE, ".git", ".claude"):
            if os.path.exists(os.path.join(d, marker)):
                return d
        parent = os.path.dirname(d)
        if parent == d:
            # No marker found — default to cwd
            return os.getcwd()
        d = parent


def anchors_path():
    return os.path.join(find_project_root(), ANCHORS_FILE)


def read_anchors():
    """Return list of dicts: {type, target, hash, description}."""
    path = anchors_path()
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            entries.append({
                "type": parts[0],
                "target": parts[1],
                "hash": parts[2],
                "description": " | ".join(parts[3:]),  # description may contain |
            })
    return entries


def write_anchors(entries):
    path = anchors_path()
    with open(path, "w") as f:
        f.write(ANCHORS_HEADER)
        for e in entries:
            f.write(f"{e['type']} | {e['target']} | {e['hash']} | {e['description']}\n")


def hash_content(content: str) -> str:
    """Full SHA-256 hex digest of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def short_hash(full_hash: str) -> str:
    return full_hash[:8]


def compute_hash(target_type, target, root):
    """Compute the SHA-256 hash for a target. Returns (full_hash, error_msg)."""
    if target_type == "file":
        fpath = os.path.join(root, target)
        if not os.path.isfile(fpath):
            return None, f"File not found: {fpath}"
        with open(fpath, "r") as f:
            return hash_content(f.read()), None

    elif target_type == "lines":
        # target looks like path/to/file.py:45-80
        file_part, range_part = target.rsplit(":", 1)
        fpath = os.path.join(root, file_part)
        if not os.path.isfile(fpath):
            return None, f"File not found: {fpath}"
        start, end = [int(x) for x in range_part.split("-")]
        with open(fpath, "r") as f:
            lines = f.readlines()
        # 1-indexed, inclusive
        selected = lines[start - 1 : end]
        return hash_content("".join(selected)), None

    elif target_type == "folder":
        dpath = os.path.join(root, target)
        if not os.path.isdir(dpath):
            return None, f"Folder not found: {dpath}"
        # Hash sorted list of relative file paths within the folder
        file_list = []
        for dirpath, _, filenames in os.walk(dpath):
            for fname in filenames:
                rel = os.path.relpath(os.path.join(dirpath, fname), root)
                file_list.append(rel)
        file_list.sort()
        return hash_content("\n".join(file_list)), None

    return None, f"Unknown type: {target_type}"


def parse_target(target_str):
    """Parse a target string into (type, normalized_target).

    Returns (type, target) where target is relative to project root.
    """
    root = find_project_root()
    # Make path relative to project root
    if os.path.isabs(target_str):
        # Handle absolute paths — make relative
        rel = os.path.relpath(target_str, root)
    else:
        rel = target_str

    # Check for line range (file.py:45-80)
    if ":" in rel:
        file_part, range_part = rel.rsplit(":", 1)
        if "-" in range_part and all(p.isdigit() for p in range_part.split("-")):
            return "lines", f"{file_part}:{range_part}"

    # Check for folder (trailing slash or is a directory)
    if rel.endswith("/"):
        return "folder", rel
    full = os.path.join(root, rel)
    if os.path.isdir(full):
        if not rel.endswith("/"):
            rel += "/"
        return "folder", rel

    return "file", rel


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_add(args):
    root = find_project_root()
    target_type, target = parse_target(args.target)

    # Validate existence
    if target_type == "file":
        if not os.path.isfile(os.path.join(root, target)):
            print(f"Error: File not found: {target}", file=sys.stderr)
            sys.exit(1)
    elif target_type == "lines":
        file_part = target.rsplit(":", 1)[0]
        if not os.path.isfile(os.path.join(root, file_part)):
            print(f"Error: File not found: {file_part}", file=sys.stderr)
            sys.exit(1)
    elif target_type == "folder":
        if not os.path.isdir(os.path.join(root, target)):
            print(f"Error: Folder not found: {target}", file=sys.stderr)
            sys.exit(1)

    # Check for duplicates
    entries = read_anchors()
    for e in entries:
        if e["target"] == target:
            print(f"Already anchored: {target}")
            return

    # Compute hash
    full_h, err = compute_hash(target_type, target, root)
    if err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    desc = args.desc or "no description"
    entries.append({
        "type": target_type,
        "target": target,
        "hash": short_hash(full_h),
        "description": desc,
    })
    write_anchors(entries)
    print(f"Anchored {target} ({target_type}) — \"{desc}\"")


def cmd_remove(args):
    target_type, target = parse_target(args.target)
    entries = read_anchors()
    new_entries = [e for e in entries if e["target"] != target]
    if len(new_entries) == len(entries):
        print(f"Error: No anchor found for: {target}", file=sys.stderr)
        sys.exit(1)
    write_anchors(new_entries)
    print(f"Removed anchor: {target}")


def cmd_list(args):
    entries = read_anchors()
    if not entries:
        print("No anchors set.")
        return

    root = find_project_root()
    # Table header
    print(f"{'Type':<8} {'Target':<40} {'Hash':<10} {'Status':<8} Description")
    print("-" * 90)
    for e in entries:
        full_h, err = compute_hash(e["type"], e["target"], root)
        if err:
            status = "ERROR"
        elif short_hash(full_h) != e["hash"]:
            status = "DRIFTED"
        else:
            status = "OK"
        print(f"{e['type']:<8} {e['target']:<40} {e['hash']:<10} {status:<8} {e['description']}")


def cmd_check(args):
    entries = read_anchors()
    if not entries:
        print("No anchors set.")
        return

    root = find_project_root()
    has_drift = False
    for e in entries:
        full_h, err = compute_hash(e["type"], e["target"], root)
        if err:
            print(f"ERROR: {e['target']} — {err}")
            has_drift = True
        elif short_hash(full_h) != e["hash"]:
            print(f"DRIFTED: {e['target']} — hash was {e['hash']}, now {short_hash(full_h)}")
            has_drift = True

    if has_drift:
        sys.exit(1)
    else:
        print("All anchors OK.")


def cmd_update(args):
    target_type, target = parse_target(args.target)
    entries = read_anchors()
    root = find_project_root()
    found = False
    for e in entries:
        if e["target"] == target:
            full_h, err = compute_hash(e["type"], e["target"], root)
            if err:
                print(f"Error: {err}", file=sys.stderr)
                sys.exit(1)
            e["hash"] = short_hash(full_h)
            found = True
            break

    if not found:
        print(f"Error: No anchor found for: {target}", file=sys.stderr)
        sys.exit(1)

    write_anchors(entries)
    print(f"Updated hash for {target}")


def cmd_setup(args):
    root = find_project_root()
    # Determine the skill scripts directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_path = os.path.dirname(script_dir)  # parent of scripts/

    enforce_edit = os.path.join(script_dir, "enforce_edit.sh")
    enforce_bash = os.path.join(script_dir, "enforce_bash.sh")

    # Build the hook config we want to add
    hook_config = {
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
                            "command": enforce_edit
                        }
                    ]
                },
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": enforce_bash
                        }
                    ]
                }
            ]
        }
    }

    settings_path = os.path.join(root, SETTINGS_REL)
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)

    if os.path.exists(settings_path):
        with open(settings_path, "r") as f:
            settings = json.load(f)
    else:
        settings = {}

    # Merge permissions.deny
    if "permissions" not in settings:
        settings["permissions"] = {}
    if "deny" not in settings["permissions"]:
        settings["permissions"]["deny"] = []
    for rule in hook_config["permissions"]["deny"]:
        if rule not in settings["permissions"]["deny"]:
            settings["permissions"]["deny"].append(rule)

    # Merge hooks.PreToolUse
    if "hooks" not in settings:
        settings["hooks"] = {}
    if "PreToolUse" not in settings["hooks"]:
        settings["hooks"]["PreToolUse"] = []

    existing_commands = set()
    for hook_group in settings["hooks"]["PreToolUse"]:
        for h in hook_group.get("hooks", []):
            existing_commands.add(h.get("command", ""))

    for hook_group in hook_config["hooks"]["PreToolUse"]:
        cmd = hook_group["hooks"][0]["command"]
        if cmd not in existing_commands:
            settings["hooks"]["PreToolUse"].append(hook_group)

    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)
        f.write("\n")

    print(f"Anchor enforcement configured in {SETTINGS_REL}")
    print(f"  Edit/Write hook: {enforce_edit}")
    print(f"  Bash hook:       {enforce_bash}")
    print(f"  Deny rules:      Edit(.anchors), Write(.anchors)")
    print(f"\nRun /hooks in Claude Code to verify.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="anchor",
        description="Protect code regions from AI modification.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # add
    p_add = sub.add_parser("add", help="Anchor a file, line range, or folder")
    p_add.add_argument("target", help="Target: file.py, file.py:10-20, or folder/")
    p_add.add_argument("--desc", help="Description of why this is anchored")

    # remove
    p_rm = sub.add_parser("remove", help="Remove an anchor")
    p_rm.add_argument("target", help="Target to un-anchor")

    # list
    sub.add_parser("list", help="List all anchors with status")

    # check
    sub.add_parser("check", help="Check for drift in anchored content")

    # update
    p_up = sub.add_parser("update", help="Update hash for an anchor after intentional change")
    p_up.add_argument("target", help="Target to update")

    # setup
    sub.add_parser("setup", help="Install enforcement hooks in .claude/settings.json")

    args = parser.parse_args()
    {
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "check": cmd_check,
        "update": cmd_update,
        "setup": cmd_setup,
    }[args.command](args)


if __name__ == "__main__":
    main()
