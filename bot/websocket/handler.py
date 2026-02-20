"""
WebSocket 메시지 핸들러

Binance WebSocket 메시지를 수신하여 Event로 변환 후 저장
"""

import logging
from typing import Any

from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState
from bot.websocket.mapper import WebSocketEventMapper

logger = logging.getLogger(__name__)


class WebSocketMessageHandler:
    """WebSocket 메시지 핸들러
    
    Binance User Data Stream 메시지를 Event로 변환하여 EventStore에 저장.
    메시지 타입별로 적절한 이벤트 생성.
    
    Args:
        event_store: 이벤트 저장소
        scope: 기본 거래 범위
        target_symbol: 타겟 심볼 (None이면 모든 심볼 처리)
    """
    
    def __init__(
        self,
        event_store: EventStore,
        scope: Scope,
        target_symbol: str | None = None,
    ):
        self.event_store = event_store
        self.scope = scope
        self.target_symbol = target_symbol
        self.mapper = WebSocketEventMapper(scope)
        
        # 통계
        self._message_count = 0
        self._event_count = 0
        self._error_count = 0
    
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
        
        return saved_events
    
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
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._message_count = 0
        self._event_count = 0
        self._error_count = 0
