#!/usr/bin/env python3
"""De-LLM pass: em dashes, meta headers/footers, Related docs link dumps.

Always review the diff after running. Table cells that used em dash as "empty"
may need manual fix (use - or n/a, not bare :).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EM_DASH = "\u2014"

PART_OF_RE = re.compile(r"^Part of \[([^\]]+)\]\([^\)]+\)\.\s*\n+", re.MULTILINE)
BACK_FOOTER_RE = re.compile(r"\n+\[← [^\]]+\]\([^\)]+\)\s*\n?$")
RELATED_DOCS_RE = re.compile(r"\n## Related docs\n\n(?:- [^\n]+\n)+", re.MULTILINE)
BOLD_EM_DASH_RE = re.compile(r"\*\*([^*]+)\*\* " + EM_DASH + r" ")


def clean_markdown(text: str) -> tuple[str, list[str]]:
    changes: list[str] = []
    orig = text

    if PART_OF_RE.search(text):
        text = PART_OF_RE.sub("", text)
        changes.append("removed Part of header")

    if BACK_FOOTER_RE.search(text):
        text = BACK_FOOTER_RE.sub("\n", text)
        changes.append("removed ← footer")

    if RELATED_DOCS_RE.search(text):
        text = RELATED_DOCS_RE.sub("\n", text)
        changes.append("removed Related docs section")

    if BOLD_EM_DASH_RE.search(text):
        text = BOLD_EM_DASH_RE.sub(r"**\1**: ", text)
        changes.append("**Label** — → **Label**:")

    if EM_DASH in text:
        count = text.count(EM_DASH)
        text = text.replace(f" {EM_DASH} ", ": ")
        changes.append(f"replaced {count} em dash(es)")

    return text, changes if text != orig else []


def main() -> None:
    parser = argparse.ArgumentParser(description="De-LLM cleanup for markdown doc suites")
    parser.add_argument(
        "paths",
        nargs="*",
        default=["docs/suite"],
        help="Files or directories (default: docs/suite)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    parser.add_argument(
        "--exclude",
        action="append",
        default=["workflows"],
        help="Directory name segments to skip (default: workflows)",
    )
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_file() and p.suffix == ".md":
            files.append(p)
        elif p.is_dir():
            for md in sorted(p.rglob("*.md")):
                if any(part in args.exclude for part in md.parts):
                    continue
                files.append(md)

    if not files:
        print("No markdown files found.", file=sys.stderr)
        raise SystemExit(1)

    touched = 0
    for md in files:
        text = md.read_text(encoding="utf-8")
        cleaned, changes = clean_markdown(text)
        if not changes:
            continue
        touched += 1
        rel = md.as_posix()
        print(f"{rel}: {', '.join(changes)}")
        if not args.dry_run:
            md.write_text(cleaned, encoding="utf-8")

    print(f"\n{'Would update' if args.dry_run else 'Updated'} {touched} file(s). Review diff before publish.")


if __name__ == "__main__":
    main()
