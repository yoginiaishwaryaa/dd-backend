# Database Design

## Schema Diagram

![Delta Schema](/images/Delta_Schema_Diagram.png)

## Database Schema

### Users Table
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR,
    github_user_id INTEGER UNIQUE,
    github_username VARCHAR,
    current_refresh_token_hash VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

### Installations Table
```sql
CREATE TABLE installations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id BIGINT UNIQUE NOT NULL, 
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    account_name VARCHAR,
    account_type VARCHAR,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_installations_user ON installations(user_id);
```

### Repositories Table
```sql
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    installation_id BIGINT REFERENCES installations(installation_id) ON DELETE CASCADE,
    repo_name VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_suspended BOOLEAN DEFAULT FALSE,
    avatar_url VARCHAR,
    docs_root_path VARCHAR DEFAULT '/docs',
    target_branch VARCHAR DEFAULT 'main',
    style_preference VARCHAR DEFAULT 'professional',
    file_ignore_patterns VARCHAR[],
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(installation_id, repo_name)
);
```

### Drift Events Table
```sql
CREATE TABLE drift_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID REFERENCES repositories(id) ON DELETE CASCADE,
    pr_number INTEGER NOT NULL,
    base_branch VARCHAR NOT NULL,
    head_branch VARCHAR NOT NULL,
    base_sha VARCHAR NOT NULL,
    head_sha VARCHAR NOT NULL,
    check_run_id BIGINT,
    docs_pr_number INTEGER,
    retry_count INTEGER DEFAULT 0 NOT NULL,
    processing_phase VARCHAR DEFAULT 'queued',
    drift_result VARCHAR DEFAULT 'pending',
    overall_drift_score FLOAT,
    summary VARCHAR,
    error_message VARCHAR,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT check_processing_phase CHECK (processing_phase IN ('queued', 'scouting', 'analyzing', 'generating', 'verifying', 'completed', 'failed')),
    CONSTRAINT check_drift_result CHECK (drift_result IN ('pending', 'clean', 'drift_detected', 'missing_docs', 'error'))
);

CREATE INDEX idx_drift_active_runs ON drift_events (repo_id) 
WHERE processing_phase NOT IN ('completed', 'failed');
```

### Drift Findings Table
```sql
CREATE TABLE drift_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drift_event_id UUID REFERENCES drift_events(id) ON DELETE CASCADE,
    code_path VARCHAR NOT NULL,
    doc_file_path VARCHAR,
    change_type VARCHAR,
    drift_type VARCHAR,
    drift_score FLOAT,
    explanation VARCHAR,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT check_finding_change_type CHECK (change_type IN ('added', 'modified', 'deleted')),
    CONSTRAINT check_start_drift_type CHECK (drift_type IN ('outdated_docs', 'missing_docs', 'ambiguous_docs'))
);
```

### Code Changes Table
```sql
CREATE TABLE code_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drift_event_id UUID REFERENCES drift_events(id) ON DELETE CASCADE,
    file_path VARCHAR NOT NULL,
    change_type VARCHAR,
    is_code BOOLEAN DEFAULT TRUE,
    is_ignored BOOLEAN DEFAULT FALSE NOT NULL,
    CONSTRAINT check_code_change_type CHECK (change_type IN ('added', 'modified', 'deleted'))
);
```

### Notifications Table
```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

## Database Migrations

Using Alembic for database migrations:

```bash
# Create a new migration
make migrate msg="add new column to users"

# Apply all pending migrations
make up

# Apply one migration
make up-one

# Rollback to base
make down

# Rollback one migration
make down-one

# View migration history
make history
```

> **NOTE**: The `make` commands are designed to work only on Linux.  
> If you are using another OS, please check the Makefile and execute the corresponding commands directly.
