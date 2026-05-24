"""Project-wide constants — single source of truth for every magic value.

Rule: no bare integer or string literal in route handlers, CRUD functions,
schemas, or models. Import the name from here instead.

Grouping
--------
- API prefixes / versioning
- Pagination / query limits
- Batch operation limits
- Field-level validation bounds
- Rate-limiting parameters (v1 fixed-window, v2 token-bucket, v2 sliding-window)
"""

# ---------------------------------------------------------------------------
# API routing
# ---------------------------------------------------------------------------
API_V1_PREFIX: str = "/api/v1"
API_V2_PREFIX: str = "/api/v2"

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
DEFAULT_PAGE_SIZE: int = 100
MAX_PAGE_SIZE: int = 1000

# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------
MAX_BATCH_SIZE: int = 1000  # records per /batch request
MIN_BATCH_SIZE: int = 1

# ---------------------------------------------------------------------------
# Record field validation
# ---------------------------------------------------------------------------
SOURCE_MAX_LENGTH: int = 255
SOURCE_MIN_LENGTH: int = 1
TAGS_MAX_COUNT: int = 10

# ---------------------------------------------------------------------------
# Rate limiting — v1 fixed-window (slowapi)
# ---------------------------------------------------------------------------
V1_RATE_LIMIT: str = "1000/minute"
HEALTH_RATE_LIMIT: str = "100/minute"
AUTH_LOGIN_RATE_LIMIT: str = "10/minute"  # brute-force protection for /auth/token

# ---------------------------------------------------------------------------
# Rate limiting — v2 token bucket
# ---------------------------------------------------------------------------
TOKEN_BUCKET_CAPACITY: int = 20  # max burst size (tokens)
TOKEN_BUCKET_REFILL_PER_SEC: float = 10 / 60  # 10 requests per minute → ≈0.167/s

# ---------------------------------------------------------------------------
# Rate limiting — v2 sliding window
# ---------------------------------------------------------------------------
SLIDING_WINDOW_LIMIT: int = 10  # max requests in the window
SLIDING_WINDOW_SECONDS: int = 60  # rolling window size
# ---------------------------------------------------------------------------
# Retry-After jitter (thundering herd prevention)
# ---------------------------------------------------------------------------
JITTER_MIN_SECONDS: float = 5.0  # minimum random offset
JITTER_MAX_SECONDS: float = 10.0  # maximum random offset

# ---------------------------------------------------------------------------
# Concurrent enrichment (Step 8)
# ---------------------------------------------------------------------------
ENRICH_SEMAPHORE_LIMIT: int = 10  # cap concurrent external API calls
ENRICH_MAX_IDS: int = 50  # max record IDs per /enrich request
ENRICH_MIN_IDS: int = 1  # min record IDs per /enrich request

# ---------------------------------------------------------------------------
# Idempotent upsert (Step 9)
# ---------------------------------------------------------------------------
UPSERT_MODE_IDEMPOTENT: str = "idempotent"  # 201 on create, 200 on conflict
UPSERT_MODE_STRICT: str = "strict"  # 201 on create, 409 on conflict

# ---------------------------------------------------------------------------
# Caching — Redis
# ---------------------------------------------------------------------------
CACHE_KEY_RECORD: str = "dp:record:{record_id}"  # Redis key namespace

# ---------------------------------------------------------------------------
# Source Registry
# ---------------------------------------------------------------------------
SOURCE_PROFILE_NAME_MAX: int = 255
SOURCE_PROFILE_URL_MAX: int = 2048
SOURCE_PROFILE_TYPE_MAX: int = 64  # rest | webhook | file | graphql | grpc
SOURCE_PROFILE_OWNER_MAX: int = 128
SOURCE_PROFILE_SCHEMA_VERSION_MAX: int = 64
SOURCE_PROFILE_DESCRIPTION_MAX: int = 1024
SOURCE_HEALTH_TIMEOUT_SECONDS: float = 10.0  # probe timeout
SOURCE_HEALTH_UNHEALTHY_THRESHOLD_MS: int = 5000  # >5 s → "degraded"

# ---------------------------------------------------------------------------
# Contract & Drift Detection
# ---------------------------------------------------------------------------
CONTRACT_SCHEMA_VERSION_MAX: int = 64
CONTRACT_SNAPSHOT_NOTE_MAX: int = 512
DRIFT_SUMMARY_MAX: int = 1024
CONTRACT_COMPATIBILITY_MIN_SCORE: float = 0.0
CONTRACT_COMPATIBILITY_MAX_SCORE: float = 100.0
CONTRACT_PENALTY_ADDED_FIELD: float = 2.0
CONTRACT_PENALTY_REMOVED_FIELD: float = 20.0
CONTRACT_PENALTY_TYPE_CHANGE: float = 15.0

