"""
하드코딩 상수 - 변경될 일이 거의 없는 고정값

중요: 경로는 반드시 pathlib.Path 사용 (Windows/Linux 크로스 플랫폼)
"""

from pathlib import Path


# 프로젝트 루트 (이 파일 기준 2단계 상위: core/constants.py → alphaengine/)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent


class BinanceEndpoints:
    """Binance API 엔드포인트 (고정값)
    
    공식 문서: https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
    """

    # Production (USDT-M Futures)
    PROD_REST_URL: str = "https://fapi.binance.com"
    PROD_WS_URL: str = "wss://fstream.binance.com"

    # Testnet (USDT-M Futures)
    TEST_REST_URL: str = "https://demo-fapi.binance.com"
    TEST_WS_URL: str = "wss://fstream.binancefuture.com"


class Defaults:
    """기본값 상수"""

    EXCHANGE: str = "BINANCE"
    VENUE: str = "FUTURES"
    ACCOUNT_ID: str = "main"
    TIMEFRAME: str = "5m"

    WEB_HOST: str = "127.0.0.1"
    WEB_PORT: int = 8000

    LOG_LEVEL: str = "INFO"
    POLL_INTERVAL_SEC: int = 30


class Paths:
    """프로젝트 경로 상수 (pathlib 사용 - OS 독립적)"""

    # 디렉토리
    CONFIG_DIR: Path = PROJECT_ROOT / "config"
    DATA_DIR: Path = PROJECT_ROOT / "data"

    # 설정 파일
    SECRETS_FILE: Path = CONFIG_DIR / "secrets.yaml"

    # DB 파일
    PROD_DB: Path = DATA_DIR / "alphaengine_prod.db"
    TEST_DB: Path = DATA_DIR / "alphaengine_test.db"


class RateLimitThresholds:
    """Rate Limit 임계값"""

    WEIGHT_WARN: int = 1500  # 경고
    WEIGHT_SLOW: int = 2000  # 속도 저하
    WEIGHT_STOP: int = 2300  # 요청 중단
