#!/usr/bin/env python3
"""
Publish docs/suite markdown to Confluence Cloud as ADF pages with internal links.

Idempotent: fetches the existing page tree, diffs desired vs remote ADF, and only
creates/updates pages that changed.

Requires: pip install -r requirements.txt (md-to-adf)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from md_to_adf import convert, validate
from md_to_adf.cli.errors import AccessError, AuthError, NetworkError, NotFoundError
from md_to_adf.confluence.auth import build_token_auth_header
from md_to_adf.confluence.client import ConfluenceClient
from md_to_adf.mermaid.detector import find_mermaid_blocks

DEFAULT_SOURCE = "docs/suite"
DEFAULT_ROOT_PAGE_REL = "README.md"
STATE_FILENAME = ".confluence-publish.json"
CONFIG_FILENAME = "confluence.publish.toml"
CONFIG_EXAMPLE_FILENAME = "confluence.publish.example.toml"
LINK_PATTERN = re.compile(r"(!?\[)([^\]]*)\]\(([^)]+)\)")
WIKI_PAGE_ID_RE = re.compile(r"/pages/(\d+)(?:/|$|\?)")

# Default sibling order under the suite root (override via [publish.section_order]).
DEFAULT_SECTION_ORDER: dict[str, int] = {
    "overview": 0,
    "how-to": 1,
    "technical": 2,
    "assets": 99,
}

# Optional audience subfolders under how-to/ or technical/ (override via [publish.audience_order]).
DEFAULT_AUDIENCE_ORDER: dict[str, int] = {
    "users": 0,
    "admins": 1,
    "superadmin": 2,
    "engineering": 3,
    "devops": 4,
}

# Generic repo-root path prefixes for inline GitHub links (override via publish.github_path_prefixes).
DEFAULT_REPO_PATH_PREFIXES: tuple[str, ...] = (
    "docs/",
    "scripts/",
    "deploy/",
    "deployment/",
    "infra/",
    ".github/",
    "src/",
    "lib/",
    "apps/",
    "packages/",
    "tests/",
    "tools/",
)

DEFAULT_ROOT_REPO_FILENAMES: frozenset[str] = frozenset(
    {
        "README.md",
        "Dockerfile",
        "requirements.txt",
        "package.json",
        "go.mod",
        "Cargo.toml",
        "pyproject.toml",
    }
)

# Mermaid rendering modes (config: publish.mermaid_strategy)
MERMAID_STRATEGIES = ("png", "png-local", "cloud", "code")
MERMAID_ALIASES = {"auto": "png", "image": "png-local", "macro": "cloud"}
MERMAID_CLOUD_PLACEHOLDER_ICON = (
    "https://mermaid.stratus-addons.com/images/mermaid144.png"
)
MERMAID_CLOUD_TITLE = "Mermaid Diagrams for Confluence"
MERMAID_PNG_BACKGROUND = "white"
MERMAID_THEME = "default"


def mermaid_cli_command(*, input_path: str, output_path: str) -> list[str] | None:
    """Build an mmdc or npx @mermaid-js/mermaid-cli command."""
    exe = shutil.which("mmdc") or shutil.which("mmdc.cmd")
    if exe:
        return [
            exe,
            "-i",
            input_path,
            "-o",
            output_path,
            "-t",
            MERMAID_THEME,
            "-b",
            MERMAID_PNG_BACKGROUND,
        ]
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if npx:
        return [
            npx,
            "--yes",
            "@mermaid-js/mermaid-cli",
            "-i",
            input_path,
            "-o",
            output_path,
            "-t",
            MERMAID_THEME,
            "-b",
            MERMAID_PNG_BACKGROUND,
        ]
    return None


def is_mmdc_available() -> bool:
    if shutil.which("mmdc") or shutil.which("mmdc.cmd"):
        return True
    return bool(shutil.which("npx") or shutil.which("npx.cmd"))


def flatten_png_white_background(path: Path) -> bool:
    """Composite a PNG onto an opaque white background (Confluence focus mode)."""
    try:
        from PIL import Image
    except ImportError:
        return False

    with Image.open(path) as im:
        rgba = im.convert("RGBA")
        white = Image.new("RGB", rgba.size, (255, 255, 255))
        white.paste(rgba, mask=rgba.split()[3])
        white.save(path, format="PNG")
    return True


def finalize_mermaid_png(path: Path) -> None:
    """Ensure rendered diagram PNGs are opaque white, not transparent."""
    if not flatten_png_white_background(path):
        print(
            "  warning: Pillow not installed; mermaid PNG may have a transparent "
            "background in Confluence focus mode (pip install Pillow)",
            file=sys.stderr,
        )


def normalize_mermaid_strategy(raw: str) -> str:
    """Map config/CLI value to a canonical strategy name."""
    value = (raw or "png").strip().lower()
    value = MERMAID_ALIASES.get(value, value)
    if value not in MERMAID_STRATEGIES:
        allowed = ", ".join(MERMAID_STRATEGIES + tuple(MERMAID_ALIASES))
        raise ValueError(f"Invalid mermaid_strategy {raw!r}; use one of: {allowed}")
    return value


def default_config_path(source_dir: Path) -> Path:
    return source_dir / CONFIG_FILENAME


def load_publish_config(config_path: Path) -> dict[str, Any]:
    if not config_path.is_file():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]

    with config_path.open("rb") as fh:
        data = tomllib.load(fh)
    return data if isinstance(data, dict) else {}


def _normalize_rel_path(rel: str) -> str:
    return str(rel).replace("\\", "/").strip()


def _load_string_int_map(raw: Any, defaults: dict[str, int]) -> dict[str, int]:
    if not isinstance(raw, dict):
        return dict(defaults)
    out = dict(defaults)
    for key, value in raw.items():
        if key is None or value is None:
            continue
        out[str(key).strip()] = int(value)
    return out


def _load_path_migrations(pub: dict[str, Any]) -> dict[str, str]:
    raw = pub.get("path_migrations")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for old_rel, new_rel in raw.items():
        old = _normalize_rel_path(str(old_rel))
        new = _normalize_rel_path(str(new_rel))
        if old and new:
            out[old] = new
    return out


def _load_skip_files(pub: dict[str, Any]) -> set[str]:
    raw = pub.get("skip_files")
    if not isinstance(raw, list):
        return set()
    return {_normalize_rel_path(str(x)) for x in raw if str(x).strip()}


def _load_github_path_prefixes(
    pub: dict[str, Any],
    workspace_root: Path | None,
) -> tuple[str, ...]:
    raw = pub.get("github_path_prefixes")
    if isinstance(raw, list) and raw:
        prefixes = [_normalize_rel_path(str(x)).rstrip("/") + "/" for x in raw if str(x).strip()]
        return tuple(dict.fromkeys(prefixes))
    if isinstance(raw, dict):
        nested = raw.get("prefixes")
        if isinstance(nested, list) and nested:
            prefixes = [_normalize_rel_path(str(x)).rstrip("/") + "/" for x in nested if str(x).strip()]
            return tuple(dict.fromkeys(prefixes))

    prefixes = list(DEFAULT_REPO_PATH_PREFIXES)
    if workspace_root and workspace_root.is_dir():
        for entry in sorted(workspace_root.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                candidate = f"{entry.name}/"
                if candidate not in prefixes:
                    prefixes.append(candidate)
    return tuple(prefixes)


def _load_root_repo_filenames(pub: dict[str, Any]) -> frozenset[str]:
    raw = pub.get("github_root_filenames")
    if isinstance(raw, list) and raw:
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return DEFAULT_ROOT_REPO_FILENAMES


@dataclass(frozen=True)
class LinkPathConfig:
    """Repo-root path heuristics for inline GitHub link detection."""

    repo_path_prefixes: tuple[str, ...]
    root_repo_filenames: frozenset[str]


@dataclass
class PublishLayoutConfig:
    """Suite layout and state migration settings (from publish.* TOML)."""

    path_migrations: dict[str, str] = field(default_factory=dict)
    section_order: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_SECTION_ORDER))
    audience_order: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_AUDIENCE_ORDER))
    skip_files: set[str] = field(default_factory=set)
    link_paths: LinkPathConfig = field(
        default_factory=lambda: LinkPathConfig(
            repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
            root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
        )
    )

    @classmethod
    def from_settings(
        cls,
        pub: dict[str, Any],
        workspace_root: Path | None = None,
    ) -> "PublishLayoutConfig":
        if not isinstance(pub, dict):
            pub = {}
        prefixes = _load_github_path_prefixes(pub, workspace_root)
        return cls(
            path_migrations=_load_path_migrations(pub),
            section_order=_load_string_int_map(pub.get("section_order"), DEFAULT_SECTION_ORDER),
            audience_order=_load_string_int_map(pub.get("audience_order"), DEFAULT_AUDIENCE_ORDER),
            skip_files=_load_skip_files(pub),
            link_paths=LinkPathConfig(
                repo_path_prefixes=prefixes,
                root_repo_filenames=_load_root_repo_filenames(pub),
            ),
        )


def resolve_setting(
    cli_value: str | None,
    env_name: str,
    config_value: str | None,
    default: str | None = None,
) -> str | None:
    if cli_value:
        return cli_value
    env = os.environ.get(env_name)
    if env:
        return env
    if config_value not in (None, ""):
        return str(config_value)
    return default


def resolve_float_setting(
    cli_value: float | None,
    env_name: str,
    config_value: Any,
    default: float,
) -> float:
    if cli_value is not None:
        return float(cli_value)
    env = os.environ.get(env_name)
    if env:
        return float(env)
    if config_value not in (None, ""):
        return float(config_value)
    return default


def resolve_int_setting(
    cli_value: int | None,
    env_name: str,
    config_value: Any,
    default: int,
) -> int:
    if cli_value is not None:
        return int(cli_value)
    env = os.environ.get(env_name)
    if env:
        return int(env)
    if config_value not in (None, ""):
        return int(config_value)
    return default


def resolve_bool_setting(
    cli_value: bool | None,
    config_value: Any,
    default: bool,
) -> bool:
    if cli_value is not None:
        return cli_value
    if config_value is not None:
        return bool(config_value)
    return default


@dataclass
class HttpRetryConfig:
    """Timeouts and retry policy for Confluence REST calls."""

    api_timeout: float = 90.0
    upload_timeout: float = 300.0
    max_retries: int = 6
    backoff_base: float = 2.0
    request_delay_sec: float = 0.25
    checkpoint_after_each_page: bool = True

    @classmethod
    def from_settings(cls, pub: dict[str, Any], args: argparse.Namespace) -> "HttpRetryConfig":
        http = pub.get("http")
        if not isinstance(http, dict):
            http = {}
        no_checkpoint = getattr(args, "no_checkpoint", False)
        return cls(
            api_timeout=resolve_float_setting(
                getattr(args, "api_timeout", None),
                "CONFLUENCE_API_TIMEOUT",
                http.get("api_timeout_sec"),
                90.0,
            ),
            upload_timeout=resolve_float_setting(
                getattr(args, "upload_timeout", None),
                "CONFLUENCE_UPLOAD_TIMEOUT",
                http.get("upload_timeout_sec"),
                300.0,
            ),
            max_retries=resolve_int_setting(
                getattr(args, "max_retries", None),
                "CONFLUENCE_MAX_RETRIES",
                http.get("max_retries"),
                6,
            ),
            backoff_base=resolve_float_setting(
                None,
                "CONFLUENCE_RETRY_BACKOFF",
                http.get("backoff_base_sec"),
                2.0,
            ),
            request_delay_sec=max(
                0.0,
                resolve_float_setting(
                    None,
                    "CONFLUENCE_REQUEST_DELAY_MS",
                    http.get("request_delay_ms"),
                    250.0,
                )
                / 1000.0,
            ),
            checkpoint_after_each_page=resolve_bool_setting(
                False if no_checkpoint else None,
                http.get("checkpoint_after_each_page"),
                True,
            ),
        )


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return isinstance(reason, (TimeoutError, OSError)) or _is_retryable_http_error(
            reason
        )
    if isinstance(exc, OSError):
        return True
    return False


def urlopen_with_retry(
    req: urllib.request.Request,
    *,
    timeout: float,
    max_retries: int,
    backoff_base: float,
    label: str = "",
) -> Any:
    """urllib.request.urlopen with exponential backoff on timeouts and 5xx/429."""
    last_exc: BaseException | None = None
    for attempt in range(max(1, max_retries)):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if not _is_retryable_http_error(exc) or attempt >= max_retries - 1:
                raise
        except BaseException as exc:
            last_exc = exc
            if not _is_retryable_http_error(exc) or attempt >= max_retries - 1:
                raise
        wait = backoff_base**attempt + random.uniform(0, 0.5)
        detail = label or req.full_url
        print(
            f"  HTTP retry {attempt + 1}/{max_retries} ({detail}): {last_exc} "
            f"— sleeping {wait:.1f}s",
            file=sys.stderr,
        )
        time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError("urlopen_with_retry failed without exception")


class ResilientConfluenceClient(ConfluenceClient):
    """Confluence client with longer timeouts, upload retries, and network fault tolerance."""

    def __init__(
        self,
        domain: str,
        auth_header: str,
        http: HttpRetryConfig | None = None,
    ):
        self.http = http or HttpRetryConfig()
        super().__init__(
            domain,
            auth_header,
            timeout=int(self.http.api_timeout),
            max_retries=1,
        )

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None):
        url = f"https://{self.domain}{path}"
        data = json.dumps(payload).encode("utf-8") if payload else None
        last_error: urllib.error.HTTPError | None = None

        for attempt in range(self.http.max_retries):
            req = urllib.request.Request(
                url, data=data, headers=self._headers, method=method
            )
            try:
                with urlopen_with_retry(
                    req,
                    timeout=self.http.api_timeout,
                    max_retries=1,
                    backoff_base=self.http.backoff_base,
                    label=f"{method} {path}",
                ) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                last_error = e
                if _is_retryable_http_error(e) and attempt < self.http.max_retries - 1:
                    wait = self.http.backoff_base**attempt + random.uniform(0, 0.5)
                    print(
                        f"  API retry {attempt + 1}/{self.http.max_retries} "
                        f"({method} {path}): HTTP {e.code} — sleeping {wait:.1f}s",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
                if e.code == 401:
                    raise AuthError(
                        "Authentication failed",
                        hint="Check your API token at ~/.md-to-adf/config.toml",
                    ) from e
                if e.code == 403:
                    raise AccessError(
                        "Insufficient permissions",
                        hint="Verify your token has write access to this space",
                    ) from e
                if e.code == 404:
                    raise NotFoundError(
                        "Resource not found",
                        hint="Check the space key or page ID",
                    ) from e
                raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt >= self.http.max_retries - 1:
                    raise NetworkError(
                        f"Network error talking to Confluence ({method} {path})",
                        hint="Check connectivity or raise publish.http upload/api timeouts",
                    ) from e
                wait = self.http.backoff_base**attempt + random.uniform(0, 0.5)
                print(
                    f"  API retry {attempt + 1}/{self.http.max_retries} "
                    f"({method} {path}): {e} — sleeping {wait:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(wait)

        if last_error and last_error.code == 429:
            raise NetworkError(
                "Rate limited by Confluence",
                hint="Wait a moment and try again",
            ) from last_error
        if last_error and last_error.code >= 500:
            raise NetworkError(
                f"Confluence server error ({last_error.code})",
                hint="Check status.atlassian.com",
            ) from last_error
        if last_error:
            raise last_error
        raise NetworkError("Request failed", hint="Unknown Confluence API error")

    def attach_file(
        self,
        page_id: str,
        file_path: str,
        filename: str,
        content_type: str = "image/png",
    ) -> dict[str, Any]:
        boundary = "----md-to-adf-boundary"
        with open(file_path, "rb") as f:
            file_data = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

        headers = {
            "Authorization": self.auth_header,
            "X-Atlassian-Token": "nocheck",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        url = f"https://{self.domain}/wiki/rest/api/content/{page_id}/child/attachment"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urlopen_with_retry(
            req,
            timeout=self.http.upload_timeout,
            max_retries=self.http.max_retries,
            backoff_base=self.http.backoff_base,
            label=f"upload {filename}",
        ) as resp:
            return json.loads(resp.read().decode())


@dataclass
class PageSpec:
    rel_path: str
    abs_path: Path
    title: str
    parent_rel: str | None
    sort_key: tuple


@dataclass
class RemotePage:
    page_id: str
    title: str
    parent_id: str
    adf: dict[str, Any] | None = None
    adf_fingerprint: str | None = None


@dataclass
class PublishStats:
    unchanged: int = 0
    created: int = 0
    updated: int = 0
    skipped_dry_run: int = 0


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def extract_title(content: str, filename: str) -> str:
    for line in content.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    stem = Path(filename).stem
    return stem.replace("-", " ").replace("_", " ").title()


def strip_leading_h1(content: str) -> str:
    lines = content.splitlines()
    if lines and re.match(r"^#\s+", lines[0]):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines)


def folder_sort_key(
    folder_parts: tuple[str, ...],
    layout: PublishLayoutConfig,
) -> tuple[Any, ...]:
    if not folder_parts:
        return (0,)
    section = folder_parts[0]
    section_order = layout.section_order.get(section, 50)
    if len(folder_parts) >= 2 and folder_parts[1] in layout.audience_order:
        return (section_order, layout.audience_order[folder_parts[1]], *folder_parts[2:])
    return (section_order, *folder_parts[1:])


def discover_pages(source_dir: Path, layout: PublishLayoutConfig) -> list[PageSpec]:
    pages: list[PageSpec] = []
    for path in sorted(source_dir.rglob("*.md")):
        rel = posix_rel(path, source_dir)
        if rel in layout.skip_files:
            continue
        content = path.read_text(encoding="utf-8")
        title = extract_title(content, path.name)
        parent_rel = resolve_parent_rel(rel, source_dir)
        parts = PurePosixPath(rel).parts
        sort_key = (
            folder_sort_key(parts[:-1], layout),
            0 if path.name == "README.md" else 1,
            path.name,
        )
        pages.append(PageSpec(rel, path, title, parent_rel, sort_key))
    pages.sort(key=lambda p: p.sort_key)
    return pages


def resolve_parent_rel(rel: str, source_dir: Path) -> str | None:
    parts = PurePosixPath(rel).parts
    if len(parts) == 1:
        return None
    parent_dir = PurePosixPath(*parts[:-1])

    if parts[-1] == "README.md":
        # Section index: attach under nearest ancestor README (e.g. technical/README.md)
        for depth in range(len(parent_dir.parts), 0, -1):
            ancestor = PurePosixPath(*parent_dir.parts[:depth]) / "README.md"
            ancestor_rel = ancestor.as_posix()
            if ancestor_rel != rel and (source_dir / ancestor_rel).is_file():
                return ancestor_rel
        return "README.md"

    readme = (parent_dir / "README.md").as_posix()
    if readme != rel and (source_dir / readme).is_file():
        return readme
    return "README.md"


@dataclass
class LinkTarget:
    rel_path: str
    title: str
    page_id: str | None = None

    def wiki_url(self, domain: str, space_key: str) -> str | None:
        if not self.page_id:
            return None
        return page_wiki_url(domain, space_key, self.page_id, self.title)


@dataclass
class LinkCatalog:
    by_rel: dict[str, LinkTarget]
    domain: str
    space_key: str

    def url_for(self, rel_path: str) -> str | None:
        target = self.by_rel.get(rel_path)
        return target.wiki_url(self.domain, self.space_key) if target else None

    def refresh_from_publisher(self, publisher: "SuitePublisher") -> None:
        for rel, page_id in publisher.page_ids.items():
            if rel in self.by_rel:
                self.by_rel[rel].page_id = page_id
                if rel in publisher.page_titles:
                    self.by_rel[rel].title = publisher.page_titles[rel]

    def update_page_id(self, rel_path: str, page_id: str) -> None:
        if rel_path in self.by_rel:
            self.by_rel[rel_path].page_id = page_id

    def urls_map(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for rel, target in self.by_rel.items():
            url = target.wiki_url(self.domain, self.space_key)
            if url:
                out[rel] = url
        return out

    def scan_unresolved(
        self, specs: list[PageSpec], github: GitHubLinkConfig | None
    ) -> list[tuple[str, str, str]]:
        unresolved: list[tuple[str, str, str]] = []
        suite_prefix = github.suite_prefix if github else DEFAULT_SOURCE
        for spec in specs:
            for href in extract_markdown_hrefs(spec.abs_path.read_text(encoding="utf-8")):
                path_part, _ = split_href(href)
                if not path_part or path_part.startswith("#"):
                    continue
                if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path_part):
                    continue
                resolved_suite = resolve_href(spec.rel_path, href)
                if resolved_suite and resolved_suite in self.by_rel:
                    if not self.url_for(resolved_suite):
                        unresolved.append(
                            (spec.rel_path, href, "target page has no Confluence id yet")
                        )
                    continue
                repo_path, _ = resolve_repo_path(
                    spec.rel_path,
                    href,
                    suite_prefix,
                    github.link_paths if github else None,
                )
                if repo_path and github:
                    continue
                if resolved_suite and resolved_suite.endswith(".md"):
                    unresolved.append((spec.rel_path, href, "not in published suite"))
                elif not github:
                    unresolved.append((spec.rel_path, href, "outside suite, no github_repo"))
        return unresolved


def build_link_catalog(
    specs: list[PageSpec],
    page_ids: dict[str, str],
    page_titles: dict[str, str],
    domain: str,
    space_key: str,
    dry_run: bool = False,
) -> LinkCatalog:
    by_rel: dict[str, LinkTarget] = {}
    for spec in specs:
        pid = page_ids.get(spec.rel_path)
        if not pid and dry_run:
            pid = f"dry-{spec.rel_path}"
        by_rel[spec.rel_path] = LinkTarget(
            rel_path=spec.rel_path,
            title=page_titles.get(spec.rel_path, spec.title),
            page_id=pid,
        )
    return LinkCatalog(by_rel=by_rel, domain=domain, space_key=space_key)


def split_href(href: str) -> tuple[str, str | None]:
    href = href.strip()
    if "#" not in href:
        return href, None
    path, fragment = href.split("#", 1)
    return path, fragment or None


def extract_markdown_hrefs(content: str) -> list[str]:
    return [m.group(3).strip() for m in LINK_PATTERN.finditer(content) if not m.group(1).startswith("!")]


def resolve_href(source_rel: str, href: str) -> str | None:
    path_part, _ = split_href(href)
    path_part = path_part.strip()
    if not path_part or path_part.startswith("#"):
        return None
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path_part):
        return None
    if path_part.startswith("/"):
        return None
    base = PurePosixPath(source_rel).parent
    target = (base / path_part).as_posix()
    return normalize_posix_path(target) or None


def normalize_posix_path(path: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(path).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return PurePosixPath(*parts).as_posix() if parts else ""


def resolve_repo_path(
    source_rel: str,
    href: str,
    suite_prefix: str = DEFAULT_SOURCE,
    link_paths: LinkPathConfig | None = None,
) -> tuple[str | None, str | None]:
    """Resolve a markdown href to a repo-root-relative path."""
    paths = link_paths or LinkPathConfig(
        repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
        root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
    )
    path_part, fragment = split_href(href)
    path_part = path_part.strip()
    if not path_part or path_part.startswith("#"):
        return None, fragment
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path_part):
        return None, fragment
    if path_part.startswith("/"):
        return None, fragment
    clean = path_part.lstrip("./")
    if is_repo_root_path(clean, paths):
        return clean, fragment
    source_full = f"{suite_prefix}/{source_rel}"
    target = normalize_posix_path(
        str(PurePosixPath(source_full).parent / path_part)
    )
    if target:
        target = target.replace("\\", "/")
    return (target or None), fragment


def suite_rel_from_repo_path(repo_path: str, suite_prefix: str = DEFAULT_SOURCE) -> str | None:
    prefix = suite_prefix.rstrip("/") + "/"
    normalized = repo_path.strip().rstrip("/").replace("\\", "/")
    if normalized == suite_prefix.rstrip("/"):
        return "README.md"
    if normalized.startswith(prefix):
        rel = normalized[len(prefix) :]
        return rel or "README.md"
    return None


def confluence_url_for_repo_path(
    repo_path: str,
    catalog: LinkCatalog | None,
    suite_prefix: str,
    page_urls: dict[str, str] | None = None,
    fragment: str | None = None,
) -> tuple[str, str] | None:
    """Map a repo-root path under docs/suite/ to its Confluence wiki URL."""
    suite_rel = suite_rel_from_repo_path(repo_path, suite_prefix)
    if not suite_rel or not catalog or suite_rel not in catalog.by_rel:
        return None
    urls = dict(catalog.urls_map())
    if page_urls:
        urls.update(page_urls)
    url = urls.get(suite_rel) or catalog.url_for(suite_rel)
    if not url:
        return None
    if fragment:
        url = f"{url}#{fragment}"
    return suite_rel, url


def is_suite_markdown_path(repo_path: str, suite_prefix: str) -> bool:
    """True when repo_path points at a markdown file inside the published suite."""
    rel = suite_rel_from_repo_path(repo_path, suite_prefix)
    return bool(rel and rel.endswith(".md"))


@dataclass
class GitHubLinkConfig:
    repo_url: str
    ref: str = "main"
    suite_prefix: str = DEFAULT_SOURCE
    link_inline_paths: bool = True
    link_paths: LinkPathConfig = field(
        default_factory=lambda: LinkPathConfig(
            repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
            root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
        )
    )

    @classmethod
    def from_settings(
        cls,
        *,
        github_repo: str | None,
        github_ref: str | None,
        repo_base_url: str | None,
        suite_prefix: str,
        link_inline_paths: bool = True,
        link_paths: LinkPathConfig | None = None,
    ) -> "GitHubLinkConfig | None":
        paths = link_paths or LinkPathConfig(
            repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
            root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
        )
        if github_repo:
            return cls(
                repo_url=github_repo.rstrip("/"),
                ref=github_ref or "main",
                suite_prefix=suite_prefix,
                link_inline_paths=link_inline_paths,
                link_paths=paths,
            )
        if repo_base_url:
            parsed = cls._parse_legacy_repo_base_url(repo_base_url)
            if parsed:
                base, ref, _subdir = parsed
                return cls(
                    repo_url=base,
                    ref=ref,
                    suite_prefix=suite_prefix,
                    link_inline_paths=link_inline_paths,
                    link_paths=paths,
                )
        return None

    @staticmethod
    def _parse_legacy_repo_base_url(url: str) -> tuple[str, str, str] | None:
        url = url.rstrip("/")
        m = re.match(
            r"(https?://github\.com/[^/]+/[^/]+)/(blob|tree)/([^/]+)(?:/(.*))?$",
            url,
        )
        if m:
            return m.group(1), m.group(3), m.group(4) or ""
        return None

    def url_for_path(self, repo_path: str, fragment: str | None = None) -> str:
        repo_path = repo_path.strip().lstrip("/").replace("\\", "/")
        base = self.repo_url.rstrip("/")
        if repo_path.endswith("/") or self._looks_like_directory(repo_path):
            url = f"{base}/tree/{self.ref}/{repo_path.rstrip('/')}"
        else:
            url = f"{base}/blob/{self.ref}/{repo_path}"
        if fragment:
            url = f"{url}#{fragment}"
        return url

    @staticmethod
    def _looks_like_directory(path: str) -> bool:
        if path.endswith("/"):
            return True
        name = PurePosixPath(path).name
        return "." not in name and name != ""


GCP_LINK_SCHEME = "gcp://"


@dataclass
class GcpDeploymentConfig:
    """Optional GCP Console deep links for DevOps docs (from publish.gcp_deployment)."""

    project_id: str
    region: str = "us-central1"
    zone: str = ""
    artifact_registry_repo: str = ""
    backend_service: str = ""
    frontend_service: str = ""
    cloud_sql_instance: str = ""
    documents_bucket: str = ""
    cloud_build_trigger: str = ""
    qdrant_vm: str = ""
    ingest_worker_vm: str = ""
    secret_family: str = ""

    @classmethod
    def from_settings(cls, pub: dict[str, Any]) -> "GcpDeploymentConfig | None":
        raw = pub.get("gcp_deployment")
        if not isinstance(raw, dict):
            return None
        enabled = raw.get("enabled", raw.get("link_gcp_urls", True))
        if enabled is False:
            return None
        project_id = str(raw.get("project_id") or "").strip()
        if not project_id:
            return None
        region = str(raw.get("region") or "us-central1").strip()
        zone = str(raw.get("zone") or raw.get("compute_zone") or "").strip()
        if not zone:
            zone = f"{region}-a"
        return cls(
            project_id=project_id,
            region=region,
            zone=zone,
            artifact_registry_repo=str(raw.get("artifact_registry_repo") or ""),
            backend_service=str(raw.get("backend_service") or ""),
            frontend_service=str(raw.get("frontend_service") or ""),
            cloud_sql_instance=str(raw.get("cloud_sql_instance") or ""),
            documents_bucket=str(raw.get("documents_bucket") or ""),
            cloud_build_trigger=str(raw.get("cloud_build_trigger") or ""),
            qdrant_vm=str(raw.get("qdrant_vm") or ""),
            ingest_worker_vm=str(raw.get("ingest_worker_vm") or ""),
            secret_family=str(raw.get("secret_family") or ""),
        )

    def _project_q(self) -> str:
        return urllib.parse.quote(self.project_id, safe="")

    def _region_q(self) -> str:
        return urllib.parse.quote(self.region, safe="")

    def _zone_q(self) -> str:
        return urllib.parse.quote(self.zone, safe="")

    def url_for(self, path: str) -> str | None:
        """Map gcp:// resource path to a Cloud Console URL."""
        path = path.strip().lstrip("/").lower()
        project = self._project_q()
        region = self._region_q()
        zone = self._zone_q()

        if not path or path in {"project", "dashboard", "home"}:
            return f"https://console.cloud.google.com/home/dashboard?project={project}"

        if path in {"cloud-run", "run"}:
            return f"https://console.cloud.google.com/run?project={project}"

        if path in {"cloud-run/backend", "run/backend", "backend"}:
            if not self.backend_service:
                return None
            svc = urllib.parse.quote(self.backend_service, safe="")
            return (
                f"https://console.cloud.google.com/run/detail/{region}/{svc}"
                f"/metrics?project={project}"
            )

        if path in {"cloud-run/frontend", "run/frontend", "frontend"}:
            if not self.frontend_service:
                return None
            svc = urllib.parse.quote(self.frontend_service, safe="")
            return (
                f"https://console.cloud.google.com/run/detail/{region}/{svc}"
                f"/metrics?project={project}"
            )

        if path in {"cloud-build", "cloud-build/triggers", "build", "build/triggers", "triggers"}:
            return f"https://console.cloud.google.com/cloud-build/triggers?project={project}"

        if path in {"cloud-build/history", "build/history", "builds"}:
            return f"https://console.cloud.google.com/cloud-build/builds?project={project}"

        if path in {"gcs", "gcs/documents", "storage", "storage/documents", "documents"}:
            if not self.documents_bucket:
                return None
            bucket = urllib.parse.quote(self.documents_bucket, safe="")
            return f"https://console.cloud.google.com/storage/browser/{bucket}?project={project}"

        if path in {"sql", "cloud-sql", "cloudsql"}:
            if not self.cloud_sql_instance:
                return None
            inst = urllib.parse.quote(self.cloud_sql_instance, safe="")
            return (
                f"https://console.cloud.google.com/sql/instances/{inst}"
                f"/overview?project={project}"
            )

        if path in {"secrets", "secret-manager"}:
            return f"https://console.cloud.google.com/security/secret-manager?project={project}"

        if path in {"compute", "compute/instances", "vms"}:
            return f"https://console.cloud.google.com/compute/instances?project={project}"

        if path in {"qdrant"}:
            if self.qdrant_vm:
                vm = urllib.parse.quote(self.qdrant_vm, safe="")
                return (
                    f"https://console.cloud.google.com/compute/instancesDetail/zones/"
                    f"{zone}/instances/{vm}?project={project}"
                )
            return f"https://console.cloud.google.com/compute/instances?project={project}"

        if path in {"ingest-worker", "ingest/worker", "worker"}:
            if self.ingest_worker_vm:
                vm = urllib.parse.quote(self.ingest_worker_vm, safe="")
                return (
                    f"https://console.cloud.google.com/compute/instancesDetail/zones/"
                    f"{zone}/instances/{vm}?project={project}"
                )
            return f"https://console.cloud.google.com/compute/instances?project={project}"

        if path in {"artifacts", "artifact-registry"}:
            if not self.artifact_registry_repo:
                return f"https://console.cloud.google.com/artifacts?project={project}"
            repo = urllib.parse.quote(self.artifact_registry_repo, safe="")
            return (
                f"https://console.cloud.google.com/artifacts/docker/{project}"
                f"/{region}/{repo}?project={project}"
            )

        if path in {"vpc", "vpc/connectors", "connectors"}:
            return f"https://console.cloud.google.com/networking/connectors/list?project={project}"

        if path in {"pubsub", "pub-sub"}:
            return f"https://console.cloud.google.com/cloudpubsub/topic/list?project={project}"

        if path.startswith("gcs/"):
            bucket = urllib.parse.quote(path[4:], safe="")
            return f"https://console.cloud.google.com/storage/browser/{bucket}?project={project}"

        return None

    def gcp_href(self, href: str) -> str | None:
        href = href.strip()
        if not href.lower().startswith(GCP_LINK_SCHEME):
            return None
        return self.url_for(href[len(GCP_LINK_SCHEME) :])


