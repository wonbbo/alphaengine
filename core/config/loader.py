"""
설정 로더

secrets.yaml 로드 및 거래소 설정 생성
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from core.constants import BinanceEndpoints, Paths
from core.types import TradingMode


@dataclass(frozen=True)
class Secrets:
    """보안 설정 (secrets.yaml에서 로드)

    불변 데이터 구조로 설정 변경 방지
    """

    mode: TradingMode
    api_key: str
    api_secret: str
    web_secret_key: str


@dataclass(frozen=True)
class ExchangeConfig:
    """거래소 연결 설정

    API 키와 엔드포인트 정보를 포함
    """

    rest_url: str
    ws_url: str
    api_key: str
    api_secret: str


class SecretsLoadError(Exception):
    """Secrets 로드 실패 예외"""

    pass


def load_secrets(path: Path | None = None) -> Secrets:
    """secrets.yaml 파일 로드

    Args:
        path: secrets.yaml 경로 (None이면 기본 경로 사용)

    Returns:
        Secrets 인스턴스

    Raises:
        SecretsLoadError: 파일이 없거나 형식이 잘못된 경우
        ValueError: 유효하지 않은 mode인 경우
    """
    if path is None:
        path = Paths.SECRETS_FILE

    if not path.exists():
        raise SecretsLoadError(f"secrets.yaml 파일을 찾을 수 없습니다: {path}")

    try:
        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise SecretsLoadError(f"secrets.yaml 파싱 실패: {e}") from e

    if data is None:
        raise SecretsLoadError("secrets.yaml이 비어 있습니다")

    # mode 검증
    mode_str = data.get("mode")
    if mode_str is None:
        raise SecretsLoadError("secrets.yaml에 'mode' 필드가 없습니다")

    try:
        mode = TradingMode(mode_str)
    except ValueError as e:
        valid_modes = [m.value for m in TradingMode]
        raise ValueError(
            f"유효하지 않은 mode입니다: '{mode_str}'. "
            f"유효한 값: {valid_modes}"
        ) from e

    # 해당 모드의 API 키 로드
    mode_config = data.get(mode.value)
    if mode_config is None:
        raise SecretsLoadError(
            f"secrets.yaml에 '{mode.value}' 설정이 없습니다"
        )

    api_key = mode_config.get("api_key")
    api_secret = mode_config.get("api_secret")

    if not api_key:
        raise SecretsLoadError(
            f"secrets.yaml의 {mode.value} 섹션에 'api_key'가 없습니다"
        )
    if not api_secret:
        raise SecretsLoadError(
            f"secrets.yaml의 {mode.value} 섹션에 'api_secret'가 없습니다"
        )

    # Web secret key 로드
    web_config = data.get("web", {})
    web_secret_key = web_config.get("secret_key", "")

    if not web_secret_key:
        raise SecretsLoadError(
            "secrets.yaml의 web 섹션에 'secret_key'가 없습니다"
        )

    return Secrets(
        mode=mode,
        api_key=api_key,
        api_secret=api_secret,
        web_secret_key=web_secret_key,
    )


def get_exchange_config(secrets: Secrets) -> ExchangeConfig:
    """모드에 따른 거래소 설정 반환

    Args:
        secrets: Secrets 인스턴스

    Returns:
        ExchangeConfig 인스턴스 (Production 또는 Testnet)
    """
    if secrets.mode == TradingMode.PRODUCTION:
        return ExchangeConfig(
            rest_url=BinanceEndpoints.PROD_REST_URL,
            ws_url=BinanceEndpoints.PROD_WS_URL,
            api_key=secrets.api_key,
            api_secret=secrets.api_secret,
        )
    else:
        return ExchangeConfig(
            rest_url=BinanceEndpoints.TEST_REST_URL,
            ws_url=BinanceEndpoints.TEST_WS_URL,
            api_key=secrets.api_key,
            api_secret=secrets.api_secret,
        )


def get_db_path(secrets: Secrets) -> Path:
    """모드에 따른 DB 경로 반환

    Args:
        secrets: Secrets 인스턴스

    Returns:
        DB 파일 경로 (Path 타입)
    """
    if secrets.mode == TradingMode.PRODUCTION:
        return Paths.PROD_DB
    else:
        return Paths.TEST_DB


class Settings:
    """애플리케이션 설정 (싱글턴 패턴)

    secrets.yaml을 로드하고 관련 설정을 제공
    """

    _instance: "Settings | None" = None
    _secrets: Secrets | None = None

    def __new__(cls, secrets_path: Path | None = None) -> "Settings":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, secrets_path: Path | None = None) -> None:
        if self._secrets is None:
            self._secrets = load_secrets(secrets_path)

    @property
    def mode(self) -> TradingMode:
        """현재 거래 모드"""
        assert self._secrets is not None
        return self._secrets.mode

    @property
    def api_key(self) -> str:
        """API 키"""
        assert self._secrets is not None
        return self._secrets.api_key

    @property
    def api_secret(self) -> str:
        """API Secret"""
        assert self._secrets is not None
        return self._secrets.api_secret

    @property
    def web_secret_key(self) -> str:
        """Web JWT Secret Key"""
        assert self._secrets is not None
        return self._secrets.web_secret_key

    @property
    def exchange_config(self) -> ExchangeConfig:
        """현재 모드의 거래소 설정"""
        assert self._secrets is not None
        return get_exchange_config(self._secrets)

    @property
    def db_path(self) -> Path:
        """현재 모드의 DB 경로"""
        assert self._secrets is not None
        return get_db_path(self._secrets)

    @classmethod
    def reset(cls) -> None:
        """싱글턴 인스턴스 초기화 (테스트용)"""
        cls._instance = None
        cls._secrets = None


def get_settings(secrets_path: Path | None = None) -> Settings:
    """Settings 인스턴스 반환

    Args:
        secrets_path: secrets.yaml 경로 (None이면 기본 경로 사용)

    Returns:
        Settings 싱글턴 인스턴스
    """
    return Settings(secrets_path)
