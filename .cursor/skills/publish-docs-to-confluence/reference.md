# Confluence publish reference

Generic reference for publishing any markdown documentation suite to Confluence Cloud via `publish_suite.py`. Project-specific values live in TOML beside the source folder.

## Initial setup questionnaire

Use when starting a new suite or onboarding a new repo. Copy answers into `confluence.publish.toml` (local, gitignored).

```
Product / suite name (root title only): ___________
Markdown source path (publish.source): ___________  (default: docs/suite)
GitHub repository URL: ___________
Default branch for code links: ___________

Confluence domain (no scheme): ___________
Space key: ___________
Parent page ID (folder above suite root): ___________
Root page ID (existing landing page, if any): ___________

Atlassian account email: ___________
API token: ___________  (local TOML only; never commit)

Mermaid strategy [cloud|png|png-local|code]: png
Link inline repo paths to GitHub? [yes|no]: yes
```

**Common mistakes**

| Mistake | Fix |
|---------|-----|
| `parent_page_id` = suite root id | Parent is the Confluence page **one level above** the product landing page |
| Auth 401 | Email must match the Atlassian account that created the token |
| Title collision on publish | Add unique `[publish.page_titles]` entry |
| Old titles stuck after rename | Config `[publish.page_titles]` overrides `.confluence-publish.json` cache |
| Renamed markdown file creates duplicate Confluence page | Add `old = "new"` under `[publish.path_migrations]` |
| Inline code links to wrong GitHub paths | Set `publish.github_path_prefixes` or rely on auto-discovery of top-level dirs |
| Suite `.md` links go to GitHub | Use relative `[Title](path.md)` links; run `--audit-links` |
| New page publishes with wrong title | Add path to **local** `confluence.publish.toml` `[publish.page_titles]`, not example only |
| PowerShell `--only` fails with multiple files | Quote the argument: `--only "a.md,b.md"` |

## Local config files

| File | Committed? | Purpose |
|------|------------|---------|
| `confluence.publish.example.toml` | Yes | Template: page titles, section order, path migrations, GCP shape (no secrets) |
| `confluence.publish.toml` | **No** | Credentials, API token, live page ids; **publish reads this** |
| `confluence.publish.env.example` | Yes | Optional env override template (domain, ids, github ref) |
| `confluence.publish.env` | **No** | Loaded by `publish.ps1` on Windows |
| `.confluence-publish.json` | **No** | Page id cache (under `publish.source`) |
| `publish.ps1` | Yes (optional) | Repo-root wrapper: `.\docs\suite\publish.ps1` |

**Workflow:** edit **local TOML** for every publish. Mirror stable `[publish.page_titles]` and structural keys to **example TOML** when merging to main.

## Configuration

**File:** `{publish.source}/confluence.publish.toml` (gitignored)  
**Template:** `{publish.source}/confluence.publish.example.toml` (committed)

**Setting priority (highest first):**

1. CLI flags (`--email`, `--token`, `--domain`, `--source`, `--config`, …)
2. Environment variables (`CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`, …)
3. Config file

**Gitignore:** `confluence.publish.toml`, `confluence.publish.env`, `.confluence-publish.json` (or `publish.state_file`)

### `[confluence]`

| Key | Required | Description |
|-----|----------|-------------|
| `domain` | yes | Atlassian host, e.g. `myorg.atlassian.net` |
| `email` | yes | Account that owns the API token |
| `api_token` | yes | Atlassian API token (Cloud) |
| `space_key` | yes | Confluence space key |
| `parent_page_id` | yes | Page id **above** the suite root |
| `root_page_id` | no | Existing landing page for `publish.root_page_rel` |

### `[publish]`

