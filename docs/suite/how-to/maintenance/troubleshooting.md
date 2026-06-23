# Troubleshooting guide

Work through these layers when a PR run fails or the dashboard looks unhealthy.

## API keys (three places)

### 1. Global: AI Config

**AI Config → AI Models** holds model picks and provider API keys.

1. Enter or update keys
2. Click **Save**
3. Click **Test Model** and confirm success

### 2. Pipeline variables: Azure DevOps

Saving AI Config does not update Azure DevOps automatically.

1. Open the repository card → **Azure Pipeline** tab
2. Review the readiness checklist
3. Click **Fix Issues**

This syncs keys, dashboard URL, PAT, GCS bucket settings, and the PR-Agent image into pipeline variables. Required after onboarding and after every key rotation.

### 3. Runner VM (self-hosted)

On the runner machine, env file is usually `/opt/pr-agent-runner/env`. Pipeline variables override the file when both are set.

See [Choosing and configuring AI models](../choosing-and-configuring-ai-models.md) for the full sync flow.

## PAT problems

**Repositories → General → Test Token** checks profile, project access, repo read, and pipeline read. It does **not** prove the PAT can post PR comments.

For reviews to appear, the PAT needs **Code (Read & write)**. The identity shown at wizard **Step 1 Connect** is the user comments will appear under.

## Code context service

- **AI Config → Code Context** → **Test Connection** (global)
- Per-repo overrides: **PR-Agent Config → Code Context**
- Health summary: **Overview → Context Service** card

If context is enabled but the service is down, review/improve may fail or skip enrichment while describe still runs.

## Azure pipeline readiness

On **Azure Pipeline** tab:

- **Setup Readiness Checklist** shows YAML, variables, and policy status
- **Fix Issues** updates YAML, syncs variables, and repairs build validation

Common messages:

- Policy exists but points at an old pipeline definition → run **Fix Issues**
- **Merge setup PR** banner → merge the PR in the shared pipeline repo first
- PAT identity warning → confirm Step 1 identity matches who should own review comments

## Runner health

- Azure DevOps → Organization Settings → Agent pools → agent **Online**
- Dashboard → repository **Status** tab or **Repositories → Action Runners**
- GCP serial console if the VM failed bootstrap

See [Self-hosted runners](../../technical/self-hosted-runners.md).
