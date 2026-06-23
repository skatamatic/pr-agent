# Configuration

Part of the [Dashboard API](README.md) reference.

Global PR-Agent config, model discovery, and context-service testing. JWT required for all routes in this section.

---

## GET `/api/config`

Merged config with secrets masked.

---

## POST `/api/config`

**Request**

```json
{
  "config": {
    "config": { "model": "anthropic/claude-sonnet-4-6-20260205", "temperature": 0.2 },
    "pr_reviewer": { "num_max_findings": 15 },
    "api_keys": { "openai": "sk-...", "anthropic": "sk-ant-..." }
  }
}
```

Backend splits sections into `configuration.toml`, `secrets.toml`, and context files in GCS/local storage. Deep-merge preserves keys not sent.

---

## GET `/api/config/dashboard-auto-setup`

Dashboard auto-setup state.

---

## POST `/api/config/bulk-upload`

Multipart upload of a `.zip` containing recognized config filenames (`configuration.toml`, `secrets.toml`, etc.). Extracted files overwrite storage individually; a rotated backup is created first.

---

## GET/POST `/api/config/pr-agent-path`

PR-Agent install path on the runner host.

---

## POST `/api/config/pr-agent-path/validate`

Validate a proposed path without saving.

---

## GET `/api/models/available`

List models available given current config keys.

---

## POST `/api/models/test`

```json
{
  "model": "anthropic/claude-sonnet-4-6-20260205",
  "use_saved_config": true,
  "api_keys": { "anthropic": "sk-ant-..." }
}
```

---

## POST `/api/config/test-context-service`

```json
{
  "url": "https://context.example.com",
  "username": "user",
  "password": "pass",
  "timeout": 30
}
```