| Key | Default | Description |
|-----|---------|-------------|
| `source` | `docs/suite` | Markdown root relative to repo |
| `root_page_rel` | `README.md` | Landing file under `source` |
| `state_file` | `.confluence-publish.json` | Page id cache filename (under `source`) |
| `github_repo` | (none) | GitHub URL for code/file links |
| `github_ref` | `main` | Branch/tag/commit for GitHub links |
| `link_inline_paths` | `true` | Link `` `path/to/file` `` spans to GitHub |
| `github_verify_paths` | `true` | Skip links that 404 on GitHub (local fallback) |
| `github_token` | (none) | Optional; or `GITHUB_TOKEN` env |
| `mermaid_strategy` | `png` | `cloud`, `png`, `png-local`, or `code` |
| `mermaid_macro_key` | `mermaid-cloud` | Confluence macro key when strategy is `cloud` |
| `delete_orphan_page_ids` | `[]` | Page ids for `delete_confluence_pages.py --from-config` |

### `[publish.page_titles]`

Maps relative markdown path → Confluence page title. **Pin every page** to avoid space-wide title collisions.

```toml
[publish.page_titles]
"README.md" = "My Product"
"overview/README.md" = "Product overview"
"how-to/README.md" = "How-to guides"
```

Title resolution order:

1. `[publish.page_titles]` from config (always wins)
2. Cached title in state file
3. First `# H1` in markdown
4. Filename title-cased

Body upload strips the leading `# H1`; Confluence shows the pinned title separately.

### `[publish.path_migrations]`

When markdown files are **renamed or moved** after they already have Confluence page ids, map old relative paths to new ones. State migrates on load; old keys drop on save.

```toml
[publish.path_migrations]
# Monolith split into hub
"technical/deployment-on-gcp.md" = "technical/deployment/README.md"
# Subpage merged back into hub
"technical/azure-architecture/pipeline-triggers-and-skips.md" = "technical/azure-architecture/README.md"
# Removed product duplicate
"overview/value-and-rollout.md" = "overview/what-is-this-project.md"
```

New repos omit this section until the first rename of a **published** file.

### Layout and ordering

**`[publish.section_order]`** sibling order under the suite root (default: `overview` → `how-to` → `technical` → `assets` last):

```toml
[publish.section_order]
overview = 0
how-to = 1
technical = 2
assets = 99
```

**`[publish.audience_order]`** order under audience subfolders when used:

```toml
[publish.audience_order]
users = 0
admins = 1
devops = 2
engineering = 3
```

Many suites use flat `how-to/` + `technical/`; `[publish.section_order]` is enough.

**`publish.skip_files`** relative paths excluded from publish (common: WIP under `workflows/`):

```toml
skip_files = [
  "workflows/README.md",
  "workflows/draft-onboarding.md",
]
```

Promote content from `workflows/` into `how-to/` or `technical/`, then remove from `skip_files`.

### GitHub inline link detection

Paths in backticks become GitHub links when they look like repo-root paths.

**Auto-discovery (default):** common prefixes (`docs/`, `src/`, `scripts/`, …) plus every **top-level directory** in the repo.

**Override prefixes:**

```toml
github_path_prefixes = ["backend/", "frontend/", "packages/api/"]
```

**Root filenames** (no directory prefix):

```toml
github_root_filenames = ["Dockerfile", "pyproject.toml", "package.json"]
```

### `[publish.gcp_deployment]` (optional)

Rewrites `gcp://…` links in markdown to Cloud Console URLs. Fields are **product-specific**; copy the shape from your project's `confluence.publish.example.toml`. Common keys: `project_id`, `region`, `backend_service`, `frontend_service`, `cloud_sql_instance`, `documents_bucket`, `artifact_registry_repo`. See `GcpDeploymentConfig` in `publish_suite.py` for supported `gcp://` path aliases.

### `[publish.http]`

| Field | Default | Purpose |
|-------|---------|---------|
| `api_timeout_sec` | `90` | JSON API timeout |
| `upload_timeout_sec` | `300` | Mermaid PNG / attachment upload |
| `max_retries` | `6` | Retries on timeout, 429, 5xx |
| `backoff_base_sec` | `2` | Exponential backoff base |
| `request_delay_ms` | `250` | Pause after each successful page write |
| `checkpoint_after_each_page` | `true` | Save state after every CREATE/UPDATE |

