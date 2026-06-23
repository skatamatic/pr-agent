#!/usr/bin/env python3
"""Replace SCREENSHOT PLACEHOLDER blocks with pulled image markdown (ADF order)."""

from __future__ import annotations

import argparse
import json
import re
import tomllib
import urllib.request
from pathlib import Path, PurePosixPath

from md_to_adf.confluence.auth import build_token_auth_header

REPO_ROOT = Path(__file__).resolve().parents[4]
PLACEHOLDER_RE = re.compile(
    r">\s*\*\*\[SCREENSHOT PLACEHOLDER\]\*\*\s*\n(?:>\s*[^\n]*\n?)+",
    re.MULTILINE,
)
MERMAID_NAME_RE = re.compile(r"^mermaid-[a-f0-9]+\.png$", re.I)


def load_config(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def fetch_media_order(domain: str, auth: str, page_id: str) -> list[str]:
    url = f"https://{domain}/wiki/api/v2/pages/{page_id}?body-format=atlas_doc_format"
    req = urllib.request.Request(url, headers={"Authorization": auth})
    data = json.loads(urllib.request.urlopen(req, timeout=90).read())
    adf = json.loads(data["body"]["atlas_doc_format"]["value"])

    att_url = f"https://{domain}/wiki/rest/api/content/{page_id}/child/attachment?limit=100"
    req2 = urllib.request.Request(att_url, headers={"Authorization": auth})
    atts = json.loads(urllib.request.urlopen(req2, timeout=90).read()).get("results") or []
    id_to_title: dict[str, str] = {}
    for att in atts:
        title = str(att.get("title") or "")
        fid = (att.get("extensions") or {}).get("fileId")
        if fid and title:
            id_to_title[str(fid)] = title

    order: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "mediaSingle":
                for child in node.get("content") or []:
                    if child.get("type") != "media":
                        continue
                    fid = child.get("attrs", {}).get("id")
                    title = id_to_title.get(str(fid), "") if fid else ""
                    if title and not MERMAID_NAME_RE.match(title):
                        order.append(title)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(adf)
    return order


def markdown_href(page_rel: str, asset_rel: str, alt: str) -> str:
    doc = PurePosixPath(page_rel).parent
    prefix = "/".join([".."] * len(doc.parts))
    href = f"{prefix}/{asset_rel}" if prefix else asset_rel
    return f"![{alt}]({href})"


def apply_placeholders(text: str, images: list[tuple[str, str]]) -> tuple[str, int]:
    """images: list of (alt, markdown line)"""
    idx = 0

    def repl(_: re.Match[str]) -> str:
        nonlocal idx
        if idx >= len(images):
            return ""
        line = images[idx][1]
        idx += 1
        return line + "\n"

    updated = PLACEHOLDER_RE.sub(repl, text)
    return updated, idx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(REPO_ROOT / "docs/suite/confluence.publish.toml"))
    parser.add_argument("--report", default=str(REPO_ROOT / "docs/suite/assets/.pull-report.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    conf = cfg["confluence"]
    pub = cfg.get("publish") or {}
    domain = conf["domain"]
    auth = build_token_auth_header(conf["email"], conf["api_token"])
    source = REPO_ROOT / str(pub.get("source") or "docs/suite")

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    by_page: dict[str, list[dict]] = {}
    for row in report:
        by_page.setdefault(row["page_rel"], []).append(row)

    state = json.loads((source / ".confluence-publish.json").read_text(encoding="utf-8"))
    pages = state.get("pages") or {}

    for page_rel, rows in sorted(by_page.items()):
        page_id = str((pages.get(page_rel) or {}).get("id") or "")
        if not page_id:
            continue
        order = fetch_media_order(domain, auth, page_id)
        if not order:
            continue

        title_to_row = {r["attachment"]: r for r in rows}
        images: list[tuple[str, str]] = []
        for title in order:
            row = title_to_row.get(title)
            if not row:
                continue
            alt = Path(title).stem
            md = markdown_href(page_rel, row["local_path"], alt)
            images.append((alt, md))

        md_path = source / page_rel
        if not md_path.is_file():
            continue
        text = md_path.read_text(encoding="utf-8")
        if not PLACEHOLDER_RE.search(text):
            continue
        new_text, used = apply_placeholders(text, images)
        if used == 0:
            continue
        print(f"{page_rel}: replaced {used} placeholder(s)")
        if not args.dry_run:
            md_path.write_text(new_text, encoding="utf-8")


if __name__ == "__main__":
    main()
