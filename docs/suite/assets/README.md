# Screenshot assets

Store dashboard screenshots under `assets/screenshots/` and reference them from suite markdown. **Commit PNGs to git.** The publish script uploads them as Confluence attachments on each sync.

## Source of truth

| Location | Role |
|----------|------|
| `assets/screenshots/{page-slug}/*.png` | **Canonical** image files (version controlled) |
| `![alt](../assets/screenshots/...)` in `.md` | Where each image appears in the doc |
| Confluence page body | Generated from markdown on publish |

**Do not paste screenshots only in the Confluence UI.** The next publish replaces the page body from markdown and removes images that are not referenced in git.

If you already uploaded images in Confluence, pull them into git first (see below).

## Add a new screenshot

1. Capture PNG (1440×900 or 1920×1080; one theme; 100% zoom).
2. Save to `assets/screenshots/{page-slug}/` (e.g. `wizard-steps/S04-step1-connect.png`).
3. In the doc markdown, on its own line:

```markdown
![Step 1 connect](../../assets/screenshots/wizard-steps/S04-step1-connect.png)
```

Use a relative path from the `.md` file to the PNG. Alt text is the caption Confluence shows.

4. Publish: `.\docs\suite\publish.ps1` (or `--only` for one page).

Publish uploads the file as a page attachment and embeds it as an inline image (same mechanism as Mermaid PNGs).

## Recover Confluence-only uploads

If screenshots were added in Confluence before markdown references existed:

```powershell
# 1. Download attachments (skips mermaid-*.png)
python .cursor/skills/publish-docs-to-confluence/scripts/pull_confluence_images.py `
  --config docs/suite/confluence.publish.toml `
  --report docs/suite/assets/.pull-report.json

# 2. Replace remaining SCREENSHOT PLACEHOLDER blocks (uses live page order)
python .cursor/skills/publish-docs-to-confluence/scripts/apply_pulled_screenshots.py

# 3. For pages with no placeholders left, add ![...](...) lines manually using .pull-report.json

# 4. Republish
.\docs\suite\publish.ps1
```

## Checklist (32)

Track captures here. Mark **Done** when the PNG is in `assets/screenshots/` and referenced in markdown.

| ID | Document | Capture | Done |
|----|----------|---------|------|
| S01 | overview/what-is-this-project | Overview: Database, **PR-Agent Config**, Context Service, Repositories cards + completed job | ☐ |
| S02 | technical/deployment/config-cloud-run-and-ops | AI Config → Advanced: config path with **From GCS** source | ☐ |
| S03 | technical/deployment/config-cloud-run-and-ops | Wizard Step 3 runner provisioning milestones | ☐ |
| S04 | how-to/onboarding/wizard-steps | Step 1 Connect with 5-step progress bar | ☑ |
| S05 | how-to/onboarding/wizard-steps | PAT identity panel after connect | ☐ |
| S06 | how-to/onboarding/wizard-steps | Step 2 repo searchable dropdown | ☐ |
| S07 | how-to/onboarding/wizard-steps | Step 3 agent pool + provision progress | ☐ |
| S08 | how-to/onboarding/wizard-steps | Step 4 after Set Up Pipeline & Check + merge PR banner | ☐ |
| S09 | how-to/onboarding/wizard-steps | Step 5 with Monitor Issues + auto-* checkboxes | ☐ |
| S10 | how-to/onboarding/wizard-steps | Post-save: **Azure Pipeline** tab readiness checklist | ☐ |
| S11 | how-to/onboarding/wizard-steps | **Fix Issues** button on Azure Pipeline tab | ☐ |
| S12 | how-to/onboarding/wizard-steps | Split: ADO pipeline run + Dashboard Jobs match | ☐ |
| S13 | how-to/maintenance | Logs tab with job filter | ☐ |
| S14 | how-to/maintenance | Failed job: operation-level error | ☐ |
| S15 | how-to/maintenance | Overview health: one card degraded | ☐ |
| S16 | how-to/maintenance | AI Config → Test Model success/failure | ☐ |
| S17 | how-to/maintenance | Azure Pipeline missing variables before Fix Issues | ☐ |
| S18 | how-to/maintenance | **General** tab Test Token results | ☐ |
| S19 | how-to/maintenance | Code Context Test Connection | ☐ |
| S20 | how-to/cleanup | Job delete preview dialog | ☑ |
| S21 | how-to/cleanup | Repository delete cleanup modal (azure_checks count) | ☑ |
| S22 | how-to/cleanup | Action Runners panel + delete | ☑ |
| S23 | how-to/cleanup | **Data Cleanup** tab (not Retention) preview | ☑ |
| S24 | how-to/configuration | AI Config → **AI Models** tab (models + keys) | ☑ |
| S25 | how-to/configuration | Advanced → Repository Settings Files | ☑ |
| S26 | how-to/configuration | PrAgentConfigEditor override highlighting | ☑ |
| S27 | how-to/configuration | Effective Config modal | ☐ |
| S28 | how-to/configuration | Best Practices tab rendered + Edit | ☑ |
| S29 | technical/azure-pr-e2e | Annotated PR comment + dashboard job | ☐ |
| S30 | technical/self-hosted-runners | Runner connection online + pool name | ☐ |
| S31 | technical/self-hosted-runners | GCP serial console bootstrap success | ☐ |
| S32 | how-to/maintenance | Azure Pipeline checklist all green after Fix Issues | ☐ |

Also captured (not in checklist IDs): PR Filters tab (`configuring-pr-filters`), Metrics tab (`reading-metrics-and-roi`).

## Capture tips

- Mask PATs, API keys, and org names if the docs go public.
- For ADO pipeline shots, show `BUILD_REASON = PullRequest` when you can.
- Number callouts on technical screenshots to match sequence diagrams.

## Diagram conventions (for doc authors)

- Split overloaded Mermaid charts; short node labels; LR for linear flows.
- Dotted lines (`-.->`) for secondary paths (config load, image pull).
- Sequence diagrams: `Note over` for repeated steps; six or fewer participants when possible.
