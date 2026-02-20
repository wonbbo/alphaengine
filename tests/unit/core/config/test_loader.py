"""
core/config/loader.py 테스트

secrets.yaml 로드, 검증, 거래소 설정 생성 테스트
"""

from pathlib import Path

import pytest

from core.config.loader import (
    Secrets,
    ExchangeConfig,
    SecretsLoadError,
    load_secrets,
    get_exchange_config,
    get_db_path,
    Settings,
    get_settings,
)
from core.constants import BinanceEndpoints, Paths
from core.types import TradingMode


class TestSecrets:
    """Secrets 데이터클래스 테스트"""

    def test_creation(self) -> None:
        """기본 생성"""
        secrets = Secrets(
            mode=TradingMode.TESTNET,
            api_key="test_key",
            api_secret="test_secret",
            web_secret_key="jwt_secret",
        )

        assert secrets.mode == TradingMode.TESTNET
        assert secrets.api_key == "test_key"
        assert secrets.api_secret == "test_secret"
        assert secrets.web_secret_key == "jwt_secret"

    def test_frozen(self) -> None:
        """불변성 확인"""
        secrets = Secrets(
            mode=TradingMode.TESTNET,
            api_key="key",
            api_secret="secret",
            web_secret_key="jwt",
        )

        with pytest.raises(AttributeError):
            secrets.api_key = "new_key"  # type: ignore


class TestExchangeConfig:
    """ExchangeConfig 데이터클래스 테스트"""

    def test_creation(self) -> None:
        """기본 생성"""
        config = ExchangeConfig(
            rest_url="https://api.example.com",
            ws_url="wss://ws.example.com",
            api_key="key",
            api_secret="secret",
        )

        assert config.rest_url == "https://api.example.com"
        assert config.ws_url == "wss://ws.example.com"

    def test_frozen(self) -> None:
        """불변성 확인"""
        config = ExchangeConfig(
            rest_url="url",
            ws_url="ws",
            api_key="key",
            api_secret="secret",
        )

        with pytest.raises(AttributeError):
            config.rest_url = "new_url"  # type: ignore


class TestLoadSecrets:
    """load_secrets 함수 테스트"""

    def test_load_testnet(self, temp_secrets_file: Path) -> None:
        """Testnet 모드 로드"""
        secrets = load_secrets(temp_secrets_file)

        assert secrets.mode == TradingMode.TESTNET
        assert secrets.api_key == "test_api_key_abcde"
        assert secrets.api_secret == "test_api_secret_fghij"
        assert secrets.web_secret_key == "test_jwt_secret_key_xyz"

    def test_load_production(self, temp_secrets_file_production: Path) -> None:
        """Production 모드 로드"""
        secrets = load_secrets(temp_secrets_file_production)

        assert secrets.mode == TradingMode.PRODUCTION
        assert secrets.api_key == "prod_api_key_12345"
        assert secrets.api_secret == "prod_api_secret_67890"

    def test_file_not_found(self, temp_dir: Path) -> None:
        """파일 없음"""
        non_existent = temp_dir / "nonexistent.yaml"

        with pytest.raises(SecretsLoadError, match="찾을 수 없습니다"):
            load_secrets(non_existent)

    def test_invalid_mode(self, temp_secrets_file_invalid_mode: Path) -> None:
        """유효하지 않은 mode"""
        with pytest.raises(ValueError, match="유효하지 않은 mode"):
            load_secrets(temp_secrets_file_invalid_mode)

    def test_empty_file(self, temp_dir: Path) -> None:
        """빈 파일"""
        empty_file = temp_dir / "empty.yaml"
        empty_file.write_text("", encoding="utf-8")

        with pytest.raises(SecretsLoadError, match="비어 있습니다"):
            load_secrets(empty_file)

    def test_missing_mode(self, temp_dir: Path) -> None:
        """mode 필드 누락"""
        content = """
testnet:
  api_key: "key"
  api_secret: "secret"
web:
  secret_key: "jwt"
"""
        file = temp_dir / "no_mode.yaml"
        file.write_text(content, encoding="utf-8")

        with pytest.raises(SecretsLoadError, match="'mode' 필드가 없습니다"):
            load_secrets(file)

    def test_missing_api_key(self, temp_dir: Path) -> None:
        """api_key 누락"""
        content = """
mode: testnet
testnet:
  api_secret: "secret"
web:
  secret_key: "jwt"
"""
        file = temp_dir / "no_api_key.yaml"
        file.write_text(content, encoding="utf-8")

        with pytest.raises(SecretsLoadError, match="'api_key'가 없습니다"):
            load_secrets(file)

    def test_missing_web_secret(self, temp_dir: Path) -> None:
        """web secret_key 누락"""
        content = """
mode: testnet
testnet:
  api_key: "key"
  api_secret: "secret"
"""
        file = temp_dir / "no_web_secret.yaml"
        file.write_text(content, encoding="utf-8")

        with pytest.raises(SecretsLoadError, match="'secret_key'가 없습니다"):
            load_secrets(file)

    def test_invalid_yaml(self, temp_dir: Path) -> None:
        """잘못된 YAML 형식"""
        file = temp_dir / "invalid.yaml"
        file.write_text("invalid: yaml: content:", encoding="utf-8")

        with pytest.raises(SecretsLoadError, match="파싱 실패"):
            load_secrets(file)


