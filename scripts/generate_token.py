#!/usr/bin/env python3
"""Generate a strong random token for MCP Command Bridge.

Usage:
    python scripts/generate_token.py           # Print token to stdout
    python scripts/generate_token.py --env     # Print as MCB_TOKEN=... export line
    python scripts/generate_token.py --write   # Write to .env file
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path


def generate_token(length: int = 32) -> str:
    """Generate a URL-safe token with ~192 bits of entropy (32 chars)."""
    return secrets.token_urlsafe(length)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a strong token for MCP Command Bridge")
    parser.add_argument("--length", type=int, default=32, help="Token byte length (default: 32, ~192 bits)")
    parser.add_argument("--env", action="store_true", help="Output as MCB_TOKEN=... export line")
    parser.add_argument("--write", action="store_true", help="Write to .env file in current directory")
    args = parser.parse_args()

    token = generate_token(args.length)

    if args.write:
        env_path = Path(".env")
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        lines = [line for line in existing.splitlines() if not line.startswith("MCB_TOKEN=")]
        lines.append(f"MCB_TOKEN={token}")
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Token written to {env_path}", file=sys.stderr)
        print(f"  MCB_TOKEN={token} ({len(token)} chars)", file=sys.stderr)
        print("  Add this .env to your .gitignore!", file=sys.stderr)
    elif args.env:
        print(f"MCB_TOKEN={token}")
    else:
        print(token)


if __name__ == "__main__":
    main()
