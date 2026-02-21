"""
OpeningBalanceReconciler

백필 완료 후 Ledger 잔고와 실제 거래소 잔고를 비교하여 조정 분개 생성.
최초 실행 시 1회만 수행하여 정확한 시작점을 보장.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope
from core.utils.dedup import make_opening_adjustment_dedup_key

logger = logging.getLogger(__name__)


class OpeningBalanceReconciler:
    """기초 잔액 정합기
    
    백필 완료 후 Ledger 잔고와 실제 거래소 잔고를 비교하여
    차이가 있으면 OpeningBalanceAdjusted 이벤트를 생성합니다.
    
    Args:
        rest_client: Binance REST 클라이언트
        event_store: 이벤트 저장소
        scope: 거래 범위
    """
    
    # 조정 임계값 (이 값 이하의 차이는 무시)
    ADJUSTMENT_THRESHOLD = Decimal("0.0001")
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        scope: Scope,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.scope = scope
    
    async def reconcile(
        self,
        ledger_balances: dict[str, dict[str, Decimal]],
    ) -> dict[str, Any]:
        """Ledger 잔고와 실제 거래소 잔고 비교 및 조정
        
        Args:
            ledger_balances: Ledger의 현재 잔고
                {
                    "FUTURES": {"USDT": Decimal("670.00"), "BNB": Decimal("0.1")},
                    "SPOT": {"USDT": Decimal("0.47"), "BNB": Decimal("0.5")},
                }
                
        Returns:
            조정 결과:
            {
                "adjusted_count": 2,
                "adjustments": [
                    {"venue": "FUTURES", "asset": "USDT", "diff": "3.52"},
                    {"venue": "SPOT", "asset": "BNB", "diff": "-0.05"},
                ],
                "skipped_count": 3,
            }
        """
        logger.info("기초 잔액 정합 시작...")
        
        # 1. 거래소에서 실제 잔고 조회
        exchange_balances = await self._fetch_exchange_balances()
        
        # 2. 차이 계산
        adjustments = self._calculate_adjustments(ledger_balances, exchange_balances)
        
        # 3. 조정 이벤트 생성
        adjusted_count = 0
        skipped_count = 0
        adjustment_details = []
        
        for adj in adjustments:
            diff = adj["diff"]
            
            # 임계값 이하는 무시
            if abs(diff) < self.ADJUSTMENT_THRESHOLD:
                skipped_count += 1
                continue
            
            saved = await self._create_adjustment_event(adj)
            if saved:
                adjusted_count += 1
                adjustment_details.append({
                    "venue": adj["venue"],
                    "asset": adj["asset"],
                    "diff": str(diff),
                    "ledger": str(adj["ledger"]),
                    "exchange": str(adj["exchange"]),
                })
        
        result = {
            "adjusted_count": adjusted_count,
            "adjustments": adjustment_details,
            "skipped_count": skipped_count,
        }
        
        logger.info(
            "기초 잔액 정합 완료",
            extra={
                "adjusted": adjusted_count,
                "skipped": skipped_count,
            },
        )
        
        return result
    
    async def _fetch_exchange_balances(self) -> dict[str, dict[str, Decimal]]:
        """거래소에서 실제 잔고 조회
        
        Returns:
            {
                "FUTURES": {"USDT": Decimal("673.52"), "BNB": Decimal("0.1")},
                "SPOT": {"USDT": Decimal("0.47"), "BNB": Decimal("0.45")},
            }
        """
        result: dict[str, dict[str, Decimal]] = {
            "FUTURES": {},
            "SPOT": {},
        }
        
        # FUTURES 잔고 조회
        try:
            futures_balances = await self.rest_client.get_balances()
            for balance in futures_balances:
                asset = balance.asset
                # Balance 객체에서 wallet_balance 사용
                amount = Decimal(str(balance.wallet_balance))
                if amount > 0:
                    result["FUTURES"][asset] = amount
        except Exception as e:
            logger.error(f"FUTURES 잔고 조회 실패: {e}")
        
        # SPOT 잔고 조회
        try:
            spot_balances = await self.rest_client.get_spot_balances()
            for asset, balance_info in spot_balances.items():
                free = Decimal(balance_info.get("free", "0"))
                locked = Decimal(balance_info.get("locked", "0"))
                total = free + locked
                if total > 0:
                    result["SPOT"][asset] = total
        except Exception as e:
            logger.error(f"SPOT 잔고 조회 실패: {e}")
        
        return result
    
    def _calculate_adjustments(
        self,
        ledger_balances: dict[str, dict[str, Decimal]],
        exchange_balances: dict[str, dict[str, Decimal]],
    ) -> list[dict[str, Any]]:
        """Ledger와 거래소 잔고 차이 계산
        
        Returns:
            조정 필요 목록:
            [
                {
                    "venue": "FUTURES",
                    "asset": "USDT",
                    "ledger": Decimal("670.00"),
                    "exchange": Decimal("673.52"),
                    "diff": Decimal("3.52"),  # 양수: 자산 증가, 음수: 자산 감소
                },
                ...
            ]
        """
        adjustments = []
        
        # 모든 venue/asset 조합 수집
        all_keys: set[tuple[str, str]] = set()
        
        for venue in ["FUTURES", "SPOT"]:
            ledger_venue = ledger_balances.get(venue, {})
            exchange_venue = exchange_balances.get(venue, {})
            
            for asset in ledger_venue:
                all_keys.add((venue, asset))
            for asset in exchange_venue:
                all_keys.add((venue, asset))
        
        # 각 조합에 대해 차이 계산
        for venue, asset in all_keys:
            ledger_amount = ledger_balances.get(venue, {}).get(asset, Decimal("0"))
            exchange_amount = exchange_balances.get(venue, {}).get(asset, Decimal("0"))
            
            diff = exchange_amount - ledger_amount
            
            if diff != Decimal("0"):
                adjustments.append({
                    "venue": venue,
                    "asset": asset,
                    "ledger": ledger_amount,
                    "exchange": exchange_amount,
                    "diff": diff,
                })
        
        return adjustments
    
    async def _create_adjustment_event(self, adjustment: dict[str, Any]) -> bool:
        """조정 이벤트 생성 및 저장"""
        venue = adjustment["venue"]
        asset = adjustment["asset"]
        diff = adjustment["diff"]
        
        dedup_key = make_opening_adjustment_dedup_key(
            mode=self.scope.mode,
            venue=venue,
            asset=asset,
        )
        
        payload = {
            "venue": venue,
            "asset": asset,
            "ledger_balance": str(adjustment["ledger"]),
            "exchange_balance": str(adjustment["exchange"]),
            "adjustment_amount": str(diff),
            "adjustment_type": "INCREASE" if diff > 0 else "DECREASE",
            "reason": "opening_balance_reconciliation",
        }
        
        # Scope 설정 (venue에 따라)
        scope_venue = "FUTURES" if venue == "FUTURES" else "SPOT"
        adjusted_scope = Scope.create(
            exchange=self.scope.exchange,
            venue=scope_venue,
            symbol="",
            mode=self.scope.mode,
        )
        
        event = Event.create(
            event_type=EventTypes.OPENING_BALANCE_ADJUSTED,
            source="BOT",
            entity_kind="RECONCILIATION",
            entity_id=f"opening_{venue}_{asset}",
            scope=adjusted_scope,
            dedup_key=dedup_key,
            payload=payload,
        )
        
        saved = await self.event_store.append(event)
        
        if saved:
            logger.info(
                f"기초 잔액 조정 이벤트 생성: {venue} {asset} {'+' if diff > 0 else ''}{diff}",
                extra={
                    "event_id": event.event_id,
                    "venue": venue,
                    "asset": asset,
                    "diff": str(diff),
                },
            )
        
        return saved
