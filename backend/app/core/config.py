from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database — shared Sira instance, isolated schema
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sira_db"
    database_schema: str = "exam_svc"

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    # Redis — shared instance, all keys prefixed exam:
    redis_url: str = "redis://localhost:6379/0"

    # Auth — validates JWTs issued by Sira (shared HS256 secret, no separate login)
    sira_jwt_secret: str = "change-in-production"
    jwt_algorithm: str = "HS256"

    # MinIO / S3 — shared instance, private exam-evidence bucket
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_exam_bucket: str = "exam-evidence"
    minio_use_ssl: bool = False

    # Claude API — exam service has its own key
    exam_anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    # Exam integrity
    exam_watermark_secret: str = "change-in-production"
    exam_evidence_retention_days: int = 2555  # 7 years

    # Generation limits (mirrors Sira's syllabus context budget)
    source_context_budget_chars: int = 400_000

    # Heartbeat / disconnection thresholds
    heartbeat_disconnected_threshold: int = 3
    session_reconnect_grace_period_seconds: int = 120

    # Feature flags
    enable_proctor_vision: bool = True
    debug: bool = False

    # Edge AI (E3-9)
    edge_ai_enabled: bool = False
    edge_sha256_verification: bool = True
    edge_skip_cloud_if_processed: bool = True
    celery_high_queue: str = "sira_exam_high"
    celery_low_queue: str = "sira_exam_low"

    # VLM config (E3-10)
    vlm_model_version: str = ""
    vlm_cdn_base: str = ""

    # Sentry (optional)
    sentry_dsn: str = ""

    # Service URLs
    frontend_url: str = "http://localhost:3001"


settings = Settings()
