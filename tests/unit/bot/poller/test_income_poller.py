"""
IncomePoller 단위 테스트
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from bot.poller.income_poller import IncomePoller
from core.types import Scope


@pytest.fixture
def scope() -> Scope:
    """테스트용 Scope"""
    return Scope(
        exchange="BINANCE",
        venue="FUTURES",
        account_id="test_account",
        symbol="XRPUSDT",
        mode="testnet",
    )


@pytest.fixture
def mock_rest_client() -> AsyncMock:
    """Mock REST 클라이언트"""
    return AsyncMock()


@pytest.fixture
def mock_event_store() -> AsyncMock:
    """Mock 이벤트 저장소"""
    store = AsyncMock()
    store.append.return_value = True
    return store


@pytest.fixture
def mock_config_store() -> AsyncMock:
    """Mock 설정 저장소"""
    store = AsyncMock()
    store.get.return_value = None
    return store


class TestIncomePollerBasics:
    """IncomePoller 기본 테스트"""
    
    def test_poller_name(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """poller_name 확인"""
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        assert poller.poller_name == "income"
    
    def test_default_poll_interval(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """기본 폴링 간격 5분"""
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        assert poller.poll_interval_seconds == 300


class TestIncomePollerPoll:
    """poll() 테스트"""
    
    @pytest.mark.asyncio
    async def test_poll_creates_funding_event(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """FUNDING_FEE 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.01234567",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 3600000,
                "tranId": 123456,
                "tradeId": "",
            }
        ]
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 1
        mock_event_store.append.assert_called_once()
        
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == "FundingApplied"
        assert event.payload["funding_fee"] == "-0.01234567"
    
    @pytest.mark.asyncio
    async def test_poll_creates_rebate_event(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """COMMISSION_REBATE 이벤트 생성"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "COMMISSION_REBATE",
                "income": "0.005",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 1800000,
                "tranId": 654321,
                "tradeId": "",
            }
        ]
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 1
        
        event = mock_event_store.append.call_args[0][0]
        assert event.event_type == "CommissionRebateReceived"
        assert event.payload["rebate_amount"] == "0.005"
    
    @pytest.mark.asyncio
    async def test_poll_ignores_other_income_types(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """다른 income 타입은 무시"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "REALIZED_PNL",
                "income": "10.5",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 1800000,
                "tranId": 111111,
                "tradeId": "222222",
            }
        ]
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 0
        mock_event_store.append.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_poll_handles_empty_result(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """빈 결과 처리"""
        mock_rest_client.get_income_history.return_value = []
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 0


class TestIncomePollerDedup:
    """중복 방지 테스트"""
    
    @pytest.mark.asyncio
    async def test_dedup_prevents_duplicates(
        self,
        mock_rest_client: AsyncMock,
        mock_event_store: AsyncMock,
        mock_config_store: AsyncMock,
        scope: Scope,
    ) -> None:
        """중복 이벤트 저장 방지"""
        now = datetime.now(timezone.utc)
        
        mock_rest_client.get_income_history.return_value = [
            {
                "symbol": "XRPUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.01",
                "asset": "USDT",
                "info": "",
                "time": int(now.timestamp() * 1000) - 3600000,
                "tranId": 123456,
                "tradeId": "",
            }
        ]
        
        mock_event_store.append.return_value = False
        
        poller = IncomePoller(
            rest_client=mock_rest_client,
            event_store=mock_event_store,
            config_store=mock_config_store,
            scope=scope,
        )
        
        result = await poller.poll()
        
        assert result["events_created"] == 0
