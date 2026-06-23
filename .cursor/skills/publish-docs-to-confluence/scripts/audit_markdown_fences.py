#!/usr/bin/env python3
"""Scan docs/suite markdown for Confluence-unsafe code fence patterns."""

from __future__ import annotations

import re
import sys
from pathlib import Path

FENCE = "```"


def scan_file(rel: str, lines: list[str]) -> list[tuple[str, int, str, str]]:
    issues: list[tuple[str, int, str, str]] = []
    in_fence = False
    fence_start = 0
    prev_nonempty = ""

    for i, line in enumerate(lines, 1):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if stripped.startswith(FENCE):
            if indent > 0:
                issues.append((rel, i, "indented_fence", line.rstrip()))
            if not in_fence:
                in_fence = True
                fence_start = i
                # Fence directly under list item (no blank line) is risky for ADF
                if re.match(r"^(\d+\.|[-*+])\s", prev_nonempty) and indent == 0:
                    issues.append(
                        (
                            rel,
                            i,
                            "fence_after_list_item",
                            f"after: {prev_nonempty[:60]}",
                        )
                    )
            else:
                in_fence = False
            prev_nonempty = line
            continue

        if in_fence:
            prev_nonempty = line
            continue

        # Same-line fence markers (not opening/closing alone)
        if FENCE in line and not stripped.startswith(FENCE):
            issues.append((rel, i, "inline_fence_marker", line.rstrip()[:100]))

        # Double-backtick wrappers (show literal backticks in source; often break in Confluence tables)
        if re.search(r"``\s*`", line):
            issues.append((rel, i, "double_backtick_wrapper", line.rstrip()[:100]))

        if stripped and not stripped.startswith(">"):
            prev_nonempty = line

    if in_fence:
        issues.append((rel, fence_start, "unclosed_fence", ""))

    return issues


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("docs/suite")
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 2

    all_issues: list[tuple[str, int, str, str]] = []
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root).as_posix()
        lines = md.read_text(encoding="utf-8").splitlines()
        all_issues.extend(scan_file(rel, lines))

    by_kind: dict[str, list] = {}
    for item in all_issues:
        by_kind.setdefault(item[2], []).append(item)

    print(f"Scanned {len(list(root.rglob('*.md')))} files under {root}")
    print(f"Found {len(all_issues)} issue(s)\n")
    for kind in sorted(by_kind):
        items = by_kind[kind]
        print(f"=== {kind} ({len(items)}) ===")
        for rel, ln, _, detail in items:
            print(f"  {rel}:{ln}  {detail}")
        print()

    return 1 if all_issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
