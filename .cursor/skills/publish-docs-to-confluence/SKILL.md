---
name: publish-docs-to-confluence
description: >-
  Publish a markdown documentation suite to Confluence Cloud: configure via TOML,
  structure pages by audience (product, users, admin, devops, engineers), author
  with parallel subagents, split oversized pages, de-LLM prose pass, then sync as
  ADF with internal links, GitHub code links, optional GCP Console links, and Mermaid.
  Use when the user wants Confluence docs, publish markdown to Atlassian, a docs suite
  setup, confluence.publish.toml, doc cleanup, or mentions a Confluence API token with docs.
---

# Publish markdown docs to Confluence

End-to-end workflow: **research and author markdown in a configurable source folder**, **structure and polish for humans**, then **publish** to Confluence Cloud as ADF pages with wired internal links, optional GitHub links for repo paths, and Mermaid rendering.

Read [reference.md](reference.md) for the full TOML schema, **audience matrix**, link rules, de-LLM checklist, and troubleshooting.

> **Skill vs published docs:** This skill may name audience *lenses* (product, admin, etc.). The published suite must not label pages "for executives" or use Audience columns in indexes.

## Quick start (any repo)

1. **Install deps** (once per machine):

```bash
pip install -r .cursor/skills/publish-docs-to-confluence/scripts/requirements.txt
```

2. **Copy config templates** next to your markdown source (default `docs/suite/`):

```bash
cp docs/suite/confluence.publish.example.toml docs/suite/confluence.publish.toml
cp docs/suite/confluence.publish.env.example docs/suite/confluence.publish.env   # optional
```

3. **Edit local TOML** (`confluence.publish.toml`, gitignored): Confluence domain, space, parent/root page ids, credentials, `publish.github_repo`, and `[publish.page_titles]` for every page. Mirror stable entries to `confluence.publish.example.toml` (committed template, no secrets).

4. **Gitignore secrets and state**:

```
docs/suite/confluence.publish.toml
docs/suite/confluence.publish.env
docs/suite/.confluence-publish.json
```

(Adjust paths if `publish.source` is not `docs/suite`.)

5. **Probe**, then **publish**:

```bash
# Bash / Linux / macOS
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --probe
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py

# Windows (repo root): loads confluence.publish.env, pins page ids
.\docs\suite\publish.ps1 --probe
.\docs\suite\publish.ps1
```

Use `--config /path/to/confluence.publish.toml` and `--source relative/markdown/root` to override defaults.

**Incremental publish (PowerShell):** quote comma-separated paths so the shell does not split them:

```powershell
.\docs\suite\publish.ps1 --only "overview/what-is-this-project.md,how-to/README.md"
```

---

## Audiences (summary)

