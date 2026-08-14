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

    # 웹이 별도 호스트에 배포되므로 교차 출처 호출이 된다 (ADR-004).
    # 쉼표로 구분한 정확한 오리진만 허용한다 — 와일드카드는 쓰지 않는다.
    cors_origins: str = "http://localhost:3000,http://localhost:3100"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # AI (§9.5). 사용 가능: stub | groq
    #
    # 모델 기본값은 실측으로 정했다. 같은 법령(법인세법 시행규칙)으로 비교했을 때
    # llama-3.3-70b 는 이 시행규칙이 바꾸지 않은 조특법 내용을 바뀐 것처럼 요약했고,
    # gpt-oss-120b 는 실제 변경분(별지 서식 교체)을 정확히 짚고 모르는 항목은 비워 두었다.
    ai_provider: str = "stub"
    ai_model: str = "openai/gpt-oss-120b"
    ai_api_key: str | None = None
    # 프롬프트를 고치면 반드시 올린다. input_hash 에 프롬프트 버전이 들어가므로,
    # 올리지 않으면 저장된 옛 결과가 재사용되어 변경이 아무 효과도 내지 않는다 (§9.5).
    # 1.1.0 — 자구 정리·조문 번호 변경 같은 형식적 개정은 changes 에서 제외
    ai_prompt_version: str = "1.1.0"

    # 국가법령정보 공동활용 OPEN API (부록 A, A등급 최우선 출처).
    # OC 는 신청 시 사용자가 직접 지정하는 식별자이며, 호출 URL의 ?OC= 값으로 들어간다.
    # URL에 노출되므로 비밀은 아니지만, 호출 한도가 이 값에 묶이므로 클라이언트에 두지 않는다.
    law_api_oc: str | None = None
    law_api_base_url: str = "https://www.law.go.kr/DRF"

    # 네이버 검색 API (뉴스 탐지용, C/D 등급).
    # developers.naver.com 에서 애플리케이션을 등록하면 무료로 받는다.
    # 크롤링 대신 공식 API 를 쓰는 이유는 §3.4 — 우회는 구현하지 않는다.
    naver_client_id: str | None = None
    naver_client_secret: str | None = None

    # 열린국회정보 (open.assembly.go.kr). 법안 발의·상임위·본회의 단계를 본다.
    # 공포된 법령만 보면 이미 늦다 — 이게 "남보다 먼저"의 앞쪽 절반이다.
    assembly_api_key: str | None = None

    # 국민참여입법센터 (lawmaking.go.kr). **가장 이른 신호**다.
    #
    # 정부가 "이렇게 바꾸겠다" 고 내놓고 의견을 받는 40일이 여기 있다.
    # 공포된 뒤에 아는 사람과 예고 단계에서 아는 사람은 고객에게 할 말이
    # 다르다.
    #
    # 법제처 OC 와 **다른 계정**이다. 국민참여입법센터에 따로 가입하고
    # 정보공개 신청을 승인받아야 하며, 값은 그 계정 ID 의 @ 앞부분이다.
    lawmaking_oc: str | None = None

    # 텔레그램 발송 (ADR-001 — 알림 채널).
    # 비밀키는 DB 에 저장하지 않는다 (§12.1). 환경변수·.env 에서만 읽는다.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

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