# ---------------------------------------------------------------------------
# Insight Engine
# ---------------------------------------------------------------------------
INSIGHT_CONFIDENCE_CRITICAL: float = 0.95
INSIGHT_CONFIDENCE_HIGH: float = 0.85
INSIGHT_CONFIDENCE_MEDIUM: float = 0.70
INSIGHT_CONFIDENCE_LOW: float = 0.55

INSIGHT_PRIORITY_P1: str = "P1"
INSIGHT_PRIORITY_P2: str = "P2"
INSIGHT_PRIORITY_P3: str = "P3"

# ---------------------------------------------------------------------------
# Subscription / Delivery
# ---------------------------------------------------------------------------
SUBSCRIPTION_DEFAULT_ESCALATION_MINUTES: int = 30
SUBSCRIPTION_DEFAULT_SUPPRESSION_MINUTES: int = 15
SUBSCRIPTION_DEFAULT_CHANNELS: tuple[str, ...] = ("webhook", "slack", "email")

# ---------------------------------------------------------------------------
# BI / Reporting
# ---------------------------------------------------------------------------
REPORTING_DEFAULT_DAYS: int = 7
REPORTING_MAX_DAYS: int = 90
REPORTING_DEFAULT_COHORT_LIMIT: int = 10
REPORTING_DEFAULT_HEATMAP_LIMIT: int = 20
REPORTING_DEFAULT_COST_LIMIT: int = 20
REPORTING_DEFAULT_FRESHNESS_LIMIT: int = 20
REPORTING_DEFAULT_SLA_THRESHOLD_HOURS: int = 24
REPORTING_MAX_SLA_THRESHOLD_HOURS: int = 168  # 7 days
REPORTING_DEFAULT_EXPORT_FORMAT: str = "json"
REPORTING_EXEC_SUMMARY_DEFAULT_SOURCE_LIMIT: int = 50
REPORTING_EXEC_SUMMARY_MAX_ACTIONS: int = 20

CACHE_TTL_RECORD: int = 3600  # 1 hour — single records are stable

# List cache (Phase 13.4) — write-heavy workload; short TTL with namespace invalidation
CACHE_KEY_LIST_PREFIX: str = "dp:records:list"
CACHE_TTL_LIST: int = 30  # 30 seconds for list pages
CACHE_LIST_MAX_SKIP: int = 500  # skip cache for large offsets (memory bloat prevention)
CACHE_LIST_MAX_LIMIT: int = 50  # skip cache for large pages

# Distributed locking (Phase 13.4) — single-node SET NX PX
CACHE_LOCK_PREFIX: str = "dp:lock"
CACHE_LOCK_DEFAULT_TTL_SECONDS: int = 300

# Cache warming (Phase 13.4)
CACHE_WARM_TOP_N_SOURCES: int = 10  # pre-warm top N source keys on startup

# ---------------------------------------------------------------------------
# Background workers (Pillar 5)
# ---------------------------------------------------------------------------
BACKGROUND_WORKER_COUNT_DEFAULT: int = 2
BACKGROUND_WORKER_QUEUE_SIZE_DEFAULT: int = 200
BACKGROUND_MAX_TRACKED_TASKS_DEFAULT: int = 500

# ---------------------------------------------------------------------------
# Notifications & emailing (Pillar 8)
# ---------------------------------------------------------------------------
NOTIFICATION_HTTP_TIMEOUT_SECONDS_DEFAULT: int = 5
NOTIFICATION_EVENT_BACKGROUND_TASK_FAILED: str = "background_task_failed"
NOTIFICATION_SEVERITY_INFO: str = "info"
NOTIFICATION_SEVERITY_WARNING: str = "warning"
NOTIFICATION_SEVERITY_CRITICAL: str = "critical"

# ---------------------------------------------------------------------------
# Vector search / AI gateway (Pillar 9)
# ---------------------------------------------------------------------------
VECTOR_SEARCH_MIN_RECORD_IDS: int = 1
VECTOR_SEARCH_MAX_RECORD_IDS: int = 100
VECTOR_SEARCH_DEFAULT_TOP_K: int = 5
VECTOR_SEARCH_MAX_TOP_K: int = 25
VECTOR_SEARCH_HTTP_TIMEOUT_SECONDS_DEFAULT: int = 10
VECTOR_SEARCH_DEFAULT_COLLECTION: str = "records"
# ---------------------------------------------------------------------------
# Scrapers (Phase 3)
# ---------------------------------------------------------------------------
SCRAPER_HTTP_TIMEOUT_SECONDS_DEFAULT: int = 30