def is_repo_root_path(text: str, link_paths: LinkPathConfig) -> bool:
    """True when inline text is already repo-root-relative (not relative to a suite .md file)."""
    text = text.strip().rstrip("/")
    if text in link_paths.root_repo_filenames:
        return True
    return any(text.startswith(prefix) for prefix in link_paths.repo_path_prefixes)


def path_exists_at_repo_root(repo_path: str, workspace_root: Path | None) -> bool:
    if not workspace_root:
        return False
    rel = repo_path.split("#", 1)[0].strip().lstrip("/").replace("\\", "/")
    if not rel:
        return False
    return (workspace_root / rel).exists()


def is_api_route_shorthand(text: str) -> bool:
    """True for REST/API shorthand that must not become GitHub file links."""
    text = text.strip()
    if text.startswith(".../") or text.startswith("/api/"):
        return True
    if re.match(r"^(GET|POST|PUT|PATCH|DELETE|HEAD)\s+", text, re.I):
        return True
    if re.search(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}", text):
        return True
    return False


def is_linkable_repo_path(text: str, link_paths: LinkPathConfig) -> bool:
    """True when inline text should become a GitHub link (strict)."""
    text = text.strip()
    if not text or "\n" in text or "`" in text:
        return False
    if any(ch in text for ch in "[]()"):
        return False
    if "{" in text or "}" in text:
        return False
    if text.startswith(("/", "~", "\\")):
        return False
    if "://" in text or text.lower().startswith("www."):
        return False
    if is_api_route_shorthand(text):
        return False
    if is_repo_root_path(text, link_paths):
        return True
    if text.startswith("roles/"):
        return False
    if re.match(r"^[A-Z][A-Z0-9_]+$", text):
        return False
    if re.match(r"^[A-Z][a-zA-Z0-9]+$", text) and "/" not in text:
        return False
    if text in link_paths.root_repo_filenames:
        return True
    if any(text.startswith(prefix) for prefix in link_paths.repo_path_prefixes):
        return True
    if text.endswith("/"):
        return True
    if "/" in text and any(text.endswith(ext) for ext in REPO_FILE_EXTENSIONS):
        return True
    return False


