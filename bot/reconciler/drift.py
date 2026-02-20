"""
Drift Detector

거래소 상태와 내부 Projection 비교하여 불일치 감지
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.domain.events import Event, EventTypes
from core.types import Scope
from core.utils.dedup import make_drift_dedup_key
from adapters.models import Balance, Position, Order

logger = logging.getLogger(__name__)


@dataclass
class DriftInfo:
    """Drift 정보"""
    drift_kind: str  # position, balance, order
    symbol: str | None
    asset: str | None
    expected: dict[str, Any]
    actual: dict[str, Any]
    description: str


class DriftDetector:
    """Drift 감지기
    
    거래소 상태와 내부 Projection을 비교하여 불일치를 감지.
    DriftDetected 이벤트를 생성하여 정합 복구 트리거.
    
    Args:
        scope: 거래 범위
    """
    
    # 수량 비교 시 허용 오차 (부동소수점 오차 방지)
    QTY_TOLERANCE = Decimal("0.00000001")
    
    def __init__(self, scope: Scope):
        self.scope = scope
    
    def detect_position_drift(
        self,
        exchange_position: Position | None,
        projection_position: dict[str, Any] | None,
        symbol: str,
    ) -> DriftInfo | None:
        """포지션 drift 감지
        
        Args:
            exchange_position: 거래소에서 조회한 포지션
            projection_position: 내부 Projection 포지션
            symbol: 심볼
            
        Returns:
            DriftInfo 또는 None (일치 시)
        """
        # 거래소: 포지션 있음, 내부: 포지션 없음
        if exchange_position and not projection_position:
            return DriftInfo(
                drift_kind="position",
                symbol=symbol,
                asset=None,
                expected={"qty": "0"},
                actual={
                    "side": exchange_position.side,
                    "qty": str(exchange_position.qty),
                    "entry_price": str(exchange_position.entry_price),
                },
                description=f"Exchange has position, projection is empty: {exchange_position.qty}",
            )
        
        # 거래소: 포지션 없음, 내부: 포지션 있음
        if not exchange_position and projection_position:
            proj_qty = Decimal(projection_position.get("qty", "0"))
            if proj_qty != Decimal("0"):
                return DriftInfo(
                    drift_kind="position",
                    symbol=symbol,
                    asset=None,
                    expected={
                        "side": projection_position.get("side"),
                        "qty": str(proj_qty),
                    },
                    actual={"qty": "0"},
                    description=f"Projection has position, exchange is empty: {proj_qty}",
                )
        
        # 둘 다 포지션 있음 - 수량/방향 비교
        if exchange_position and projection_position:
            exch_qty = exchange_position.qty
            proj_qty = Decimal(projection_position.get("qty", "0"))
            
            if abs(exch_qty - proj_qty) > self.QTY_TOLERANCE:
                return DriftInfo(
                    drift_kind="position",
                    symbol=symbol,
                    asset=None,
                    expected={
                        "side": projection_position.get("side"),
                        "qty": str(proj_qty),
                    },
                    actual={
                        "side": exchange_position.side,
                        "qty": str(exch_qty),
                    },
                    description=f"Position qty mismatch: expected {proj_qty}, actual {exch_qty}",
                )
        
        return None
    
    def detect_balance_drift(
        self,
        exchange_balance: Balance,
        projection_balance: dict[str, Any] | None,
    ) -> DriftInfo | None:
        """잔고 drift 감지
        
        Args:
            exchange_balance: 거래소에서 조회한 잔고
            projection_balance: 내부 Projection 잔고
            
        Returns:
            DriftInfo 또는 None (일치 시)
        """
        exch_free = exchange_balance.free
        exch_locked = exchange_balance.locked
        
        if not projection_balance:
            # Projection 없으면 drift
            if exch_free > Decimal("0") or exch_locked > Decimal("0"):
                return DriftInfo(
                    drift_kind="balance",
                    symbol=None,
                    asset=exchange_balance.asset,
                    expected={"free": "0", "locked": "0"},
                    actual={
                        "free": str(exch_free),
                        "locked": str(exch_locked),
                    },
                    description=f"Balance not in projection: {exchange_balance.asset}",
                )
            return None
        
        proj_free = Decimal(projection_balance.get("free", "0"))
        proj_locked = Decimal(projection_balance.get("locked", "0"))
        
        # 오차 범위 비교
        free_diff = abs(exch_free - proj_free)
        locked_diff = abs(exch_locked - proj_locked)
        
        if free_diff > self.QTY_TOLERANCE or locked_diff > self.QTY_TOLERANCE:
            return DriftInfo(
                drift_kind="balance",
                symbol=None,
                asset=exchange_balance.asset,
                expected={
                    "free": str(proj_free),
                    "locked": str(proj_locked),
                },
                actual={
                    "free": str(exch_free),
                    "locked": str(exch_locked),
                },
                description=f"Balance mismatch for {exchange_balance.asset}: "
                           f"free diff={free_diff}, locked diff={locked_diff}",
            )
        
        return None
    
    def detect_order_drift(
        self,
        exchange_orders: list[Order],
        projection_orders: list[dict[str, Any]],
        symbol: str,
    ) -> list[DriftInfo]:
        """주문 drift 감지
        
        Args:
            exchange_orders: 거래소에서 조회한 오픈 주문
            projection_orders: 내부 Projection 오픈 주문
            symbol: 심볼
            
        Returns:
            DriftInfo 리스트
        """
        drifts: list[DriftInfo] = []
        
        # 거래소 주문 ID 집합
        exch_order_ids = {str(o.order_id) for o in exchange_orders}
        
        # 내부 주문 ID 집합
        proj_order_ids = {
            str(o.get("exchange_order_id", "")) 
            for o in projection_orders
        }
        
        # 거래소에만 있는 주문 (누락된 이벤트 가능성)
        missing_in_proj = exch_order_ids - proj_order_ids
        for order_id in missing_in_proj:
            order = next(o for o in exchange_orders if str(o.order_id) == order_id)
            drifts.append(DriftInfo(
                drift_kind="order",
                symbol=symbol,
                asset=None,
                expected={"order_id": None},
                actual={
                    "order_id": order_id,
                    "side": order.side,
                    "type": order.order_type,
                    "qty": str(order.original_qty),
                },
                description=f"Order {order_id} exists on exchange but not in projection",
            ))
        
        # 내부에만 있는 주문 (이미 체결/취소되었을 가능성)
        missing_in_exch = proj_order_ids - exch_order_ids
        for order_id in missing_in_exch:
            if not order_id:  # 빈 문자열 스킵
                continue
            proj_order = next(
                o for o in projection_orders 
                if str(o.get("exchange_order_id", "")) == order_id
            )
            drifts.append(DriftInfo(
                drift_kind="order",
                symbol=symbol,
                asset=None,
                expected={
                    "order_id": order_id,
                    "status": proj_order.get("order_state"),
                },
                actual={"order_id": None},
                description=f"Order {order_id} in projection but not on exchange (may be filled/cancelled)",
            ))
        
        return drifts
    
    def create_drift_event(self, drift: DriftInfo) -> Event:
        """DriftDetected 이벤트 생성
        
        Args:
            drift: Drift 정보
            
        Returns:
            DriftDetected 이벤트
        """
        now = datetime.now(timezone.utc)
        time_bucket = now.strftime("%Y-%m-%dT%H:%M")  # 분 단위 버킷 (스팸 방지)
        
        symbol = drift.symbol or "GLOBAL"
        scope_with_symbol = Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=drift.symbol,
            mode=self.scope.mode,
        )
        
        dedup_key = make_drift_dedup_key(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            symbol=symbol,
            drift_kind=drift.drift_kind,
            time_bucket=time_bucket,
        )
        
        return Event.create(
            event_type=EventTypes.DRIFT_DETECTED,
            source="BOT",
            entity_kind="RECONCILER",
            entity_id=f"{drift.drift_kind}:{symbol}",
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "drift_kind": drift.drift_kind,
                "symbol": drift.symbol,
                "asset": drift.asset,
                "expected": drift.expected,
                "actual": drift.actual,
                "description": drift.description,
                "detected_at": now.isoformat(),
            },
        )
