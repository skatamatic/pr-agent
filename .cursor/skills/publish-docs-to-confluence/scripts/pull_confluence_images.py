#!/usr/bin/env python3
"""Download non-mermaid image attachments from published Confluence pages into assets/."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from md_to_adf.confluence.auth import build_token_auth_header

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = "docs/suite"
CONFIG_FILENAME = "confluence.publish.toml"
STATE_FILENAME = ".confluence-publish.json"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MERMAID_NAME_RE = re.compile(r"^mermaid-[a-f0-9]+\.(png|svg|mmd)$", re.I)


def load_toml(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def resolve_config(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    cfg_path = Path(args.config) if args.config else REPO_ROOT / DEFAULT_SOURCE / CONFIG_FILENAME
    if not cfg_path.is_file():
        raise SystemExit(f"Config not found: {cfg_path}")
    return cfg_path, load_toml(cfg_path)


def auth_header(conf: dict[str, Any]) -> tuple[str, str]:
    domain = str(conf.get("domain", "")).strip()
    email = str(conf.get("email", "")).strip()
    token = str(conf.get("api_token", "")).strip()
    if not all([domain, email, token]):
        raise SystemExit("Set confluence.domain, email, and api_token in config")
    return domain, build_token_auth_header(email, token)


def api_get(domain: str, auth: str, path: str, timeout: float = 90) -> dict[str, Any]:
    url = f"https://{domain}{path}" if path.startswith("/") else path
    req = urllib.request.Request(
        url,
        headers={"Authorization": auth, "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def download_url(domain: str, auth: str, url: str, dest: Path, timeout: float = 120) -> None:
    if url.startswith("/"):
        if url.startswith("/rest/"):
            url = f"https://{domain}/wiki{url}"
        else:
            url = f"https://{domain}{url}"
    req = urllib.request.Request(url, headers={"Authorization": auth}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        dest.write_bytes(resp.read())


def list_attachments(domain: str, auth: str, page_id: str) -> list[dict[str, Any]]:
    data = api_get(
        domain,
        auth,
        f"/wiki/rest/api/content/{page_id}/child/attachment?limit=100",
    )
    return list(data.get("results") or [])


def is_doc_image_attachment(title: str) -> bool:
    if MERMAID_NAME_RE.match(title):
        return False
    if title.lower().startswith("mermaid-"):
        return False
    return Path(title).suffix.lower() in IMAGE_EXT


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w.\-]+", "-", name.strip())
    return name.strip("-") or "image.png"


def page_slug(rel_path: str) -> str:
    p = Path(rel_path)
    if p.name.lower() == "readme.md":
        return p.parent.as_posix().replace("/", "-") or "root"
    return p.stem


def markdown_href_to_asset(page_rel: str, asset_rel: str) -> str:
    doc = PurePosixPath(page_rel).parent
    prefix = "/".join([".."] * len(doc.parts))
    return f"{prefix}/{asset_rel}" if prefix else asset_rel


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull Confluence page image attachments into docs/suite/assets/")
    parser.add_argument("--config", help="Path to confluence.publish.toml")
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Markdown source root")
    parser.add_argument("--only", help="Comma-separated rel paths to pull (default: all pages in state)")
    parser.add_argument(
        "--out-dir",
        default="assets/screenshots",
        help="Directory under source for downloads (default: assets/screenshots)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", help="Write JSON report of suggested markdown refs")
    args = parser.parse_args()

    _, cfg = resolve_config(args)
    conf = cfg.get("confluence") or {}
    pub = cfg.get("publish") or {}
    domain, auth = auth_header(conf)

    source = REPO_ROOT / str(pub.get("source") or args.source)
    state_path = source / str(pub.get("state_file") or STATE_FILENAME)
    if not state_path.is_file():
        raise SystemExit(f"State file not found: {state_path}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    pages: dict[str, Any] = state.get("pages") or {}

    only_set: set[str] | None = None
    if args.only:
        only_set = {p.strip().replace("\\", "/") for p in args.only.split(",") if p.strip()}

    out_root = source / args.out_dir
    report_rows: list[dict[str, Any]] = []
    total = 0

    print(f"Pulling images from {domain} into {out_root.relative_to(REPO_ROOT)}…")

    for rel_path, meta in sorted(pages.items()):
        if only_set and rel_path not in only_set:
            continue
        page_id = str((meta or {}).get("id") or "")
        if not page_id or page_id.startswith("dry-"):
            continue

        attachments = list_attachments(domain, auth, page_id)
        images = [a for a in attachments if is_doc_image_attachment(str(a.get("title") or ""))]
        if not images:
            continue

        slug = page_slug(rel_path)
        page_dir = out_root / slug
        print(f"\n{rel_path} (id {page_id}): {len(images)} image(s)")

        for att in images:
            title = sanitize_filename(str(att.get("title") or "image.png"))
            links = att.get("_links") or {}
            dl = links.get("download") or links.get("self")
            if not dl:
                print(f"  skip {title}: no download link")
                continue

            dest = page_dir / title
            rel_asset = dest.relative_to(source).as_posix()
            md_ref = f"![{Path(title).stem}]({markdown_href_to_asset(rel_path, rel_asset)})"

            if args.dry_run:
                print(f"  [dry-run] {title} -> {dest.relative_to(REPO_ROOT)}")
            else:
                page_dir.mkdir(parents=True, exist_ok=True)
                download_url(domain, auth, dl, dest)
                print(f"  saved {dest.relative_to(REPO_ROOT)}")

            report_rows.append(
                {
                    "page_rel": rel_path,
                    "page_id": page_id,
                    "attachment": title,
                    "local_path": rel_asset,
                    "markdown": md_ref,
                }
            )
            total += 1

    print(f"\nDone. {total} image(s).")
    if report_rows:
        print("\nSuggested markdown (paste into the matching doc):")
        for row in report_rows:
            print(f"  {row['page_rel']}: {row['markdown']}")

    if args.report:
        report_path = Path(args.report)
        report_path.write_text(json.dumps(report_rows, indent=2), encoding="utf-8")
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
