# Auth

Part of the [Dashboard API](README.md) reference.

JWT session endpoints for the React UI. Machine ingest uses `DASHBOARD_API_KEY` on job/operation/log routes (see [Jobs & operations](jobs-and-operations.md) and [Logs](logs.md)).

---

## POST `/api/auth/login`

Public.

**Request**

```json
{
  "username": "admin",
  "password": "mobile"
}
```

**Response `200`**

```json
{
  "data": {
    "token": "eyJ...",
    "user": {
      "id": 1,
      "username": "admin",
      "is_active": true,
      "created_at": "2026-01-01T00:00:00",
      "last_login": "2026-06-16T12:00:00"
    }
  },
  "message": "Login successful"
}
```

The session field is `token`, not `access_token`.

**Response `401`:** invalid credentials

---

## GET `/api/auth/verify`

JWT required.

**Response `200`:** `{ "data": { "user": { ... } }, "message": "Token valid" }`

---

## POST `/api/auth/change-password`

JWT required.

**Request**

```json
{
  "current_password": "mobile",
  "new_password": "your-new-password"
}
```

**Response `400`:** current password incorrect