CLI overrides: `--api-timeout`, `--upload-timeout`, `--max-retries`, `--no-checkpoint`.

### Environment variables

| Variable | Overrides |
|----------|-----------|
| `CONFLUENCE_DOMAIN` | `confluence.domain` |
| `CONFLUENCE_EMAIL` | `confluence.email` |
| `CONFLUENCE_API_TOKEN` | `confluence.api_token` |
| `CONFLUENCE_SPACE_KEY` | `confluence.space_key` |
| `CONFLUENCE_PARENT_PAGE_ID` | `confluence.parent_page_id` |
| `CONFLUENCE_ROOT_PAGE_ID` | `confluence.root_page_id` |
| `CONFLUENCE_GITHUB_REPO` | `publish.github_repo` |
| `CONFLUENCE_GITHUB_REF` | `publish.github_ref` |
| `CONFLUENCE_MERMAID_STRATEGY` | `publish.mermaid_strategy` |
| `GITHUB_TOKEN` | `publish.github_token` |

## Directory structure

Content is organized by **reader need**, not visible audience labels in prose.

| Path | Serves | Contents |
|------|--------|----------|
| `README.md` | Everyone | Product name, Start here table (role → entry page), section index |
| `overview/` | Product, new readers | What/why/features/differentiators/flow; `using-*.md` for user behavior without dashboard access |
| `how-to/` | Admin (primary), occasional user tasks | Onboarding, config, maintenance; **dashboard UI only** (no `/api/` routes); hub + subpages for long workflows |
| `technical/deployment/` | DevOps | Topology, Terraform, env, runners, ops |
| `technical/internals/`, `dashboard-api/`, `*-architecture/` | Engineers | Code paths, APIs, sequence diagrams |
| `workflows/` | Authors (WIP) | Draft copies; `skip_files` until promoted |
| `assets/` | Authors | Screenshot checklist and PNGs |

Nested sections: `README.md` is the Confluence parent for siblings.

**Users:** `overview/using-*.md` = product behavior in the user's normal tool (e.g. ADO PRs). `how-to/` = tasks inside your admin app (rare for pure end users).

**Index pages:** scope paragraph + child table (**Page | Summary** only). Suite landing may use a Start here table; child pages must not say "for executives".

## Page titles and collisions

Confluence titles are **space-wide**.

1. **Root only:** product name (`My Product`).
2. **No prefix on children:** not `My Product - Using the app`; use `Using the app`.
3. **Pin every page** in `[publish.page_titles]`.
4. **Disambiguate generics:** `Product overview`, `How-to guides`, `Technical reference`.

## Audience content matrix

Canonical matrix for subagent scoping and page placement. **Do not paste these labels into published prose.**

| Lens | Questions they ask | Content types | Example paths |
|------|-------------------|---------------|---------------|
| **Product** | What is it? Why adopt it? What is different? ROI? | Capabilities, differentiators, flow at a glance | `overview/what-is-this-project.md` |
| **Users** | What happens on my PR? Opt out? What will I see? | Behavior, expectations, screenshot placeholders | `overview/using-*.md` |
| **Admin** | Onboard repo? Fix pipeline? Filters/models? | Wizard tabs, Fix Issues, PAT scopes, config hierarchy (UI steps only) | `how-to/onboarding/`, `how-to/maintenance/` |
| **DevOps** | Deploy? What runs where? Env? Terraform? | Topology, scripts, Cloud Run/GCE, cron | `technical/deployment/` |
| **Engineers** | Pipeline flow? API routes? Code location? | Sequences, route tables, `` `file.py` `` links | `technical/internals/`, `technical/dashboard-api/` |

**Deduping:** one canonical product/why page. No second "value proposition" or "rollout" page.

