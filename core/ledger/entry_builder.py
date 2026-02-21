"""
분개 생성기

이벤트를 복식부기 분개로 변환
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from core.domain.events import Event, EventTypes
from core.ledger.types import (
    NON_FINANCIAL_EVENT_TYPES,
    JournalSide,
    TransactionType,
)

if TYPE_CHECKING:
    from core.ledger.store import LedgerStore

logger = logging.getLogger(__name__)


@dataclass
class JournalLine:
    """분개 항목
    
    서로 다른 Asset 간 거래에서 균형 검증을 위해 USDT 환산 값 필수.
    예: 0.001 BTC 매수 (45 USDT 지급)
        - BTC line: amount=0.001, asset="BTC", usdt_value=45, usdt_rate=45000
        - USDT line: amount=45, asset="USDT", usdt_value=45, usdt_rate=1
    """
    
    account_id: str
    side: str  # DEBIT or CREDIT
    
    # 원본 수량
    amount: Decimal  # 해당 Asset의 실제 수량
    asset: str  # BTC, USDT, BNB, ETH, ...
    
    # USDT 환산 (균형 검증 필수)
    usdt_value: Decimal  # USDT로 환산된 가치
    usdt_rate: Decimal  # 환산 시 사용한 환율 (1 ASSET = ? USDT)
    
    # 메타
    memo: str | None = None


@dataclass
class JournalEntry:
    """분개
    
    하나의 거래에 대한 복식부기 기록.
    차변 합계 = 대변 합계 (균형)
    """
    
    entry_id: str
    ts: datetime
    transaction_type: str
    scope_mode: str
    lines: list[JournalLine]
    
    # 연관 정보
    related_trade_id: str | None = None
    related_order_id: str | None = None
    related_position_id: str | None = None
    symbol: str | None = None
    
    # 출처
    source_event_id: str | None = None
    source: str = "BOT"
    
    # 메타
    description: str | None = None
    memo: str | None = None
    raw_data: dict[str, Any] | None = None

    def is_balanced(self) -> bool:
        """USDT 환산 가치로 균형 검증
        
        서로 다른 Asset 간 거래도 USDT 환산 값으로 균형 확인.
        예: 0.001 BTC (45 USDT) 매수 = 45 USDT 지급
        
        Returns:
            True if sum(debit.usdt_value) ≈ sum(credit.usdt_value)
        """
        total_debit = sum(
            line.usdt_value for line in self.lines if line.side == JournalSide.DEBIT.value
        )
        total_credit = sum(
            line.usdt_value for line in self.lines if line.side == JournalSide.CREDIT.value
        )
        # 부동소수점 오차 허용 (0.01 USDT 이내)
        return abs(total_debit - total_credit) < Decimal("0.01")


class JournalEntryBuilder:
    """이벤트를 분개로 변환
    
    각 이벤트 타입별로 핸들러를 호출하여 분개를 생성.
    알 수 없는 이벤트는 Fallback 핸들러로 SUSPENSE 계정에 기록.
    """
    
    def __init__(self, ledger_store: LedgerStore | None = None):
        """
        Args:
            ledger_store: 동적 계정 생성을 위한 LedgerStore 참조
        """
        self.ledger_store = ledger_store
        
        # 가격 캐시 (향후 PriceCache 연동)
        self._price_cache: dict[str, Decimal] = {}
    
    async def from_event(self, event: Event) -> JournalEntry | None:
        """이벤트에서 분개 생성
        
        지원 이벤트:
        - TradeExecuted
        - BalanceChanged (범용 잔고 변경)
        - FundingApplied
        - FeeCharged
        - InternalTransferCompleted
        - DepositCompleted
        - WithdrawCompleted
        
        미지원 이벤트:
        - 비금융 이벤트: 무시
        - 금융 이벤트(추정): Fallback → SUSPENSE 분개
        """
        handlers = {
            EventTypes.TRADE_EXECUTED: self._from_trade_executed,
            EventTypes.FUNDING_APPLIED: self._from_funding_applied,
            EventTypes.FEE_CHARGED: self._from_fee_charged,
            EventTypes.INTERNAL_TRANSFER_COMPLETED: self._from_internal_transfer,
            EventTypes.DEPOSIT_COMPLETED: self._from_deposit,
            EventTypes.WITHDRAW_COMPLETED: self._from_withdraw,
            EventTypes.BALANCE_CHANGED: self._from_balance_changed,
        }
        
        handler = handlers.get(event.event_type)
        if handler:
            return await handler(event)
        
        # Fallback 핸들러
        return await self._from_generic_event(event)
    
    async def _from_trade_executed(self, event: Event) -> JournalEntry:
        """체결 이벤트 → 분개
        
        매수: ASSET 증가 (Debit), USDT 감소 (Credit), 수수료 (Debit/Credit)
        매도: USDT 증가 (Debit), ASSET 감소 (Credit), 수수료, PnL
        
        모든 JournalLine에 usdt_value, usdt_rate 필수.
        거래 체결가(price)가 환율로 사용됨.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        symbol = payload.get("symbol", event.scope.symbol)
        side = payload.get("side", "BUY")
        qty = Decimal(str(payload.get("qty", "0")))
        price = Decimal(str(payload.get("price", "0")))  # 체결가 = 환율
        commission = Decimal(str(payload.get("commission", "0")))
        commission_asset = payload.get("commission_asset", "USDT")
        realized_pnl = Decimal(str(payload.get("realized_pnl", "0")))
        is_maker = payload.get("is_maker", False)
        
        # Base/Quote asset 추출 (예: BTCUSDT -> BTC, USDT)
        quote_asset = "USDT"
        base_asset = symbol.replace(quote_asset, "") if symbol else "UNKNOWN"
        
        quote_amount = qty * price  # USDT 환산 가치
        
        # 동적 계정 생성 (새 Asset 자동 등록)
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(venue, base_asset)
            await self.ledger_store.ensure_asset_account(venue, quote_asset)
            if commission_asset not in [base_asset, quote_asset]:
                await self.ledger_store.ensure_asset_account(venue, commission_asset)
        
        # 수수료 Asset의 USDT 환율 조회 (BNB 등)
        commission_usdt_rate = await self._get_usdt_rate(commission_asset, event.ts)
        commission_usdt_value = commission * commission_usdt_rate
        
        lines: list[JournalLine] = []
        
        if side == "BUY":
            # Base asset 증가 (Debit) - 체결가로 USDT 환산
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:{base_asset}",
                side=JournalSide.DEBIT.value,
                amount=qty,
                asset=base_asset,
                usdt_value=quote_amount,  # qty * price
                usdt_rate=price,  # 1 BTC = price USDT
            ))
            # Quote asset(USDT) 감소 (Credit)
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:{quote_asset}",
                side=JournalSide.CREDIT.value,
                amount=quote_amount,
                asset=quote_asset,
                usdt_value=quote_amount,
                usdt_rate=Decimal("1"),  # 1 USDT = 1 USDT
            ))
        else:  # SELL
            # Quote asset(USDT) 증가 (Debit)
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:{quote_asset}",
                side=JournalSide.DEBIT.value,
                amount=quote_amount,
                asset=quote_asset,
                usdt_value=quote_amount,
                usdt_rate=Decimal("1"),
            ))
            # Base asset 감소 (Credit)
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:{base_asset}",
                side=JournalSide.CREDIT.value,
                amount=qty,
                asset=base_asset,
                usdt_value=quote_amount,
                usdt_rate=price,
            ))
        
        # 수수료 (수수료 Asset의 환율 적용)
        if commission > 0:
            fee_type = "MAKER" if is_maker else "TAKER"
            lines.append(JournalLine(
                account_id=f"EXPENSE:FEE:TRADING:{fee_type}",
                side=JournalSide.DEBIT.value,
                amount=commission,
                asset=commission_asset,
                usdt_value=commission_usdt_value,
                usdt_rate=commission_usdt_rate,
            ))
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:{commission_asset}",
                side=JournalSide.CREDIT.value,
                amount=commission,
                asset=commission_asset,
                usdt_value=commission_usdt_value,
                usdt_rate=commission_usdt_rate,
            ))
        
        # 실현 손익 (USDT로 정산)
        if realized_pnl != 0:
            if realized_pnl > 0:
                # 이익: USDT 증가 (Debit), INCOME Credit
                lines.append(JournalLine(
                    account_id=f"ASSET:{venue}:USDT",
                    side=JournalSide.DEBIT.value,
                    amount=abs(realized_pnl),
                    asset="USDT",
                    usdt_value=abs(realized_pnl),
                    usdt_rate=Decimal("1"),
                ))
                lines.append(JournalLine(
                    account_id="INCOME:TRADING:REALIZED_PNL",
                    side=JournalSide.CREDIT.value,
                    amount=abs(realized_pnl),
                    asset="USDT",
                    usdt_value=abs(realized_pnl),
                    usdt_rate=Decimal("1"),
                ))
            else:
                # 손실: INCOME Debit, USDT 감소 (Credit)
                lines.append(JournalLine(
                    account_id="INCOME:TRADING:REALIZED_PNL",
                    side=JournalSide.DEBIT.value,
                    amount=abs(realized_pnl),
                    asset="USDT",
                    usdt_value=abs(realized_pnl),
                    usdt_rate=Decimal("1"),
                ))
                lines.append(JournalLine(
                    account_id=f"ASSET:{venue}:USDT",
                    side=JournalSide.CREDIT.value,
                    amount=abs(realized_pnl),
                    asset="USDT",
                    usdt_value=abs(realized_pnl),
                    usdt_rate=Decimal("1"),
                ))
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.TRADE.value,
            scope_mode=event.scope.mode,
            lines=lines,
            related_trade_id=payload.get("exchange_trade_id"),
            related_order_id=payload.get("exchange_order_id"),
            symbol=symbol,
            source_event_id=event.event_id,
            source=event.source,
            description=f"{side} {qty} {base_asset} @ {price}",
            raw_data=payload,
        )
    
    async def _from_funding_applied(self, event: Event) -> JournalEntry:
        """펀딩 수수료 이벤트 → 분개
        
        펀딩은 항상 USDT로 정산되므로 usdt_rate=1.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        amount = Decimal(str(payload.get("funding_fee", "0")))
        symbol = payload.get("symbol", event.scope.symbol)
        
        lines: list[JournalLine] = []
        
        if amount > 0:
            # 펀딩 지급 (비용)
            lines.append(JournalLine(
                account_id="EXPENSE:FEE:FUNDING:PAID",
                side=JournalSide.DEBIT.value,
                amount=abs(amount),
                asset="USDT",
                usdt_value=abs(amount),
                usdt_rate=Decimal("1"),
            ))
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:USDT",
                side=JournalSide.CREDIT.value,
                amount=abs(amount),
                asset="USDT",
                usdt_value=abs(amount),
                usdt_rate=Decimal("1"),
            ))
        else:
            # 펀딩 수령 (수익)
            lines.append(JournalLine(
                account_id=f"ASSET:{venue}:USDT",
                side=JournalSide.DEBIT.value,
                amount=abs(amount),
                asset="USDT",
                usdt_value=abs(amount),
                usdt_rate=Decimal("1"),
            ))
            lines.append(JournalLine(
                account_id="INCOME:FUNDING:RECEIVED",
                side=JournalSide.CREDIT.value,
                amount=abs(amount),
                asset="USDT",
                usdt_value=abs(amount),
                usdt_rate=Decimal("1"),
            ))
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=(
                TransactionType.FEE_FUNDING.value 
                if amount > 0 
                else TransactionType.FUNDING_RECEIVED.value
            ),
            scope_mode=event.scope.mode,
            lines=lines,
            symbol=symbol,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Funding {'paid' if amount > 0 else 'received'} {abs(amount)} USDT",
        )
    
    async def _from_deposit(self, event: Event) -> JournalEntry:
        """입금 완료 이벤트 → 분개
        
        외부(EXTERNAL)에서 내부(Binance)로 자금 이동.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        amount = Decimal(str(payload.get("amount", "0")))
        asset = payload.get("asset", "USDT")
        
        # 동적 계정 생성
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(venue, asset)
            await self.ledger_store.ensure_asset_account("EXTERNAL", asset)
        
        # USDT 환율 조회
        usdt_rate = await self._get_usdt_rate(asset, event.ts)
        usdt_value = amount * usdt_rate
        
        lines = [
            JournalLine(
                account_id=f"ASSET:{venue}:{asset}",
                side=JournalSide.DEBIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
            JournalLine(
                account_id=f"ASSET:EXTERNAL:{asset}",
                side=JournalSide.CREDIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
        ]
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.DEPOSIT.value,
            scope_mode=event.scope.mode,
            lines=lines,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Deposit {amount} {asset}",
            memo=payload.get("source", "UPBIT"),
        )
    
    async def _from_withdraw(self, event: Event) -> JournalEntry:
        """출금 완료 이벤트 → 분개
        
        내부(Binance)에서 외부(EXTERNAL)로 자금 이동.
        출금 수수료 포함.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        amount = Decimal(str(payload.get("amount", "0")))
        fee = Decimal(str(payload.get("fee", "0")))
        asset = payload.get("asset", "USDT")
        
        # 동적 계정 생성
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(venue, asset)
            await self.ledger_store.ensure_asset_account("EXTERNAL", asset)
        
        # USDT 환율 조회
        usdt_rate = await self._get_usdt_rate(asset, event.ts)
        amount_usdt_value = amount * usdt_rate
        net_amount = amount - fee
        net_usdt_value = net_amount * usdt_rate
        fee_usdt_value = fee * usdt_rate
        
        lines = [
            # 외부로 이동 (수수료 제외 순액)
            JournalLine(
                account_id=f"ASSET:EXTERNAL:{asset}",
                side=JournalSide.DEBIT.value,
                amount=net_amount,
                asset=asset,
                usdt_value=net_usdt_value,
                usdt_rate=usdt_rate,
            ),
            # 내부 자산 감소 (총액)
            JournalLine(
                account_id=f"ASSET:{venue}:{asset}",
                side=JournalSide.CREDIT.value,
                amount=amount,
                asset=asset,
                usdt_value=amount_usdt_value,
                usdt_rate=usdt_rate,
            ),
        ]
        
        # 출금 수수료
        if fee > 0:
            lines.append(JournalLine(
                account_id="EXPENSE:FEE:WITHDRAWAL",
                side=JournalSide.DEBIT.value,
                amount=fee,
                asset=asset,
                usdt_value=fee_usdt_value,
                usdt_rate=usdt_rate,
            ))
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.WITHDRAWAL.value,
            scope_mode=event.scope.mode,
            lines=lines,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Withdraw {amount} {asset} (fee: {fee})",
            memo=payload.get("destination", "UPBIT"),
        )
    
    async def _from_internal_transfer(self, event: Event) -> JournalEntry:
        """내부 이체 이벤트 → 분개
        
        Binance 내부 이체 (Spot <-> Futures).
        동일 Asset 이동이므로 환율은 동일.
        """
        payload = event.payload
        from_venue = payload.get("from_venue", "BINANCE_SPOT")
        to_venue = payload.get("to_venue", "BINANCE_FUTURES")
        amount = Decimal(str(payload.get("amount", "0")))
        asset = payload.get("asset", "USDT")
        
        # 동적 계정 생성
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(from_venue, asset)
            await self.ledger_store.ensure_asset_account(to_venue, asset)
        
        # USDT 환율 조회
        usdt_rate = await self._get_usdt_rate(asset, event.ts)
        usdt_value = amount * usdt_rate
        
        lines = [
            JournalLine(
                account_id=f"ASSET:{to_venue}:{asset}",
                side=JournalSide.DEBIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
            JournalLine(
                account_id=f"ASSET:{from_venue}:{asset}",
                side=JournalSide.CREDIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
        ]
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.INTERNAL_TRANSFER.value,
            scope_mode=event.scope.mode,
            lines=lines,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Transfer {amount} {asset} from {from_venue} to {to_venue}",
        )
    
    async def _from_fee_charged(self, event: Event) -> JournalEntry:
        """수수료 이벤트 → 분개 (별도 FeeCharged 이벤트가 있는 경우)
        
        BNB 등 USDT 외 Asset으로 수수료 지급 시 환율 적용.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        amount = Decimal(str(payload.get("fee", "0")))
        fee_type = payload.get("fee_type", "TRADING")
        asset = payload.get("asset", "USDT")
        
        # 동적 계정 생성
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(venue, asset)
        
        # USDT 환율 조회
        usdt_rate = await self._get_usdt_rate(asset, event.ts)
        usdt_value = amount * usdt_rate
        
        lines = [
            JournalLine(
                account_id=f"EXPENSE:FEE:{fee_type}",
                side=JournalSide.DEBIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
            JournalLine(
                account_id=f"ASSET:{venue}:{asset}",
                side=JournalSide.CREDIT.value,
                amount=amount,
                asset=asset,
                usdt_value=usdt_value,
                usdt_rate=usdt_rate,
            ),
        ]
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.FEE_TRADING.value,
            scope_mode=event.scope.mode,
            lines=lines,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Fee {amount} {asset} ({fee_type})",
        )
    
    async def _from_balance_changed(self, event: Event) -> JournalEntry | None:
        """범용 잔고 변경 처리.
        
        TradeExecuted, FeeCharged 등으로 처리되지 않은 잔고 변경 캐치.
        출처 불명이면 SUSPENSE 계정으로 대응.
        """
        payload = event.payload
        venue = f"BINANCE_{event.scope.venue}"
        asset = payload.get("asset", "USDT")
        
        # delta가 있으면 변화량, 없으면 free/locked 기반으로 추정
        delta_str = payload.get("delta")
        if delta_str is None:
            # delta가 없으면 처리 불가 - 무시
            logger.debug(f"BalanceChanged without delta, skipping: {event.event_id}")
            return None
        
        delta = Decimal(str(delta_str))
        if delta == 0:
            return None
        
        # 동적 계정 생성
        if self.ledger_store:
            await self.ledger_store.ensure_asset_account(venue, asset)
        
        account_id = f"ASSET:{venue}:{asset}"
        
        # USDT 환율 조회
        usdt_rate = await self._get_usdt_rate(asset, event.ts)
        usdt_value = abs(delta) * usdt_rate
        
        lines: list[JournalLine] = []
        
        if delta > 0:
            # 잔고 증가 - 출처 불명이면 SUSPENSE에서 입금
            lines = [
                JournalLine(
                    account_id=account_id,
                    side=JournalSide.DEBIT.value,
                    amount=abs(delta),
                    asset=asset,
                    usdt_value=usdt_value,
                    usdt_rate=usdt_rate,
                ),
                JournalLine(
                    account_id="EQUITY:SUSPENSE",
                    side=JournalSide.CREDIT.value,
                    amount=abs(delta),
                    asset=asset,
                    usdt_value=usdt_value,
                    usdt_rate=usdt_rate,
                ),
            ]
        else:
            # 잔고 감소 - 원인 불명이면 SUSPENSE로 출금
            lines = [
                JournalLine(
                    account_id="EQUITY:SUSPENSE",
                    side=JournalSide.DEBIT.value,
                    amount=abs(delta),
                    asset=asset,
                    usdt_value=usdt_value,
                    usdt_rate=usdt_rate,
                ),
                JournalLine(
                    account_id=account_id,
                    side=JournalSide.CREDIT.value,
                    amount=abs(delta),
                    asset=asset,
                    usdt_value=usdt_value,
                    usdt_rate=usdt_rate,
                ),
            ]
        
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.ADJUSTMENT.value,
            scope_mode=event.scope.mode,
            lines=lines,
            source_event_id=event.event_id,
            source=event.source,
            description=f"Balance {'increased' if delta > 0 else 'decreased'}: {asset} {delta}",
        )
    
    async def _from_generic_event(self, event: Event) -> JournalEntry | None:
        """알 수 없는 이벤트 Fallback 처리.
        
        금융 이벤트면 SUSPENSE 계정으로 기록.
        비금융 이벤트는 무시.
        """
        event_type = event.event_type
        
        # 비금융 이벤트는 무시
        if event_type in NON_FINANCIAL_EVENT_TYPES:
            logger.debug(f"비금융 이벤트 무시: {event_type}")
            return None
        
        # 금융 관련으로 추정되는 이벤트 - 경고 후 SUSPENSE 처리
        logger.warning(
            f"[Ledger] 알 수 없는 금융 이벤트: {event_type}. "
            f"SUSPENSE 계정으로 기록. event_id={event.event_id}"
        )
        
        # 기본 SUSPENSE 분개 생성 (금액 불명이면 0으로)
        return JournalEntry(
            entry_id=str(uuid4()),
            ts=event.ts,
            transaction_type=TransactionType.UNKNOWN.value,
            scope_mode=event.scope.mode,
            source_event_id=event.event_id,
            source="FALLBACK",
            description=f"Unhandled event: {event_type}",
            memo=f"event_type={event_type}",
            raw_data=event.payload,
            lines=[
                JournalLine(
                    account_id="EQUITY:SUSPENSE",
                    side=JournalSide.DEBIT.value,
                    amount=Decimal("0"),
                    asset="UNKNOWN",
                    usdt_value=Decimal("0"),
                    usdt_rate=Decimal("0"),
                    memo=f"Unhandled: {event_type}",
                ),
                JournalLine(
                    account_id="EQUITY:SUSPENSE",
                    side=JournalSide.CREDIT.value,
                    amount=Decimal("0"),
                    asset="UNKNOWN",
                    usdt_value=Decimal("0"),
                    usdt_rate=Decimal("0"),
                    memo=f"Unhandled: {event_type}",
                ),
            ],
        )
    
    async def _get_usdt_rate(self, asset: str, ts: datetime) -> Decimal:
        """Asset의 USDT 환율 조회
        
        환율 소스 우선순위:
        1. USDT는 항상 1
        2. 캐시된 최근 시세
        3. 기본값 + 경고 로깅
        
        Args:
            asset: BTC, ETH, BNB, USDT, ...
            ts: 거래 발생 시점 (현재는 미사용, 향후 과거 시세 조회용)
        
        Returns:
            1 ASSET = ? USDT
        """
        if asset == "USDT":
            return Decimal("1")
        
        # 캐시에서 조회
        cache_key = f"{asset}USDT"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]
        
        # Fallback: 경고 로그 + 기본값 1 (실제 운영에서는 수정 필요)
        logger.warning(
            f"[Ledger] USDT 환율 조회 실패: {asset}. "
            "수동 확인 필요. 임시로 rate=1 적용."
        )
        return Decimal("1")
    
    def set_price(self, symbol: str, price: Decimal) -> None:
        """가격 캐시 설정 (외부에서 주입)
        
        WebSocket 등에서 실시간 시세를 받아 설정.
        
        Args:
            symbol: 심볼 (예: "BTCUSDT")
            price: 현재 가격
        """
        self._price_cache[symbol] = price