REPO_FILE_EXTENSIONS = (
    ".py",
    ".md",
    ".toml",
    ".yaml",
    ".yml",
    ".sh",
    ".tpl",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".sql",
    ".html",
    ".css",
)


@dataclass
class GitHubPathVerifier:
    """Optional GitHub Contents API check before wiring inline/repo links."""

    config: GitHubLinkConfig
    token: str | None = None
    enabled: bool = True
    workspace_root: Path | None = None
    _cache: dict[tuple[str, str], bool] = field(default_factory=dict)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def _owner_repo(self) -> tuple[str, str]:
        match = re.match(
            r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$",
            self.config.repo_url.rstrip("/"),
        )
        if not match:
            raise ValueError(f"Invalid github_repo URL: {self.config.repo_url!r}")
        return match.group(1), match.group(2)

    def exists(self, repo_path: str) -> bool:
        """Return True if path exists locally or on GitHub at config.ref (cached)."""
        repo_path = repo_path.strip().lstrip("/").replace("\\", "/")
        if not repo_path:
            return False
        cache_key = (repo_path, self.config.ref)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if path_exists_at_repo_root(repo_path, self.workspace_root):
            self._cache[cache_key] = True
            return True

        if not self.enabled:
            self._cache[cache_key] = False
            return False

        owner, repo = self._owner_repo()
        encoded_path = urllib.parse.quote(repo_path, safe="/")
        api_url = (
            f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}"
            f"?ref={urllib.parse.quote(self.config.ref, safe='')}"
        )
        headers = {
            "User-Agent": "pr-agent-confluence-publish/1.0",
            "Accept": "application/vnd.github+json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(api_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                ok = 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            # Only treat 2xx as confirmed; 401/403 on private repos must not create links.
            ok = False
        except (urllib.error.URLError, OSError, TimeoutError):
            ok = path_exists_at_repo_root(repo_path, self.workspace_root)

        self._cache[cache_key] = ok
        if not ok:
            self.skipped.append((repo_path, "404"))
        return ok


def looks_like_repo_path(text: str, link_paths: LinkPathConfig | None = None) -> bool:
    paths = link_paths or LinkPathConfig(
        repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
        root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
    )
    return is_linkable_repo_path(text, paths)


def rewrite_markdown_links(
    content: str,
    source_rel: str,
    catalog: LinkCatalog | None,
    page_urls: dict[str, str] | None,
    github: GitHubLinkConfig | None,
    verifier: GitHubPathVerifier | None = None,
    gcp: GcpDeploymentConfig | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    urls = dict(catalog.urls_map() if catalog else {})
    if page_urls:
        urls.update(page_urls)
    wired: list[tuple[str, str]] = []
    suite_prefix = github.suite_prefix if github else DEFAULT_SOURCE
    link_paths = github.link_paths if github else LinkPathConfig(
        repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
        root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
    )

    def replace(match: re.Match[str]) -> str:
        prefix, text, href = match.group(1), match.group(2), match.group(3).strip()
        if prefix.startswith("!"):
            return match.group(0)
        path_part, fragment = split_href(href)
        if path_part.startswith("#") or (not path_part and fragment):
            return match.group(0)
        if gcp:
            gcp_url = gcp.gcp_href(path_part or href)
            if gcp_url:
                wired.append((href, gcp_url))
                return f"[{text}]({gcp_url})"
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", path_part or href):
            return match.group(0)

        resolved_suite = resolve_href(source_rel, href)
        if catalog and resolved_suite and resolved_suite in catalog.by_rel:
            if resolved_suite in urls:
                url = urls[resolved_suite]
                if fragment:
                    url = f"{url}#{fragment}"
                wired.append((href, url))
                return f"[{text}]({url})"
            return match.group(0)

        repo_path, repo_fragment = resolve_repo_path(
            source_rel, href, suite_prefix, link_paths
        )
        fragment = repo_fragment or fragment
        link_target: str | None = None
        if is_linkable_repo_path(path_part, link_paths):
            link_target = path_part.lstrip("./")
        elif repo_path and is_linkable_repo_path(repo_path, link_paths):
            link_target = repo_path
        if link_target and github:
            mapped = confluence_url_for_repo_path(
                link_target, catalog, suite_prefix, page_urls, fragment
            )
            if mapped:
                _, url = mapped
                wired.append((href, url))
                return f"[{text}]({url})"
            if verifier and not verifier.exists(link_target):
                return match.group(0)
            url = github.url_for_path(link_target, fragment)
            wired.append((href, url))
            return f"[{text}]({url})"

        return match.group(0)

    return LINK_PATTERN.sub(replace, content), wired


def resolve_inline_repo_path(
    source_rel: str,
    text: str,
    suite_prefix: str = DEFAULT_SOURCE,
    workspace_root: Path | None = None,
    link_paths: LinkPathConfig | None = None,
) -> str | None:
    paths = link_paths or LinkPathConfig(
        repo_path_prefixes=DEFAULT_REPO_PATH_PREFIXES,
        root_repo_filenames=DEFAULT_ROOT_REPO_FILENAMES,
    )
    text = text.strip()
    if not is_linkable_repo_path(text, paths):
        return None
    bare = text.rstrip("/")
    if is_repo_root_path(bare, paths):
        return bare
    if workspace_root and path_exists_at_repo_root(bare, workspace_root):
        return bare
    if text in paths.root_repo_filenames:
        return text
    source_full = f"{suite_prefix}/{source_rel}"
    resolved = normalize_posix_path(str(PurePosixPath(source_full).parent / text))
    if not resolved or not is_linkable_repo_path(resolved, paths):
        return None
    if workspace_root and not path_exists_at_repo_root(resolved, workspace_root):
        return None
    return resolved.replace("\\", "/")


def rewrite_inline_repo_paths(
    content: str,
    github: GitHubLinkConfig | None,
    source_rel: str = "README.md",
    verifier: GitHubPathVerifier | None = None,
    catalog: LinkCatalog | None = None,
    page_urls: dict[str, str] | None = None,
    gcp: GcpDeploymentConfig | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    if (not github or not github.link_inline_paths) and not gcp:
        return content, []

    wired: list[tuple[str, str]] = []
    out: list[str] = []
    in_fence = False
    suite_prefix = github.suite_prefix if github else DEFAULT_SOURCE

    for line in content.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or "`" not in line:
            out.append(line)
            continue

        def replace_code(match: re.Match[str]) -> str:
            path = match.group(1)
            if gcp and path.lower().startswith(GCP_LINK_SCHEME):
                url = gcp.gcp_href(path)
                if url:
                    label = path[len(GCP_LINK_SCHEME) :] or "GCP"
                    wired.append((path, url))
                    return f"[{label}]({url})"
                return match.group(0)
            if not github or not github.link_inline_paths:
                return match.group(0)
            ws = verifier.workspace_root if verifier else None
            paths = github.link_paths if github else None
            repo_path = resolve_inline_repo_path(
                source_rel, path, suite_prefix, workspace_root=ws, link_paths=paths
            )
            if not repo_path:
                return match.group(0)
            mapped = confluence_url_for_repo_path(
                repo_path, catalog, suite_prefix, page_urls
            )
            if mapped:
                _, url = mapped
                wired.append((path, url))
                return f"[{path}]({url})"
            # Suite .md paths must not fall through to GitHub.
            if is_suite_markdown_path(repo_path, suite_prefix):
                return match.group(0)
            if verifier and not verifier.exists(repo_path):
                return match.group(0)
            url = github.url_for_path(repo_path)
            wired.append((path, url))
            # Plain link text (no nested backticks): md-to-adf preserves whitespace correctly.
            return f"[{path}]({url})"

        out.append(re.sub(r"`([^`\n]+)`", replace_code, line))

    return "".join(out), wired


def expand_publish_specs(
    selected: list[PageSpec], all_specs: list[PageSpec]
) -> list[PageSpec]:
    """Include ancestor pages so Confluence parent chain exists for --only runs."""
    by_rel = {s.rel_path: s for s in all_specs}
    needed: set[str] = set()
    for spec in selected:
        current: str | None = spec.rel_path
        while current:
            needed.add(current)
            parent_rel = by_rel[current].parent_rel if current in by_rel else None
            current = parent_rel
    expanded = [by_rel[r] for r in needed if r in by_rel]
    expanded.sort(key=lambda p: p.sort_key)
    return expanded


def print_page_hierarchy(specs: list[PageSpec], page_ids: dict[str, str]) -> None:
    """Show expected Confluence parent chain for each page."""
    by_rel = {s.rel_path: s for s in specs}

    def line(rel: str, indent: int = 0) -> None:
        spec = by_rel.get(rel)
        if not spec:
            return
        pid = page_ids.get(rel, "pending")
        parent_label = spec.parent_rel or "(config parent_page_id)"
        print(f"{'  ' * indent}{rel}")
        print(f"{'  ' * indent}  title: {spec.title}")
        print(f"{'  ' * indent}  parent: {parent_label}  id: {pid}")

    print("\nExpected Confluence hierarchy:")
    roots = [s for s in specs if s.parent_rel is None]
    seen: set[str] = set()

    def walk(rel: str, depth: int) -> None:
        if rel in seen:
            return
        seen.add(rel)
        line(rel, depth)
        for child in sorted(
            (c for c in specs if c.parent_rel == rel),
            key=lambda p: p.sort_key,
        ):
                walk(child.rel_path, depth + 1)

    for root in roots:
        walk(root.rel_path, 0)
    for spec in specs:
        if spec.rel_path not in seen:
            walk(spec.rel_path, 0)


def audit_links(
    specs: list[PageSpec],
    catalog: LinkCatalog,
    github: GitHubLinkConfig | None,
    verifier: GitHubPathVerifier | None = None,
    gcp: GcpDeploymentConfig | None = None,
) -> None:
    if verifier:
        verifier.skipped.clear()

    print("\nLink catalog (planned Confluence page titles):")
    for spec in specs:
        target = catalog.by_rel[spec.rel_path]
        pid = target.page_id or "pending"
        print(f"  {spec.rel_path} -> \"{target.title}\" ({pid})")

    print("\nInternal .md link wiring:")
    confluence_links = 0
    github_md_links = 0
    github_inline_links = 0
    confluence_inline_links = 0
    gcp_links = 0
    for spec in specs:
        body = strip_leading_h1(spec.abs_path.read_text(encoding="utf-8"))
        body, wired_md = rewrite_markdown_links(
            body, spec.rel_path, catalog, None, github, verifier, gcp
        )
        _, wired_inline = rewrite_inline_repo_paths(
            body, github, spec.rel_path, verifier, catalog, None, gcp
        )
        for href, url in wired_md:
            if "/wiki/spaces/" in url:
                confluence_links += 1
                print(f"  WIRE {spec.rel_path}: {href}")
            elif "console.cloud.google.com" in url:
                gcp_links += 1
                print(f"  GCP md {spec.rel_path}: {href} -> {url}")
            elif "github.com/" in url:
                github_md_links += 1
                print(f"  GITHUB md {spec.rel_path}: {href} -> {url}")
        for path, url in wired_inline:
            if "/wiki/spaces/" in url:
                confluence_inline_links += 1
                if confluence_inline_links <= 12:
                    print(f"  WIRE inline {spec.rel_path}: `{path}`")
            elif "console.cloud.google.com" in url:
                gcp_links += 1
                if gcp_links <= 12:
                    print(f"  GCP inline {spec.rel_path}: `{path}`")
            elif "github.com/" in url:
                github_inline_links += 1
                if github_inline_links <= 12:
                    print(f"  GITHUB inline {spec.rel_path}: `{path}`")

    unresolved = catalog.scan_unresolved(specs, github)
    if unresolved:
        print(f"\nUnresolved ({len(unresolved)}):")
        for src, href, reason in unresolved[:25]:
            print(f"  {src}: ({href}) — {reason}")
    else:
        print(
            f"\nAll resolvable links mapped "
            f"({confluence_links} Confluence md, {confluence_inline_links} Confluence inline, "
            f"{github_md_links} GitHub md, {github_inline_links} GitHub inline, "
            f"{gcp_links} GCP Console)."
        )
    if verifier and verifier.skipped:
        unique = sorted(set(verifier.skipped))
        print(f"\nSkipped {len(unique)} invalid GitHub path(s) (404 on {verifier.config.ref}):")
        for repo_path, reason in unique[:25]:
            print(f"  SKIP `{repo_path}` ({reason})")
        if len(unique) > 25:
            print(f"  … and {len(unique) - 25} more")


def page_wiki_url(domain: str, space_key: str, page_id: str, title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "-"))
    return f"https://{domain}/wiki/spaces/{space_key}/pages/{page_id}/{slug}"


def normalize_wiki_href(href: str) -> str:
    path_part, fragment = split_href(href)
    if path_part.startswith("github:"):
        rest = path_part[len("github:") :]
        kind, _, repo_path = rest.partition(":")
        if kind and repo_path:
            base = f"github:{kind}:{repo_path.replace(chr(92), '/')}"
            return f"{base}#{fragment}" if fragment else base
    m = WIKI_PAGE_ID_RE.search(path_part)
    if m:
        base = f"page:{m.group(1)}"
        return f"{base}#{fragment}" if fragment else base
    gh = re.match(
        r"https?://github\.com/[^/]+/[^/]+/(blob|tree)/[^/]+/(.+?)(?:#(.*))?$",
        path_part,
    )
    if gh:
        repo_path = gh.group(2).replace("\\", "/")
        base = f"github:{gh.group(1)}:{repo_path}"
        frag = gh.group(3) or fragment
        return f"{base}#{frag}" if frag else base
    return href.replace("\\", "/") if "\\" in href else href


def normalize_adf(node: Any) -> Any:
    """Canonical form for stable ADF comparison."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        node_type = node.get("type")
        for key in sorted(node.keys()):
            value = node[key]
            if value is None:
                continue
            if key == "attrs" and isinstance(value, dict):
                attrs = {k: v for k, v in sorted(value.items()) if v is not None}
                if node_type in ("orderedList", "bulletList") and attrs.get("order") == 1:
                    attrs.pop("order", None)
                if node_type == "table" and attrs.get("layout") == "default":
                    attrs.pop("layout", None)
                if node_type in ("tableCell", "tableHeader"):
                    if attrs.get("colspan") == 1:
                        attrs.pop("colspan", None)
                    if attrs.get("rowspan") == 1:
                        attrs.pop("rowspan", None)
                if node_type == "media":
                    attrs = {k: v for k, v in attrs.items() if not str(k).startswith("__")}
                    attrs.pop("localId", None)
                if node_type == "extension":
                    ext_key = attrs.get("extensionKey", "")
                    if ext_key in ("mermaid-cloud", "mermaid"):
                        params = attrs.get("parameters") or {}
                        macro_params = params.get("macroParams") or {}
                        filename = (macro_params.get("filename") or {}).get("value")
                        revision = (macro_params.get("revision") or {}).get("value", "1")
                        if filename:
                            attrs["parameters"] = {
                                "macroParams": {
                                    "filename": {"value": filename},
                                    "revision": {"value": revision},
                                }
                            }
                        attrs.pop("localId", None)
                if attrs:
                    out[key] = attrs
                continue
            if key == "marks" and isinstance(value, list):
                marks = []
                for mark in value:
                    if not isinstance(mark, dict):
                        continue
                    m = {k: v for k, v in sorted(mark.items()) if v is not None}
                    if m.get("type") == "link" and isinstance(m.get("attrs"), dict):
                        href = m["attrs"].get("href", "")
                        m["attrs"] = {"href": normalize_wiki_href(href)}
                    marks.append(m)
                # Confluence drops code marks on linked text; ignore for stable diffs.
                if any(m.get("type") == "link" for m in marks):
                    marks = [m for m in marks if m.get("type") != "code"]
                if marks:
                    out[key] = marks
                continue
            out[key] = normalize_adf(value)
        return out
    if isinstance(node, list):
        return [normalize_adf(item) for item in node]
    return node


def adf_fingerprint(adf: dict[str, Any]) -> str:
    normalized = normalize_adf(adf)
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


GITHUB_LINK_HREF_RE = re.compile(r"github\.com/[^/]+/[^/]+/(blob|tree)/")


def render_mermaid_via_kroki(source: str) -> Path | None:
    """Render mermaid via Kroki (public service; used when local mmdc is unavailable)."""
    req = urllib.request.Request(
        "https://kroki.io/mermaid/png",
        data=source.encode("utf-8"),
        headers={
            "Content-Type": "text/plain",
            "User-Agent": "pr-agent-confluence-publish/1.0",
            "Kroki-Diagram-Options-background": MERMAID_PNG_BACKGROUND,
            "Kroki-Diagram-Options-no-transparency": "",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except (urllib.error.URLError, OSError, TimeoutError):
        return None
    if not data.startswith(b"\x89PNG"):
        return None
    out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out.write(data)
    out.close()
    path = Path(out.name)
    finalize_mermaid_png(path)
    return path


def _run_renderer_command(cmd: list[str]) -> bool:
    """Run mmdc/npx; on Windows .cmd/.bat launchers need shell=True."""
    use_shell = sys.platform == "win32" and str(cmd[0]).lower().endswith(
        (".cmd", ".bat")
    )
    try:
        if use_shell:
            quoted = " ".join(f'"{part}"' if " " in part else part for part in cmd)
            subprocess.run(
                quoted, check=True, capture_output=True, timeout=180, shell=True
            )
        else:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def render_mermaid_to_png(source: str, *, allow_remote: bool = True) -> Path | None:
    """Render mermaid source to a temporary PNG (mmdc, npx, or Kroki fallback)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".mmd", delete=False, encoding="utf-8"
    ) as src_file:
        src_file.write(source)
        src_path = src_file.name

    out_path = src_path.replace(".mmd", ".png")
    cmd = mermaid_cli_command(input_path=src_path, output_path=out_path)

    try:
        if cmd and _run_renderer_command(cmd) and Path(out_path).is_file():
            png_path = Path(out_path)
            finalize_mermaid_png(png_path)
            return png_path

        if allow_remote:
            return render_mermaid_via_kroki(source)

        return None
    finally:
        if os.path.exists(src_path):
            os.unlink(src_path)
        if os.path.exists(out_path) and not Path(out_path).is_file():
            os.unlink(out_path)


def mermaid_renderer_available(*, allow_remote: bool = True) -> bool:
    if is_mmdc_available():
        return True
    if shutil.which("npx") or shutil.which("npx.cmd"):
        return True
    return allow_remote


def strip_mermaid_macro_nodes(adf: dict[str, Any]) -> dict[str, Any]:
    """Replace legacy/broken mermaid extension nodes with code blocks."""

    def walk(nodes: list[Any]) -> None:
        for idx, node in enumerate(nodes):
            if not isinstance(node, dict):
                continue
            node_type = node.get("type")
            attrs = node.get("attrs") or {}
            ext_key = attrs.get("extensionKey", "")

            if node_type == "bodiedExtension" and ext_key == "mermaid":
                source = ""
                for block in node.get("content", []):
                    for inline in block.get("content", []):
                        if inline.get("type") == "text":
                            source += inline.get("text", "")
                nodes[idx] = {
                    "type": "codeBlock",
                    "attrs": {"language": "mermaid"},
                    "content": [{"type": "text", "text": source}],
                }
                continue

            if node_type == "extension" and ext_key in ("mermaid-cloud", "mermaid"):
                # Cannot recover source from macro-only nodes during republish.
                nodes[idx] = {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": ""}],
                }
                continue

            if isinstance(node.get("content"), list):
                walk(node["content"])

    walk(adf.get("content", []))
    return adf


def mermaid_attachment_base(source: str) -> str:
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"mermaid-{digest}"


def mermaid_cloud_ids(page_id: str, filename: str) -> tuple[str, str]:
    """Stable macro/local ids for idempotent cloud macro nodes."""
    macro_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"mermaid-cloud/{page_id}/{filename}"))
    local_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"mermaid-cloud-local/{page_id}/{filename}")
    )
    return macro_id, local_id


