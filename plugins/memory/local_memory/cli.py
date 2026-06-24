"""Operator CLI helpers for the local memory provider."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import LocalMemoryProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect Hermes local memory provider status")
    parser.add_argument("command", choices=["status", "doctor"], nargs="?", default="status")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    args = parser.parse_args(argv)
    provider = LocalMemoryProvider()
    provider.initialize("diagnostic", hermes_home=args.hermes_home, platform="cli")
    print(json.dumps(provider.diagnostics(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