# ---------------------------------------------------------------------------
# Abuse Detection (4.6)
# ---------------------------------------------------------------------------
# Signal types
ABUSE_SIGNAL_NOISY_SOURCE: str = "noisy_source"
ABUSE_SIGNAL_SUSPICIOUS_KEY: str = "suspicious_key"
ABUSE_SIGNAL_BURST_ABUSE: str = "burst_abuse"
ABUSE_SIGNAL_CREDENTIAL_STUFFING: str = "credential_stuffing"
ABUSE_SIGNAL_IP_ROTATION: str = "ip_rotation"

# Actor types
ABUSE_ACTOR_API_KEY: str = "api_key"
ABUSE_ACTOR_SOURCE_ID: str = "source_id"
ABUSE_ACTOR_IP_ADDRESS: str = "ip_address"
ABUSE_ACTOR_TENANT_ID: str = "tenant_id"

# Severity levels
ABUSE_SEVERITY_LOW: str = "low"
ABUSE_SEVERITY_MEDIUM: str = "medium"
ABUSE_SEVERITY_HIGH: str = "high"
ABUSE_SEVERITY_CRITICAL: str = "critical"

# Detection rules
ABUSE_RULE_QUOTA_EXCEEDED: str = "quota_exceeded"
ABUSE_RULE_AUTH_FAILURE_SPIKE: str = "auth_failure_spike"
ABUSE_RULE_MULTI_IP_KEY: str = "multi_ip_key"
ABUSE_RULE_ERROR_RATE_SPIKE: str = "error_rate_spike"
ABUSE_RULE_RAPID_ENUMERATION: str = "rapid_enumeration"

# Actions taken
ABUSE_ACTION_LOGGED: str = "logged"
ABUSE_ACTION_RATE_LIMITED: str = "rate_limited"
ABUSE_ACTION_BLOCKED: str = "blocked"
ABUSE_ACTION_ALERTED: str = "alerted"

# Detector thresholds
# Noisy source: emit signal when request_count > quota_per_minute * window_seconds/60 * multiplier
ABUSE_NOISY_SOURCE_MULTIPLIER_MEDIUM: float = 2.0  # 2× quota → medium
ABUSE_NOISY_SOURCE_MULTIPLIER_HIGH: float = 5.0  # 5× quota → high
ABUSE_NOISY_SOURCE_MULTIPLIER_CRITICAL: float = 10.0  # 10× quota → critical
ABUSE_NOISY_SOURCE_DEFAULT_QUOTA: int = 60  # fallback if SourceProfile has no quota

# Suspicious key: per-window thresholds
ABUSE_KEY_AUTH_FAILURE_THRESHOLD_MEDIUM: int = 5  # ≥5 auth failures → medium
ABUSE_KEY_AUTH_FAILURE_THRESHOLD_HIGH: int = 20  # ≥20 auth failures → high
ABUSE_KEY_DISTINCT_IP_THRESHOLD_MEDIUM: int = 5  # ≥5 distinct IPs in window → medium
ABUSE_KEY_DISTINCT_IP_THRESHOLD_HIGH: int = 10  # ≥10 distinct IPs → high
ABUSE_KEY_ERROR_RATE_THRESHOLD_MEDIUM: float = 0.5  # ≥50% error rate → medium
ABUSE_KEY_ERROR_RATE_THRESHOLD_HIGH: float = 0.9  # ≥90% error rate → high

# Field length caps
ABUSE_ACTOR_ID_MAX_LEN: int = 255
ABUSE_DETECTION_RULE_MAX_LEN: int = 64
ABUSE_ACTION_TAKEN_MAX_LEN: int = 32
ABUSE_IP_MAX_LEN: int = 64
ABUSE_NOTES_MAX_LEN: int = 1024

# ---------------------------------------------------------------------------
# Provider Scorecards (BI feature 7.1)
# ---------------------------------------------------------------------------
SCORECARD_DEFAULT_DAYS: int = 7
SCORECARD_MAX_DAYS: int = 90
SCORECARD_DEFAULT_LIMIT: int = 20
SCORECARD_DEFAULT_SLO_TARGET_PCT: float = 99.9  # 99.9% uptime SLO
SCORECARD_SLO_MIN_PCT: float = 90.0
SCORECARD_SLO_MAX_PCT: float = 100.0
HEALTH_SAMPLE_ERROR_MSG_MAX: int = 512
HEALTH_SAMPLE_REGION_MAX: int = 64
