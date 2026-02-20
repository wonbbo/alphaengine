"""
E2E 테스트 공통 fixture

Binance Testnet/Production에서 실제 API 호출을 위한 클라이언트, 설정, 로거 제공.
"""

import asyncio
import logging
import sys
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from core.config.loader import (
    ExchangeConfig,
    Secrets,
    load_secrets,
    get_exchange_config,
)
from core.types import TradingMode, WebSocketState
from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient


# 테스트용 상수
DEFAULT_SYMBOL = "XRPUSDT"
MIN_BALANCE_USDT = Decimal("10")  # 최소 필요 잔고

# 환경별 기본 주문 수량
TESTNET_QUANTITY = Decimal("5")   # Testnet: 5 XRP
PRODUCTION_QUANTITY = Decimal("1")  # Production: 1 XRP (최소 비용)


# -------------------------------------------------------------------------
# pytest 옵션 및 마커 등록
# -------------------------------------------------------------------------


def pytest_configure(config: Any) -> None:
    """pytest 마커 등록"""
    config.addinivalue_line(
        "markers",
        "e2e: E2E 테스트 (실제 API 호출)",
    )
    config.addinivalue_line(
        "markers",
        "slow: 느린 테스트 (재연결 등)",
    )
    config.addinivalue_line(
        "markers",
        "production_risky: Production에서 실제 자금 사용하는 위험한 테스트",
    )
    config.addinivalue_line(
        "markers",
        "readonly: 읽기 전용 테스트 (주문 없음)",
    )


def pytest_addoption(parser: Any) -> None:
    """pytest 커맨드라인 옵션 추가"""
    parser.addoption(
        "--e2e-log-dir",
        action="store",
        default=None,
        help="E2E 테스트 결과 로그 저장 경로",
    )
    parser.addoption(
        "--symbol",
        action="store",
        default=DEFAULT_SYMBOL,
        help="테스트 심볼 (기본: XRPUSDT)",
    )
    parser.addoption(
        "--production",
        action="store_true",
        default=False,
        help="Production 모드로 테스트 실행 (실제 자금 사용!)",
    )
    parser.addoption(
        "--quantity",
        action="store",
        type=str,
        default=None,
        help="테스트 주문 수량 (기본: testnet=5, production=1)",
    )
    parser.addoption(
        "--skip-confirmation",
        action="store_true",
        default=False,
        help="Production 테스트 실행 전 확인 스킵 (CI용)",
    )


# -------------------------------------------------------------------------
# Session-scoped fixtures (전체 테스트 세션 공유)
# -------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """세션 범위의 이벤트 루프"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def is_production_mode(request: Any) -> bool:
    """Production 모드 여부"""
    return request.config.getoption("--production")


@pytest.fixture(scope="session")
def secrets(request: Any, is_production_mode: bool) -> Secrets:
    """secrets.yaml 로드 (Testnet/Production 모두 지원)
    
    Raises:
        pytest.skip: 파일이 없거나 모드 불일치
    """
    try:
        loaded_secrets = load_secrets()
    except Exception as e:
        pytest.skip(f"secrets.yaml 로드 실패: {e}")
    
    if is_production_mode:
        # Production 테스트 요청
        if loaded_secrets.mode != TradingMode.PRODUCTION:
            pytest.skip(
                f"--production 옵션 사용 시 secrets.yaml도 production 모드여야 함 "
                f"(현재: {loaded_secrets.mode.value})"
            )
        
        # Production 확인 프롬프트
        skip_confirm = request.config.getoption("--skip-confirmation")
        if not skip_confirm:
            _confirm_production_test()
    else:
        # Testnet 테스트 (기본)
        if loaded_secrets.mode != TradingMode.TESTNET:
            pytest.skip(
                f"E2E 테스트는 기본적으로 testnet 모드에서 실행 "
                f"(현재: {loaded_secrets.mode.value}). "
                f"Production 테스트는 --production 옵션 필요."
            )
    
    return loaded_secrets


def _confirm_production_test() -> None:
    """Production 테스트 실행 전 확인"""
    print("\n" + "=" * 60)
    print("⚠️  WARNING: PRODUCTION 테스트 실행 ⚠️")
    print("=" * 60)
    print("이 테스트는 실제 자금을 사용합니다!")
    print("- 실제 주문이 체결됩니다")
    print("- 수수료가 발생합니다")
    print("- 포지션이 생성될 수 있습니다")
    print("=" * 60)
    
    try:
        response = input("계속하시겠습니까? (yes/no): ").strip().lower()
        if response != "yes":
            pytest.skip("사용자가 Production 테스트를 취소함")
    except EOFError:
        pytest.skip("Production 테스트 확인 불가 (--skip-confirmation 옵션 사용)")


# 하위 호환성을 위한 별칭
@pytest.fixture(scope="session")
def testnet_secrets(secrets: Secrets) -> Secrets:
    """하위 호환성: testnet_secrets -> secrets"""
    return secrets


@pytest.fixture(scope="session")
def exchange_config(secrets: Secrets) -> ExchangeConfig:
    """거래소 설정"""
    return get_exchange_config(secrets)


@pytest.fixture(scope="session")
def test_symbol(request: Any) -> str:
    """테스트 심볼"""
    return request.config.getoption("--symbol")


