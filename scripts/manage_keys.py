#!/usr/bin/env python3
"""CLI Key Provisioning & Management Tool.

Allows administrators to create, list, and revoke API keys (`arm_dev_*`, `arm_m2m_*`)
for the MVCP Control Plane. Persists salted SHA-256 hashes in `config/keys.json`.
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timezone

KEYS_FILE = os.path.join(os.path.dirname(__file__), "../config/keys.json")


def hash_key(key: str, salt: str = "mvcp_salt_2026") -> str:
    """Computes salted SHA-256 digest of plain-text API key.

    Args:
        key: Plain text key string.
        salt: Salt string.

    Returns:
        64-character hexadecimal SHA-256 string.
    """
    return hashlib.sha256((key + salt).encode("utf-8")).hexdigest()


def load_keys() -> list[dict]:
    """Loads keys database from keys.json.

    Returns:
        List of key record dictionaries.
    """
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("keys", [])
        except Exception as e:
            print(f"Error loading keys file {KEYS_FILE}: {e}", file=sys.stderr)
            return []
    return []


def save_keys(keys: list[dict]) -> None:
    """Saves keys database to config/keys.json.

    Args:
        keys: List of key record dictionaries to persist.
    """
    os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
    with open(KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump({"keys": keys}, f, indent=2)


def create_key(name: str, role: str, scopes: list[str]) -> None:
    """Generates a new plain-text API key and saves its salted SHA-256 hash.

    Args:
        name: Friendly descriptive name for the API key.
        role: Target role string ('judge', 'dev', 'm2m').
        scopes: List of allowed feature scope strings.
    """
    keys = load_keys()

    prefix = "arm_dev_" if role == "dev" else "arm_m2m_" if role == "m2m" else "arm_judge_"
    raw_token = secrets.token_hex(16)
    plain_key = f"{prefix}{raw_token}"
    key_id = f"key_{role}_{secrets.token_hex(4)}"

    salt = "mvcp_salt_2026"
    digest = hash_key(plain_key, salt)

    record = {
        "key_id": key_id,
        "name": name,
        "role": role,
        "hash": digest,
        "salt": salt,
        "scopes": scopes,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
    print(f"  Plain Key (SAVE THIS NOW): {plain_key}")
    print("==========================================================")
    print("WARNING: The plain-text key will NEVER be displayed again.")
    print("Only its salted SHA-256 digest is stored in config/keys.json\n")


def list_keys() -> None:
    """Lists all stored API keys in config/keys.json."""
    keys = load_keys()
    print("\n==========================================================")
    print(f"📋 MVCP CONTROL PLANE API KEYS ({len(keys)} records)")
    print("==========================================================")
    for k in keys:
        print(
            f" • ID: {k.get('key_id')} | Name: {k.get('name')} | Role: {k.get('role')} | Status: {k.get('status')}"
        )
        print(f"   Scopes: {', '.join(k.get('scopes', []))}")
    print("==========================================================\n")


def revoke_key(key_id: str) -> None:
    """Revokes an active API key by ID.

    Args:
        key_id: Unique key identifier string.
    """
    keys = load_keys()
    found = False
    for k in keys:
        if k.get("key_id") == key_id:
            k["status"] = "revoked"
            found = True
            break

    if found:
        save_keys(keys)
        print(f"✅ Key [{key_id}] has been REVOKED.")
    else:
        print(f"❌ Key ID [{key_id}] not found.", file=sys.stderr)


def main():
    """Main CLI entry point for API key management."""
    parser = argparse.ArgumentParser(description="MVCP Control Plane API Key Manager")
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

    if args.command == "create":
        scopes_list = [s.strip() for s in args.scopes.split(",") if s.strip()]
        create_key(args.name, args.role, scopes_list)
    elif args.command == "list":
        list_keys()
    elif args.command == "revoke":
        revoke_key(args.key_id)


if __name__ == "__main__":
    main()
