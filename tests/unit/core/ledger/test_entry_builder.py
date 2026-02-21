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


class TestJournalEntryBuilderDustConverted:
    """DustConverted 분개 생성 테스트"""
    
    @pytest.fixture
    def mock_ledger_store(self) -> MagicMock:
        """Mock LedgerStore"""
        store = MagicMock()
        store.ensure_asset_account = AsyncMock(return_value="ASSET:BINANCE_SPOT:BNB")
        return store
    
    @pytest.fixture
    def builder(self, mock_ledger_store: MagicMock) -> JournalEntryBuilder:
        """JournalEntryBuilder with mock store and BNB price cache"""
        builder = JournalEntryBuilder(ledger_store=mock_ledger_store)
        # BNB 가격 캐시 설정 (환율 조회 실패 방지)
        builder.set_price("BNBUSDT", Decimal("600"))
        return builder
    
    @pytest.fixture
    def dust_converted_event(self) -> Event:
        """Dust 전환 이벤트 (USDT → BNB)"""
        return Event(
            event_id="evt_dust_001",
            event_type=EventTypes.DUST_CONVERTED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_dust",
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="DUST",
            entity_id="308145879259",
            scope=Scope.create(venue="SPOT", mode="PRODUCTION"),
            dedup_key="BINANCE:dust:308145879259",
            payload={
                "trans_id": "308145879259",
                "operate_time": 1760140871000,
                "total_transferred_amount": "0.00093607",
                "total_service_charge": "0.00001872",
                "from_assets": ["USDT"],
                "details": [
                    {
                        "fromAsset": "USDT",
                        "amount": "1.03289826",
                        "transferedAmount": "0.00093607",
                        "serviceChargeAmount": "0.00001872",
                        "operateTime": 1760140871000,
                        "transId": 308145879259,
                        "targetAsset": "BNB",
                    }
                ],
                "source": "backfill",
            },
        )
    
    @pytest.mark.asyncio
    async def test_dust_converted_creates_balanced_entry(
        self, builder: JournalEntryBuilder, dust_converted_event: Event
    ) -> None:
        """Dust 전환 분개 균형 검증"""
        entry = await builder.from_event(dust_converted_event)
        
        assert entry is not None
        assert entry.is_balanced()
        assert entry.transaction_type == "OTHER"
    
    @pytest.mark.asyncio
    async def test_dust_converted_has_correct_lines(
        self, builder: JournalEntryBuilder, dust_converted_event: Event
    ) -> None:
        """Dust 전환 분개 항목 검증"""
        entry = await builder.from_event(dust_converted_event)
        
        assert entry is not None
        
        # USDT 감소 (Credit)
        usdt_credits = [
            line for line in entry.lines 
            if ":USDT" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        assert len(usdt_credits) == 1
        assert usdt_credits[0].amount == Decimal("1.03289826")
        
        # BNB 증가 (Debit) - 순액 (수수료 제외)
        bnb_debits = [
            line for line in entry.lines 
            if ":BNB" in line.account_id and line.side == JournalSide.DEBIT.value
        ]
        assert len(bnb_debits) == 1
        # 순액 = 0.00093607 BNB
        assert bnb_debits[0].amount == Decimal("0.00093607")
        
        # 수수료 비용 (Debit)
        fee_debits = [
            line for line in entry.lines 
            if "EXPENSE:FEE:DUST_CONVERSION" in line.account_id
        ]
        assert len(fee_debits) == 1
        assert fee_debits[0].amount == Decimal("0.00001872")
        
        # 전환 손실 (Debit) - 불리한 환율로 인한 손실
        loss_debits = [
            line for line in entry.lines 
            if "EXPENSE:CONVERSION_LOSS" in line.account_id
        ]
        assert len(loss_debits) == 1
        # 손실 = 1.03289826 USDT - (0.00093607 * 600 + 0.00001872 * 600)
        #      = 1.03289826 - 0.56164200 - 0.01123200
        #      = 0.46002426 USDT
        assert loss_debits[0].usdt_value > Decimal("0")
    
    @pytest.fixture
    def dust_converted_multi_asset_event(self) -> Event:
        """여러 자산 Dust 전환 이벤트"""
        return Event(
            event_id="evt_dust_002",
            event_type=EventTypes.DUST_CONVERTED,
            ts=datetime.now(timezone.utc),
            correlation_id="corr_dust_multi",
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="DUST",
            entity_id="308145879260",
            scope=Scope.create(venue="SPOT", mode="PRODUCTION"),
            dedup_key="BINANCE:dust:308145879260",
            payload={
                "trans_id": "308145879260",
                "operate_time": 1760140871000,
                "total_transferred_amount": "0.002",
                "total_service_charge": "0.00004",
                "from_assets": ["USDT", "USDC"],
                "details": [
                    {
                        "fromAsset": "USDT",
                        "amount": "0.5",
                        "transferedAmount": "0.001",
                        "serviceChargeAmount": "0.00002",
                        "targetAsset": "BNB",
                    },
                    {
                        "fromAsset": "USDC",
                        "amount": "0.5",
                        "transferedAmount": "0.001",
                        "serviceChargeAmount": "0.00002",
                        "targetAsset": "BNB",
                    },
                ],
                "source": "backfill",
            },
        )
    
    @pytest.mark.asyncio
    async def test_dust_converted_multi_asset(
        self, builder: JournalEntryBuilder, dust_converted_multi_asset_event: Event
    ) -> None:
        """여러 자산 Dust 전환 분개"""
        entry = await builder.from_event(dust_converted_multi_asset_event)
        
        assert entry is not None
        assert entry.is_balanced()
        
        # USDT, USDC 각각 Credit
        usdt_credits = [
            line for line in entry.lines 
            if ":USDT" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        usdc_credits = [
            line for line in entry.lines 
            if ":USDC" in line.account_id and line.side == JournalSide.CREDIT.value
        ]
        
        assert len(usdt_credits) == 1
        assert usdt_credits[0].amount == Decimal("0.5")
        
        assert len(usdc_credits) == 1
        assert usdc_credits[0].amount == Decimal("0.5")


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


class TestJournalEntryBuilderHistoricalPricing:
    """과거 환율 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_from_rest_client(self) -> None:
        """REST 클라이언트로 과거 환율 조회"""
        from unittest.mock import AsyncMock
        
        mock_rest_client = AsyncMock()
        mock_rest_client.get_klines.return_value = [
            {"close": "550.25"}
        ]
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        
        ts = datetime.now(timezone.utc)
        rate = await builder._get_usdt_rate("BNB", ts)
        
        assert rate == Decimal("550.25")
        mock_rest_client.get_klines.assert_called_once()
        
        call_args = mock_rest_client.get_klines.call_args
        assert call_args.kwargs["symbol"] == "BNBUSDT"
        assert call_args.kwargs["interval"] == "1m"
        assert call_args.kwargs["limit"] == 1
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_caches_historical_price(self) -> None:
        """과거 환율 조회 결과가 캐시에 저장됨"""
        from unittest.mock import AsyncMock
        
        mock_rest_client = AsyncMock()
        mock_rest_client.get_klines.return_value = [
            {"close": "42000.00"}
        ]
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        
        ts = datetime.now(timezone.utc)
        
        rate1 = await builder._get_usdt_rate("BTC", ts)
        rate2 = await builder._get_usdt_rate("BTC", ts)
        
        assert rate1 == Decimal("42000.00")
        assert rate2 == Decimal("42000.00")
        
        assert mock_rest_client.get_klines.call_count == 1
        assert "BTCUSDT" in builder._price_cache
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_prefers_cache_over_api(self) -> None:
        """캐시가 있으면 API 호출 안함"""
        from unittest.mock import AsyncMock
        
        mock_rest_client = AsyncMock()
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        builder.set_price("ETHUSDT", Decimal("3500.00"))
        
        ts = datetime.now(timezone.utc)
        rate = await builder._get_usdt_rate("ETH", ts)
        
        assert rate == Decimal("3500.00")
        mock_rest_client.get_klines.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_fallback_on_api_error(self) -> None:
        """API 에러 시 기본값 1 반환"""
        from unittest.mock import AsyncMock
        
        mock_rest_client = AsyncMock()
        mock_rest_client.get_klines.side_effect = Exception("API Error")
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        
        ts = datetime.now(timezone.utc)
        rate = await builder._get_usdt_rate("BNB", ts)
        
        assert rate == Decimal("1")
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_fallback_on_empty_result(self) -> None:
        """API 결과가 비어있으면 기본값 1 반환"""
        from unittest.mock import AsyncMock
        
        mock_rest_client = AsyncMock()
        mock_rest_client.get_klines.return_value = []
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        
        ts = datetime.now(timezone.utc)
        rate = await builder._get_usdt_rate("DOGE", ts)
        
        assert rate == Decimal("1")
    
    @pytest.mark.asyncio
    async def test_get_usdt_rate_without_rest_client(self) -> None:
        """REST 클라이언트 없이 캐시 미스 시 기본값 1 반환"""
        builder = JournalEntryBuilder()
        
        ts = datetime.now(timezone.utc)
        rate = await builder._get_usdt_rate("SOL", ts)
        
        assert rate == Decimal("1")
