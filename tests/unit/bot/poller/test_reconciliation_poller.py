"""
ReconciliationPoller 단위 테스트
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from bot.poller.reconciliation_poller import ReconciliationPoller
from core.types import Scope


class MockPosition:
    """get_position() 결과 Mock"""
    def __init__(self, position_amt: str):
        self.position_amt = position_amt


class MockConfigStore:
    """ConfigStore Mock"""
    def __init__(self):
        self._data = {}
    
    async def get(self, key: str):
        return self._data.get(key)
    
    async def set(self, key: str, value):
        self._data[key] = value


@pytest.fixture
def scope():
    return Scope.create(
        exchange="BINANCE",
        venue="FUTURES",
        symbol="XRPUSDT",
        mode="production",
    )


@pytest.fixture
def mock_rest_client():
    """Binance REST 클라이언트 Mock"""
    client = MagicMock()
    
    # 포지션 없음
    client.get_position = AsyncMock(return_value=MockPosition("0"))
    
    # FUTURES 잔고
    client.get_balances = AsyncMock(return_value=[])
    
    # SPOT 잔고
    client.get_spot_balances = AsyncMock(return_value={})
    
    return client


@pytest.fixture
def mock_event_store():
    """EventStore Mock"""
    store = MagicMock()
    store.append = AsyncMock(return_value=True)
    return store


@pytest.fixture
def mock_config_store():
    return MockConfigStore()


@pytest.fixture
async def mock_ledger_getter():
    """Ledger 잔고 조회 Mock"""
    async def getter():
        return {
            "FUTURES": {"USDT": Decimal("670.00")},
            "SPOT": {"USDT": Decimal("0.47")},
        }
    return getter


class TestReconciliationPoller:
    """ReconciliationPoller 테스트"""
    
    @pytest.mark.asyncio
    async def test_should_reconcile_first_time(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """첫 실행 시 정합 필요"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        assert poller._should_reconcile() is True
    
    @pytest.mark.asyncio
    async def test_should_not_reconcile_within_24h(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """24시간 이내면 정합 불필요"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        # 1시간 전에 정합 수행
        poller._last_reconciliation_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        assert poller._should_reconcile() is False
    
    @pytest.mark.asyncio
    async def test_should_reconcile_after_24h(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """24시간 경과 후 정합 필요"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        # 25시간 전에 정합 수행
        poller._last_reconciliation_time = datetime.now(timezone.utc) - timedelta(hours=25)
        
        assert poller._should_reconcile() is True
    
    @pytest.mark.asyncio
    async def test_skip_when_position_open(
        self,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """포지션 있으면 정합 건너뜀"""
        rest_client = MagicMock()
        rest_client.get_position = AsyncMock(return_value=MockPosition("100"))  # 포지션 있음
        rest_client.get_balances = AsyncMock(return_value=[])
        rest_client.get_spot_balances = AsyncMock(return_value={})
        
        poller = ReconciliationPoller(
            rest_client=rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        # 24시간 경과
        poller._last_reconciliation_time = datetime.now(timezone.utc) - timedelta(hours=25)
        
        # poll 실행
        result = await poller._do_poll(datetime.now(timezone.utc))
        
        # 포지션 있어서 0 반환 (정합 안 함)
        assert result == 0
    
    @pytest.mark.asyncio
    async def test_reconcile_when_no_position(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """포지션 없으면 정합 수행"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        # 24시간 경과
        poller._last_reconciliation_time = datetime.now(timezone.utc) - timedelta(hours=25)
        
        # poll 실행
        result = await poller._do_poll(datetime.now(timezone.utc))
        
        # 정합 수행됨 (차이 없으면 0이지만 정합 시도함)
        # 마지막 정합 시간이 업데이트됨
        assert poller._last_reconciliation_time is not None
        # 최근에 업데이트됐어야 함 (1분 이내)
        time_diff = datetime.now(timezone.utc) - poller._last_reconciliation_time
        assert time_diff.total_seconds() < 60
    
    @pytest.mark.asyncio
    async def test_has_open_position_true(
        self,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """포지션 수량 > 0이면 True"""
        rest_client = MagicMock()
        rest_client.get_position = AsyncMock(return_value=MockPosition("50.5"))
        
        poller = ReconciliationPoller(
            rest_client=rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        result = await poller._has_open_position()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_has_open_position_false(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """포지션 수량 = 0이면 False"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        result = await poller._has_open_position()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_has_open_position_negative_qty(
        self,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """음수 포지션(SHORT)도 포지션 있음"""
        rest_client = MagicMock()
        rest_client.get_position = AsyncMock(return_value=MockPosition("-100"))
        
        poller = ReconciliationPoller(
            rest_client=rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        result = await poller._has_open_position()
        assert result is True
    
    @pytest.mark.asyncio
    async def test_has_open_position_api_error_returns_true(
        self,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """API 에러 시 안전하게 True 반환"""
        rest_client = MagicMock()
        rest_client.get_position = AsyncMock(side_effect=Exception("API Error"))
        
        poller = ReconciliationPoller(
            rest_client=rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        result = await poller._has_open_position()
        # 에러 시 안전하게 포지션 있다고 가정
        assert result is True
    
    @pytest.mark.asyncio
    async def test_initialize_restores_last_reconciliation_time(
        self,
        mock_rest_client,
        mock_event_store,
        scope,
        mock_ledger_getter,
    ):
        """초기화 시 마지막 정합 시간 복구"""
        config_store = MockConfigStore()
        
        # 저장된 상태
        last_time = datetime.now(timezone.utc) - timedelta(hours=12)
        await config_store.set(
            "poller_reconciliation_last_reconciliation",
            {"last_reconciliation_time": last_time.isoformat()},
        )
        
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        await poller.initialize()
        
        assert poller._last_reconciliation_time is not None
        # 12시간 전이므로 정합 불필요
        assert poller._should_reconcile() is False
    
    @pytest.mark.asyncio
    async def test_poller_name(
        self,
        mock_rest_client,
        mock_event_store,
        mock_config_store,
        mock_ledger_getter,
        scope,
    ):
        """poller_name 확인"""
        poller = ReconciliationPoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
            ledger_balance_getter=mock_ledger_getter,
            target_symbol="XRPUSDT",
        )
        
        assert poller.poller_name == "reconciliation"
