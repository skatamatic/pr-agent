# Adding an Azure DevOps repository

The **Add Repository** wizard walks through five steps. The UI labels them Step 1–5; internal state is 0-indexed.

**Entry:** Dashboard → **Repositories** → **Add Repository** → **Azure DevOps**

| UI step | Name | What happens |
|---------|------|--------------|
| **Step 1** | Connect | Org URL + PAT → discovery + PAT identity |
| **Step 2** | Select Repo | Choose project/repository |
| **Step 3** | Runner Setup | Agent pool; optional GCE VM provision |
| **Step 4** | Pipeline Setup | YAML + policy via **Set Up Pipeline & Check** |
| **Step 5** | Review & Save | Repo flags → **Add Repository** |

Detailed step-by-step: [Wizard steps](wizard-steps.md).

## Before you start

You'll need:

- Dashboard login
- Azure DevOps PAT with the scopes below
- At least one **online** self-hosted agent in your pool
- LLM API keys in **AI Config**
- If provisioning VMs from the UI: `GCP_RUNNER_PROJECT_ID` and `GCP_RUNNER_PR_AGENT_IMAGE` on the backend

**PAT scopes (minimum):**

- **Code: Read & write**: post review comments, push config PRs
- **Build: Read & execute**: pipeline defs, variables, queue runs
- **Project and team: Read**: discovery, list repos/branches
- **Graph: Read**: optional; improves PAT identity display at wizard Step 1

**Test Token** on the **General** tab only validates read access. It won't catch missing comment-write or policy-write permissions.

## After onboarding: repository card tabs

Once saved, the repo card has six tabs:

- **Status**: runner health, config check
- **General**: PAT edit, **Test Token**
- **Azure Pipeline**: readiness checklist, **Fix Issues**, YAML/policy status
- **Agent Install**: manual agent install instructions
- **Best Practices**: coding standards editor
- **PR-Agent Config**: per-repo overrides

**Fix Issues** is mandatory after onboarding: the wizard does not sync pipeline variables. See [Wizard steps → Step 4](wizard-steps.md#step-4-pipeline-setup).

## Verify end-to-end

1. Open test PR on branch with build validation policy
2. ADO pipeline: `BUILD_REASON = PullRequest`, agent pool assigned
3. Dashboard **Jobs**: new run appears for the PR
4. PR shows review/description from PR-Agent

## Cross-repo pipeline

Pipeline YAML may live in `pr-agent-pipelines` while the PR targets another repo. Runner resolves PR repo via `SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI`. See [Azure PR architecture](../../technical/azure-architecture/README.md#cross-repo-build-validation).

## Troubleshooting

- **Pipeline queued forever**: agent offline in pool
- **No dashboard job**: `DASHBOARD_URL` / `DASHBOARD_API_KEY` not in synced variables
- **LLM 401**: sync variables; check AI Config keys
- **Setup PR pending**: merge PR in shared pipeline repo first
- **Wrong comment author**: check PAT identity from Step 1
- **Config file not found**: create settings from **PR-Agent Config** or **Best Practices** on the default branch

For day-2 ops: [Maintenance and diagnostics](../maintenance/README.md), [Configuration and overrides](../configuration-and-overrides.md).
