# Publish docs/suite to Confluence using docs/suite/confluence.publish.toml.
# Run from repo root: .\docs\suite\publish.ps1 [--probe] [--audit-links] [other publish_suite.py flags]

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $RepoRoot

$EnvFile = Join-Path $PSScriptRoot "confluence.publish.env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"')
            Set-Item -Path "Env:$name" -Value $value
        }
    }
} else {
    # Pin stable page ids so stale user env cannot reparent the suite.
    $env:CONFLUENCE_PARENT_PAGE_ID = "4620319"
    $env:CONFLUENCE_ROOT_PAGE_ID = "5347967000"
}

$PublishScript = Join-Path $RepoRoot ".cursor/skills/publish-docs-to-confluence/scripts/publish_suite.py"
if (-not (Test-Path $PublishScript)) {
    throw "Publish script not found: $PublishScript"
}

python $PublishScript @args
exit $LASTEXITCODE
