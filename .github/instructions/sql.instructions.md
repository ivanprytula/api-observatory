---
name: sql-standards
description: "Apply to: database files (infra/database/init.sql, migrations). Enforces readable SQL, proper indexing, constraint patterns, and migration best practices."
applyTo: "infra/database/**/*.sql, backend/migrations/**/*.py"
---

# SQL Code Standards

## Query Style & Formatting

### Readability
- **Uppercase keywords**: SELECT, FROM, WHERE, JOIN, GROUP BY, ORDER BY.
- **Lowercase identifiers**: table names, column names.
- **Indentation**: 2 spaces for nested clauses.
- **Line breaks**: One clause per line for complex queries.

```sql
-- Good: readable, clear structure
SELECT
  u.id,
  u.name,
  u.email,
  COUNT(p.id) AS post_count
FROM users AS u
LEFT JOIN posts AS p ON u.id = p.user_id
WHERE u.created_at > '2024-01-01'
GROUP BY u.id, u.name, u.email
ORDER BY post_count DESC
LIMIT 10;

-- Bad: cramped, hard to parse
SELECT u.id,u.name,u.email,COUNT(p.id)AS post_count FROM users AS u LEFT JOIN posts AS p ON u.id=p.user_id WHERE u.created_at>'2024-01-01'GROUP BY u.id,u.name,u.email ORDER BY post_count DESC LIMIT 10;
```

### Naming Conventions
- **Tables**: Plural, lowercase, snake_case (e.g., `users`, `user_posts`).
- **Columns**: Lowercase, snake_case, descriptive (e.g., `created_at`, `is_active`).
- **Primary keys**: Always `id` (bigint, auto-increment).
- **Foreign keys**: `{table}_id` (e.g., `user_id`).
- **Boolean fields**: `is_` or `has_` prefix (e.g., `is_active`, `has_verified_email`).

```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  email VARCHAR(255) UNIQUE NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_posts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  content TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## Schema Design

### Data Types
- **Integers**: `BIGINT` for IDs (not `INT`, future-proof).
- **Strings**: `VARCHAR(n)` with explicit max length, or `TEXT` for unbounded.
- **Timestamps**: Always `TIMESTAMP WITH TIME ZONE` for UTC consistency.
- **Booleans**: `BOOLEAN` (not `TINYINT`).
- **Decimals**: `NUMERIC(precision, scale)` for financial data.

### Constraints & Indexes
```sql
-- Good: comprehensive constraints
CREATE TABLE orders (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  total_amount NUMERIC(19, 2) NOT NULL CHECK (total_amount >= 0),
  status VARCHAR(50) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed')),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT unique_user_order UNIQUE(user_id, created_at)  -- Prevent duplicates
);

-- Index for common queries
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);

-- Composite index for frequent filter + sort
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
```

### Foreign Keys & Cascading
```sql
-- Good: cascade delete for cleanup
CREATE TABLE user_posts (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL
);

-- Bad: no cascade (orphaned records)
CREATE TABLE user_posts (
  user_id BIGINT NOT NULL REFERENCES users(id),
  title VARCHAR(255) NOT NULL
);
```

---

## Common Patterns

### Soft Deletes
Mark records as deleted without actually removing them (for audit trails):
```sql
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,

  CHECK (deleted_at IS NULL OR deleted_at <= CURRENT_TIMESTAMP)
);

-- Query active users (most common)
SELECT * FROM users WHERE deleted_at IS NULL;

-- Update to "soft delete"
UPDATE users SET deleted_at = CURRENT_TIMESTAMP WHERE id = 123;

-- Restore if needed
UPDATE users SET deleted_at = NULL WHERE id = 123;
```

### Audit Trail
Track who changed what and when:
```sql
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  entity_type VARCHAR(50) NOT NULL,  -- e.g., 'users', 'orders'
  entity_id BIGINT NOT NULL,
  action VARCHAR(50) NOT NULL,  -- 'create', 'update', 'delete'
  old_values JSONB,  -- Store as JSON for flexibility
  new_values JSONB,
  changed_by BIGINT REFERENCES users(id),
  changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to auto-log changes
CREATE FUNCTION log_change()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO audit_log (entity_type, entity_id, action, old_values, new_values, changed_by)
  VALUES ('users', NEW.id, 'update', row_to_json(OLD), row_to_json(NEW), current_user_id);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_update_trigger AFTER UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION log_change();
```

---

## Migrations (Alembic)

### Migration Structure
```python
"""Add user_posts table.

Revision ID: 8f3e5b2a1c0d
Revises: 7a2c1f3e9b5d
Create Date: 2024-03-18 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "8f3e5b2a1c0d"
down_revision = "7a2c1f3e9b5d"
branch_labels = None
depends_on = None


def upgrade():
    """Apply the migration (forward)."""
    op.create_table(
        "user_posts",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_user_posts_user_id", "user_posts", ["user_id"])
    op.create_index("idx_user_posts_created_at", "user_posts", ["created_at"])


def downgrade():
    """Revert the migration (backward)."""
    op.drop_index("idx_user_posts_created_at", table_name="user_posts")
    op.drop_index("idx_user_posts_user_id", table_name="user_posts")
    op.drop_table("user_posts")
```

### Best Practices
- **One logical change per migration**: Don't combine unrelated schema changes.
- **Always write reversible migrations**: Both `upgrade()` and `downgrade()` must work.
- **Test migrations**: Run forward and backward to catch issues early.
- **Use descriptive messages**: Migration filenames and docstrings should explain the intent.
- **Never modify migrations after deployment**: Create a new migration to fix issues.

---

## Performance Considerations

### Indexing Strategy
- **Index frequently filtered columns**: WHERE clauses, JOINs, ORDER BY.
- **Composite indexes**: For queries filtering on multiple columns.
- **Avoid over-indexing**: Each index adds write overhead; only index if query analysis justifies it.

```sql
-- Query: SELECT * FROM orders WHERE user_id = ? AND status = ?
-- Fast with composite index on (user_id, status):
EXPLAIN ANALYZE
SELECT * FROM orders WHERE user_id = 123 AND status = 'pending';

CREATE INDEX idx_orders_user_status ON orders(user_id, status);
```

### Query Optimization
```sql
-- Bad: N+1 queries problem (do this in Python loop, not SQL)
SELECT * FROM users;
-- Then for each user, run: SELECT COUNT(*) FROM posts WHERE user_id = ?

-- Good: single query with aggregation
SELECT
  u.id,
  u.name,
  COUNT(p.id) AS post_count
FROM users u
LEFT JOIN posts p ON u.id = p.user_id
GROUP BY u.id, u.name;

-- Or with subquery (if aggregation is conditional)
SELECT
  u.id,
  u.name,
  (SELECT COUNT(*) FROM posts WHERE user_id = u.id AND status = 'published') AS published_count
FROM users u;
```

---

## Common Pitfalls

- **Missing timestamps**: Always include `created_at` and `updated_at `.
- **No constraints**: Let database enforce business rules (NOT NULL, UNIQUE, CHECK, FK).
- **Bad timezone handling**: Always use `TIMESTAMP WITH TIME ZONE` (not `TIMESTAMP`).
- **Over-complex migrations**: Keep migrations focused and testable.
- **Ignoring indexes**: Query performance degrades on large tables without proper indexing.
