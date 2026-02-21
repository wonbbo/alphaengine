"""
OpeningBalanceAdjusted 이벤트 분개 테스트
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

from core.domain.events import Event, EventTypes
from core.ledger.entry_builder import JournalEntryBuilder, JournalSide
from core.types import Scope


def create_opening_adjustment_event(
    venue: str = "FUTURES",
    asset: str = "USDT",
    ledger_balance: str = "670.00",
    exchange_balance: str = "673.52",
    adjustment_amount: str = "3.52",
    adjustment_type: str = "INCREASE",
) -> Event:
    """테스트용 OpeningBalanceAdjusted 이벤트 생성"""
    scope = Scope.create(
        exchange="BINANCE",
        venue=venue,
        symbol="",
        mode="production",
    )
    
    return Event.create(
        event_type=EventTypes.OPENING_BALANCE_ADJUSTED,
        source="BOT",
        entity_kind="RECONCILIATION",
        entity_id=f"opening_{venue}_{asset}",
        scope=scope,
        dedup_key=f"opening_adjustment:production:{venue}:{asset}",
        payload={
            "venue": venue,
            "asset": asset,
            "ledger_balance": ledger_balance,
            "exchange_balance": exchange_balance,
            "adjustment_amount": adjustment_amount,
            "adjustment_type": adjustment_type,
            "reason": "opening_balance_reconciliation",
        },
    )


class TestJournalEntryBuilderOpeningBalanceAdjusted:
    """OpeningBalanceAdjusted 분개 테스트"""
    
    @pytest.mark.asyncio
    async def test_increase_adjustment_creates_balanced_entry(self):
        """자산 증가 조정 시 균형 잡힌 분개 생성"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            venue="FUTURES",
            asset="USDT",
            adjustment_amount="3.52",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.is_balanced()
        assert len(entry.lines) == 2
    
    @pytest.mark.asyncio
    async def test_increase_adjustment_correct_accounts(self):
        """자산 증가 조정 시 올바른 계정 사용"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            venue="FUTURES",
            asset="USDT",
            adjustment_amount="3.52",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        # ASSET Debit (자산 증가)
        asset_line = next(
            line for line in entry.lines
            if line.account_id == "ASSET:BINANCE_FUTURES:USDT"
        )
        assert asset_line.side == JournalSide.DEBIT.value
        assert asset_line.amount == Decimal("3.52")
        
        # EQUITY Credit (자본 조정)
        equity_line = next(
            line for line in entry.lines
            if line.account_id == "EQUITY:OPENING_ADJUSTMENT"
        )
        assert equity_line.side == JournalSide.CREDIT.value
    
    @pytest.mark.asyncio
    async def test_decrease_adjustment_correct_accounts(self):
        """자산 감소 조정 시 올바른 계정 사용"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            venue="SPOT",
            asset="BNB",
            ledger_balance="0.60",
            exchange_balance="0.50",
            adjustment_amount="-0.10",  # 음수
            adjustment_type="DECREASE",
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        assert entry.is_balanced()
        
        # EQUITY Debit (자본 조정)
        equity_line = next(
            line for line in entry.lines
            if line.account_id == "EQUITY:OPENING_ADJUSTMENT"
        )
        assert equity_line.side == JournalSide.DEBIT.value
        
        # ASSET Credit (자산 감소)
        asset_line = next(
            line for line in entry.lines
            if line.account_id == "ASSET:BINANCE_SPOT:BNB"
        )
        assert asset_line.side == JournalSide.CREDIT.value
        assert asset_line.amount == Decimal("0.10")  # abs 적용됨
    
    @pytest.mark.asyncio
    async def test_zero_adjustment_returns_none(self):
        """조정 금액 0이면 None 반환"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            adjustment_amount="0",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        assert entry is None
    
    @pytest.mark.asyncio
    async def test_non_usdt_asset_rate_lookup(self):
        """USDT 외 자산은 환율 조회"""
        mock_rest_client = MagicMock()
        mock_rest_client.get_klines = AsyncMock(return_value=[
            {"close": "650.0"}  # BNB 가격
        ])
        
        builder = JournalEntryBuilder(rest_client=mock_rest_client)
        event = create_opening_adjustment_event(
            venue="FUTURES",
            asset="BNB",
            ledger_balance="0.10",
            exchange_balance="0.15",
            adjustment_amount="0.05",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        assert entry is not None
        
        # BNB line에 환율 적용
        bnb_line = next(
            line for line in entry.lines
            if line.asset == "BNB"
        )
        assert bnb_line.usdt_rate == Decimal("650.0")
        assert bnb_line.usdt_value == Decimal("0.05") * Decimal("650.0")
    
    @pytest.mark.asyncio
    async def test_adjustment_description_contains_details(self):
        """분개 설명에 상세 정보 포함"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            venue="FUTURES",
            asset="USDT",
            ledger_balance="670.00",
            exchange_balance="673.52",
            adjustment_amount="3.52",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        assert "FUTURES" in entry.description
        assert "USDT" in entry.description
        assert "670.00" in entry.description or "ledger" in entry.description.lower()
    
    @pytest.mark.asyncio
    async def test_spot_venue_uses_correct_account(self):
        """SPOT venue 조정 시 BINANCE_SPOT 계정 사용"""
        builder = JournalEntryBuilder()
        event = create_opening_adjustment_event(
            venue="SPOT",
            asset="USDT",
            adjustment_amount="5.00",
            adjustment_type="INCREASE",
        )
        
        entry = await builder.from_event(event)
        
        asset_line = next(
            line for line in entry.lines
            if line.side == JournalSide.DEBIT.value
        )
        assert "BINANCE_SPOT" in asset_line.account_id
