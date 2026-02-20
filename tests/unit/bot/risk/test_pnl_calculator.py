"""
PnLCalculator 테스트

일일 손익 계산 테스트.
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from bot.risk.pnl_calculator import PnLCalculator
from core.domain.events import Event
from core.types import Scope


class TestPnLCalculatorGetDailyPnL:
    """PnLCalculator.get_daily_pnl() 테스트"""
    
    @pytest.fixture
    def mock_event_store(self) -> MagicMock:
        """Mock EventStore"""
        store = MagicMock()
        store.get_events_by_type = AsyncMock()
        return store
    
    @pytest.fixture
    def calculator(self, mock_event_store: MagicMock) -> PnLCalculator:
        """Calculator 픽스처"""
        return PnLCalculator(event_store=mock_event_store)
    
    def _create_trade_event(
        self,
        realized_pnl: str,
        exchange: str = "BINANCE",
        venue: str = "FUTURES",
        account_id: str = "default",
        mode: str = "TESTNET",
        symbol: str = "XRPUSDT",
    ) -> Event:
        """테스트용 TradeExecuted 이벤트 생성"""
        return Event(
            event_id="test-event-id",
            event_type="TradeExecuted",
            ts=datetime.now(timezone.utc),
            correlation_id="test-correlation",
            causation_id=None,
            command_id=None,
            source="EXCHANGE",
            entity_kind="TRADE",
            entity_id="trade-123",
            scope=Scope(
                exchange=exchange,
                venue=venue,
                account_id=account_id,
                symbol=symbol,
                mode=mode,
            ),
            dedup_key="test-dedup",
            payload={"realized_pnl": realized_pnl},
        )
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_no_events(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """이벤트 없음"""
        mock_event_store.get_events_by_type.return_value = []
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert pnl == Decimal("0")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_single_event(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """단일 이벤트"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.50"),
        ]
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert pnl == Decimal("10.50")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_multiple_events(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """여러 이벤트 합산"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.00"),
            self._create_trade_event("-5.50"),
            self._create_trade_event("3.25"),
        ]
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert pnl == Decimal("7.75")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_filters_by_scope(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """Scope 필터링"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.00", symbol="XRPUSDT"),
            self._create_trade_event("20.00", symbol="BTCUSDT"),  # 다른 심볼
            self._create_trade_event("5.00", exchange="OTHER"),   # 다른 거래소
        ]
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert pnl == Decimal("10.00")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_all_symbols(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """심볼 미지정 시 전체"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.00", symbol="XRPUSDT"),
            self._create_trade_event("20.00", symbol="BTCUSDT"),
        ]
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol=None,  # 전체
        )
        
        assert pnl == Decimal("30.00")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_handles_invalid_pnl(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """잘못된 PnL 값 처리"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.00"),
            self._create_trade_event("invalid"),  # 잘못된 값
            self._create_trade_event("5.00"),
        ]
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        # invalid는 무시되고 10 + 5 = 15
        assert pnl == Decimal("15.00")
    
    @pytest.mark.asyncio
    async def test_get_daily_pnl_error_returns_zero(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """에러 시 0 반환"""
        mock_event_store.get_events_by_type.side_effect = Exception("DB Error")
        
        pnl = await calculator.get_daily_pnl(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert pnl == Decimal("0")


class TestPnLCalculatorGetPnLSummary:
    """PnLCalculator.get_pnl_summary() 테스트"""
    
    @pytest.fixture
    def mock_event_store(self) -> MagicMock:
        store = MagicMock()
        store.get_events_by_type = AsyncMock()
        return store
    
    @pytest.fixture
    def calculator(self, mock_event_store: MagicMock) -> PnLCalculator:
        return PnLCalculator(event_store=mock_event_store)
    
    def _create_trade_event(self, realized_pnl: str) -> Event:
        return Event(
            event_id="test-event-id",
            event_type="TradeExecuted",
            ts=datetime.now(timezone.utc),
            correlation_id="test-correlation",
            causation_id=None,
            command_id=None,
            source="EXCHANGE",
            entity_kind="TRADE",
            entity_id="trade-123",
            scope=Scope(
                exchange="BINANCE",
                venue="FUTURES",
                account_id="default",
                symbol="XRPUSDT",
                mode="TESTNET",
            ),
            dedup_key="test-dedup",
            payload={"realized_pnl": realized_pnl},
        )
    
    @pytest.mark.asyncio
    async def test_get_pnl_summary(self, calculator: PnLCalculator, mock_event_store: MagicMock) -> None:
        """PnL 요약"""
        mock_event_store.get_events_by_type.return_value = [
            self._create_trade_event("10.00"),
            self._create_trade_event("-5.00"),
            self._create_trade_event("3.00"),
            self._create_trade_event("0"),  # 무승부
        ]
        
        summary = await calculator.get_pnl_summary(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="default",
            mode="TESTNET",
            symbol="XRPUSDT",
        )
        
        assert summary["daily_pnl"] == Decimal("8.00")
        assert summary["trade_count_today"] == 4
        assert summary["winning_trades_today"] == 2
        assert summary["losing_trades_today"] == 1