def build_mermaid_cloud_extension(
    filename: str,
    page_id: str,
    *,
    macro_key: str = "mermaid-cloud",
    revision: str = "1",
) -> dict[str, Any]:
    """ADF extension node for Mermaid Diagrams for Confluence (mermaid-cloud macro)."""
    macro_id, local_id = mermaid_cloud_ids(page_id, filename)
    return {
        "type": "extension",
        "attrs": {
            "layout": "default",
            "extensionType": "com.atlassian.confluence.macro.core",
            "extensionKey": macro_key,
            "parameters": {
                "macroParams": {
                    "filename": {"value": filename},
                    "revision": {"value": revision},
                },
                "macroMetadata": {
                    "macroId": {"value": macro_id},
                    "schemaVersion": {"value": "1"},
                    "placeholder": [
                        {
                            "type": "icon",
                            "data": {"url": MERMAID_CLOUD_PLACEHOLDER_ICON},
                        }
                    ],
                    "title": MERMAID_CLOUD_TITLE,
                },
            },
            "localId": local_id,
        },
    }


def attach_text_file(
    client: ConfluenceClient, page_id: str, content: str, filename: str
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        return client.attach_file(page_id, tmp_path, filename, content_type="text/plain")
    finally:
        os.unlink(tmp_path)


def ensure_mermaid_cloud_attachments(
    client: ConfluenceClient,
    page_id: str,
    source: str,
    *,
    allow_remote: bool = True,
) -> str | None:
    """Upload mermaid source + PNG attachments; return base filename or None."""
    base = mermaid_attachment_base(source)
    png_name = f"{base}.png"
    existing = {a.get("title"): a for a in list_page_attachments(client, page_id)}

    if base not in existing:
        attach_text_file(client, page_id, source, base)

    png_path = render_mermaid_to_png(source, allow_remote=allow_remote)
    if not png_path:
        return base if png_name in existing else None
    try:
        publish_mermaid_png_attachment(client, page_id, png_path, png_name, existing)
    finally:
        try:
            png_path.unlink(missing_ok=True)
        except OSError:
            pass

    return base


def embed_mermaid_cloud_macros(
    adf: dict[str, Any],
    page_id: str,
    client: ConfluenceClient,
    *,
    macro_key: str = "mermaid-cloud",
    allow_remote: bool = True,
) -> dict[str, Any]:
    """Publish mermaid blocks via the mermaid-cloud Confluence app macro."""
    adf = strip_mermaid_macro_nodes(adf)
    blocks = find_mermaid_blocks(adf)
    if not blocks:
        return adf

    embedded = 0
    for block in reversed(blocks):
        source = block["source"]
        filename = ensure_mermaid_cloud_attachments(
            client, page_id, source, allow_remote=allow_remote
        )
        if not filename:
            continue
        block["parent"][block["index"]] = build_mermaid_cloud_extension(
            filename, page_id, macro_key=macro_key
        )
        embedded += 1

    if embedded:
        print(f"    embedded {embedded} mermaid diagram(s) via {macro_key} macro")
    return adf


def list_page_attachments(client: ConfluenceClient, page_id: str) -> list[dict[str, Any]]:
    """Return attachment metadata for a page (v1 REST API)."""
    http = getattr(client, "http", None) or HttpRetryConfig()
    url = f"https://{client.domain}/wiki/rest/api/content/{page_id}/child/attachment?limit=100"
    req = urllib.request.Request(
        url,
        headers={"Authorization": client.auth_header, "Accept": "application/json"},
    )
    with urlopen_with_retry(
        req,
        timeout=http.api_timeout,
        max_retries=http.max_retries,
        backoff_base=http.backoff_base,
        label=f"list attachments {page_id}",
    ) as resp:
        data = json.loads(resp.read().decode())
    return list(data.get("results") or [])


def attachment_record_to_media_single(att: dict[str, Any], page_id: str) -> dict[str, Any]:
    """Build a mediaSingle node from a Confluence attachment record."""
    extensions = att.get("extensions") or {}
    file_id = extensions.get("fileId") or att.get("id")
    if not file_id:
        raise ValueError(f"attachment missing fileId: {att}")
    collection = extensions.get("collectionName") or f"contentId-{page_id}"
    return {
        "type": "mediaSingle",
        "attrs": {"layout": "center", "width": 760, "widthType": "pixel"},
        "content": [
            {
                "type": "media",
                "attrs": {
                    "width": 760,
                    "id": str(file_id),
                    "collection": collection,
                    "type": "file",
                    "height": 400,
                },
            }
        ],
    }


def attachment_to_media_single(upload_result: dict[str, Any], page_id: str) -> dict[str, Any]:
    results = upload_result.get("results") or []
    if not results:
        raise ValueError("attachment upload returned no results")
    return attachment_record_to_media_single(results[0], page_id)


def update_page_attachment_data(
    client: ConfluenceClient,
    page_id: str,
    attachment_id: str,
    file_path: str,
    *,
    filename: str,
    content_type: str = "image/png",
) -> None:
    """Replace attachment bytes (same filename) via Confluence v1 REST API."""
    boundary = "----md-to-adf-boundary"
    with open(file_path, "rb") as fh:
        file_data = fh.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    headers = {
        "Authorization": client.auth_header,
        "X-Atlassian-Token": "nocheck",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    url = (
        f"https://{client.domain}/wiki/rest/api/content/{page_id}"
        f"/child/attachment/{attachment_id}/data"
    )
    http = getattr(client, "http", None) or HttpRetryConfig()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urlopen_with_retry(
        req,
        timeout=http.upload_timeout,
        max_retries=http.max_retries,
        backoff_base=http.backoff_base,
        label=f"update attachment {filename}",
    ):
        return


def publish_mermaid_png_attachment(
    client: ConfluenceClient,
    page_id: str,
    png_path: Path,
    filename: str,
    existing: dict[str, dict[str, Any]],
    *,
    content_type: str = "image/png",
) -> dict[str, Any]:
    """Upload a new PNG attachment or replace an existing one with the same title."""
    att = existing.get(filename)
    if att and att.get("id"):
        update_page_attachment_data(
            client,
            page_id,
            str(att["id"]),
            str(png_path),
            filename=filename,
            content_type=content_type,
        )
        refreshed = {a.get("title"): a for a in list_page_attachments(client, page_id)}
        att = refreshed.get(filename, att)
        return attachment_record_to_media_single(att, page_id)

    try:
        upload = client.attach_file(page_id, str(png_path), filename, content_type=content_type)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise
        refreshed = {a.get("title"): a for a in list_page_attachments(client, page_id)}
        att = refreshed.get(filename)
        if not att or not att.get("id"):
            raise
        update_page_attachment_data(
            client,
            page_id,
            str(att["id"]),
            str(png_path),
            filename=filename,
            content_type=content_type,
        )
        return attachment_record_to_media_single(att, page_id)

    return attachment_to_media_single(upload, page_id)


def embed_mermaid_images(
    adf: dict[str, Any],
    page_id: str,
    client: ConfluenceClient,
    *,
    allow_remote: bool = True,
) -> dict[str, Any]:
    """Render mermaid code blocks to PNG attachments and swap in mediaSingle nodes."""
    adf = strip_mermaid_macro_nodes(adf)
    blocks = find_mermaid_blocks(adf)
    if not blocks:
        return adf

    temp_files: list[Path] = []
    embedded = 0
    existing = {a.get("title"): a for a in list_page_attachments(client, page_id)}
    try:
        for block in reversed(blocks):
            source = block["source"]
            digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
            filename = f"mermaid-{digest}.png"

            png_path = render_mermaid_to_png(source, allow_remote=allow_remote)
            if not png_path:
                if filename in existing:
                    media = attachment_record_to_media_single(existing[filename], page_id)
                    block["parent"][block["index"]] = media
                    embedded += 1
                continue
            temp_files.append(png_path)
            media = publish_mermaid_png_attachment(
                client, page_id, png_path, filename, existing
            )
            existing = {a.get("title"): a for a in list_page_attachments(client, page_id)}
            block["parent"][block["index"]] = media
            embedded += 1
    finally:
        for path in temp_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    if embedded:
        print(f"    embedded {embedded} mermaid diagram(s) as PNG attachments")
    return adf


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
IMAGE_LINK_TEXT_RE = re.compile(r"^\[[^\]]+\]$")


def resolve_local_image_path(href: str, md_abs_path: Path, source_dir: Path) -> Path | None:
    """Resolve a markdown image href to a file under publish.source."""
    href = (href or "").strip()
    if not href or href.startswith(("http://", "https://", "gcp://", "mailto:")):
        return None
    clean = href.split("#")[0].split("?")[0]
    candidate = (md_abs_path.parent / clean).resolve()
    if candidate.suffix.lower() not in IMAGE_EXTENSIONS:
        return None
    if not candidate.is_file():
        return None
    try:
        candidate.relative_to(source_dir.resolve())
    except ValueError:
        return None
    return candidate


def paragraph_image_href(paragraph: dict[str, Any]) -> str | None:
    """md-to-adf renders ![alt](path) as a linked [alt] text node."""
    if paragraph.get("type") != "paragraph":
        return None
    content = paragraph.get("content") or []
    if len(content) != 1 or content[0].get("type") != "text":
        return None
    text = content[0].get("text") or ""
    if not IMAGE_LINK_TEXT_RE.match(text):
        return None
    marks = content[0].get("marks") or []
    link = next((m for m in marks if m.get("type") == "link"), None)
    if not link:
        return None
    return link.get("attrs", {}).get("href") or None


def guess_image_content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def embed_local_images(
    adf: dict[str, Any],
    page_id: str,
    client: ConfluenceClient,
    spec: PageSpec,
    source_dir: Path,
) -> dict[str, Any]:
    """Upload local markdown images as attachments and embed mediaSingle nodes."""
    content = adf.get("content")
    if not isinstance(content, list):
        return adf

    existing = {a.get("title"): a for a in list_page_attachments(client, page_id)}
    embedded = 0

    for idx in range(len(content) - 1, -1, -1):
        node = content[idx]
        href = paragraph_image_href(node)
        if not href:
            continue
        image_path = resolve_local_image_path(href, spec.abs_path, source_dir)
        if not image_path:
            continue
        filename = image_path.name
        media = publish_mermaid_png_attachment(
            client,
            page_id,
            image_path,
            filename,
            existing,
            content_type=guess_image_content_type(image_path),
        )
        existing = {a.get("title"): a for a in list_page_attachments(client, page_id)}
        content[idx] = media
        embedded += 1

    if embedded:
        print(f"    embedded {embedded} screenshot(s) as PNG attachments")
    return adf


def polish_github_links_in_adf(node: Any) -> Any:
    """Add code marks to GitHub links and strip stray backticks from link text."""
    if isinstance(node, dict):
        if node.get("type") == "text":
            marks = list(node.get("marks") or [])
            text = node.get("text", "")
            link_mark = next((m for m in marks if m.get("type") == "link"), None)
            if link_mark:
                href = link_mark.get("attrs", {}).get("href", "")
                if text.startswith("`") and text.endswith("`") and len(text) >= 2:
                    text = text[1:-1]
                    node = {**node, "text": text}
                if GITHUB_LINK_HREF_RE.search(href) and not any(
                    m.get("type") == "code" for m in marks
                ):
                    marks = marks + [{"type": "code"}]
                    node = {**node, "marks": marks}
        return {k: polish_github_links_in_adf(v) for k, v in node.items()}
    if isinstance(node, list):
        return [polish_github_links_in_adf(item) for item in node]
    return node


class SuitePublisher:
    def __init__(
        self,
        client: ConfluenceClient,
        domain: str,
        space_key: str,
        parent_id: str,
        source_dir: Path,
        mermaid_strategy: str = "png",
        mermaid_macro_key: str = "mermaid-cloud",
        dry_run: bool = False,
        force: bool = False,
        root_page_id: str | None = None,
        root_page_rel: str = DEFAULT_ROOT_PAGE_REL,
        layout: PublishLayoutConfig | None = None,
    ):
        self.client = client
        self.domain = domain
        self.space_key = space_key
        self.parent_id = parent_id
        self.root_page_id = root_page_id
        self.root_page_rel = root_page_rel
        self.source_dir = source_dir
        self.layout = layout or PublishLayoutConfig()
        self.mermaid_strategy = normalize_mermaid_strategy(mermaid_strategy)
        self.mermaid_macro_key = mermaid_macro_key or "mermaid-cloud"
        self.dry_run = dry_run
        self.force = force
        self.page_ids: dict[str, str] = {}
        self.page_titles: dict[str, str] = {}
        self.page_urls: dict[str, str] = {}
        self._state_page_ids: dict[str, str] = {}
        self.remote_pages: dict[str, RemotePage] = {}
        self.children_by_parent: dict[str, list[RemotePage]] = {}
        self.link_catalog: LinkCatalog | None = None
        self.github_verifier: GitHubPathVerifier | None = None
        self.stats = PublishStats()
        self.http: HttpRetryConfig = getattr(client, "http", None) or HttpRetryConfig()
        self._checkpoint_state_path: Path | None = None
        self._checkpoint_all_specs: list[PageSpec] | None = None

    def publish_title(self, spec: PageSpec) -> str:
        """Confluence page title: state/config pin wins over markdown H1."""
        return self.page_titles.get(spec.rel_path) or spec.title

    def _maybe_checkpoint(self) -> None:
        if (
            self.dry_run
            or not self.http.checkpoint_after_each_page
            or not self._checkpoint_state_path
        ):
            return
        self.save_state(self._checkpoint_state_path, self._checkpoint_all_specs)
        if self.http.request_delay_sec > 0:
            time.sleep(self.http.request_delay_sec)

    def _after_write(self, spec: PageSpec) -> None:
        self._maybe_checkpoint()

    def apply_config_overrides(self, pub_cfg: dict[str, Any]) -> None:
        """Seed root page id and optional title pins from publish config."""
        if self.root_page_id:
            self.page_ids.setdefault(self.root_page_rel, self.root_page_id)
            self._state_page_ids.setdefault(self.root_page_rel, self.root_page_id)
        pinned = pub_cfg.get("page_titles")
        if isinstance(pinned, dict):
            for rel, title in pinned.items():
                if title:
                    # Config pins always win over cached state titles.
                    self.page_titles[str(rel).replace("\\", "/")] = str(title).strip()

    def load_state(self, state_path: Path) -> None:
        if not state_path.is_file():
            return
        data = json.loads(state_path.read_text(encoding="utf-8"))
        pages = data.get("pages", {})
        for old_rel, new_rel in self.layout.path_migrations.items():
            if old_rel in pages and new_rel not in pages:
                pages[new_rel] = pages.pop(old_rel)
        for rel, info in pages.items():
            pid = str(info["id"])
            self.page_ids[rel] = pid
            self._state_page_ids[rel] = pid
            self.page_titles[rel] = info.get("title", "")
            if info.get("url"):
                self.page_urls[rel] = info["url"]

    def save_state(self, state_path: Path, all_specs: list[PageSpec] | None = None) -> None:
        # Merge with existing state so --only runs do not drop other page ids
        existing: dict[str, Any] = {}
        if state_path.is_file():
            try:
                existing = json.loads(state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        pages = dict(existing.get("pages", {}))
        for old_rel in self.layout.path_migrations:
            pages.pop(old_rel, None)
        for rel, pid in self.page_ids.items():
            pages[rel] = {
                "id": pid,
                "title": self.page_titles.get(rel, ""),
                "url": self.page_urls.get(rel, ""),
            }
        payload = {
            "domain": self.domain,
            "space_key": self.space_key,
            "parent_id": self.parent_id,
            "root_page_id": self.root_page_id,
            "root_page_rel": self.root_page_rel,
            "pages": pages,
        }
        state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def confluence_parent_id(self, spec: PageSpec) -> str:
        if spec.parent_rel is None:
            return self.parent_id
        parent_id = self.page_ids.get(spec.parent_rel)
        if not parent_id:
            raise RuntimeError(
                f"Parent page not mapped for {spec.rel_path} (needs {spec.parent_rel})"
            )
        return parent_id

    def list_children(self, parent_id: str) -> list[RemotePage]:
        results: list[RemotePage] = []
        cursor: str | None = None
        while True:
            path = f"/wiki/api/v2/pages/{parent_id}/children?limit=250"
            if cursor:
                path += f"&cursor={urllib.parse.quote(cursor)}"
            try:
                data = self.client._get(path)
            except urllib.error.HTTPError:
                break
            for item in data.get("results", []):
                page_id = str(item["id"])
                parent = str(item.get("parentId") or parent_id)
                results.append(RemotePage(page_id=page_id, title=item["title"], parent_id=parent))
            next_link = data.get("_links", {}).get("next")
            if not next_link:
                break
            parsed = urllib.parse.urlparse(next_link)
            qs = urllib.parse.parse_qs(parsed.query)
            cursor = qs.get("cursor", [None])[0]
            if not cursor:
                break
        return results

    def fetch_page_adf(self, page_id: str) -> dict[str, Any] | None:
        try:
            data = self.client._get(
                f"/wiki/api/v2/pages/{page_id}?body-format=atlas_doc_format"
            )
        except urllib.error.HTTPError:
            return None
        body = data.get("body", {}).get("atlas_doc_format", {})
        raw = body.get("value")
        if not raw:
            return None
        if isinstance(raw, str):
            return json.loads(raw)
        return raw

    def fetch_remote_tree(self) -> None:
        """BFS all pages under root_page_id (or parent_id), including the root page."""
        print("\nFetching existing Confluence pages…")
        tree_root = self.root_page_id or self.parent_id
        if self.root_page_id:
            try:
                root_data = self.client._get(f"/wiki/api/v2/pages/{self.root_page_id}")
                root_parent = str(root_data.get("parentId") or self.parent_id)
                self.remote_pages[self.root_page_id] = RemotePage(
                    page_id=self.root_page_id,
                    title=str(root_data.get("title") or ""),
                    parent_id=root_parent,
                )
            except urllib.error.HTTPError:
                pass

        queue = [tree_root]
        seen: set[str] = set()

        while queue:
            current_parent = queue.pop(0)
            children = self.list_children(current_parent)
            self.children_by_parent[current_parent] = children
            for child in children:
                if child.page_id in seen:
                    continue
                seen.add(child.page_id)
                self.remote_pages[child.page_id] = child
                queue.append(child.page_id)

        print(f"  Found {len(self.remote_pages)} page(s) under tree root {tree_root}")

    def _find_child_by_title(self, parent_id: str, title: str) -> RemotePage | None:
        for child in self.children_by_parent.get(parent_id, []):
            if child.title == title:
                return child
        return None

    def reconcile_with_remote(self, specs: list[PageSpec]) -> None:
        """Map local rel_path -> Confluence page ID by walking expected hierarchy."""
        print("\nReconciling local docs with Confluence tree…")
        mapped = 0
        pending = list(specs)
        for _ in range(len(specs) + 1):
            progress = False
            still_pending: list[PageSpec] = []
            for spec in pending:
                if spec.parent_rel and spec.parent_rel not in self.page_ids:
                    still_pending.append(spec)
                    continue

                try:
                    parent_id = self.confluence_parent_id(spec)
                except RuntimeError:
                    still_pending.append(spec)
                    continue

                if spec.rel_path in self.page_ids:
                    continue

                remote = self._find_child_by_title(parent_id, self.publish_title(spec))
                if remote:
                    self.page_ids[spec.rel_path] = remote.page_id
                    self.page_titles[spec.rel_path] = self.publish_title(spec)
                    self.page_urls[spec.rel_path] = page_wiki_url(
                        self.domain, self.space_key, remote.page_id, self.publish_title(spec)
                    )
                    mapped += 1
                    progress = True
                    continue

                state_id = self._state_page_ids.get(spec.rel_path)
                if state_id and state_id in self.remote_pages:
                    remote = self.remote_pages[state_id]
                    if remote.parent_id == parent_id:
                        self.page_ids[spec.rel_path] = state_id
                        pinned = self.publish_title(spec)
                        self.page_titles[spec.rel_path] = pinned
                        self.page_urls[spec.rel_path] = page_wiki_url(
                            self.domain, self.space_key, state_id, pinned
                        )
                        mapped += 1
                        progress = True

            pending = still_pending
            if not progress:
                break

        print(f"  Mapped {len(self.page_ids)}/{len(specs)} page(s) to existing Confluence pages")

    def refresh_page_urls(self) -> None:
        for rel, page_id in self.page_ids.items():
            title = self.page_titles.get(rel, "")
            if title:
                self.page_urls[rel] = page_wiki_url(
                    self.domain, self.space_key, page_id, title
                )

    def build_adf(
        self,
        spec: PageSpec,
        github: GitHubLinkConfig | None,
        catalog: LinkCatalog | None = None,
        gcp: GcpDeploymentConfig | None = None,
    ) -> dict[str, Any]:
        raw = spec.abs_path.read_text(encoding="utf-8")
        body = strip_leading_h1(raw)
        cat = catalog or self.link_catalog
        body, _ = rewrite_markdown_links(
            body,
            spec.rel_path,
            cat,
            self.page_urls or None,
            github,
            self.github_verifier,
            gcp,
        )
        body, _ = rewrite_inline_repo_paths(
            body,
            github,
            spec.rel_path,
            self.github_verifier,
            cat,
            self.page_urls or None,
            gcp,
        )
        adf = convert(body)
        adf = polish_github_links_in_adf(adf)
        errors = validate(adf)
        if errors:
            print(f"  warning: ADF validation issues in {spec.rel_path}:", file=sys.stderr)
            for err in errors[:5]:
                print(f"    - {err}", file=sys.stderr)
        return adf

    def finalize_mermaid(self, adf: dict[str, Any], page_id: str | None) -> dict[str, Any]:
        """Apply mermaid strategy after the page exists (for image uploads)."""
        strategy = self.mermaid_strategy
        adf = strip_mermaid_macro_nodes(adf)

        if strategy == "code":
            return adf

        if strategy == "cloud":
            if page_id and not self.dry_run:
                return embed_mermaid_cloud_macros(
                    adf,
                    page_id,
                    self.client,
                    macro_key=self.mermaid_macro_key,
                    allow_remote=True,
                )
            return adf

        # png / png-local: attach rendered PNGs (local mmdc, optional Kroki fallback)
        allow_remote = strategy == "png"
        if page_id and not self.dry_run and mermaid_renderer_available(
            allow_remote=allow_remote
        ):
            return embed_mermaid_images(
                adf, page_id, self.client, allow_remote=allow_remote
            )

        if strategy == "png" and not mermaid_renderer_available(allow_remote=False):
            print(
                "  note: no local mermaid-cli; png strategy will use Kroki.io "
                "(set png-local to forbid remote rendering, or code to skip diagrams)",
                file=sys.stderr,
            )
        elif strategy == "png-local" and not mermaid_renderer_available(
            allow_remote=False
        ):
            print(
                "  note: mermaid-cli not found; publishing diagrams as code blocks "
                "(install @mermaid-js/mermaid-cli or use mermaid_strategy = \"png\")",
                file=sys.stderr,
            )
        return adf

    def finalize_page_adf(
        self, adf: dict[str, Any], page_id: str | None, spec: PageSpec | None = None
    ) -> dict[str, Any]:
        """Mermaid rendering + local screenshot uploads."""
        adf = self.finalize_mermaid(adf, page_id)
        if page_id and not self.dry_run and spec is not None:
            adf = embed_local_images(adf, page_id, self.client, spec, self.source_dir)
        return adf

    def get_remote_fingerprint(self, page_id: str) -> str | None:
        remote = self.remote_pages.get(page_id)
        if remote and remote.adf_fingerprint:
            return remote.adf_fingerprint
        adf = self.fetch_page_adf(page_id)
        if not adf:
            return None
        fp = adf_fingerprint(adf)
        if remote:
            remote.adf = adf
            remote.adf_fingerprint = fp
        else:
            self.remote_pages[page_id] = RemotePage(
                page_id=page_id, title="", parent_id="", adf=adf, adf_fingerprint=fp
            )
        return fp

    def remote_title(self, page_id: str) -> str | None:
        remote = self.remote_pages.get(page_id)
        return remote.title if remote else None

    def create_page(self, spec: PageSpec, adf: dict[str, Any]) -> str:
        parent_id = self.confluence_parent_id(spec)
        title = self.publish_title(spec)
        if self.dry_run:
            fake = f"dry-{spec.rel_path}"
            self.page_ids[spec.rel_path] = fake
            self.page_titles[spec.rel_path] = title
            self.page_urls[spec.rel_path] = page_wiki_url(
                self.domain, self.space_key, fake, title
            )
            self.stats.skipped_dry_run += 1
            print(f"  [dry-run] CREATE {spec.rel_path} -> '{title}'")
            return fake

        result = self.client.create_page(
            adf, self.space_key, title, parent_id=parent_id
        )
        page_id = str(result["id"])
        final_adf = self.finalize_page_adf(adf, page_id, spec)
        if adf_fingerprint(final_adf) != adf_fingerprint(adf):
            self.client.update_page(final_adf, page_id, title)
            adf = final_adf
        else:
            adf = final_adf
        self.page_ids[spec.rel_path] = page_id
        self.page_titles[spec.rel_path] = title
        self.page_urls[spec.rel_path] = page_wiki_url(
            self.domain, self.space_key, page_id, title
        )
        remote = RemotePage(page_id=page_id, title=title, parent_id=parent_id, adf=adf)
        remote.adf_fingerprint = adf_fingerprint(adf)
        self.remote_pages[page_id] = remote
        self.children_by_parent.setdefault(parent_id, []).append(remote)
        self.stats.created += 1
        parent_label = spec.parent_rel or "parent_page_id"
        print(
            f"  CREATE {spec.rel_path} -> '{title}' "
            f"(id {page_id}, under {parent_label})"
        )
        self._after_write(spec)
        return page_id

    def update_page(self, spec: PageSpec, adf: dict[str, Any], reason: str) -> None:
        page_id = self.page_ids[spec.rel_path]
        title = self.publish_title(spec)
        if self.dry_run:
            self.stats.skipped_dry_run += 1
            print(f"  [dry-run] UPDATE {spec.rel_path} ({reason})")
            return

        self.client.update_page(adf, page_id, title)
        self.page_titles[spec.rel_path] = title
        self.page_urls[spec.rel_path] = page_wiki_url(
            self.domain, self.space_key, page_id, title
        )
        remote = self.remote_pages.get(page_id)
        if remote:
            remote.title = title
            remote.adf = adf
            remote.adf_fingerprint = adf_fingerprint(adf)
        self.stats.updated += 1
        print(f"  UPDATE {spec.rel_path} ({reason})")
        self._after_write(spec)

    def move_page_v1(self, page_id: str, position: str, target_id: str) -> None:
        """Move a page using the v1 relative move API (before/after/append)."""
        path = f"/wiki/rest/api/content/{page_id}/move/{position}/{target_id}"
        self.client._put(path, {})

    def ensure_page_parents(self, specs: list[PageSpec]) -> None:
        """Re-parent Confluence pages when local hierarchy changed."""
        print("\nEnsuring Confluence page hierarchy…")
        moves = 0
        for spec in specs:
            page_id = self.page_ids.get(spec.rel_path)
            if not page_id or page_id.startswith("dry-"):
                continue
            try:
                expected_parent = self.confluence_parent_id(spec)
            except RuntimeError:
                continue
            remote = self.remote_pages.get(page_id)
            if not remote:
                continue
            if remote.parent_id == expected_parent:
                continue
            if self.dry_run:
                print(
                    f"  [dry-run] MOVE {spec.rel_path} under "
                    f"{spec.parent_rel or 'parent_page_id'}"
                )
                continue
            self.move_page_v1(page_id, "append", expected_parent)
            if remote:
                remote.parent_id = expected_parent
            moves += 1
            print(
                f"  MOVE {spec.rel_path} -> under "
                f"{spec.parent_rel or 'parent_page_id'}"
            )
        if moves:
            self.fetch_remote_tree()

    def ensure_sibling_order(self, specs: list[PageSpec]) -> None:
        """Order direct children under each parent to match local sort_key."""
        print("\nEnsuring Confluence sibling order…")
        by_parent: dict[str | None, list[PageSpec]] = {}
        for spec in specs:
            by_parent.setdefault(spec.parent_rel, []).append(spec)
        moves = 0
        for children in by_parent.values():
            if len(children) < 2:
                continue
            ordered = sorted(children, key=lambda p: p.sort_key)
            prev_id: str | None = None
            for spec in ordered:
                page_id = self.page_ids.get(spec.rel_path)
                if not page_id or page_id.startswith("dry-"):
                    continue
                if prev_id is None:
                    prev_id = page_id
                    continue
                if self.dry_run:
                    print(f"  [dry-run] REORDER {spec.rel_path} after previous sibling")
                    prev_id = page_id
                    continue
                try:
                    self.move_page_v1(page_id, "after", prev_id)
                    moves += 1
                except urllib.error.HTTPError as e:
                    if e.code not in (400, 404):
                        raise
                prev_id = page_id
        if moves:
            print(f"  Reordered {moves} page(s)")

    def publish(
        self,
        github: GitHubLinkConfig | None,
        state_path: Path,
        only: str | None = None,
        gcp: GcpDeploymentConfig | None = None,
    ) -> None:
        all_specs = discover_pages(self.source_dir, self.layout)
        if not all_specs:
            raise SystemExit(f"No markdown files under {self.source_dir}")

        publish_specs = all_specs
        if only:
            only_set = {p.strip().replace("\\", "/") for p in only.split(",") if p.strip()}
            selected = [s for s in all_specs if s.rel_path in only_set]
            if len(selected) != len(only_set):
                missing = only_set - {s.rel_path for s in selected}
                raise SystemExit(f"No file matching --only {missing!r} under {self.source_dir}")
            publish_specs = expand_publish_specs(selected, all_specs)
            print(f"Publishing {len(selected)} page(s) (+ {len(publish_specs) - len(selected)} ancestor(s) for hierarchy)")

        specs = publish_specs

        self._checkpoint_state_path = state_path
        self._checkpoint_all_specs = all_specs

        print(f"Syncing {len(specs)} page(s) from {self.source_dir}")
        print(f"  Space: {self.space_key}  Parent: {self.parent_id}  Domain: {self.domain}")
        if self.root_page_id:
            print(f"  Root page: {self.root_page_rel} -> id {self.root_page_id}")
        if self.force:
            print("  Mode: force (push all pages regardless of diff)")

        if github:
            print(f"  GitHub: {github.repo_url} @ {github.ref}")
        if gcp:
            print(f"  GCP Console links: {gcp.project_id} ({gcp.region})")
        print(
            f"  HTTP: api_timeout={self.http.api_timeout}s, "
            f"upload_timeout={self.http.upload_timeout}s, "
            f"max_retries={self.http.max_retries}, "
            f"checkpoint={'on' if self.http.checkpoint_after_each_page else 'off'}"
        )
        if self.github_verifier and self.github_verifier.enabled:
            print("  GitHub path verify: on (404 paths stay as code, not links)")
        if self.mermaid_strategy in ("png", "png-local"):
            local = mermaid_renderer_available(allow_remote=False)
            remote = " + Kroki fallback" if self.mermaid_strategy == "png" else ""
            renderer = f"local {('available' if local else 'unavailable')}{remote}"
            print(f"  Mermaid: {self.mermaid_strategy} ({renderer})")
        elif self.mermaid_strategy == "cloud":
            print(
                f"  Mermaid: cloud ({self.mermaid_macro_key} macro + attachments)"
            )
        elif self.mermaid_strategy == "code":
            print("  Mermaid: code (fenced blocks, no rendering)")

        self.fetch_remote_tree()
        self.reconcile_with_remote(specs)

        for spec in all_specs:
            self.page_titles.setdefault(spec.rel_path, spec.title)

        # Full-suite catalog so links resolve to any page already on Confluence
        self.link_catalog = build_link_catalog(
            all_specs,
            self.page_ids,
            self.page_titles,
            self.domain,
            self.space_key,
            dry_run=self.dry_run,
        )
        self.refresh_page_urls()
        self.link_catalog.refresh_from_publisher(self)

        print("\nPass 1: link catalog + hierarchy")
        print_page_hierarchy(specs, self.page_ids)
        audit_links(specs, self.link_catalog, github, self.github_verifier, gcp)

        # Pass 2: create missing pages (parents first via sort_key)
        while True:
            missing = [s for s in specs if s.rel_path not in self.page_ids]
            if not missing:
                break
            print(f"\nPass 2: creating {len(missing)} missing page(s)...")
            self.link_catalog.refresh_from_publisher(self)
            for spec in missing:
                adf = self.build_adf(spec, github, self.link_catalog, gcp)
                self.create_page(spec, adf)
                self.link_catalog.update_page_id(spec.rel_path, self.page_ids[spec.rel_path])
            self.refresh_page_urls()
            self.link_catalog.refresh_from_publisher(self)

        self.ensure_page_parents(specs)
        self.ensure_sibling_order(specs)

        # Pass 3: post-process — rewrite all .md links now that every page id exists
        print("\nPass 3: link wiring + content diff (all pages have Confluence ids)")
        self.link_catalog.refresh_from_publisher(self)
        self.refresh_page_urls()
        audit_links(specs, self.link_catalog, github, self.github_verifier, gcp)

        for spec in specs:
            page_id = self.page_ids.get(spec.rel_path)
            if not page_id:
                continue

            try:
                desired = self.build_adf(spec, github, self.link_catalog, gcp)
                desired = self.finalize_page_adf(desired, page_id, spec)
                desired_fp = adf_fingerprint(desired)

                if self.force:
                    self.update_page(spec, desired, "forced")
                    continue

                if self.dry_run:
                    print(f"  [dry-run] would compare {spec.rel_path} (id {page_id})")
                    continue

                remote_title = self.remote_title(page_id)
                title = self.publish_title(spec)
                if remote_title and remote_title != title:
                    self.update_page(spec, desired, "title changed")
                    continue

                remote_fp = self.get_remote_fingerprint(page_id)
                if remote_fp is None:
                    self.update_page(spec, desired, "no remote body")
                elif remote_fp != desired_fp:
                    self.update_page(spec, desired, "content or links changed")
                else:
                    self.stats.unchanged += 1
                    print(f"  SKIP  {spec.rel_path} (unchanged)")
            except (urllib.error.URLError, TimeoutError, OSError, NetworkError) as exc:
                print(
                    f"\nPublish stopped at {spec.rel_path}: {exc}",
                    file=sys.stderr,
                )
                if not self.dry_run and self._checkpoint_state_path:
                    self.save_state(self._checkpoint_state_path, all_specs)
                    print(
                        f"Checkpoint saved: {self._checkpoint_state_path}. "
                        f"Re-run the same command; completed pages are skipped via diff.",
                        file=sys.stderr,
                    )
                raise SystemExit(1) from exc

        if not self.dry_run:
            self.save_state(state_path, all_specs)
            print(f"\nSaved page map: {state_path}")

        print(
            f"\nDone. "
            f"{self.stats.unchanged} unchanged, "
            f"{self.stats.created} created, "
            f"{self.stats.updated} updated."
        )
        if self.dry_run:
            print(f"  ({self.stats.skipped_dry_run} dry-run action(s) logged)")


def parse_args(config_defaults: dict[str, Any]) -> argparse.Namespace:
    conf = config_defaults.get("confluence", {})
    pub = config_defaults.get("publish", {})

    p = argparse.ArgumentParser(description="Publish docs/suite to Confluence (ADF, idempotent)")
    p.add_argument("--source", default=None, help=f"Markdown root (default: from config or {DEFAULT_SOURCE})")
    p.add_argument(
        "--config",
        default=None,
        help=f"Config TOML path (default: <source>/{CONFIG_FILENAME})",
    )
    p.add_argument("--domain", default=None)
    p.add_argument("--email", default=None)
    p.add_argument("--token", default=None)
    p.add_argument("--space", default=None)
    p.add_argument("--parent-id", default=None)
    p.add_argument("--root-page-id", default=None)
    p.add_argument(
        "--repo-base-url",
        default=None,
        help="Legacy: GitHub blob base URL (prefer --github-repo)",
    )
    p.add_argument(
        "--github-repo",
        default=None,
        help="GitHub repo URL for code/file links, e.g. https://github.com/org/repo",
    )
    p.add_argument(
        "--github-ref",
        default=None,
        help="Git branch/tag/commit for GitHub links (default: main)",
    )
    p.add_argument(
        "--no-link-inline-paths",
        action="store_true",
        help="Do not auto-link inline `path/to/file` code spans to GitHub",
    )
    p.add_argument(
        "--no-github-verify",
        action="store_true",
        help="Skip GitHub Contents API 404 checks for inline/repo file links",
    )
    p.add_argument(
        "--github-token",
        default=None,
        help="GitHub token for path verification (or GITHUB_TOKEN / config github_token)",
    )
    p.add_argument(
        "--mermaid",
        choices=MERMAID_STRATEGIES + tuple(MERMAID_ALIASES),
        default=None,
        help="Mermaid rendering: png (default), png-local, cloud, code "
        "(aliases: auto=png, image=png-local, macro=cloud)",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan without API writes")
    p.add_argument("--force", action="store_true", help="Push all pages even if unchanged")
    p.add_argument(
        "--probe",
        action="store_true",
        help="Verify auth, parent page, and ADF conversion only (no writes)",
    )
    p.add_argument(
        "--audit-links",
        action="store_true",
        help="Print link catalog and wiring plan only (no writes)",
    )
    p.add_argument(
        "--only",
        default=None,
        help="Publish only these files (comma-separated), e.g. technical/dashboard-api/README.md,technical/dashboard-api/auth.md",
    )
    p.add_argument(
        "--state-file",
        default=None,
        help=f"Page ID map (default: <source>/{STATE_FILENAME})",
    )
    p.add_argument(
        "--api-timeout",
        type=float,
        default=None,
        help="Confluence JSON API timeout in seconds (default: 90)",
    )
    p.add_argument(
        "--upload-timeout",
        type=float,
        default=None,
        help="Attachment upload timeout in seconds (default: 300)",
    )
    p.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help="Max retries per API/upload call on timeout or 5xx/429 (default: 6)",
    )
    p.add_argument(
        "--no-checkpoint",
        action="store_true",
        help="Do not save .confluence-publish.json after each page write",
    )
    args = p.parse_args()

    args.source = resolve_setting(args.source, "", pub.get("source"), DEFAULT_SOURCE) or DEFAULT_SOURCE
    args.domain = resolve_setting(args.domain, "CONFLUENCE_DOMAIN", conf.get("domain"))
    args.email = resolve_setting(args.email, "CONFLUENCE_EMAIL", conf.get("email"))
    args.token = resolve_setting(
        args.token, "CONFLUENCE_API_TOKEN", conf.get("api_token")
    )
    args.space = resolve_setting(args.space, "CONFLUENCE_SPACE_KEY", conf.get("space_key"))
    args.parent_id = resolve_setting(
        args.parent_id, "CONFLUENCE_PARENT_PAGE_ID", conf.get("parent_page_id")
    )
    args.root_page_id = resolve_setting(
        args.root_page_id, "CONFLUENCE_ROOT_PAGE_ID", conf.get("root_page_id")
    )
    args.repo_base_url = resolve_setting(
        args.repo_base_url, "CONFLUENCE_REPO_BASE_URL", pub.get("repo_base_url")
    )
    args.github_repo = resolve_setting(
        args.github_repo, "CONFLUENCE_GITHUB_REPO", pub.get("github_repo")
    )
    args.github_ref = resolve_setting(
        args.github_ref, "CONFLUENCE_GITHUB_REF", pub.get("github_ref"), "main"
    )
    args.mermaid = normalize_mermaid_strategy(
        resolve_setting(
            args.mermaid,
            "CONFLUENCE_MERMAID_STRATEGY",
            pub.get("mermaid_strategy"),
            "png",
        )
    )
    args.mermaid_macro_key = resolve_setting(
        getattr(args, "mermaid_macro_key", None),
        "CONFLUENCE_MERMAID_MACRO_KEY",
        pub.get("mermaid_macro_key"),
        "mermaid-cloud",
    )
    return args


def build_gcp_config(pub: dict[str, Any]) -> GcpDeploymentConfig | None:
    return GcpDeploymentConfig.from_settings(pub)


def build_github_config(
    args: argparse.Namespace,
    suite_prefix: str,
    pub: dict[str, Any],
    layout: PublishLayoutConfig | None = None,
) -> GitHubLinkConfig | None:
    link_inline = pub.get("link_inline_paths", True)
    if getattr(args, "no_link_inline_paths", False):
        link_inline = False
    link_paths = layout.link_paths if layout else None
    return GitHubLinkConfig.from_settings(
        github_repo=getattr(args, "github_repo", None),
        github_ref=getattr(args, "github_ref", None),
        repo_base_url=getattr(args, "repo_base_url", None),
        suite_prefix=suite_prefix,
        link_inline_paths=bool(link_inline),
        link_paths=link_paths,
    )


def build_github_verifier(
    github: GitHubLinkConfig | None,
    pub: dict[str, Any],
    args: argparse.Namespace,
    workspace_root: Path | None = None,
) -> GitHubPathVerifier | None:
    if not github:
        return None
    enabled = not getattr(args, "no_github_verify", False)
    if "github_verify_paths" in pub:
        enabled = enabled and bool(pub.get("github_verify_paths"))
    token = resolve_setting(
        getattr(args, "github_token", None),
        "CONFLUENCE_GITHUB_TOKEN",
        pub.get("github_token"),
    )
    if not token:
        token = os.environ.get("GITHUB_TOKEN")
    return GitHubPathVerifier(
        config=github,
        token=token,
        enabled=enabled,
        workspace_root=workspace_root,
    )


def run_probe(
    client: ConfluenceClient,
    domain: str,
    space_key: str,
    parent_id: str,
    source_dir: Path,
    layout: PublishLayoutConfig | None = None,
) -> None:
    """Read-only connectivity check before a full publish."""
    page_layout = layout or PublishLayoutConfig()
    print("=== Confluence probe (read-only) ===\n")

    print(f"Domain:     {domain}")
    print(f"Space:      {space_key}")
    print(f"Parent ID:  {parent_id}")
    print(f"Source:     {source_dir}\n")

    space = client._get(f"/wiki/api/v2/spaces?keys={space_key}")
    results = space.get("results", [])
    if not results:
        raise SystemExit(f"Space '{space_key}' not found or not accessible")
    print(f"OK Space resolved: {results[0].get('name')} (id {results[0].get('id')})")

    parent = client._get(f"/wiki/api/v2/pages/{parent_id}")
    print(f"OK Parent page: \"{parent.get('title')}\" (id {parent.get('id')})")

    children = client._get(f"/wiki/api/v2/pages/{parent_id}/children?limit=250")
    child_list = children.get("results", [])
    print(f"OK Existing children under parent: {len(child_list)}")
    for child in child_list[:10]:
        print(f"    - {child.get('title')} (id {child.get('id')})")
    if len(child_list) > 10:
        print(f"    … and {len(child_list) - 10} more")

    md_files = sorted(source_dir.rglob("*.md"))
    print(f"\nOK Local markdown files under source: {len(md_files)}")

    sample = source_dir / "README.md"
    if sample.is_file():
        specs = discover_pages(source_dir, page_layout)
        spec = specs[0]
        pub = SuitePublisher(client, domain, space_key, parent_id, source_dir, layout=page_layout)
        adf = pub.build_adf(spec, github=None, catalog=None)
        fp = adf_fingerprint(adf)
        errors = validate(adf)
        print(
            f"OK ADF conversion sample: {spec.rel_path} "
            f"({len(adf.get('content', []))} blocks, sha256={fp[:12]}...)"
        )
        if errors:
            print(f"  ADF validation warnings: {len(errors)}")

    print("\nProbe OK — ready to publish. Use --only README.md for a single-page trial.")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]

    # First pass: read --source and --config from argv only (before full config merge)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--source", default=DEFAULT_SOURCE)
    pre.add_argument("--config", default=None)
    pre_args, _ = pre.parse_known_args()

    source_dir = (repo_root / pre_args.source).resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")

    config_path = Path(pre_args.config) if pre_args.config else default_config_path(source_dir)
    if not config_path.is_file() and pre_args.config:
        raise SystemExit(f"Config file not found: {config_path}")
    if not config_path.is_file():
        example = source_dir / CONFIG_EXAMPLE_FILENAME
        hint = f" Copy {example.name} to {CONFIG_FILENAME}." if example.is_file() else ""
        print(f"Note: no config at {config_path}.{hint}", file=sys.stderr)

    config_data = load_publish_config(config_path) if config_path.is_file() else {}
    args = parse_args(config_data)

    source_dir = (repo_root / args.source).resolve()
    if not source_dir.is_dir():
        raise SystemExit(f"Source directory not found: {source_dir}")

    missing = [
        name
        for name, val in (
            ("domain (config/confluence.domain)", args.domain),
            ("email (config/confluence.email)", args.email),
            ("api_token (config/confluence.api_token)", args.token),
            ("space_key (config/confluence.space_key)", args.space),
            ("parent_page_id (config/confluence.parent_page_id)", args.parent_id),
        )
        if not val
    ]
    if missing and not args.dry_run and not args.probe and not args.audit_links:
        print("Missing required settings:", ", ".join(missing), file=sys.stderr)
        print(f"Set in {config_path} or via CONFLUENCE_* env vars.", file=sys.stderr)
        raise SystemExit(2)

    pub_cfg = config_data.get("publish", {})
    if not isinstance(pub_cfg, dict):
        pub_cfg = {}

    layout = PublishLayoutConfig.from_settings(pub_cfg, repo_root)

    state_rel = pub_cfg.get("state_file")
    if not args.state_file and state_rel:
        state_path = source_dir / str(state_rel)
    elif not args.state_file:
        state_path = source_dir / STATE_FILENAME
    else:
        state_path = Path(args.state_file)

    if config_path.is_file() and not args.dry_run:
        print(f"Using config: {config_path}")

    auth = build_token_auth_header(args.email or "dry-run@example.com", args.token or "dry-run")
    http_cfg = HttpRetryConfig.from_settings(pub_cfg, args)
    client = ResilientConfluenceClient(
        args.domain or "example.atlassian.net", auth, http_cfg
    )

    if args.probe:
        if missing:
            print("Missing required settings:", ", ".join(missing), file=sys.stderr)
            raise SystemExit(2)
        run_probe(
            client,
            args.domain,
            args.space,
            str(args.parent_id),
            source_dir,
            layout,
        )
        return

    root_page_id = args.root_page_id
    if not root_page_id and state_path.is_file():
        try:
            state_data = json.loads(state_path.read_text(encoding="utf-8"))
            root_page_id = state_data.get("root_page_id")
        except json.JSONDecodeError:
            pass

    publisher = SuitePublisher(
        client=client,
        domain=args.domain or "example.atlassian.net",
        space_key=args.space or "DRY",
        parent_id=str(args.parent_id or "0"),
        source_dir=source_dir,
        mermaid_strategy=args.mermaid,
        mermaid_macro_key=args.mermaid_macro_key,
        dry_run=args.dry_run or args.audit_links,
        force=args.force,
        root_page_id=str(root_page_id) if root_page_id else None,
        root_page_rel=str(pub_cfg.get("root_page_rel") or DEFAULT_ROOT_PAGE_REL),
        layout=layout,
    )
    publisher.load_state(state_path)
    publisher.apply_config_overrides(pub_cfg)

    suite_prefix = source_dir.relative_to(repo_root).as_posix()
    github = build_github_config(args, suite_prefix, pub_cfg, layout)
    gcp = build_gcp_config(pub_cfg)
    publisher.github_verifier = build_github_verifier(
        github, pub_cfg, args, workspace_root=repo_root
    )

    if args.audit_links:
        specs = discover_pages(source_dir, layout)
        publisher.fetch_remote_tree()
        publisher.reconcile_with_remote(specs)
        for spec in specs:
            publisher.page_titles.setdefault(spec.rel_path, spec.title)
        catalog = build_link_catalog(
            specs,
            publisher.page_ids,
            publisher.page_titles,
            publisher.domain,
            publisher.space_key,
            dry_run=False,
        )
        publisher.refresh_page_urls()
        catalog.refresh_from_publisher(publisher)
        audit_links(specs, catalog, github, publisher.github_verifier, gcp)
        return

    publisher.publish(
        github=github,
        state_path=state_path,
        only=args.only,
        gcp=gcp,
    )


if __name__ == "__main__":
    main()
