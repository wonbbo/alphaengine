"""
core/constants.py 테스트

모든 경로가 pathlib.Path 타입이고, 상수가 정상적으로 접근 가능한지 확인
"""

from pathlib import Path

from core.constants import (
    PROJECT_ROOT,
    BinanceEndpoints,
    Defaults,
    Paths,
    RateLimitThresholds,
)


class TestProjectRoot:
    """PROJECT_ROOT 테스트"""

    def test_project_root_is_path(self) -> None:
        """PROJECT_ROOT가 Path 타입인지 확인"""
        assert isinstance(PROJECT_ROOT, Path)

    def test_project_root_is_absolute(self) -> None:
        """PROJECT_ROOT가 절대 경로인지 확인"""
        assert PROJECT_ROOT.is_absolute()

    def test_project_root_contains_core_directory(self) -> None:
        """PROJECT_ROOT에 core 디렉토리가 있는지 확인"""
        core_dir = PROJECT_ROOT / "core"
        assert core_dir.exists()


class TestBinanceEndpoints:
    """BinanceEndpoints 테스트"""

    def test_production_rest_url(self) -> None:
        """Production REST URL 확인"""
        assert BinanceEndpoints.PROD_REST_URL == "https://fapi.binance.com"

    def test_production_ws_url(self) -> None:
        """Production WebSocket URL 확인"""
        assert BinanceEndpoints.PROD_WS_URL == "wss://fstream.binance.com"

    def test_testnet_rest_url(self) -> None:
        """Testnet REST URL 확인"""
        assert BinanceEndpoints.TEST_REST_URL == "https://testnet.binancefuture.com"

    def test_testnet_ws_url(self) -> None:
        """Testnet WebSocket URL 확인"""
        assert BinanceEndpoints.TEST_WS_URL == "wss://stream.binancefuture.com"

    def test_urls_are_strings(self) -> None:
        """모든 URL이 문자열인지 확인"""
        assert isinstance(BinanceEndpoints.PROD_REST_URL, str)
        assert isinstance(BinanceEndpoints.PROD_WS_URL, str)
        assert isinstance(BinanceEndpoints.TEST_REST_URL, str)
        assert isinstance(BinanceEndpoints.TEST_WS_URL, str)


class TestDefaults:
    """Defaults 테스트"""

    def test_exchange_default(self) -> None:
        """기본 거래소 확인"""
        assert Defaults.EXCHANGE == "BINANCE"

    def test_venue_default(self) -> None:
        """기본 거래 장소 확인"""
        assert Defaults.VENUE == "FUTURES"

    def test_account_id_default(self) -> None:
        """기본 계좌 ID 확인"""
        assert Defaults.ACCOUNT_ID == "main"

    def test_timeframe_default(self) -> None:
        """기본 타임프레임 확인"""
        assert Defaults.TIMEFRAME == "5m"

    def test_web_host_default(self) -> None:
        """기본 웹 호스트 확인"""
        assert Defaults.WEB_HOST == "127.0.0.1"

    def test_web_port_default(self) -> None:
        """기본 웹 포트 확인"""
        assert Defaults.WEB_PORT == 8000
        assert isinstance(Defaults.WEB_PORT, int)

    def test_log_level_default(self) -> None:
        """기본 로그 레벨 확인"""
        assert Defaults.LOG_LEVEL == "INFO"

    def test_poll_interval_default(self) -> None:
        """기본 폴링 간격 확인"""
        assert Defaults.POLL_INTERVAL_SEC == 30
        assert isinstance(Defaults.POLL_INTERVAL_SEC, int)


class TestPaths:
    """Paths 테스트"""

    def test_config_dir_is_path(self) -> None:
        """CONFIG_DIR이 Path 타입인지 확인"""
        assert isinstance(Paths.CONFIG_DIR, Path)

    def test_data_dir_is_path(self) -> None:
        """DATA_DIR이 Path 타입인지 확인"""
        assert isinstance(Paths.DATA_DIR, Path)

    def test_secrets_file_is_path(self) -> None:
        """SECRETS_FILE이 Path 타입인지 확인"""
        assert isinstance(Paths.SECRETS_FILE, Path)

    def test_prod_db_is_path(self) -> None:
        """PROD_DB가 Path 타입인지 확인"""
        assert isinstance(Paths.PROD_DB, Path)

    def test_test_db_is_path(self) -> None:
        """TEST_DB가 Path 타입인지 확인"""
        assert isinstance(Paths.TEST_DB, Path)

    def test_config_dir_under_project_root(self) -> None:
        """CONFIG_DIR이 PROJECT_ROOT 하위인지 확인"""
        assert Paths.CONFIG_DIR == PROJECT_ROOT / "config"

    def test_data_dir_under_project_root(self) -> None:
        """DATA_DIR이 PROJECT_ROOT 하위인지 확인"""
        assert Paths.DATA_DIR == PROJECT_ROOT / "data"

    def test_secrets_file_under_config_dir(self) -> None:
        """SECRETS_FILE이 CONFIG_DIR 하위인지 확인"""
        assert Paths.SECRETS_FILE == Paths.CONFIG_DIR / "secrets.yaml"

    def test_prod_db_under_data_dir(self) -> None:
        """PROD_DB가 DATA_DIR 하위인지 확인"""
        assert Paths.PROD_DB == Paths.DATA_DIR / "alphaengine_prod.db"

    def test_test_db_under_data_dir(self) -> None:
        """TEST_DB가 DATA_DIR 하위인지 확인"""
        assert Paths.TEST_DB == Paths.DATA_DIR / "alphaengine_test.db"


class TestRateLimitThresholds:
    """RateLimitThresholds 테스트"""

    def test_weight_warn(self) -> None:
        """경고 임계값 확인"""
        assert RateLimitThresholds.WEIGHT_WARN == 1500
        assert isinstance(RateLimitThresholds.WEIGHT_WARN, int)

    def test_weight_slow(self) -> None:
        """속도 저하 임계값 확인"""
        assert RateLimitThresholds.WEIGHT_SLOW == 2000
        assert isinstance(RateLimitThresholds.WEIGHT_SLOW, int)

    def test_weight_stop(self) -> None:
        """요청 중단 임계값 확인"""
        assert RateLimitThresholds.WEIGHT_STOP == 2300
        assert isinstance(RateLimitThresholds.WEIGHT_STOP, int)

    def test_thresholds_increasing_order(self) -> None:
        """임계값이 증가 순서인지 확인"""
        assert (
            RateLimitThresholds.WEIGHT_WARN
            < RateLimitThresholds.WEIGHT_SLOW
            < RateLimitThresholds.WEIGHT_STOP
        )