@pytest.fixture(scope="session")
def test_quantity(request: Any, is_production_mode: bool) -> Decimal:
    """테스트 주문 수량
    
    환경별 기본값:
    - Testnet: 5 XRP
    - Production: 1 XRP (최소 비용)
    
    --quantity 옵션으로 커스텀 수량 지정 가능.
    """
    custom_qty = request.config.getoption("--quantity")
    if custom_qty:
        return Decimal(custom_qty)
    
    return PRODUCTION_QUANTITY if is_production_mode else TESTNET_QUANTITY


@pytest.fixture(scope="session")
def log_dir(request: Any) -> Path | None:
    """E2E 로그 디렉토리"""
    log_path = request.config.getoption("--e2e-log-dir")
    if log_path:
        path = Path(log_path)
        path.mkdir(parents=True, exist_ok=True)
        return path
    return None


# -------------------------------------------------------------------------
# Function-scoped fixtures (테스트별 새 인스턴스)
# -------------------------------------------------------------------------


@pytest_asyncio.fixture
async def rest_client(
    exchange_config: ExchangeConfig,
) -> AsyncGenerator[BinanceRestClient, None]:
    """REST 클라이언트 (테스트별 새 인스턴스)
    
    테스트 완료 후 자동으로 close() 호출.
    """
    client = BinanceRestClient(
        base_url=exchange_config.rest_url,
        api_key=exchange_config.api_key,
        api_secret=exchange_config.api_secret,
        timeout=30.0,
        max_retries=3,
    )
    
    yield client
    
    await client.close()


@pytest_asyncio.fixture
async def ws_client(
    exchange_config: ExchangeConfig,
    rest_client: BinanceRestClient,
) -> AsyncGenerator[BinanceWsClient, None]:
    """WebSocket 클라이언트 (테스트별 새 인스턴스)
    
    테스트 완료 후 자동으로 stop() 호출.
    """
    # 수신된 메시지 저장
    received_messages: list[dict[str, Any]] = []
    state_changes: list[WebSocketState] = []
    
    async def on_message(msg: dict[str, Any]) -> None:
        received_messages.append(msg)
    
    async def on_state_change(state: WebSocketState) -> None:
        state_changes.append(state)
    
    client = BinanceWsClient(
        ws_base_url=exchange_config.ws_url,
        rest_client=rest_client,
        on_message=on_message,
        on_state_change=on_state_change,
    )
    
    # 메시지/상태 기록 접근용 속성 추가
    client._test_messages = received_messages  # type: ignore
    client._test_states = state_changes  # type: ignore
    
    yield client
    
    await client.stop()


# -------------------------------------------------------------------------
# Helper fixtures
# -------------------------------------------------------------------------


@pytest.fixture
def e2e_logger(request: Any, log_dir: Path | None) -> logging.Logger:
    """테스트별 로거
    
    콘솔과 파일(log_dir 지정 시)에 로그 출력.
    """
    from tests.e2e.utils.logger import setup_e2e_logger
    
    test_name = request.node.name
    return setup_e2e_logger(test_name, log_dir)


@pytest_asyncio.fixture
async def ensure_no_position(
    rest_client: BinanceRestClient,
    test_symbol: str,
) -> AsyncGenerator[None, None]:
    """테스트 전/후 포지션 정리
    
    테스트 시작 전과 종료 후 열린 포지션을 청산.
    """
    await _close_all_positions(rest_client, test_symbol)
    
    yield
    
    await _close_all_positions(rest_client, test_symbol)


@pytest_asyncio.fixture
async def ensure_no_orders(
    rest_client: BinanceRestClient,
    test_symbol: str,
) -> AsyncGenerator[None, None]:
    """테스트 전/후 주문 정리
    
    테스트 시작 전과 종료 후 열린 주문을 취소.
    """
    await rest_client.cancel_all_orders(test_symbol)
    
    yield
    
    await rest_client.cancel_all_orders(test_symbol)


@pytest_asyncio.fixture
async def check_balance(
    rest_client: BinanceRestClient,
) -> None:
    """USDT 잔고 확인
    
    최소 잔고 미만 시 테스트 스킵.
    """
    balances = await rest_client.get_balances()
    usdt_balance = next(
        (b for b in balances if b.asset == "USDT"),
        None,
    )
    
    if usdt_balance is None or usdt_balance.available_balance < MIN_BALANCE_USDT:
        pytest.skip(
            f"USDT 잔고 부족 (필요: {MIN_BALANCE_USDT}, "
            f"현재: {usdt_balance.available_balance if usdt_balance else 0})"
        )


# -------------------------------------------------------------------------
# 헬퍼 함수
# -------------------------------------------------------------------------


async def _close_all_positions(
    client: BinanceRestClient,
    symbol: str,
) -> None:
    """모든 포지션 청산"""
    from adapters.models import OrderRequest
    
    position = await client.get_position(symbol)
    
    if position is None or position.quantity == Decimal("0"):
        return
    
    # 포지션 반대 방향으로 시장가 주문
    side = "SELL" if position.is_long else "BUY"
    
    request = OrderRequest.market(
        symbol=symbol,
        side=side,
        quantity=position.quantity,
        reduce_only=True,
    )
    
    await client.place_order(request)
