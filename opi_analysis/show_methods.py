#!/usr/bin/env python
"""
show_methods.py  –  inspect an OPI vocab-schema JSON file.

Features
--------
• List every Block* definition it finds.
• Print the attribute names of an individual block.
• Verbose mode (-v) adds type & one-line description.

Usage examples
--------------
# 1) Just show everything the file contains
python show_block_attrs.py opi_vocab_schema.json           # lists all Block* names

# 2) List and quit (identical to omitting <section>)
python show_block_attrs.py opi_vocab_schema.json --list

# 3) Inspect one block (terse / verbose)
python show_block_attrs.py opi_vocab_schema.json BlockMp2
python show_block_attrs.py opi_vocab_schema.json BlockMp2 -v
"""

import argparse
import json
import sys
from pathlib import Path
from textwrap import indent


# ──────────────────────────────────────────────────────────────────────────
def load_schema(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        sys.exit(f"❌  Failed to read or parse JSON: {exc}")


def list_blocks(schema: dict) -> list[str]:
    """Return all keys in $defs that start with 'Block'."""
    return sorted(k for k in schema.get("$defs", {}) if k.startswith("Block"))


def print_block_table(blocks: list[str]) -> None:
    print("\nAvailable %-blocks:")
    print(indent("\n".join(blocks), "  "))
    print()


def pick_section(schema: dict, name: str) -> dict:
    try:
        return schema["$defs"][name]
    except KeyError as exc:
        sys.exit(f'❌  Section "{name}" not found in $defs.')


def describe_props(props: dict, verbose: bool = False) -> None:
    if verbose:
        # tidy column print
        print()
        for key, meta in props.items():
            typ = meta.get("type") or ", ".join(
                m.get("type", "?") for m in meta.get("anyOf", [])
            )
            descr = meta.get("title", "") or meta.get("description", "")
            print(f"{key:20} {typ:10} {descr.splitlines()[0]}")
    else:
        print(" ".join(sorted(props)))


# ──────────────────────────────────────────────────────────────────────────
def main() -> None:
    ap = argparse.ArgumentParser(description="Inspect OPI JSON-Schema blocks.")
    ap.add_argument("schema", type=Path, help="Path to opi_vocab_schema.json")
    ap.add_argument("section", nargs="?", help="Block name, e.g. BlockMp2")
    ap.add_argument("-v", "--verbose", action="store_true", help="Verbose property info")
    ap.add_argument("-l", "--list", action="store_true", help="List all blocks & exit")
    ns = ap.parse_args()

    schema = load_schema(ns.schema)
    blocks = list_blocks(schema)

    # ---- ‘list’ mode or no section supplied --------------------------------
    if ns.list or ns.section is None:
        print_block_table(blocks)
        if ns.list:
            return
        # no section? -> done
        sys.exit(0)

    # ---- show the chosen block ---------------------------------------------
    if ns.section not in blocks:
        sys.exit(f'❌  "{ns.section}" is not a recognised Block*. Use --list to view all.')

    props = pick_section(schema, ns.section).get("properties", {})
    if not props:
        sys.exit(f'⚠️  "{ns.section}" has no "properties" node.')
    describe_props(props, verbose=ns.verbose)


if __name__ == "__main__":
    main()
