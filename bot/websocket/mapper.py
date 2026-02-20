"""
WebSocket 메시지 → Event 변환 매퍼

Binance WebSocket 메시지를 도메인 Event로 변환
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.domain.events import Event, EventTypes
from core.types import Scope
from core.utils.dedup import make_trade_dedup_key, make_order_dedup_key

logger = logging.getLogger(__name__)


class WebSocketEventMapper:
    """WebSocket 메시지 → Event 변환
    
    Binance User Data Stream 메시지를 AlphaEngine Event로 변환.
    dedup_key를 생성하여 중복 이벤트 방지.
    """
    
    def __init__(self, scope: Scope):
        """
        Args:
            scope: 기본 거래 범위 (symbol은 메시지에서 추출)
        """
        self.scope = scope
    
    def _scope_with_symbol(self, symbol: str) -> Scope:
        """심볼이 포함된 Scope 생성"""
        return Scope(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            account_id=self.scope.account_id,
            symbol=symbol,
            mode=self.scope.mode,
        )
    
    def _ms_to_datetime(self, timestamp_ms: int) -> datetime:
        """밀리초 타임스탬프 → datetime (UTC)"""
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    
    # -------------------------------------------------------------------------
    # ACCOUNT_UPDATE 처리
    # -------------------------------------------------------------------------
    
    def map_account_update(self, msg: dict[str, Any]) -> list[Event]:
        """ACCOUNT_UPDATE 메시지 → Event 리스트
        
        Args:
            msg: ACCOUNT_UPDATE 메시지
            
        Returns:
            BalanceChanged, PositionChanged 이벤트 리스트
        """
        events: list[Event] = []
        
        data = msg.get("a", {})
        tx_time = msg.get("T", 0)
        event_time = msg.get("E", 0)
        update_reason = data.get("m", "UNKNOWN")
        
        # 잔고 변경 처리
        for balance_data in data.get("B", []):
            event = self._create_balance_changed_event(
                balance_data, tx_time, event_time, update_reason
            )
            if event:
                events.append(event)
        
        # 포지션 변경 처리
        for position_data in data.get("P", []):
            event = self._create_position_changed_event(
                position_data, tx_time, event_time, update_reason
            )
            if event:
                events.append(event)
        
        return events
    
    def _create_balance_changed_event(
        self,
        data: dict[str, Any],
        tx_time: int,
        event_time: int,
        reason: str,
    ) -> Event | None:
        """BalanceChanged 이벤트 생성"""
        asset = data.get("a", "")
        if not asset:
            return None
        
        wallet_balance = data.get("wb", "0")
        cross_wallet = data.get("cw", "0")
        balance_change = data.get("bc", "0")
        
        # 변경이 없으면 스킵
        if Decimal(balance_change) == Decimal("0"):
            return None
        
        # dedup_key: 거래소:venue:자산:balance:타임스탬프
        dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{asset}:balance:{tx_time}"
        
        return Event.create(
            event_type=EventTypes.BALANCE_CHANGED,
            source="WEBSOCKET",
            entity_kind="BALANCE",
            entity_id=asset,
            scope=self.scope,
            dedup_key=dedup_key,
            payload={
                "asset": asset,
                "wallet_balance": wallet_balance,
                "cross_wallet_balance": cross_wallet,
                "balance_change": balance_change,
                "reason": reason,
                "transaction_time": tx_time,
                "event_time": event_time,
            },
        )
    
    def _create_position_changed_event(
        self,
        data: dict[str, Any],
        tx_time: int,
        event_time: int,
        reason: str,
    ) -> Event | None:
        """PositionChanged 이벤트 생성"""
        symbol = data.get("s", "")
        if not symbol:
            return None
        
        position_amount = data.get("pa", "0")
        entry_price = data.get("ep", "0")
        accumulated_realized = data.get("cr", "0")
        unrealized_pnl = data.get("up", "0")
        margin_type = data.get("mt", "cross")
        isolated_wallet = data.get("iw", "0")
        position_side = data.get("ps", "BOTH")
        
        # dedup_key: 거래소:venue:심볼:position:타임스탬프
        dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{symbol}:position:{tx_time}"
        
        scope_with_symbol = self._scope_with_symbol(symbol)
        
        return Event.create(
            event_type=EventTypes.POSITION_CHANGED,
            source="WEBSOCKET",
            entity_kind="POSITION",
            entity_id=symbol,
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "symbol": symbol,
                "position_amount": position_amount,
                "entry_price": entry_price,
                "accumulated_realized": accumulated_realized,
                "unrealized_pnl": unrealized_pnl,
                "margin_type": margin_type,
                "isolated_wallet": isolated_wallet,
                "position_side": position_side,
                "reason": reason,
                "transaction_time": tx_time,
                "event_time": event_time,
            },
        )
    
    # -------------------------------------------------------------------------
    # ORDER_TRADE_UPDATE 처리
    # -------------------------------------------------------------------------
    
    def map_order_trade_update(self, msg: dict[str, Any]) -> list[Event]:
        """ORDER_TRADE_UPDATE 메시지 → Event 리스트
        
        Args:
            msg: ORDER_TRADE_UPDATE 메시지
            
        Returns:
            TradeExecuted, OrderPlaced, OrderCancelled 등 이벤트 리스트
        """
        events: list[Event] = []
        
        order_data = msg.get("o", {})
        if not order_data:
            return events
        
        symbol = order_data.get("s", "")
        if not symbol:
            return events
        
        # 체결 발생 확인
        execution_type = order_data.get("x", "")
        last_filled_qty = order_data.get("l", "0")
        
        # 체결 이벤트 (TRADE 실행이고 체결 수량 > 0)
        if execution_type == "TRADE" and Decimal(last_filled_qty) > Decimal("0"):
            trade_event = self._create_trade_executed_event(order_data)
            if trade_event:
                events.append(trade_event)
        
        # 주문 상태 변경 이벤트
        order_event = self._create_order_event(order_data)
        if order_event:
            events.append(order_event)
        
        return events
    
    def _create_trade_executed_event(self, data: dict[str, Any]) -> Event | None:
        """TradeExecuted 이벤트 생성"""
        symbol = data.get("s", "")
        trade_id = str(data.get("t", ""))
        
        if not trade_id or trade_id == "0":
            return None
        
        exchange_order_id = str(data.get("i", ""))
        client_order_id = data.get("c", "")
        side = data.get("S", "")
        last_qty = data.get("l", "0")
        last_price = data.get("L", "0")
        commission = data.get("n", "0")
        commission_asset = data.get("N", "")
        realized_pnl = data.get("rp", "0")
        trade_time = data.get("T", 0)
        is_maker = data.get("m", False)
        
        # dedup_key: TRD 규칙 준수
        dedup_key = make_trade_dedup_key(
            exchange=self.scope.exchange,
            venue=self.scope.venue,
            symbol=symbol,
            exchange_trade_id=trade_id,
        )
        
        scope_with_symbol = self._scope_with_symbol(symbol)
        
        return Event.create(
            event_type=EventTypes.TRADE_EXECUTED,
            source="WEBSOCKET",
            entity_kind="TRADE",
            entity_id=trade_id,
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "exchange_trade_id": trade_id,
                "exchange_order_id": exchange_order_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "qty": last_qty,
                "price": last_price,
                "commission": commission,
                "commission_asset": commission_asset,
                "realized_pnl": realized_pnl,
                "trade_time": trade_time,
                "is_maker": is_maker,
            },
        )
    
    def _create_order_event(self, data: dict[str, Any]) -> Event | None:
        """주문 상태 이벤트 생성 (OrderPlaced, OrderCancelled, OrderUpdated 등)"""
        symbol = data.get("s", "")
        exchange_order_id = str(data.get("i", ""))
        order_status = data.get("X", "")
        execution_type = data.get("x", "")
        
        if not exchange_order_id:
            return None
        
        # 이벤트 타입 결정
        event_type = self._determine_order_event_type(order_status, execution_type)
        if not event_type:
            return None
        
        client_order_id = data.get("c", "")
        side = data.get("S", "")
        order_type = data.get("o", "")
        time_in_force = data.get("f", "")
        original_qty = data.get("q", "0")
        price = data.get("p", "0")
        avg_price = data.get("ap", "0")
        stop_price = data.get("sp", "0")
        executed_qty = data.get("z", "0")
        cumulative_quote_qty = data.get("Z", "0")
        order_time = data.get("T", 0)
        update_time = data.get("E", 0)
        reduce_only = data.get("R", False)
        position_side = data.get("ps", "BOTH")
        
        # dedup_key: 주문 상태별로 고유하게
        # OrderPlaced는 기본 order dedup_key, 상태 변경은 상태별 dedup_key 사용
        if event_type == EventTypes.ORDER_PLACED:
            dedup_key = make_order_dedup_key(
                exchange=self.scope.exchange,
                venue=self.scope.venue,
                symbol=symbol,
                exchange_order_id=exchange_order_id,
            )
        else:
            # 상태 변경 시 상태+시간으로 고유화
            dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{symbol}:order:{exchange_order_id}:{order_status}:{update_time}"
        
        scope_with_symbol = self._scope_with_symbol(symbol)
        
        return Event.create(
            event_type=event_type,
            source="WEBSOCKET",
            entity_kind="ORDER",
            entity_id=exchange_order_id,
            scope=scope_with_symbol,
            dedup_key=dedup_key,
            payload={
                "exchange_order_id": exchange_order_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "order_status": order_status,
                "execution_type": execution_type,
                "time_in_force": time_in_force,
                "original_qty": original_qty,
                "executed_qty": executed_qty,
                "price": price,
                "avg_price": avg_price,
                "stop_price": stop_price,
                "cumulative_quote_qty": cumulative_quote_qty,
                "reduce_only": reduce_only,
                "position_side": position_side,
                "order_time": order_time,
                "update_time": update_time,
            },
        )
    
    def _determine_order_event_type(
        self,
        order_status: str,
        execution_type: str,
    ) -> str | None:
        """주문 상태/실행 타입에 따른 이벤트 타입 결정"""
        # 새 주문
        if order_status == "NEW" and execution_type == "NEW":
            return EventTypes.ORDER_PLACED
        
        # 취소됨
        if order_status == "CANCELED":
            return EventTypes.ORDER_CANCELLED
        
        # 거부됨
        if order_status == "REJECTED":
            return EventTypes.ORDER_REJECTED
        
        # 만료됨
        if order_status == "EXPIRED":
            return EventTypes.ORDER_CANCELLED  # 만료도 취소로 처리
        
        # 부분 체결 또는 완전 체결 (상태 업데이트)
        if order_status in ("PARTIALLY_FILLED", "FILLED"):
            return EventTypes.ORDER_UPDATED
        
        # 기타 상태 변경
        if execution_type in ("TRADE", "AMENDMENT"):
            return EventTypes.ORDER_UPDATED
        
        return None
    
    # -------------------------------------------------------------------------
    # MARGIN_CALL 처리
    # -------------------------------------------------------------------------
    
    def map_margin_call(self, msg: dict[str, Any]) -> list[Event]:
        """MARGIN_CALL 메시지 → Event 리스트
        
        Args:
            msg: MARGIN_CALL 메시지
            
        Returns:
            RiskGuardRejected 또는 관련 이벤트 리스트
        """
        events: list[Event] = []
        
        event_time = msg.get("E", 0)
        cross_wallet_balance = msg.get("cw", "0")
        positions = msg.get("p", [])
        
        for pos in positions:
            symbol = pos.get("s", "")
            position_side = pos.get("ps", "")
            position_amount = pos.get("pa", "0")
            margin_type = pos.get("mt", "")
            unrealized_pnl = pos.get("up", "0")
            maintenance_margin = pos.get("mm", "0")
            
            dedup_key = f"{self.scope.exchange}:{self.scope.venue}:{symbol}:margin_call:{event_time}"
            scope_with_symbol = self._scope_with_symbol(symbol)
            
            event = Event.create(
                event_type=EventTypes.RISK_GUARD_REJECTED,
                source="WEBSOCKET",
                entity_kind="POSITION",
                entity_id=symbol,
                scope=scope_with_symbol,
                dedup_key=dedup_key,
                payload={
                    "reason": "MARGIN_CALL",
                    "symbol": symbol,
                    "position_side": position_side,
                    "position_amount": position_amount,
                    "margin_type": margin_type,
                    "unrealized_pnl": unrealized_pnl,
                    "maintenance_margin": maintenance_margin,
                    "cross_wallet_balance": cross_wallet_balance,
                    "event_time": event_time,
                },
            )
            events.append(event)
        
        return events
    
    # -------------------------------------------------------------------------
    # WebSocket 상태 이벤트
    # -------------------------------------------------------------------------
    
    def create_ws_connected_event(self) -> Event:
        """WebSocketConnected 이벤트 생성"""
        now = datetime.now(timezone.utc)
        ts_ms = int(now.timestamp() * 1000)
        
        return Event.create(
            event_type=EventTypes.WS_CONNECTED,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="websocket",
            scope=self.scope,
            dedup_key=f"{self.scope.exchange}:ws:connected:{ts_ms}",
            payload={"connected_at": now.isoformat()},
        )
    
    def create_ws_disconnected_event(self, reason: str = "") -> Event:
        """WebSocketDisconnected 이벤트 생성"""
        now = datetime.now(timezone.utc)
        ts_ms = int(now.timestamp() * 1000)
        
        return Event.create(
            event_type=EventTypes.WS_DISCONNECTED,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="websocket",
            scope=self.scope,
            dedup_key=f"{self.scope.exchange}:ws:disconnected:{ts_ms}",
            payload={
                "disconnected_at": now.isoformat(),
                "reason": reason,
            },
        )
    
    def create_ws_reconnected_event(self) -> Event:
        """WebSocketReconnected 이벤트 생성"""
        now = datetime.now(timezone.utc)
        ts_ms = int(now.timestamp() * 1000)
        
        return Event.create(
            event_type=EventTypes.WS_RECONNECTED,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="websocket",
            scope=self.scope,
            dedup_key=f"{self.scope.exchange}:ws:reconnected:{ts_ms}",
            payload={"reconnected_at": now.isoformat()},
        )
