"""InitialCapitalEstablished 이벤트 → Ledger 분개 테스트"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.domain.events import Event
from core.ledger.entry_builder import JournalEntryBuilder
from core.ledger.types import JournalSide
from core.types import Scope


def create_initial_capital_event(
    spot_balances: list[dict] | None = None,
    futures_assets: list[dict] | None = None,
    snapshot_date: str = "2026-02-18",
) -> Event:
    """InitialCapitalEstablished 테스트용 이벤트 생성"""
    if spot_balances is None:
        spot_balances = []
    if futures_assets is None:
        futures_assets = []
    
    return Event(
        event_id="evt-initial-001",
        event_type="InitialCapitalEstablished",
        ts=datetime(2026, 2, 18, 0, 0, 0, tzinfo=timezone.utc),
        correlation_id="corr_initial_001",
        causation_id=None,
        command_id=None,
        source="recovery",
        entity_kind="CAPITAL",
        entity_id="initial_testnet",
        scope=Scope.create(venue="SYSTEM", mode="testnet"),
        dedup_key="testnet:initial_capital:2026-02-18",
        payload={
            "snapshot_date": snapshot_date,
            "spot_balances": spot_balances,
            "futures_assets": futures_assets,
        },
    )


class TestJournalEntryBuilderInitialCapital:
    """InitialCapitalEstablished 이벤트 처리 테스트"""
    
    @pytest.mark.asyncio
    async def test_initial_capital_creates_balanced_entry(self) -> None:
        """초기 자산 이벤트가 균형 잡힌 분개 생성"""
        event = create_initial_capital_event(
            spot_balances=[
                {"asset": "USDT", "free": "0.47498", "locked": "0"},
            ],
            futures_assets=[
                {"asset": "USDT", "walletBalance": "673.51619127"},
            ],
        )
        
        builder = JournalEntryBuilder()
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # Debit과 Credit 합계 검증 (균형)
        total_debit = sum(
            line.usdt_value for line in entry.lines
            if line.side == JournalSide.DEBIT.value
        )
        total_credit = sum(
            line.usdt_value for line in entry.lines
            if line.side == JournalSide.CREDIT.value
        )
        
        assert total_debit == total_credit, f"Debit({total_debit}) != Credit({total_credit})"
    
    @pytest.mark.asyncio
    async def test_initial_capital_has_correct_accounts(self) -> None:
        """초기 자산 이벤트가 올바른 계정으로 분개"""
        event = create_initial_capital_event(
            spot_balances=[
                {"asset": "USDT", "free": "100.00", "locked": "0"},
            ],
            futures_assets=[
                {"asset": "USDT", "walletBalance": "500.00"},
                {"asset": "BNB", "walletBalance": "0.1"},
            ],
        )
        
        builder = JournalEntryBuilder()
        builder.set_price("BNBUSDT", Decimal("650"))
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # 계정 확인
        account_ids = [line.account_id for line in entry.lines]
        
        assert "ASSET:BINANCE_SPOT:USDT" in account_ids
        assert "ASSET:BINANCE_FUTURES:USDT" in account_ids
        assert "ASSET:BINANCE_FUTURES:BNB" in account_ids
        assert "EQUITY:INITIAL_CAPITAL" in account_ids
    
    @pytest.mark.asyncio
    async def test_initial_capital_correct_amounts(self) -> None:
        """초기 자산 이벤트가 정확한 금액으로 분개"""
        event = create_initial_capital_event(
            futures_assets=[
                {"asset": "USDT", "walletBalance": "673.51619127"},
            ],
        )
        
        builder = JournalEntryBuilder()
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # FUTURES USDT Debit 라인 확인
        futures_usdt_line = next(
            (line for line in entry.lines 
             if line.account_id == "ASSET:BINANCE_FUTURES:USDT"),
            None
        )
        
        assert futures_usdt_line is not None
        assert futures_usdt_line.amount == Decimal("673.51619127")
        assert futures_usdt_line.side == JournalSide.DEBIT.value
        
        # EQUITY Credit 라인 확인
        equity_line = next(
            (line for line in entry.lines 
             if line.account_id == "EQUITY:INITIAL_CAPITAL"),
            None
        )
        
        assert equity_line is not None
        assert equity_line.side == JournalSide.CREDIT.value
        assert equity_line.usdt_value == Decimal("673.51619127")
    
    @pytest.mark.asyncio
    async def test_initial_capital_ignores_zero_balances(self) -> None:
        """잔고가 0인 자산은 분개에서 제외"""
        event = create_initial_capital_event(
            spot_balances=[
                {"asset": "USDT", "free": "100.00", "locked": "0"},
                {"asset": "BTC", "free": "0", "locked": "0"},
            ],
            futures_assets=[
                {"asset": "USDT", "walletBalance": "500.00"},
                {"asset": "USDC", "walletBalance": "0"},
            ],
        )
        
        builder = JournalEntryBuilder()
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # BTC, USDC 계정이 없어야 함
        account_ids = [line.account_id for line in entry.lines]
        
        assert "ASSET:BINANCE_SPOT:BTC" not in account_ids
        assert "ASSET:BINANCE_FUTURES:USDC" not in account_ids
        
        # 총 3개 라인: SPOT USDT, FUTURES USDT, EQUITY
        assert len(entry.lines) == 3
    
    @pytest.mark.asyncio
    async def test_initial_capital_description_includes_total(self) -> None:
        """분개 설명에 총액과 snapshot 날짜 포함"""
        event = create_initial_capital_event(
            futures_assets=[
                {"asset": "USDT", "walletBalance": "1000.00"},
            ],
            snapshot_date="2026-02-18",
        )
        
        builder = JournalEntryBuilder()
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert "1000" in entry.description
        assert "2026-02-18" in entry.description
    
    @pytest.mark.asyncio
    async def test_initial_capital_with_non_usdt_asset_uses_rate(self) -> None:
        """비-USDT 자산의 경우 환율 적용"""
        event = create_initial_capital_event(
            futures_assets=[
                {"asset": "BNB", "walletBalance": "0.1"},
            ],
        )
        
        builder = JournalEntryBuilder()
        builder.set_price("BNBUSDT", Decimal("650"))
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # BNB 라인의 USDT 가치 확인
        bnb_line = next(
            (line for line in entry.lines 
             if line.account_id == "ASSET:BINANCE_FUTURES:BNB"),
            None
        )
        
        assert bnb_line is not None
        assert bnb_line.amount == Decimal("0.1")
        assert bnb_line.usdt_value == Decimal("65")  # 0.1 * 650
        assert bnb_line.usdt_rate == Decimal("650")
    
    @pytest.mark.asyncio
    async def test_initial_capital_mixed_spot_and_futures(self) -> None:
        """SPOT과 FUTURES 자산이 함께 있는 경우"""
        event = create_initial_capital_event(
            spot_balances=[
                {"asset": "USDT", "free": "100.50", "locked": "10.00"},
                {"asset": "BNB", "free": "0.5", "locked": "0"},
            ],
            futures_assets=[
                {"asset": "USDT", "walletBalance": "500.00"},
            ],
        )
        
        builder = JournalEntryBuilder()
        builder.set_price("BNBUSDT", Decimal("600"))
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # SPOT USDT = 100.50 + 10.00 = 110.50
        spot_usdt_line = next(
            (line for line in entry.lines 
             if line.account_id == "ASSET:BINANCE_SPOT:USDT"),
            None
        )
        assert spot_usdt_line is not None
        assert spot_usdt_line.amount == Decimal("110.50")
        
        # SPOT BNB = 0.5, USDT 가치 = 300
        spot_bnb_line = next(
            (line for line in entry.lines 
             if line.account_id == "ASSET:BINANCE_SPOT:BNB"),
            None
        )
        assert spot_bnb_line is not None
        assert spot_bnb_line.amount == Decimal("0.5")
        assert spot_bnb_line.usdt_value == Decimal("300")
        
        # 총 USDT 가치 = 110.50 + 300 + 500 = 910.50
        equity_line = next(
            (line for line in entry.lines 
             if line.account_id == "EQUITY:INITIAL_CAPITAL"),
            None
        )
        assert equity_line is not None
        assert equity_line.usdt_value == Decimal("910.50")


class TestJournalEntryBuilderEpochDateFilter:
    """epoch_date 필터링 테스트"""
    
    @pytest.mark.asyncio
    async def test_event_before_epoch_date_returns_none(self) -> None:
        """epoch_date 이전 이벤트는 None 반환"""
        from core.domain.events import Event, EventTypes
        
        # epoch_date = 2026-02-18
        epoch_date = datetime(2026, 2, 18, 0, 0, 0, tzinfo=timezone.utc)
        
        # 2024-02-25 이벤트 (epoch_date 이전)
        old_event = Event(
            event_id="evt-old-001",
            event_type=EventTypes.DUST_CONVERTED,
            ts=datetime(2024, 2, 25, 0, 0, 0, tzinfo=timezone.utc),
            correlation_id="corr_001",
            causation_id=None,
            command_id=None,
            source="backfill",
            entity_kind="DUST",
            entity_id="dust_001",
            scope=Scope.create(venue="SPOT", mode="testnet"),
            dedup_key="testnet:dust:001",
            payload={
                "total_transferred_amount": "0.001",
                "total_service_charge": "0.0001",
                "from_assets": ["USDT"],
                "details": [
                    {"fromAsset": "USDT", "amount": "1.0", "transferedAmount": "0.001"}
                ],
            },
        )
        
        builder = JournalEntryBuilder(epoch_date=epoch_date)
        builder.set_price("BNBUSDT", Decimal("400"))
        
        entry = await builder.from_event(old_event)
        
        assert entry is None
    
    @pytest.mark.asyncio
    async def test_event_after_epoch_date_is_processed(self) -> None:
        """epoch_date 이후 이벤트는 정상 처리"""
        from core.domain.events import Event, EventTypes
        
        # epoch_date = 2026-02-18
        epoch_date = datetime(2026, 2, 18, 0, 0, 0, tzinfo=timezone.utc)
        
        # 2026-02-19 이벤트 (epoch_date 이후)
        new_event = Event(
            event_id="evt-new-001",
            event_type=EventTypes.DUST_CONVERTED,
            ts=datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc),
            correlation_id="corr_002",
            causation_id=None,
            command_id=None,
            source="backfill",
            entity_kind="DUST",
            entity_id="dust_002",
            scope=Scope.create(venue="SPOT", mode="testnet"),
            dedup_key="testnet:dust:002",
            payload={
                "total_transferred_amount": "0.001",
                "total_service_charge": "0.0001",
                "from_assets": ["USDT"],
                "details": [
                    {"fromAsset": "USDT", "amount": "1.0", "transferedAmount": "0.001"}
                ],
            },
        )
        
        builder = JournalEntryBuilder(epoch_date=epoch_date)
        builder.set_price("BNBUSDT", Decimal("400"))
        
        entry = await builder.from_event(new_event)
        
        assert entry is not None
    
    @pytest.mark.asyncio
    async def test_initial_capital_always_processed_regardless_of_epoch(self) -> None:
        """InitialCapitalEstablished는 epoch_date와 무관하게 항상 처리"""
        # epoch_date = 2030-01-01 (미래)
        epoch_date = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # 2026-02-18 InitialCapitalEstablished (epoch_date 이전)
        event = create_initial_capital_event(
            futures_assets=[
                {"asset": "USDT", "walletBalance": "500.00"},
            ],
        )
        
        builder = JournalEntryBuilder(epoch_date=epoch_date)
        
        entry = await builder.from_event(event)
        
        # InitialCapitalEstablished는 epoch_date 이전이어도 처리됨
        assert entry is not None
    
    @pytest.mark.asyncio
    async def test_no_epoch_date_processes_all_events(self) -> None:
        """epoch_date 미설정 시 모든 이벤트 처리"""
        from core.domain.events import Event, EventTypes
        
        # 아주 오래된 이벤트
        old_event = Event(
            event_id="evt-ancient-001",
            event_type=EventTypes.DUST_CONVERTED,
            ts=datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            correlation_id="corr_003",
            causation_id=None,
            command_id=None,
            source="backfill",
            entity_kind="DUST",
            entity_id="dust_003",
            scope=Scope.create(venue="SPOT", mode="testnet"),
            dedup_key="testnet:dust:003",
            payload={
                "total_transferred_amount": "0.001",
                "total_service_charge": "0.0001",
                "from_assets": ["USDT"],
                "details": [
                    {"fromAsset": "USDT", "amount": "1.0", "transferedAmount": "0.001"}
                ],
            },
        )
        
        # epoch_date 미설정
        builder = JournalEntryBuilder()
        builder.set_price("BNBUSDT", Decimal("400"))
        
        entry = await builder.from_event(old_event)
        
        # epoch_date가 없으면 모두 처리
        assert entry is not None
