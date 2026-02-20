"""
BnbFeeManager 단위 테스트

BNB 자동 충전 로직 검증.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from bot.bnb_fee.manager import BnbFeeManager, MIN_BNB_ORDER_QTY
from adapters.models import Balance
from core.types import Scope


@pytest.fixture
def mock_scope() -> Scope:
    """테스트용 Scope"""
    return Scope(
        exchange="BINANCE",
        venue="FUTURES",
        account_id="test_account",
        symbol=None,
        mode="PRODUCTION",
    )


@pytest.fixture
def mock_binance() -> AsyncMock:
    """Mock Binance REST 클라이언트"""
    client = AsyncMock()
    client._time_synced = True
    return client


@pytest.fixture
def mock_config_store() -> AsyncMock:
    """Mock ConfigStore"""
    store = AsyncMock()
    store.get = AsyncMock(return_value={
        "enabled": True,
        "min_bnb_ratio": "0.01",
        "target_bnb_ratio": "0.02",
        "min_trigger_usdt": "10",
        "check_interval_sec": 3600,
    })
    return store


@pytest.fixture
def mock_event_store() -> AsyncMock:
    """Mock EventStore"""
    store = AsyncMock()
    store.append = AsyncMock(return_value=True)
    return store


@pytest.fixture
def bnb_fee_manager(
    mock_binance: AsyncMock,
    mock_config_store: AsyncMock,
    mock_event_store: AsyncMock,
    mock_scope: Scope,
) -> BnbFeeManager:
    """BnbFeeManager 인스턴스"""
    return BnbFeeManager(
        binance=mock_binance,
        config_store=mock_config_store,
        event_store=mock_event_store,
        scope=mock_scope,
        notifier_callback=None,
    )


class TestBnbFeeManagerShouldCheck:
    """체크 시점 판단 테스트"""
    
    @pytest.mark.asyncio
    async def test_should_check_when_interval_passed(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_config_store: AsyncMock,
    ) -> None:
        """체크 주기가 지나면 True 반환"""
        # check_interval_sec을 0으로 설정하여 항상 체크
        mock_config_store.get.return_value = {
            "enabled": True,
            "min_bnb_ratio": "0.01",
            "target_bnb_ratio": "0.02",
            "min_trigger_usdt": "10",
            "check_interval_sec": 0,  # 항상 체크
        }
        
        # 마지막 체크 시간을 오래 전으로 설정
        bnb_fee_manager._last_check_time = 0.0
        
        result = await bnb_fee_manager.should_check()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_should_not_check_when_disabled(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_config_store: AsyncMock,
    ) -> None:
        """기능 비활성화 시 False 반환"""
        mock_config_store.get.return_value = {"enabled": False}
        
        result = await bnb_fee_manager.should_check()
        
        assert result is False


class TestBnbFeeManagerCheckAndReplenish:
    """BNB 체크 및 충전 테스트"""
    
    @pytest.mark.asyncio
    async def test_no_replenish_when_disabled(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_config_store: AsyncMock,
    ) -> None:
        """기능 비활성화 시 충전 안 함"""
        mock_config_store.get.return_value = {"enabled": False}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_no_replenish_when_bnb_ratio_sufficient(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """BNB 비율이 충분하면 충전 안 함"""
        # Futures 잔고: BNB 2 (200 USDT), USDT 800 → 비율 20%
        mock_binance.get_balances.return_value = [
            Balance(
                asset="BNB",
                wallet_balance=Decimal("2"),
                available_balance=Decimal("2"),
                cross_wallet_balance=Decimal("2"),
                unrealized_pnl=Decimal("0"),
            ),
            Balance(
                asset="USDT",
                wallet_balance=Decimal("800"),
                available_balance=Decimal("800"),
                cross_wallet_balance=Decimal("800"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        # BNB 가격: 100 USDT
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        # 20% > 1% (min_ratio) → 충전 불필요
        assert result is False
        mock_binance.internal_transfer.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_replenish_from_spot_bnb(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """Spot BNB가 충분하면 이체만 수행"""
        # Futures 잔고: BNB 0, USDT 1000 → 비율 0%
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("1000"),
                available_balance=Decimal("1000"),
                cross_wallet_balance=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        # BNB 가격: 100 USDT
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        
        # Spot 잔고: BNB 1 (충분)
        mock_binance.get_spot_balances.return_value = {
            "BNB": {"free": "1", "locked": "0"},
        }
        
        mock_binance.internal_transfer.return_value = {"tranId": "123"}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is True
        
        # BNB 이체 호출 확인
        mock_binance.internal_transfer.assert_called()
        call_args = mock_binance.internal_transfer.call_args
        assert call_args.kwargs["asset"] == "BNB"
        assert call_args.kwargs["from_account"] == "SPOT"
        assert call_args.kwargs["to_account"] == "FUTURES"
    
    @pytest.mark.asyncio
    async def test_replenish_buy_bnb_with_spot_usdt(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """Spot USDT로 BNB 구매 후 이체"""
        # Futures 잔고: BNB 0, USDT 1000
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("1000"),
                available_balance=Decimal("1000"),
                cross_wallet_balance=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        # BNB 가격: 100 USDT
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        
        # Spot 잔고: BNB 없음, USDT 충분
        mock_binance.get_spot_balances.return_value = {
            "USDT": {"free": "100", "locked": "0"},
        }
        
        mock_binance.spot_market_buy.return_value = {
            "executedQty": "0.2",
            "cummulativeQuoteQty": "20.4",
        }
        
        mock_binance.internal_transfer.return_value = {"tranId": "123"}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is True
        
        # BNB 구매 호출 확인
        mock_binance.spot_market_buy.assert_called_once()
        buy_call = mock_binance.spot_market_buy.call_args
        assert buy_call.kwargs["symbol"] == "BNBUSDT"
        
        # BNB 이체 호출 확인
        mock_binance.internal_transfer.assert_called()
    
    @pytest.mark.asyncio
    async def test_replenish_transfer_usdt_from_futures_then_buy(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """Spot USDT 부족 시 Futures에서 이체 후 구매"""
        # Futures 잔고: BNB 0, USDT 1000
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("1000"),
                available_balance=Decimal("1000"),
                cross_wallet_balance=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        # BNB 가격: 100 USDT
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        
        # Spot 잔고: 없음
        mock_binance.get_spot_balances.return_value = {}
        
        mock_binance.spot_market_buy.return_value = {
            "executedQty": "0.2",
            "cummulativeQuoteQty": "20.4",
        }
        
        mock_binance.internal_transfer.return_value = {"tranId": "123"}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is True
        
        # Futures -> Spot USDT 이체 호출 확인
        transfer_calls = mock_binance.internal_transfer.call_args_list
        
        # 첫 번째 호출: USDT 이체 (Futures -> Spot)
        usdt_transfer_found = False
        for call in transfer_calls:
            if call.kwargs.get("asset") == "USDT" and call.kwargs.get("from_account") == "FUTURES":
                usdt_transfer_found = True
                break
        
        assert usdt_transfer_found, "USDT 이체 (Futures -> Spot) 호출 없음"
        
        # BNB 구매 호출 확인
        mock_binance.spot_market_buy.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_replenish_when_amount_too_small(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
        mock_config_store: AsyncMock,
    ) -> None:
        """필요 금액이 최소 트리거 미만이면 충전 안 함"""
        # min_trigger_usdt를 높게 설정
        mock_config_store.get.return_value = {
            "enabled": True,
            "min_bnb_ratio": "0.01",
            "target_bnb_ratio": "0.011",  # 목표를 최소와 비슷하게
            "min_trigger_usdt": "100",     # 높은 최소 트리거
            "check_interval_sec": 3600,
        }
        
        # Futures 잔고: 작은 금액
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("100"),
                available_balance=Decimal("100"),
                cross_wallet_balance=Decimal("100"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_no_replenish_when_already_in_progress(
        self,
        bnb_fee_manager: BnbFeeManager,
    ) -> None:
        """이미 충전 진행 중이면 중복 실행 방지"""
        bnb_fee_manager._replenish_in_progress = True
        
        result = await bnb_fee_manager.check_and_replenish()
        
        assert result is False


class TestBnbFeeManagerGetBnbPrice:
    """BNB 가격 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_bnb_price_success(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """BNB 가격 조회 성공"""
        mock_binance.get_ticker_price.return_value = {"price": "123.45"}
        
        price = await bnb_fee_manager._get_bnb_price()
        
        assert price == Decimal("123.45")
    
    @pytest.mark.asyncio
    async def test_get_bnb_price_failure(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
    ) -> None:
        """BNB 가격 조회 실패 시 0 반환"""
        mock_binance.get_ticker_price.side_effect = Exception("API Error")
        
        price = await bnb_fee_manager._get_bnb_price()
        
        assert price == Decimal("0")


class TestBnbFeeManagerStatus:
    """상태 조회 테스트"""
    
    def test_get_status(
        self,
        bnb_fee_manager: BnbFeeManager,
    ) -> None:
        """상태 정보 반환"""
        bnb_fee_manager._replenish_in_progress = False
        bnb_fee_manager._last_check_time = 12345.0
        
        status = bnb_fee_manager.get_status()
        
        assert status["replenish_in_progress"] is False
        assert status["last_check_time"] == 12345.0


class TestBnbFeeManagerForceCheck:
    """강제 체크 테스트"""
    
    @pytest.mark.asyncio
    async def test_force_check_resets_time(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
        mock_config_store: AsyncMock,
    ) -> None:
        """강제 체크 시 마지막 체크 시간 리셋"""
        mock_config_store.get.return_value = {"enabled": False}
        
        bnb_fee_manager._last_check_time = 999999.0
        
        await bnb_fee_manager.force_check()
        
        # 체크 시간이 리셋되어 check_and_replenish 호출됨
        # (enabled=False이므로 False 반환)
        assert bnb_fee_manager._last_check_time == 0.0


class TestBnbFeeManagerNotification:
    """알림 테스트"""
    
    @pytest.mark.asyncio
    async def test_notification_callback_called(
        self,
        mock_binance: AsyncMock,
        mock_config_store: AsyncMock,
        mock_event_store: AsyncMock,
        mock_scope: Scope,
    ) -> None:
        """충전 시 알림 콜백 호출"""
        notifier_callback = AsyncMock()
        
        manager = BnbFeeManager(
            binance=mock_binance,
            config_store=mock_config_store,
            event_store=mock_event_store,
            scope=mock_scope,
            notifier_callback=notifier_callback,
        )
        
        # Futures 잔고: BNB 0, USDT 1000
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("1000"),
                available_balance=Decimal("1000"),
                cross_wallet_balance=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        mock_binance.get_spot_balances.return_value = {
            "BNB": {"free": "1", "locked": "0"},
        }
        mock_binance.internal_transfer.return_value = {"tranId": "123"}
        
        await manager.check_and_replenish()
        
        # 알림 콜백 호출 확인
        assert notifier_callback.call_count >= 1


class TestBnbFeeManagerEvents:
    """이벤트 기록 테스트"""
    
    @pytest.mark.asyncio
    async def test_events_recorded_on_replenish(
        self,
        bnb_fee_manager: BnbFeeManager,
        mock_binance: AsyncMock,
        mock_event_store: AsyncMock,
    ) -> None:
        """충전 시 이벤트 기록"""
        # Futures 잔고: BNB 0, USDT 1000
        mock_binance.get_balances.return_value = [
            Balance(
                asset="USDT",
                wallet_balance=Decimal("1000"),
                available_balance=Decimal("1000"),
                cross_wallet_balance=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
            ),
        ]
        
        mock_binance.get_ticker_price.return_value = {"price": "100"}
        mock_binance.get_spot_balances.return_value = {
            "BNB": {"free": "1", "locked": "0"},
        }
        mock_binance.internal_transfer.return_value = {"tranId": "123"}
        
        await bnb_fee_manager.check_and_replenish()
        
        # 이벤트 기록 확인 (BnbBalanceLow, BnbReplenishStarted, BnbReplenishCompleted)
        assert mock_event_store.append.call_count >= 3
        
        # 이벤트 타입 확인
        event_types = [
            call.args[0].event_type
            for call in mock_event_store.append.call_args_list
        ]
        
        assert "BnbBalanceLow" in event_types
        assert "BnbReplenishStarted" in event_types
        assert "BnbReplenishCompleted" in event_types
