#!/usr/bin/env python3
"""CLI Key Provisioning & Management Tool for MVCP Control Plane.

Allows administrators to create, list, and revoke API keys (`arm_dev_*`, `arm_m2m_*`, `arm_judge_*`).
Persists salted SHA-256 hashes with per-key random salts for safe verification.
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

# Absolute path resolution anchored to repo rootpython scripts/manage_keys.py create --name "curl-test" --role dev
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
CONTROL_PLANE_DIR = REPO_ROOT / "src" / "control_plane"

DEFAULT_KEYS_PATH = CONTROL_PLANE_DIR / "data" / "keys.json"
TEMPLATE_KEYS_PATH = CONTROL_PLANE_DIR / "config" / "keys.json.example"

# Global module path state target
KEYS_FILE: Path = Path(os.getenv("KEYS_FILE_PATH", DEFAULT_KEYS_PATH)).resolve()


def hash_key(key: str, salt: str) -> str:
    """Computes SHA-256 digest of plain-text API key using a unique per-key salt."""
    return hashlib.sha256((key + salt).encode("utf-8")).hexdigest()


def load_keys() -> list[dict]:
    """Loads keys database from the configured json file.

    Aborts execution on JSON parse error to prevent accidental file clobbering.
    """
    if KEYS_FILE.exists():
        try:
            with open(KEYS_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("keys", [])
        except json.JSONDecodeError as e:
            print(f"❌ ERROR: File at {KEYS_FILE} contains invalid JSON: {e}", file=sys.stderr)
            print("Aborting to prevent data loss. Fix or remove the file.", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ ERROR reading keys file {KEYS_FILE}: {e}", file=sys.stderr)
            sys.exit(1)
    return []


def save_keys(keys: list[dict]) -> None:
    """Saves keys database to the configured json file."""
    KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump({"keys": keys}, f, indent=2)


def create_key(name: str, role: str, scopes: list[str]) -> None:
    """Generates a new plain-text API key and saves its uniquely salted SHA-256 hash."""
    keys = load_keys()

    prefix_map = {
        "dev": "arm_dev_",
        "m2m": "arm_m2m_",
        "judge": "arm_judge_",
    }
    prefix = prefix_map.get(role, "arm_dev_")

    raw_token = secrets.token_hex(16)
    plain_key = f"{prefix}{raw_token}"
    key_id = f"key_{role}_{secrets.token_hex(4)}"

    salt = secrets.token_hex(16)
    digest = hash_key(plain_key, salt)

    record = {
        "key_id": key_id,
        "name": name,
        "role": role,
        "hash": digest,
        "salt": salt,
        "scopes": scopes,
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
    }

    keys.append(record)
    save_keys(keys)

    print("\n==========================================================")
    print("🔑 NEW API KEY GENERATED SUCCESSFULLY")
    print("==========================================================")
    print(f"  Key ID : {key_id}")
    print(f"  Name   : {name}")
    print(f"  Role   : {role}")
    print(f"  Scopes : {', '.join(scopes)}")
    print(f"  Target : {KEYS_FILE}")
    print(f"  Plain Key (SAVE THIS NOW): {plain_key}")
    print("==========================================================")
    print("WARNING: The plain-text key will NEVER be displayed again.")
    print("Only its uniquely salted SHA-256 digest is stored.\n")


def list_keys() -> None:
    """Lists all stored API keys in the database."""
    keys = load_keys()
    print("\n==========================================================")
    print(f"📋 MVCP CONTROL PLANE API KEYS ({len(keys)} records)")
    print(f"   Storage Location: {KEYS_FILE}")
    print("==========================================================")
    if not keys:
        print("   (No keys found)")
    for k in keys:
        print(
            f" • ID: {k.get('key_id')} | Name: {k.get('name')} | Role: {k.get('role')} | Status: {k.get('status')}"
        )
        print(f"   Scopes: {', '.join(k.get('scopes', []))}")
        print(f"   Created: {k.get('created_at')}")
    print("==========================================================\n")


def revoke_key(key_id: str) -> None:
    """Revokes an active API key by ID."""
    keys = load_keys()
    found = False
    for k in keys:
        if k.get("key_id") == key_id:
            k["status"] = "revoked"
            k["revoked_at"] = datetime.now(UTC).isoformat()
            found = True
            break

    if found:
        save_keys(keys)
        print(f"✅ Key [{key_id}] has been REVOKED.")
    else:
        print(f"❌ Key ID [{key_id}] not found in {KEYS_FILE}.", file=sys.stderr)


def main():
    """Main CLI entry point for API key management."""
    global KEYS_FILE

    parser = argparse.ArgumentParser(description="MVCP Control Plane API Key Manager")
    parser.add_argument(
        "--file",
        type=Path,
        help="Override target path to keys.json (defaults to KEYS_FILE_PATH env var or src/control_plane/data/keys.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: create
    parser_create = subparsers.add_parser("create", help="Create a new API key")
    parser_create.add_argument("--name", required=True, help="Friendly name for the key")
    parser_create.add_argument(
        "--role", choices=["judge", "dev", "m2m"], default="dev", help="Key role"
    )
    parser_create.add_argument(
        "--scopes", default="compiler,autotuner", help="Comma-separated scopes"
    )

    # Subcommand: list
    subparsers.add_parser("list", help="List all API keys")

    # Subcommand: revoke
    parser_revoke = subparsers.add_parser("revoke", help="Revoke an existing API key")
    parser_revoke.add_argument("--key-id", required=True, help="ID of the key to revoke")

    args = parser.parse_args()

    if args.file:
        KEYS_FILE = args.file.resolve()

    if args.command == "create":
        scopes_list = [s.strip() for s in args.scopes.split(",") if s.strip()]
        create_key(args.name, args.role, scopes_list)
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        revoke_key(args.key_id)


if __name__ == "__main__":
    main()
