#!/usr/bin/env python3
"""Delete Confluence pages by id (orphans after doc renames/merges)."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from md_to_adf.confluence.auth import build_token_auth_header

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = "docs/suite"
CONFIG_FILENAME = "confluence.publish.toml"


def load_config(path: Path) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def resolve_config_path(args: argparse.Namespace) -> Path:
    if args.config:
        return Path(args.config)
    source = args.source or DEFAULT_SOURCE
    return (REPO_ROOT / source / CONFIG_FILENAME).resolve()


def api_request(
    domain: str,
    auth_header: str,
    method: str,
    path: str,
    timeout: float = 90,
) -> dict[str, Any] | None:
    url = f"https://{domain}{path}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": auth_header, "Accept": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if not body:
                return None
            return json.loads(body.decode())
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode(errors="replace")
        raise SystemExit(f"HTTP {exc.code} {method} {path}: {err_body}") from exc


def get_page(domain: str, auth: str, page_id: str) -> dict[str, Any]:
    data = api_request(domain, auth, "GET", f"/wiki/api/v2/pages/{page_id}")
    if not data:
        raise SystemExit(f"Page {page_id}: empty response")
    return data


def delete_page(domain: str, auth: str, page_id: str, dry_run: bool) -> None:
    info = get_page(domain, auth, page_id)
    title = info.get("title", "?")
    parent = info.get("parentId", "?")
    print(f"  {page_id}: \"{title}\" (parent {parent})")
    if dry_run:
        print("    [dry-run] would DELETE")
        return
    api_request(domain, auth, "DELETE", f"/wiki/api/v2/pages/{page_id}")
    print("    deleted")


def main() -> None:
    p = argparse.ArgumentParser(description="Delete Confluence pages by id")
    p.add_argument(
        "page_ids",
        nargs="*",
        help="Page ids to delete (or use --from-config)",
    )
    p.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"Markdown suite root under repo (default: {DEFAULT_SOURCE})",
    )
    p.add_argument(
        "--config",
        default=None,
        help=f"Path to confluence.publish.toml (default: <source>/{CONFIG_FILENAME})",
    )
    p.add_argument(
        "--from-config",
        action="store_true",
        help="Also delete ids listed in [publish.delete_orphan_page_ids]",
    )
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    config_path = resolve_config_path(args)
    if not config_path.is_file():
        raise SystemExit(f"Config not found: {config_path}")

    cfg = load_config(config_path)
    conf = cfg.get("confluence", {})
    pub = cfg.get("publish", {})
    if not isinstance(conf, dict) or not isinstance(pub, dict):
        raise SystemExit("Invalid config structure")

    domain = str(conf.get("domain", "")).strip()
    email = str(conf.get("email", "")).strip()
    token = str(conf.get("api_token", "")).strip()
    if not domain or not email or not token:
        raise SystemExit("confluence.domain, email, and api_token required in config")

    page_ids = list(args.page_ids)
    if args.from_config:
        raw = pub.get("delete_orphan_page_ids", [])
        if isinstance(raw, list):
            page_ids.extend(str(x).strip() for x in raw if str(x).strip())

    seen: set[str] = set()
    unique: list[str] = []
    for pid in page_ids:
        if pid not in seen:
            seen.add(pid)
            unique.append(pid)

    if not unique:
        raise SystemExit("No page ids provided")

    auth = build_token_auth_header(email, token)
    print(f"Deleting {len(unique)} page(s) from {domain}…")
    for pid in unique:
        delete_page(domain, auth, pid, args.dry_run)
    print("Done.")


if __name__ == "__main__":
    main()
