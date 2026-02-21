"""JournalEntryBuilder 테스트"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.domain.events import Event, EventTypes
from core.ledger.entry_builder import JournalEntry, JournalEntryBuilder, JournalLine
from core.ledger.types import JournalSide, TransactionType
from core.types import Scope


class TestJournalLine:
    """JournalLine 테스트"""
    
    def test_create_debit_line(self) -> None:
        """Debit 라인 생성"""
        line = JournalLine(
            account_id="ASSET:BINANCE_FUTURES:BTC",
            side=JournalSide.DEBIT.value,
            amount=Decimal("0.001"),
            asset="BTC",
            usdt_value=Decimal("45"),
            usdt_rate=Decimal("45000"),
        )
        
        assert line.side == "DEBIT"
        assert line.amount == Decimal("0.001")
        assert line.usdt_value == Decimal("45")
    
    def test_create_credit_line(self) -> None:
        """Credit 라인 생성"""
        line = JournalLine(
            account_id="ASSET:BINANCE_FUTURES:USDT",
            side=JournalSide.CREDIT.value,
            amount=Decimal("45"),
            asset="USDT",
            usdt_value=Decimal("45"),
            usdt_rate=Decimal("1"),
        )
        
        assert line.side == "CREDIT"
        assert line.asset == "USDT"


class TestJournalEntry:
    """JournalEntry 테스트"""
    
    def test_balanced_entry(self) -> None:
        """균형 분개 검증"""
        entry = JournalEntry(
            entry_id="test-001",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:BTC",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("0.001"),
                    asset="BTC",
                    usdt_value=Decimal("45"),
                    usdt_rate=Decimal("45000"),
                ),
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("45"),
                    asset="USDT",
                    usdt_value=Decimal("45"),
                    usdt_rate=Decimal("1"),
                ),
            ],
        )
        
        assert entry.is_balanced() is True
    
    def test_unbalanced_entry(self) -> None:
        """불균형 분개 검증"""
        entry = JournalEntry(
            entry_id="test-002",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:BTC",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("0.001"),
                    asset="BTC",
                    usdt_value=Decimal("45"),
                    usdt_rate=Decimal("45000"),
                ),
                # Credit이 더 적음
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("40"),
                    asset="USDT",
                    usdt_value=Decimal("40"),
                    usdt_rate=Decimal("1"),
                ),
            ],
        )
        
        assert entry.is_balanced() is False
    
    def test_balanced_with_small_tolerance(self) -> None:
        """소액 오차 허용 (0.01 USDT 이내)"""
        entry = JournalEntry(
            entry_id="test-003",
            ts=datetime.now(timezone.utc),
            transaction_type=TransactionType.TRADE.value,
            scope_mode="testnet",
            lines=[
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:BTC",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("0.001"),
                    asset="BTC",
                    usdt_value=Decimal("45.005"),
                    usdt_rate=Decimal("45005"),
                ),
                JournalLine(
                    account_id="ASSET:BINANCE_FUTURES:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("45"),
                    asset="USDT",
                    usdt_value=Decimal("45"),
                    usdt_rate=Decimal("1"),
                ),
            ],
        )
        
        # 0.005 차이는 0.01 이내이므로 균형으로 간주
        assert entry.is_balanced() is True


class TestJournalEntryBuilderTradeExecuted:
    """TradeExecuted 분개 생성 테스트"""
    
    @pytest.fixture
    def mock_ledger_store(self) -> MagicMock:
        """Mock LedgerStore"""
        store = MagicMock()
        store.ensure_asset_account = AsyncMock(return_value="ASSET:BINANCE_FUTURES:BTC")
        return store
    
    @pytest.fixture
    def builder(self, mock_ledger_store: MagicMock) -> JournalEntryBuilder:
        """JournalEntryBuilder with mock store"""
        return JournalEntryBuilder(ledger_store=mock_ledger_store)
    
    @pytest.fixture
    def buy_trade_event(self) -> Event:
        """매수 체결 이벤트"""
        return Event(
            event_id="evt_001",
            event_type=EventTypes.TRADE_EXECUTED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_001",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="TRADE",
            entity_id="trade_001",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:BTCUSDT:trade:123",
            payload={
                "exchange_trade_id": "123",
                "exchange_order_id": "456",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "qty": "0.001",
                "price": "45000.00",
                "commission": "0.045",
                "commission_asset": "USDT",
                "realized_pnl": "0",
                "is_maker": False,
            },
        )
    
    @pytest.mark.asyncio
    async def test_buy_trade_creates_balanced_entry(
        self, builder: JournalEntryBuilder, buy_trade_event: Event
    ) -> None:
        """매수 체결 분개 균형 검증"""
        entry = await builder.from_event(buy_trade_event)
        
        assert entry is not None
        assert entry.is_balanced()
        assert entry.transaction_type == TransactionType.TRADE.value
        assert entry.symbol == "BTCUSDT"
    
    @pytest.mark.asyncio
    async def test_buy_trade_has_correct_lines(
        self, builder: JournalEntryBuilder, buy_trade_event: Event
    ) -> None:
        """매수 체결 분개 항목 검증"""
        entry = await builder.from_event(buy_trade_event)
        
        assert entry is not None
        
        # BTC 증가 (Debit)
        btc_debits = [
            line for line in entry.lines 
            if "BTC" in line.account_id and line.side == JournalSide.DEBIT.value
        ]
        assert len(btc_debits) == 1
        assert btc_debits[0].amount == Decimal("0.001")
        
        # USDT 감소 (Credit) - 거래 금액 + 수수료
        usdt_credits = [
            line for line in entry.lines 
            if "USDT" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        total_usdt_credit = sum(line.amount for line in usdt_credits)
        assert total_usdt_credit == Decimal("45.045")  # 45 + 0.045
    
    @pytest.fixture
    def sell_trade_event_with_pnl(self) -> Event:
        """매도 체결 + 실현손익 이벤트"""
        return Event(
            event_id="evt_002",
            event_type=EventTypes.TRADE_EXECUTED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_002",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="TRADE",
            entity_id="trade_002",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:BTCUSDT:trade:124",
            payload={
                "exchange_trade_id": "124",
                "exchange_order_id": "457",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "qty": "0.001",
                "price": "46000.00",
                "commission": "0.046",
                "commission_asset": "USDT",
                "realized_pnl": "10.00",
                "is_maker": True,
            },
        )
    
    @pytest.mark.asyncio
    async def test_sell_trade_with_pnl_creates_balanced_entry(
        self, builder: JournalEntryBuilder, sell_trade_event_with_pnl: Event
    ) -> None:
        """매도 체결 + 실현손익 분개 균형 검증"""
        entry = await builder.from_event(sell_trade_event_with_pnl)
        
        assert entry is not None
        assert entry.is_balanced()
        
        # 실현 손익 항목 확인
        pnl_lines = [line for line in entry.lines if "REALIZED_PNL" in line.account_id]
        assert len(pnl_lines) == 1
        assert pnl_lines[0].side == JournalSide.CREDIT.value  # 이익은 Credit
        assert pnl_lines[0].amount == Decimal("10.00")


class TestJournalEntryBuilderFunding:
    """Funding 분개 생성 테스트"""
    
    @pytest.fixture
    def builder(self) -> JournalEntryBuilder:
        return JournalEntryBuilder()
    
    @pytest.mark.asyncio
    async def test_funding_paid(self, builder: JournalEntryBuilder) -> None:
        """펀딩 지급 분개"""
        event = Event(
            event_id="evt_003",
            event_type=EventTypes.FUNDING_APPLIED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_003",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="FUNDING",
            entity_id="funding_001",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:BTCUSDT:funding:001",
            payload={
                "symbol": "BTCUSDT",
                "funding_fee": "0.50",  # 양수 = 지급
            },
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.is_balanced()
        assert entry.transaction_type == TransactionType.FEE_FUNDING.value
        
        # 비용 증가 (Debit)
        expense_lines = [line for line in entry.lines if "EXPENSE" in line.account_id]
        assert len(expense_lines) == 1
        assert expense_lines[0].side == JournalSide.DEBIT.value
    
    @pytest.mark.asyncio
    async def test_funding_received(self, builder: JournalEntryBuilder) -> None:
        """펀딩 수령 분개"""
        event = Event(
            event_id="evt_004",
            event_type=EventTypes.FUNDING_APPLIED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_004",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="FUNDING",
            entity_id="funding_002",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:BTCUSDT:funding:002",
            payload={
                "symbol": "BTCUSDT",
                "funding_fee": "-0.30",  # 음수 = 수령
            },
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.is_balanced()
        assert entry.transaction_type == TransactionType.FUNDING_RECEIVED.value
        
        # 수익 증가 (Credit)
        income_lines = [line for line in entry.lines if "INCOME" in line.account_id]
        assert len(income_lines) == 1
        assert income_lines[0].side == JournalSide.CREDIT.value


class TestJournalEntryBuilderFallback:
    """Fallback 핸들러 테스트"""
    
    @pytest.fixture
    def builder(self) -> JournalEntryBuilder:
        return JournalEntryBuilder()
    
    @pytest.mark.asyncio
    async def test_non_financial_event_returns_none(
        self, builder: JournalEntryBuilder
    ) -> None:
        """비금융 이벤트는 None 반환"""
        event = Event(
            event_id="evt_heartbeat",
            event_type="EngineStarted",  # 비금융 이벤트
            ts=datetime.now(timezone.utc),
            correlation_id="corr_hb",
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="engine_001",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="engine:started:001",
            payload={},
        )
        
        entry = await builder.from_event(event)
        
        # 비금융 이벤트는 무시
        assert entry is None
    
    @pytest.mark.asyncio
    async def test_unknown_financial_event_creates_suspense_entry(
        self, builder: JournalEntryBuilder
    ) -> None:
        """알 수 없는 금융 이벤트는 SUSPENSE 분개 생성"""
        event = Event(
            event_id="evt_unknown_001",
            event_type="SomeNewFinancialEvent",  # 알 수 없는 타입
            ts=datetime.now(timezone.utc),
            correlation_id="corr_unknown",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="UNKNOWN",
            entity_id="unknown_001",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:BTCUSDT:unknown:001",
            payload={"some_field": "some_value"},
        )
        
        entry = await builder.from_event(event)
        
        # Fallback으로 처리됨
        assert entry is not None
        assert entry.transaction_type == TransactionType.UNKNOWN.value
        
        # SUSPENSE 계정 사용
        suspense_lines = [line for line in entry.lines if "SUSPENSE" in line.account_id]
        assert len(suspense_lines) >= 1


class TestJournalEntryBuilderBalanceChanged:
    """BalanceChanged 범용 핸들러 테스트"""
    
    @pytest.fixture
    def mock_ledger_store(self) -> MagicMock:
        """Mock LedgerStore"""
        store = MagicMock()
        store.ensure_asset_account = AsyncMock(return_value="ASSET:BINANCE_FUTURES:USDT")
        return store
    
    @pytest.fixture
    def builder(self, mock_ledger_store: MagicMock) -> JournalEntryBuilder:
        return JournalEntryBuilder(ledger_store=mock_ledger_store)
    
    @pytest.mark.asyncio
    async def test_balance_increase_creates_adjustment(
        self, builder: JournalEntryBuilder
    ) -> None:
        """잔고 증가 - ADJUSTMENT 분개 생성"""
        event = Event(
            event_id="evt_balance_001",
            event_type=EventTypes.BALANCE_CHANGED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_balance",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="BALANCE",
            entity_id="balance_001",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:balance:001",
            payload={
                "asset": "USDT",
                "delta": "100.00",  # 증가
            },
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.transaction_type == TransactionType.ADJUSTMENT.value
        assert entry.is_balanced()
        
        # Asset 증가 (Debit)
        asset_debits = [
            line for line in entry.lines 
            if "ASSET" in line.account_id and line.side == JournalSide.DEBIT.value
        ]
        assert len(asset_debits) == 1
        assert asset_debits[0].amount == Decimal("100.00")
        
        # SUSPENSE 대응 (Credit)
        suspense_credits = [
            line for line in entry.lines 
            if "SUSPENSE" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        assert len(suspense_credits) == 1
    
    @pytest.mark.asyncio
    async def test_balance_decrease_creates_adjustment(
        self, builder: JournalEntryBuilder
    ) -> None:
        """잔고 감소 - ADJUSTMENT 분개 생성"""
        event = Event(
            event_id="evt_balance_002",
            event_type=EventTypes.BALANCE_CHANGED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_balance",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="BALANCE",
            entity_id="balance_002",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:balance:002",
            payload={
                "asset": "USDT",
                "delta": "-50.00",  # 감소
            },
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.transaction_type == TransactionType.ADJUSTMENT.value
        assert entry.is_balanced()
        
        # Asset 감소 (Credit)
        asset_credits = [
            line for line in entry.lines 
            if "ASSET" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        assert len(asset_credits) == 1
        assert asset_credits[0].amount == Decimal("50.00")
    
    @pytest.mark.asyncio
    async def test_balance_changed_without_delta_returns_none(
        self, builder: JournalEntryBuilder
    ) -> None:
        """delta 없는 BalanceChanged는 None 반환"""
        event = Event(
            event_id="evt_balance_003",
            event_type=EventTypes.BALANCE_CHANGED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_balance",
            causation_id=None,
            command_id=None,
            source="WEBSOCKET",
            entity_kind="BALANCE",
            entity_id="balance_003",
            scope=Scope.create(venue="FUTURES", mode="testnet"),
            dedup_key="BINANCE:FUTURES:balance:003",
            payload={
                "asset": "USDT",
                "free": "1000.00",
                "locked": "0",
                # delta 없음
            },
        )
        
        entry = await builder.from_event(event)
        
        # delta 없으면 처리 불가
        assert entry is None


class TestJournalEntryBuilderPriceCache:
    """가격 캐시 테스트"""
    
    def test_set_price(self) -> None:
        """가격 설정"""
        builder = JournalEntryBuilder()
        builder.set_price("BTCUSDT", Decimal("45000"))
        
        assert builder._price_cache["BTCUSDT"] == Decimal("45000")
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_for_usdt(self) -> None:
        """USDT 환율은 항상 1"""
        builder = JournalEntryBuilder()
        rate = await builder._get_usdt_rate("USDT", datetime.now(timezone.utc))
        
        assert rate == Decimal("1")
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_from_cache(self) -> None:
        """캐시에서 환율 조회"""
        builder = JournalEntryBuilder()
        builder.set_price("BTCUSDT", Decimal("45000"))
        
        rate = await builder._get_usdt_rate("BTC", datetime.now(timezone.utc))
        
        assert rate == Decimal("45000")
