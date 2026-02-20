"""
WebSocket 메시지 핸들러

Binance WebSocket 메시지를 수신하여 Event로 변환 후 저장.
전략 이벤트 콜백 지원 (on_trade, on_order_update).
"""

import logging
from typing import Any, Callable, Awaitable

from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState
from bot.websocket.mapper import WebSocketEventMapper
from strategies.base import TradeEvent, OrderEvent

logger = logging.getLogger(__name__)

# 콜백 타입 정의
TradeEventCallback = Callable[[TradeEvent], Awaitable[bool]]
OrderEventCallback = Callable[[OrderEvent], Awaitable[bool]]


class WebSocketMessageHandler:
    """WebSocket 메시지 핸들러
    
    Binance User Data Stream 메시지를 Event로 변환하여 EventStore에 저장.
    메시지 타입별로 적절한 이벤트 생성.
    
    전략 이벤트 콜백:
    - on_trade_callback: 체결 발생 시 호출 (TradeEvent)
    - on_order_callback: 주문 상태 변경 시 호출 (OrderEvent)
    
    Args:
        event_store: 이벤트 저장소
        scope: 기본 거래 범위
        target_symbol: 타겟 심볼 (None이면 모든 심볼 처리)
        on_trade_callback: 체결 이벤트 콜백 (선택)
        on_order_callback: 주문 이벤트 콜백 (선택)
    """
    
    def __init__(
        self,
        event_store: EventStore,
        scope: Scope,
        target_symbol: str | None = None,
        on_trade_callback: TradeEventCallback | None = None,
        on_order_callback: OrderEventCallback | None = None,
    ):
        self.event_store = event_store
        self.scope = scope
        self.target_symbol = target_symbol
        self.mapper = WebSocketEventMapper(scope)
        
        # 전략 이벤트 콜백
        self._on_trade_callback = on_trade_callback
        self._on_order_callback = on_order_callback
        
        # 통계
        self._message_count = 0
        self._event_count = 0
        self._error_count = 0
        self._strategy_callback_count = 0
    
    async def handle(self, message: dict[str, Any]) -> int:
        """메시지 처리
        
        Args:
            message: WebSocket 메시지 (JSON 파싱됨)
            
        Returns:
            저장된 이벤트 수
        """
        self._message_count += 1
        
        try:
            event_type = message.get("e")
            
            if event_type == "ACCOUNT_UPDATE":
                events = await self._handle_account_update(message)
            elif event_type == "ORDER_TRADE_UPDATE":
                events = await self._handle_order_trade_update(message)
            elif event_type == "MARGIN_CALL":
                events = await self._handle_margin_call(message)
            elif event_type == "listenKeyExpired":
                # listenKey 만료 - 재연결 필요
                logger.warning("listenKey expired, reconnection needed")
                events = []
            else:
                # 알 수 없는 메시지 타입 (무시)
                logger.debug(f"Unknown message type: {event_type}")
                events = []
            
            return len(events)
            
        except Exception as e:
            self._error_count += 1
            logger.error(
                "메시지 처리 실패",
                extra={"error": str(e), "message_type": message.get("e")},
            )
            return 0
    
    async def _handle_account_update(self, msg: dict[str, Any]) -> list:
        """ACCOUNT_UPDATE 처리"""
        events = self.mapper.map_account_update(msg)
        
        saved_events = []
        for event in events:
            # 타겟 심볼 필터링 (포지션 이벤트의 경우)
            if self.target_symbol and event.scope.symbol:
                if event.scope.symbol != self.target_symbol:
                    continue
            
            saved = await self.event_store.append(event)
            if saved:
                self._event_count += 1
                saved_events.append(event)
                logger.debug(
                    f"Event saved: {event.event_type}",
                    extra={
                        "event_id": event.event_id,
                        "entity_id": event.entity_id,
                    },
                )
        
        return saved_events
    
    async def _handle_order_trade_update(self, msg: dict[str, Any]) -> list:
        """ORDER_TRADE_UPDATE 처리"""
        # 타겟 심볼 필터링
        order_data = msg.get("o", {})
        symbol = order_data.get("s", "")
        
        if self.target_symbol and symbol != self.target_symbol:
            return []
        
        events = self.mapper.map_order_trade_update(msg)
        
        saved_events = []
        for event in events:
            saved = await self.event_store.append(event)
            if saved:
                self._event_count += 1
                saved_events.append(event)
                logger.debug(
                    f"Event saved: {event.event_type}",
                    extra={
                        "event_id": event.event_id,
                        "entity_id": event.entity_id,
                    },
                )
        
        # 전략 이벤트 콜백 호출 (이벤트 저장 후 즉시)
        await self._dispatch_strategy_callbacks(msg)
        
        return saved_events
    
    async def _dispatch_strategy_callbacks(self, msg: dict[str, Any]) -> None:
        """전략 이벤트 콜백 디스패치
        
        ORDER_TRADE_UPDATE 메시지에서 TradeEvent/OrderEvent를 생성하고
        등록된 콜백에 전달.
        """
        # TradeEvent 콜백
        if self._on_trade_callback:
            try:
                trade_event = self.mapper.create_strategy_trade_event(msg)
                if trade_event:
                    self._strategy_callback_count += 1
                    await self._on_trade_callback(trade_event)
                    logger.debug(
                        f"Strategy on_trade callback executed",
                        extra={"trade_id": trade_event.trade_id},
                    )
            except Exception as e:
                logger.error(
                    f"Strategy on_trade callback failed: {e}",
                    extra={"error": str(e)},
                )
        
        # OrderEvent 콜백
        if self._on_order_callback:
            try:
                order_event = self.mapper.create_strategy_order_event(msg)
                if order_event:
                    self._strategy_callback_count += 1
                    await self._on_order_callback(order_event)
                    logger.debug(
                        f"Strategy on_order callback executed",
                        extra={"order_id": order_event.order_id, "status": order_event.status},
                    )
            except Exception as e:
                logger.error(
                    f"Strategy on_order callback failed: {e}",
                    extra={"error": str(e)},
                )
    
    def set_trade_callback(self, callback: TradeEventCallback | None) -> None:
        """체결 이벤트 콜백 설정
        
        Args:
            callback: 체결 이벤트 콜백 함수 (None이면 해제)
        """
        self._on_trade_callback = callback
    
    def set_order_callback(self, callback: OrderEventCallback | None) -> None:
        """주문 이벤트 콜백 설정
        
        Args:
            callback: 주문 이벤트 콜백 함수 (None이면 해제)
        """
        self._on_order_callback = callback
    
    async def _handle_margin_call(self, msg: dict[str, Any]) -> list:
        """MARGIN_CALL 처리"""
        events = self.mapper.map_margin_call(msg)
        
        saved_events = []
        for event in events:
            # 타겟 심볼 필터링
            if self.target_symbol and event.scope.symbol:
                if event.scope.symbol != self.target_symbol:
                    continue
            
            saved = await self.event_store.append(event)
            if saved:
                self._event_count += 1
                saved_events.append(event)
                logger.warning(
                    f"MARGIN_CALL event saved",
                    extra={
                        "event_id": event.event_id,
                        "symbol": event.scope.symbol,
                    },
                )
        
        return saved_events
    
    async def on_state_change(self, new_state: WebSocketState) -> None:
        """WebSocket 상태 변경 처리
        
        Args:
            new_state: 새로운 상태
        """
        # 상태 변경 이벤트 생성 및 저장
        if new_state == WebSocketState.CONNECTED:
            event = self.mapper.create_ws_connected_event()
        elif new_state == WebSocketState.DISCONNECTED:
            event = self.mapper.create_ws_disconnected_event()
        elif new_state == WebSocketState.RECONNECTING:
            event = self.mapper.create_ws_disconnected_event(reason="reconnecting")
            # RECONNECTING은 이후 CONNECTED 시 reconnected 이벤트 생성
        else:
            return
        
        saved = await self.event_store.append(event)
        if saved:
            self._event_count += 1
            logger.info(
                f"WebSocket state event saved: {event.event_type}",
                extra={"state": new_state.value},
            )
    
    def get_stats(self) -> dict[str, int]:
        """통계 반환"""
        return {
            "message_count": self._message_count,
            "event_count": self._event_count,
            "error_count": self._error_count,
            "strategy_callback_count": self._strategy_callback_count,
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._message_count = 0
        self._event_count = 0
        self._error_count = 0
        self._strategy_callback_count = 0