class TestGetExchangeConfig:
    """get_exchange_config 함수 테스트"""

    def test_testnet_config(self) -> None:
        """Testnet 설정"""
        secrets = Secrets(
            mode=TradingMode.TESTNET,
            api_key="test_key",
            api_secret="test_secret",
            web_secret_key="jwt",
        )

        config = get_exchange_config(secrets)

        assert config.rest_url == BinanceEndpoints.TEST_REST_URL
        assert config.ws_url == BinanceEndpoints.TEST_WS_URL
        assert config.api_key == "test_key"
        assert config.api_secret == "test_secret"

    def test_production_config(self) -> None:
        """Production 설정"""
        secrets = Secrets(
            mode=TradingMode.PRODUCTION,
            api_key="prod_key",
            api_secret="prod_secret",
            web_secret_key="jwt",
        )

        config = get_exchange_config(secrets)

        assert config.rest_url == BinanceEndpoints.PROD_REST_URL
        assert config.ws_url == BinanceEndpoints.PROD_WS_URL
        assert config.api_key == "prod_key"
        assert config.api_secret == "prod_secret"


class TestGetDbPath:
    """get_db_path 함수 테스트"""

    def test_testnet_db(self) -> None:
        """Testnet DB 경로"""
        secrets = Secrets(
            mode=TradingMode.TESTNET,
            api_key="key",
            api_secret="secret",
            web_secret_key="jwt",
        )

        db_path = get_db_path(secrets)

        assert db_path == Paths.TEST_DB
        assert isinstance(db_path, Path)

    def test_production_db(self) -> None:
        """Production DB 경로"""
        secrets = Secrets(
            mode=TradingMode.PRODUCTION,
            api_key="key",
            api_secret="secret",
            web_secret_key="jwt",
        )

        db_path = get_db_path(secrets)

        assert db_path == Paths.PROD_DB
        assert isinstance(db_path, Path)


class TestSettings:
    """Settings 클래스 테스트"""

    def setup_method(self) -> None:
        """각 테스트 전에 싱글턴 초기화"""
        Settings.reset()

    def test_creation(self, temp_secrets_file: Path) -> None:
        """기본 생성"""
        settings = Settings(temp_secrets_file)

        assert settings.mode == TradingMode.TESTNET
        assert settings.api_key == "test_api_key_abcde"

    def test_singleton(self, temp_secrets_file: Path) -> None:
        """싱글턴 확인"""
        settings1 = Settings(temp_secrets_file)
        settings2 = Settings()  # 경로 없이 호출

        assert settings1 is settings2

    def test_properties(self, temp_secrets_file: Path) -> None:
        """프로퍼티 확인"""
        settings = Settings(temp_secrets_file)

        assert isinstance(settings.mode, TradingMode)
        assert isinstance(settings.api_key, str)
        assert isinstance(settings.api_secret, str)
        assert isinstance(settings.web_secret_key, str)
        assert isinstance(settings.exchange_config, ExchangeConfig)
        assert isinstance(settings.db_path, Path)

    def test_exchange_config(self, temp_secrets_file: Path) -> None:
        """거래소 설정"""
        settings = Settings(temp_secrets_file)
        config = settings.exchange_config

        assert config.rest_url == BinanceEndpoints.TEST_REST_URL
        assert config.ws_url == BinanceEndpoints.TEST_WS_URL

    def test_db_path(self, temp_secrets_file: Path) -> None:
        """DB 경로"""
        settings = Settings(temp_secrets_file)

        assert settings.db_path == Paths.TEST_DB

    def test_reset(self, temp_secrets_file: Path) -> None:
        """reset 후 재생성"""
        settings1 = Settings(temp_secrets_file)
        Settings.reset()
        settings2 = Settings(temp_secrets_file)

        # reset 후에는 새 인스턴스
        assert settings1 is not settings2


class TestGetSettings:
    """get_settings 함수 테스트"""

    def setup_method(self) -> None:
        """각 테스트 전에 싱글턴 초기화"""
        Settings.reset()

    def test_returns_settings(self, temp_secrets_file: Path) -> None:
        """Settings 인스턴스 반환"""
        settings = get_settings(temp_secrets_file)

        assert isinstance(settings, Settings)
        assert settings.mode == TradingMode.TESTNET

    def test_singleton_via_function(self, temp_secrets_file: Path) -> None:
        """함수를 통한 싱글턴 확인"""
        settings1 = get_settings(temp_secrets_file)
        settings2 = get_settings()

        assert settings1 is settings2
