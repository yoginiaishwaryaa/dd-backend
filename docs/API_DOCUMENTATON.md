# API Endpoints

## Authentication Endpoints (`/api/auth`)

### POST `/auth/signup`
Create a new user account.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword_hash",
  "full_name": "John Doe"
}
```

**Response:**
- Sets `access_token` and `refresh_token` cookies
```json
{
  "email": "user@example.com",
  "name": "User Name"
}
```

### POST `/auth/login`
Login with email and password.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "securepassword_hash"
}
```

**Response:**
- Sets `access_token` and `refresh_token` cookies
```json
{
  "email": "user@example.com",
  "name": "User Name"
}
```

### POST `/auth/logout`
Logout and invalidate tokens.

**Response:**
- Deletes `access_token` and `refresh_token` cookies
```json
{
  "message": "Logout successfully"
}
```

### GET `/auth/github/callback`
GitHub OAuth callback handler.

**Query Params:**
- `code`: Authorization code from GitHub


## Webhook Endpoints (`/api/webhook`)

### POST `/webhook/github`
Receives GitHub webhook events.

**Headers:**
- `X-GitHub-Event`: Event Type (e.g., `pull_request`, `push`)
- `X-Hub-Signature-256`: HMAC signature for verification

**Request Body:**
GitHub Webhook Payload 

**Response:**
```json
{
  "status": "Received and Processed Event"
}
```

## Repository Endpoints (`/api/repos`)

### GET `/repos`
List all repositories for the authenticated user.

**Response:**
```json
[
  {
    "id": "13b1034a-d60b-4747-a87e-2b696da261db",
    "repo_name": "owner/repo_name",
    "is_active": true,
    "is_suspended": false,
    "avatar_url": "repo avatar url",
    "docs_root_path": "/docs",
    "target_branch": "main",
    "style_preference": "professional",
    "file_ignore_patterns": null,
    "last_synced_at": null,
  }
]
```

### PUT `/repos/{repo_id}/activate`
Activate or deactivate drift monitoring for a repository.

**Request Body:**
```json
{
  "is_active": false
}
```

**Response:**
```json
{
  "id": "13b1034a-d60b-4747-a87e-2b696da261db",
  "repo_name": "owner/repo_name",
  "is_active": false,
  "is_suspended": false,
  "avatar_url": "repo avatar url",
  "docs_root_path": "/docs",
  "target_branch": "main",
  "style_preference": "professional",
  "file_ignore_patterns": null,
  "last_synced_at": null,
}
```

### PUT `/repos/{repo_id}/settings`
Update repository configuration.

**Request Body:**
```json
{
  "docs_root_path": "/docs",
  "target_branch": "main",
  "style_preference": "technical",
  "file_ignore_patterns": ["*.test.js", "*.spec.ts"]
}
```

**Response:**
```json
{
  "id": "13b1034a-d60b-4747-a87e-2b696da261db",
  "repo_name": "owner/repo_name",
  "is_active": true,
  "is_suspended": false,
  "avatar_url": "repo avatar url",
  "docs_root_path": "/docs",
  "target_branch": "main",
  "style_preference": "technical",
  "file_ignore_patterns": ["*.test.js", "*.spec.ts"],
  "last_synced_at": null,
}
```

### GET `/repos/{repo_id}/drift-events`
Get all drift events for a repository, ordered by most recent first.

**Response:**
```json
[
  {
    "id": "a3f9c120-12d4-4b3e-9c7a-1a2b3c4d5e6f",
    "pr_number": 42,
    "base_branch": "main",
    "head_branch": "feat/update-auth",
    "processing_phase": "completed",
    "drift_result": "drift_detected",
    "overall_drift_score": 0.8,
    "summary": "Authentication flow was updated but related docs were not.",
    "error_message": null,
    "started_at": "2026-02-28T19:59:19.752504Z",
    "completed_at": "2026-02-28T19:59:22.853917Z",
    "created_at": "2026-02-28T19:59:10.705067Z"
  }
]
```

## Dashboard Endpoints (`/api/dashboard`)

### GET `/dashboard/stats`
Get dashboard statistics for the authenticated user.

**Response:**
```json
{
  "installations_count": 2,
  "repos_linked_count": 10,
  "drift_events_count": 32,
  "pr_waiting_count": 4
}
```

### GET `/dashboard/repos`
Get basic repository information for the 5 most recently linked repositories:

**Response:**
```json
[
  {
    "name": "repo name",
    "description": "repo description",
    "language": "Python",
    "stargazers_count": 2,
    "forks_count": 5,
    "avatar_url": "Avatar URL"
  }
]
```

## Notification Endpoints (`/api/notifications`)

### GET `/notifications`
Get all notifications for the user, ordered by most recent first.

**Response:**
```json
[
  {
    "id": "b2e1d3c4-11a2-4f3e-8b9a-0c1d2e3f4a5b",
    "content": "Drift detected in PR #42 for owner/repo_name.",
    "is_read": false,
    "created_at": "2026-03-01T10:00:00.000000Z"
  }
]
```

### PATCH `/notifications/{notification_id}/read`
Mark a single notification as read.

**Response:**
```json
{
  "id": "b2e1d3c4-11a2-4f3e-8b9a-0c1d2e3f4a5b",
  "content": "Drift detected in PR #42 for owner/repo_name.",
  "is_read": true,
  "created_at": "2026-03-01T10:00:00.000000Z"
}
```

### PATCH `/notifications/read-all`
Mark all notifications for the authenticated user as read.

**Response:**
```json
{
  "message": "All notifications marked as read"
}
```

### DELETE `/notifications/{notification_id}`
Delete a single notification.

**Response:**
```json
{
  "message": "Notification deleted"
}
```

### DELETE `/notifications`
Delete all notifications for the authenticated user.

**Response:**
```json
{
  "message": "All notifications deleted"
}
```

## API Testing

[Bruno](https://www.usebruno.com/) can be used as the API testing client. Pre-configured `.bru` collection files for all endpoints are available in the [`/bruno`](../bruno) directory.
