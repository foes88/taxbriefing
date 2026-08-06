"""애플리케이션 설정.

비밀키는 환경변수 또는 Secret Manager에서만 읽는다 (§12.1 민감 운영정보: DB 저장 금지).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "docs" / "contracts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TAXBRIEFING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: str = "local"
    debug: bool = False

    database_url: str = "postgresql+psycopg://taxbriefing:taxbriefing@localhost:5432/taxbriefing"

    # 인증 (§12.3). 운영에서는 반드시 주입한다.
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    # 표시 시간대. 저장은 UTC, 표시는 Asia/Seoul (§8.1).
    display_timezone: str = "Asia/Seoul"

    # AI (§9.5). MVP 기본값은 stub — 실제 제공자 계정은 미결 항목 ⑨.
    ai_provider: str = "stub"
    ai_model: str = "stub-analysis-v1"
    ai_api_key: str | None = None
    ai_prompt_version: str = "1.0.0"

    # 국가법령정보 공동활용 OPEN API (부록 A, A등급 최우선 출처).
    # OC 는 신청 시 사용자가 직접 지정하는 식별자이며, 호출 URL의 ?OC= 값으로 들어간다.
    # URL에 노출되므로 비밀은 아니지만, 호출 한도가 이 값에 묶이므로 클라이언트에 두지 않는다.
    law_api_oc: str | None = None
    law_api_base_url: str = "https://www.law.go.kr/DRF"

    # 수집 SSRF 방어 (§12.3, AT-14).
    collector_max_redirects: int = 3
    collector_timeout_seconds: float = 20.0
    collector_allow_private_ips: bool = False

    # 멱등성 레코드 보존기간 (§NFR-005).
    idempotency_ttl_hours: int = 24

    contracts_dir: Path = Field(default=CONTRACTS_DIR)

    @field_validator("jwt_secret")
    @classmethod
    def _reject_weak_secret_outside_local(cls, v: str, info) -> str:
        env = (info.data or {}).get("environment", "local")
        if env in ("local", "test"):
            return v
        if v == "dev-only-insecure-secret-change-me":
            raise ValueError("TAXBRIEFING_JWT_SECRET must be set outside local/test")
        # HS256 은 32바이트 이상 키를 요구한다 (RFC 7518 §3.2).
        if len(v.encode("utf-8")) < 32:
            raise ValueError("TAXBRIEFING_JWT_SECRET must be at least 32 bytes for HS256")
        return v

    @property
    def ai_output_schema_path(self) -> Path:
        return self.contracts_dir / "ai_output_schema.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
