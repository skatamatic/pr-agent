# Azure DevOps PR-Agent Pipeline Setup Guide

This guide helps you set up PR-Agent to run automatically on Azure DevOps pipelines using self-hosted agents.

## Prerequisites

1. **Self-hosted Azure DevOps agent** (Windows or Linux)
2. **Python 3.12** installed on the agent
3. **Git** installed on the agent
4. **Access to your Azure DevOps organization** with permissions to create pipelines

## Setup Steps

### 1. Configure Pipeline Variables

In your Azure DevOps project, go to **Pipelines > Library** and create a new variable group called `PR-Agent-Config` with these variables:

#### Required Variables:
- `OPENAI_KEY` - Your OpenAI API key (mark as secret)
- `ANTHROPIC_KEY` - Your Anthropic API key (mark as secret)

#### Optional Variables (if using C# Context Service):
- `CONTEXT_PASSWORD` - Password for your C# context service (mark as secret)

### 2. Create the Pipeline

1. In Azure DevOps, go to **Pipelines > Create Pipeline**
2. Choose **Azure Repos Git** (or your source)
3. Select your repository
4. Choose **Existing Azure Pipelines YAML file**
5. Select the `azure-pipelines-pr-agent.yml` file
6. Review and save the pipeline

### 3. Configure Agent Pool

Update the pipeline YAML to match your agent pool:

```yaml
pool:
  name: 'your-agent-pool-name'  # Replace with your actual pool name
  demands:
  - agent.os -equals Windows_NT  # or Linux
```

### 4. Configure Repository Permissions

The pipeline needs access to pull request information. Ensure the build service has these permissions:

1. Go to **Project Settings > Repositories**
2. Select your repository
3. Go to **Security** tab
4. Find **[Project Name] Build Service** account
5. Grant these permissions:
   - **Contribute**: Allow
   - **Contribute to pull requests**: Allow
   - **Create branch**: Allow (for auto-suggestions)

### 5. Enable System.AccessToken

The pipeline uses `$(System.AccessToken)` for Azure DevOps API access:

1. Edit your pipeline
2. Go to **Variables** tab
3. Enable **"Let scripts access the OAuth token"** under **Agent job**

### 6. Branch Policy (Optional but Recommended)

To automatically trigger PR-Agent on all pull requests:

1. Go to **Repos > Branches**
2. Click **...** next to your main branch (e.g., `main`, `master`)
3. Select **Branch policies**
4. Under **Build validation**, add your PR-Agent pipeline
5. Set **Trigger** to "Automatic" and **Policy requirement** to "Optional"

## Configuration Options

### Environment Variables in Pipeline

You can customize PR-Agent behavior by setting these variables in the pipeline YAML:

```yaml
variables:
  # Auto-run tools (true/false)
  AZURE_DEVOPS_CONFIG.AUTO_DESCRIBE: 'true'   # Auto-generate PR descriptions
  AZURE_DEVOPS_CONFIG.AUTO_REVIEW: 'true'     # Auto-review code
  AZURE_DEVOPS_CONFIG.AUTO_IMPROVE: 'true'    # Auto-suggest improvements
  
  # AI Model Configuration
  CONFIG.MODEL: 'gpt-4'                       # or claude-3-5-sonnet-20241022
  CONFIG.FALLBACK_MODELS: 'gpt-4o,claude-3-5-sonnet-20241022'
```

### Repository-Specific Settings

Create a `.pr_agent.toml` file in your repository root for repo-specific configuration:

```toml
[config]
model = "gpt-4"
max_tokens = 8000

[pr_description]
publish_description = true
add_original_user_description = true

[pr_reviewer]
require_security_review = true
require_score = true

[pr_code_suggestions]
num_code_suggestions = 5
```

## Troubleshooting

### Common Issues:

1. **Pipeline doesn't trigger on PRs**:
   - Check that `trigger: none` and `pr:` sections are configured correctly
   - Verify branch policies include the pipeline

2. **Authentication errors**:
   - Ensure `System.AccessToken` is enabled
   - Check that build service has repository permissions

3. **Module import errors**:
   - Verify Python 3.12 is installed on the agent
   - Check that `requirements.txt` installation succeeded

4. **C# Context Service connection issues**:
   - Verify the service is running on `localhost:7110`
   - Check firewall settings on the agent

### Debug Mode:

Add this variable to enable verbose logging:

```yaml
variables:
  CONFIG.LOG_LEVEL: 'DEBUG'
```

## Agent Performance Tips

1. **Use pip cache**: The pipeline includes pip caching to speed up builds
2. **Pre-install Python packages**: Consider pre-installing common packages on your agents
3. **Git shallow clone**: The pipeline uses `--single-branch` for faster checkouts

## Security Considerations

1. **Store secrets securely**: Use Azure DevOps variable groups with secret variables
2. **Limit repository access**: Grant minimal permissions to the build service
3. **Review generated content**: PR-Agent suggestions should be reviewed before merging

## Next Steps

After setup:

1. Create a test pull request to verify the pipeline works
2. Check pipeline logs for any errors
3. Review generated PR descriptions, reviews, and suggestions
4. Adjust configuration as needed for your team's workflow

For advanced configuration options, see the [PR-Agent documentation](https://github.com/Codium-ai/pr-agent). 