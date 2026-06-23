# Using AI code reviews in Azure DevOps

For developers working in pull requests. Dashboard access is not required.

## Scope

PR-Agent reviews security, complex logic, async/threading, test gaps, and team **best practices**. With **code context** enabled, it can reference dependencies outside the diff.

It does not replace your linter or formatter. ESLint, StyleCop, Prettier, and similar tools own formatting and style.

## What runs on your PR

When PR-Agent is enabled, **build validation** runs on PR open/update (not on every comment). A self-hosted agent runs PR-Agent in Docker. Output appears as PR comments and optional description updates.

| Tool | Output |
|------|--------|
| **Describe** | PR title and description |
| **Review** | Security, logic, concurrency, tests, best practices |
| **Improve** | Substantive suggestions (not style fixes) |

Runtime depends on diff size, models, and whether code context is on. Expect a few minutes.

## When nothing runs

- Build validation missing on the target branch (admin configuration).
- Pipeline not triggered as a PR build (`BUILD_REASON` must be `PullRequest`).
- `[no_bots]` or `[nobots]` in the PR description when your org enables that filter.
- Diff over the configured **line limit** (PR-Agent posts an explanation comment).
- **Describe** skipped when the PR already has a description (`skip_if_description_exists`).
- Review skipped when prior PR-Agent output exists (`skip_if_review_suggestions_exist`).

If runs are consistently missing, ask your admin. [Configuring PR filters](../how-to/configuring-pr-filters.md).

## Opting out

When `terminate_on_no_bots` is enabled, add to the PR description:

```text
[no_bots]
```

(or `[nobots]`). The pipeline exits without running tools.

## Reading output

Review comments group findings by severity or category (per prompt config). Expect security, logic, concurrency, and design findings, not formatting nits. File and line references come from the diff. With **code context** for C#, reviews may cite code outside the diff.

**Improve** suggestions are not auto-commits. Apply them like any other review comment.

## best_practices.md

Some repos add **`best_practices.md`** at the root. PR-Agent injects it into **review** and **improve** (not describe). Use it for validation rules, error-handling patterns, and threading conventions. Do not duplicate linter rules.

Admins edit via the dashboard **Best Practices** tab or direct repo commits.

## Admin-owned settings

Models, API keys, pipeline YAML, and global filters are configured by administrators: [Configuration and overrides](../how-to/configuration-and-overrides.md), [Adding an Azure DevOps repository](../how-to/onboarding/README.md), [What is this project?](what-is-this-project.md), [Azure PR architecture](../technical/azure-architecture/README.md).