Every suite serves **five reader types**. Route by topic and depth, not labels. Full matrix, placement rules, and subagent scoping: [reference.md → Audience content matrix](reference.md#audience-content-matrix).

| Lens | Typical location |
|------|------------------|
| **Product** | `overview/` (one canonical "what/why" page) |
| **Users** | `overview/using-*.md` (product behavior, no dashboard); rare user tasks in `how-to/` |
| **Admin** | `how-to/onboarding/`, `how-to/maintenance/`, config how-tos |
| **DevOps** | `technical/deployment/`, env/TOML, cron, runners |
| **Engineers** | `technical/internals/`, `technical/dashboard-api/`, `technical/*-architecture/` |

**`technical/` split:** `deployment/` = infra and runbooks (DevOps). `internals/`, `dashboard-api/`, architecture pages = code and API depth (engineers).

**Anti-patterns:** duplicate "value/rollout" page; Audience column on indexes; 400-line monoliths mixing wizard + API + ROI.

---

## Phase 0: Collect setup (ask if missing)

Before writing docs or publishing, confirm every item below. Do not guess credentials or page IDs.

| Field | TOML / file | Notes |
|-------|-------------|-------|
| **Markdown source** | `publish.source` | Folder of `.md` files (default `docs/suite`) |
| **GitHub repo** | `publish.github_repo` | For inline `` `src/foo.py` `` links |
| **Default branch** | `publish.github_ref` | Branch/tag for GitHub links (default `main`) |
| **Confluence domain** | `confluence.domain` | e.g. `myorg.atlassian.net` (no `https://`) |
| **Space key** | `confluence.space_key` | e.g. `ENG` |
| **Parent page ID** | `confluence.parent_page_id` | Page **above** the suite root, not the root itself |
| **Root page ID** | `confluence.root_page_id` | Existing landing page for `root_page_rel` (omit on first create) |
| **Root page title** | `[publish.page_titles]` | Product name only on the landing page |
| **Atlassian email** | `confluence.email` | Must match the API token owner |
| **API token** | `confluence.api_token` | In local TOML only; never commit |
| **Env overrides** | `confluence.publish.env` | Optional; non-secret ids/URLs; loaded by `publish.ps1` |

**Page ID from URL:** `…/wiki/spaces/SPACE/pages/5347508594/Title` → `5347508594`.

---

## Phase 1: Scaffold directory structure

```
{publish.source}/
├── README.md                    # Suite landing: product name, Start here table, section index
├── overview/                    # Product value, user-facing concepts, flow at a glance
├── how-to/                      # Admin/operator task guides
├── technical/                   # DevOps (deployment/) + engineering (internals/, api/, arch/)
├── workflows/                   # Optional WIP drafts (list in publish.skip_files)
├── assets/                      # Screenshot PNGs + capture checklist (assets/README.md)
├── confluence.publish.example.toml
├── confluence.publish.env.example
├── publish.ps1                  # Windows wrapper (optional but recommended)
└── confluence.publish.toml      # gitignored
```

**Page title rules**

- Root `README.md`: product name only.
- Child pages: no `{Product} -` title prefix; pin distinctive titles in `[publish.page_titles]`.
- Nested folders: `README.md` is the Confluence parent for siblings.
- Subpage title prefixes when the space collides: `GCP: Topology`, `Maintenance: Troubleshooting`.

**`workflows/` staging:** Keep work-in-progress or experimental copies here; add paths to `publish.skip_files` until promoted into `how-to/` or `technical/`.

See [reference.md → Layout and ordering](reference.md#layout-and-ordering).

---

## Phase 2: Research and author (parallel subagents)

Do not write the whole suite from memory. Launch **parallel `explore` subagents** (readonly, code-backed). Use `generalPurpose` only when the agent must also edit files outside the doc tree.

### Recommended agent split

Run **in parallel** (adjust paths to the repo):

| Lens | Investigate | Write to |
|------|-------------|----------|
| Product | Capabilities, differentiators, end-to-end flow | `overview/README.md`, `overview/what-is-*.md` |
| Users | PR/UI behavior, skip conditions, opt-out | `overview/using-*.md` |
| Admin | Wizard, config surfaces, Fix Issues, filters | `how-to/onboarding/`, `how-to/maintenance/`, config how-tos |
| DevOps | Terraform, cloud services, env vars, deploy scripts, runners | `technical/deployment/` |
| Engineers | Pipeline runner, API routes, config loader, telemetry | `technical/internals/`, `technical/dashboard-api/`, architecture |

Optional extras: API routes-only agent, integration-specific agent (ADO, metrics, security).

### Subagent prompt requirements

Each prompt **must** include: repo path; target markdown paths; lens (tone only, not labels in prose); cross-link targets; de-LLM bans (see Phase 4); git-backed `![alt](path.png)` on major admin UI steps (see [Images in docs](#images-in-docs)); real `` `path/to/file.py` `` on engineer pages.

**Admin / `how-to/` lens:** write dashboard UI only (tabs, buttons, wizards, field labels). **Do not** put `GET`/`POST` lines, `/api/...` routes, TOML snippets, or `[section].key` paths in how-tos. Link to `technical/toml-configuration-system.md` or `technical/dashboard-api/` when file or REST detail is needed.

Template: [reference.md → Subagent prompt template](reference.md#subagent-prompt-template).

### Synthesis pass (parent agent)

1. Merge section `README.md` indexes (scope + child table with **Summary** only).
2. Dedupe product/why into one overview page.
3. Fix relative links and heading anchors.
4. Update suite `README.md` **Start here** table.
5. Add new paths to **`confluence.publish.toml`** `[publish.page_titles]` (and mirror to example TOML when stable).

---

## Phase 3: Structure pass (split, merge, indexes)

Split when a page exceeds ~150-200 lines or mixes lenses. Merge when a subpage is thin (< ~40 lines) or duplicates "why" narrative.

Hub + subpages pattern: `technical/deployment/README.md` + topic files. Subpages link to the hub with normal inline links only (no `Part of` / `←` footers).

**After split or merge:** update cross-links and indexes; `[publish.path_migrations]` for old paths with Confluence ids; remove dead paths from `page_titles`; orphan cleanup (see [reference.md → Orphan pages](reference.md#orphan-pages-after-merges-or-renames)).

---

## Phase 4: De-LLM and Confluence formatting pass

Run **before every publish** on the full `{publish.source}` tree (exclude `workflows/` if skipped).

```bash
# Automated first pass (always review diff)
python .cursor/skills/publish-docs-to-confluence/scripts/de_llm_pass.py docs/suite --dry-run
python .cursor/skills/publish-docs-to-confluence/scripts/de_llm_pass.py docs/suite

# Verification
rg $'\u2014' docs/suite/
rg -i 'this guide is|this page covers|related docs|part of \[|← ' docs/suite/
python .cursor/skills/publish-docs-to-confluence/scripts/audit_markdown_fences.py docs/suite
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --audit-links
```

Full banned-pattern list and Confluence markdown rules: [reference.md → De-LLM pass](reference.md#de-llm-and-formatting-pass-required).

### Quality gates

**Block publish**

- [ ] Zero em dashes (`rg` clean on published tree)
- [ ] `--audit-links`: suite `.md` links show as `WIRE`, not `GITHUB`
- [ ] `[publish.page_titles]` entry for every non-skipped markdown file
- [ ] `audit_markdown_fences.py` clean (or fixes applied)
- [ ] Path migrations + orphan ids updated after any merge/rename

**Should fix before calling done**

- [ ] No executive/leadership/stakeholder framing in body text
- [ ] Single canonical product/why page in `overview/`
- [ ] Index tables use **Summary** only (no Audience column)
- [ ] UI screenshots live in `assets/screenshots/` with `![alt](relative/path.png)` in markdown (not Confluence-only)
- [ ] `how-to/` has no `/api/` routes or HTTP method blocks (`rg '/api/' how-to/` clean)
- [ ] `how-to/` has no TOML examples or config key paths unless linked out to `technical/` (`rg -i '\.toml|```toml' how-to/` clean)

**Nice to have**

- [ ] Checklist in `assets/README.md` updated
- [ ] Engineer pages link to primary source files

---

## Images in docs (source of truth in git)

**Risk:** Publish **replaces** each Confluence page body from markdown. Images pasted only in the Confluence editor are **lost** on the next sync.

### Authoring rules

| Rule | Do | Don't |
|------|-----|-------|
| Storage | Commit PNG under `assets/screenshots/{page-slug}/` | Rely on Confluence-only paste |
| Markdown | `![alt text](relative/path.png)` on its own line | Bare URLs or HTML `<img>` |
| Paths | Relative from the `.md` file (e.g. `../assets/screenshots/...`) | Absolute machine paths |
| Alt text | Short UI label ("Delete job from Jobs tab") | Empty alt or filename-only |
| Planning | Optional `SCREENSHOT PLACEHOLDER` blockquote while drafting | Ship placeholders to Confluence |

Publish runs `embed_local_images()` in `publish_suite.py`: uploads the file as a page attachment and embeds inline (`mediaSingle`, same pattern as Mermaid).

### Recover Confluence-only uploads (one-time)

```powershell
python .cursor/skills/publish-docs-to-confluence/scripts/pull_confluence_images.py --config docs/suite/confluence.publish.toml
python .cursor/skills/publish-docs-to-confluence/scripts/apply_pulled_screenshots.py
# Add any remaining ![...](...) lines manually, then republish
.\docs\suite\publish.ps1
```

Checklist and capture targets: [docs/suite/assets/README.md](../../../docs/suite/assets/README.md). Full detail: [reference.md → Images in docs](reference.md#images-in-docs).

---

## How-to authoring (admin lens)

`how-to/` is for **dashboard operators**: what to click, which tab, what the preview shows.

| Include | Exclude (put in `technical/` instead) |
|---------|-----------------------------------------------------|
| Nav paths (**Jobs**, **AI Config → PR Filters**) | `GET /api/...`, `POST /api/...` blocks |
| Button names (**Fix Issues**, **Test Model**) | JSON request/response examples |
| UI field labels (**Max lines changed**, **Default Model**) | TOML blocks, `.pr_agent.toml`, `[section].key` paths |
| One link to technical docs when no UI exists | Inline route strings in procedure steps |

Verification before publish:

```bash
rg '/api/' docs/suite/how-to/
rg '^(GET|POST|PUT|DELETE)\s' docs/suite/how-to/
rg -i '\.toml|```toml|\[config\]|\[pr_' docs/suite/how-to/
```

Both should return no matches.

---

## Phase 5: Link rules

| Target | Write as | Publishes to |
|--------|----------|--------------|
| Another suite page | `[Title](relative/path.md)` | Confluence |
| Repo code | `` `src/main.py` `` | GitHub blob |
| Repo doc outside suite | `` `deploy/README.md` `` | GitHub blob |
| GCP Console (optional) | `[Backend](gcp://cloud-run/backend)` | Cloud Console |

Never put raw GitHub URLs in source markdown.

---

## Phase 6: Publish

```bash
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --probe
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --only "README.md"
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --audit-links
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --dry-run
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --force   # push all pages
```

After structural changes (splits, index renames), prefer a **full publish** so link catalogs stay consistent.

**Orphans:** `delete_confluence_pages.py --from-config` then clear `delete_orphan_page_ids` from TOML; prune stale keys from `.confluence-publish.json` if needed.

**Never** commit `confluence.publish.toml`, `confluence.publish.env`, or echo `api_token` in chat.

---

## Bootstrapping a new repo

1. Create `{publish.source}/`, `confluence.publish.example.toml`, optional `publish.ps1` + env example.
2. Copy to local TOML; set `[confluence]` and `[publish]`; pin every page title.
3. Create suite root in Confluence (or first publish); set `root_page_id`.
4. `--probe`, then `--only README.md`.
5. Phase 2 subagents → Phase 3 structure → Phase 4 de-LLM → full publish.
6. Add `[publish.path_migrations]` only when renaming files that already have Confluence ids.

Reference implementation: **PR-Agent** `docs/suite/` (overview / how-to / technical, hub subpages, `publish.ps1`).

---

## Agent checklist (full doc initiative)

1. **Setup**: Local TOML + env, Confluence ids, GitHub repo, page titles.
2. **Scaffold**: Source tree; `skip_files` for `workflows/` if used.
3. **Research**: Parallel `explore` subagents (product, users, admin, devops, engineers).
4. **Synthesize**: Indexes, dedupe, cross-links, Start here table, TOML titles.
5. **Structure**: Split/merge; path_migrations.
6. **De-LLM**: `de_llm_pass.py` + verification commands.
7. **Probe + audit**: `--probe`, `--audit-links`, fence audit.
8. **Publish**: Full sync (or `--only` for small follow-ups).
9. **Reconcile**: Delete orphan pages; clear orphan ids; prune state file.
10. **Handoff**: Root Confluence URL; structural change summary.

## Scripts

| Script | Purpose |
|--------|---------|
| [publish_suite.py](scripts/publish_suite.py) | Main publish/sync |
| [de_llm_pass.py](scripts/de_llm_pass.py) | Em dashes, Part of/←/Related docs cleanup |
| [pull_confluence_images.py](scripts/pull_confluence_images.py) | Download Confluence screenshot attachments into assets/ |
| [apply_pulled_screenshots.py](scripts/apply_pulled_screenshots.py) | Replace PLACEHOLDER blocks using live page image order |
| [delete_confluence_pages.py](scripts/delete_confluence_pages.py) | Remove orphan pages by id |
| [audit_markdown_fences.py](scripts/audit_markdown_fences.py) | Confluence-unsafe fenced code |

Full CLI and TOML keys: [reference.md](reference.md)