## Deep-dive authoring with subagents

Use parallel **`explore`** subagents (readonly) before drafting. Minimum: one agent per lens that applies. Add subsystem agents (API-only, deployment-only) for large products.

### Parallel run pattern

1. Launch all agents in **one message** (multiple Task tool calls).
2. Each agent reads code/config; returns markdown paths + gaps.
3. Parent: synthesis (indexes, dedupe, cross-links, **local TOML titles**).
4. Structure pass: split/merge.
5. De-LLM pass: full tree before publish.

Use **`generalPurpose`** only when the agent must edit non-doc repo files.

### Subagent prompt template

```
Repo: {absolute path}
Lens: {product|users|admin|devops|engineers}
Task: Document {topics} for Confluence suite at {publish.source}/.

Requirements:
- Read actual code and config; cite routes, env vars, file paths from the repo.
- Write markdown to: {explicit file list}
- Match depth to lens (reference.md audience matrix); do NOT label the audience in the doc.
- Cross-link related pages with relative [Title](path.md) links.
- Use tables for env vars and route lists; no blank lines inside table rows.
- Do NOT use em dashes (U+2014).
- Do NOT use meta phrases ("This page covers", "This guide is for", "Related docs", "Part of", footer "← Back").
- Admin / how-to lens: dashboard UI only (tabs, buttons, wizards). Do NOT include GET/POST lines or `/api/...` routes; link to `technical/dashboard-api/` for REST.
- Admin UI steps: use git-backed `![alt](../assets/screenshots/page-slug/file.png)` (see assets/README.md); blockquote placeholders OK while drafting.
- Engineer pages: link code with `path/to/file.ext` backticks.

Return:
- Files created/updated
- Gaps needing a follow-up agent
- Suggested splits if any topic exceeded ~150 lines
```

### Synthesis checklist (parent agent)

- [ ] Section `README.md` indexes updated
- [ ] Suite `README.md` Start here table updated
- [ ] No duplicate product/why pages
- [ ] All new paths in **local** `confluence.publish.toml` `[publish.page_titles]` (mirror to example when stable)
- [ ] Cross-links resolve (`rg` for old paths after moves)

## Images in docs

Publish **overwrites** Confluence page bodies from markdown. Inline images must be in git, not only in the Confluence editor.

### Workflow

| Step | Action |
|------|--------|
| Capture | PNG → `assets/screenshots/{page-slug}/filename.png` (commit to git) |
| Reference | `![alt text](relative/path/to.png)` on its own line in the doc |
| Alt text | Describe the UI ("PR Filters tab in AI Config"), not just the filename |
| Publish | `publish_suite.py` uploads attachment + embeds `mediaSingle` |
| Verify | Confluence page shows image after sync; file remains in git |

Paths must resolve under `publish.source` (typically `docs/suite/`). Use relative paths from the markdown file (e.g. `../assets/screenshots/...`).

### md-to-adf behavior

Standard markdown images become linked `[alt]` text in ADF. `embed_local_images()` (in `publish_suite.py`) detects those paragraphs, uploads the local PNG, and swaps in a proper inline image attachment (same pattern as Mermaid PNGs).

### Recover Confluence-only images

```bash
python .cursor/skills/publish-docs-to-confluence/scripts/pull_confluence_images.py --config docs/suite/confluence.publish.toml --report docs/suite/assets/.pull-report.json
python .cursor/skills/publish-docs-to-confluence/scripts/apply_pulled_screenshots.py
```

Then add any remaining `![...](...)` lines manually from `.pull-report.json` and republish.

### Planning placeholders

Optional blockquote placeholders during authoring; replace with real `![...](...)` before publish. See checklist in `assets/README.md`.

## How-to authoring (view-centric)

`how-to/` pages serve **dashboard operators**. Write procedures in terms of navigation and controls the reader sees.

**Include:** tab names, button labels, modal titles, field labels as shown in the UI.

**Exclude:** HTTP method + path blocks, JSON bodies, cron auth headers, TOML file names, config key paths (`[pr_filters]`, `config.model`), and raw file examples unless **no dashboard control exists** (then one link to `technical/toml-configuration-system.md`).

**API detail:** one optional trailing link per topic, e.g. "For REST details, see [Dashboard API: Jobs](technical/dashboard-api/jobs-and-operations.md)."

**Verification:**

```bash
rg '/api/' docs/suite/how-to/
rg '^(GET|POST|PUT|DELETE)\s' docs/suite/how-to/
rg -i '\.toml|```toml|\[config\]|\[pr_' docs/suite/how-to/
```

## Screenshot placeholders (legacy blockquote format)

During drafting, optional blockquote markers are OK until a PNG exists:

```markdown
> **SCREENSHOT PLACEHOLDER:** Jobs tab → row menu → Delete Job & Related Data
```

Replace with `![Delete job](../assets/screenshots/cleanup-and-retention/delete-job.png)` before publish. `apply_pulled_screenshots.py` can swap placeholders using Confluence attachment order when recovering old uploads.

## Structure pass: split, merge, migrations

### Split (hub + subpages)

**Triggers:** page > ~150-200 lines; mixed lenses; hard to maintain.

```
how-to/onboarding/
├── README.md              # Hub: prerequisites, tabs, troubleshooting summary
└── wizard-steps.md        # Steps 1-5 detail
```

**After split:** hub child table; inline links only; pin titles; `path_migrations` from old monolith if already published.

### Merge

**Triggers:** thin subpage; duplicated narrative; user request to recombine.

**After merge:** fold into hub; update links; `path_migrations` from deleted subpage → merged file; orphan cleanup below.

## API / reference split pattern

```
technical/dashboard-api/
├── README.md
├── auth.md
├── jobs-and-operations.md
└── …
```

Pin titles in `[publish.page_titles]`. Use prefixed titles only when the space collides.

## De-LLM and formatting pass (required)

Run on entire `{publish.source}` before every publish (respect `skip_files`).

### Automated pass

```bash
python .cursor/skills/publish-docs-to-confluence/scripts/de_llm_pass.py docs/suite --dry-run
python .cursor/skills/publish-docs-to-confluence/scripts/de_llm_pass.py docs/suite
```

Then manual review: fix table cells where em dash meant "empty" (`-` or `n/a`, not `:`).

### Banned patterns

| Pattern | Action |
|---------|--------|
| U+2014 em dash | Comma, period, colon, or `**Label**: text` |
| `At its core`, `In summary`, `It's worth noting` | Delete; lead with fact |
| `This page/guide covers`, `This guide is for {role}` | Delete |
| `Suggested narrative`, `Caveats to disclose`, `Executive summary` | Plain headings or drop |
| `Related docs` / `See also` link-only sections | Remove; inline links in body |
| `Part of [Parent](README.md).` | Remove |
| `[← Parent](README.md)` footers | Remove |
| `: not X` | `, not X` or new sentence |
| `for executives`, `leadership`, `stakeholder-oriented` in body | Remove |
| Duplicate value/rollout page | Merge into product overview |
| Rhetorical italic question chains | Direct statements |

### Confluence-safe markdown

| Issue | Rule |
|-------|------|
| Tables | No blank lines between rows |
| Key/value pairs | Prefer bullets if 2-column tables render poorly |
| Fenced code | Column 0 only; not nested under list items |
| Table empty cells | `-` or `n/a`, not em dash |

### Verification

```bash
rg $'\u2014' docs/suite/
rg -i 'this guide is|this page covers|related docs|part of \[|← ' docs/suite/
python .cursor/skills/publish-docs-to-confluence/scripts/audit_markdown_fences.py docs/suite
python .cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py --audit-links
```

### Quality gate tiers

| Tier | Checks |
|------|--------|
| **Block publish** | Zero em dashes; `--audit-links` WIRE not GITHUB; `page_titles` complete; fence audit clean; migrations/orphans handled |
| **Should fix** | No executive framing; single product/why page; index Summary-only; major UI flows have placeholders |
| **Nice to have** | `assets/README.md` checklist updated; engineer pages link primary sources |

## Authentication

Confluence Cloud REST API: HTTP Basic auth `base64(email:api_token)`. Cloud only (not Data Center PAT scheme).

## Link rewriting

**Three-pass publish:** link catalog → create missing pages → post-process with full catalog.

| Target | Source in markdown | Resolves to |
|--------|-------------------|-------------|
| Suite page | `[Title](../how-to/foo.md)` | Confluence wiki URL |
| Suite root | `` `docs/suite/README.md` `` (under `publish.source`) | Root page |
| Repo code | `` `src/main.py` `` | GitHub blob |
| Repo doc outside suite | `` `deploy/README.md` `` | GitHub blob |
| GCP (optional) | `[Service](gcp://cloud-run/backend)` | Cloud Console |

Run `--audit-links` to preview wiring.

## GCP Console links (optional)

Configure `[publish.gcp_deployment]` with your project's resource names. Authoring:

```markdown
[Cloud Run backend](gcp://cloud-run/backend)
[Documents bucket](gcp://gcs/documents)
```

Path aliases: see `GcpDeploymentConfig.url_for` in `publish_suite.py`.

## Re-runs and updates

State file: `{rel_path: {id, title, url}}`.

Each run: fetch live tree → reconcile → diff ADF fingerprint → skip unchanged. Config titles override cache.

- **`--force`**: push all pages regardless of fingerprint.
- **Manual Confluence edits:** delete state or fix ids before re-publish.

After **splits or index renames**, run a **full publish** (not only changed files) so link catalogs stay consistent.

### Orphan pages after merges or renames

The publish script **does not delete** Confluence pages when markdown is removed.

```bash
# 1. Add ids to local TOML
# publish.delete_orphan_page_ids = ["5347968232"]

python .cursor/skills/publish-docs-to-confluence/scripts/delete_confluence_pages.py --from-config --config docs/suite/confluence.publish.toml

# 2. Clear delete_orphan_page_ids from TOML after success

# 3. Prune stale keys from .confluence-publish.json if the delete script left them
```

Single page: `delete_confluence_pages.py PAGE_ID`

## Mermaid strategies

| Strategy | Behavior |
|----------|----------|
| `cloud` | Mermaid Diagrams for Confluence macro (`mermaid_macro_key`) |
| `png` | PNG via local `mmdc` or Kroki fallback |
| `png-local` | PNG via local CLI only |
| `code` | Fenced code blocks, no rendering |

## Example suite (PR-Agent)

`docs/suite/` reference implementation:

- `confluence.publish.example.toml`, `publish.ps1`, `confluence.publish.env.example`
- Layout: `overview/`, `how-to/`, `technical/` (hub subpages: `deployment/`, `onboarding/`, `dashboard-api/`)
- `workflows/` listed in `skip_files` for WIP drafts
- De-LLM conventions; path migrations for splits/merges

## API endpoints used

| Operation | Endpoint |
|-----------|----------|
| Resolve space | `GET /wiki/api/v2/spaces?keys={KEY}` |
| Create page | `POST /wiki/api/v2/pages` |
| Update page | `PUT /wiki/api/v2/pages/{id}` |
| List children | `GET /wiki/api/v2/pages/{id}/children` |

Body representation: `atlas_doc_format` (ADF).

## Scripts

| Script | Purpose |
|--------|---------|
| `publish_suite.py` | Main publish/sync |
| `pull_confluence_images.py` | Download Confluence screenshot attachments |
| `apply_pulled_screenshots.py` | Apply pulled images to PLACEHOLDER blocks |
| `delete_confluence_pages.py` | Remove orphan pages by id |
| `audit_markdown_fences.py` | Confluence-unsafe fenced code |
