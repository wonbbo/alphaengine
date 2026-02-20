"""
WebSocket Listener

Binance WebSocket 클라이언트를 래핑하여 이벤트 수신 및 저장 관리
"""

import logging
from typing import Any

from adapters.binance.ws_client import BinanceWsClient
from adapters.binance.rest_client import BinanceRestClient
from core.storage.event_store import EventStore
from core.types import Scope, WebSocketState
from bot.websocket.handler import (
    WebSocketMessageHandler,
    TradeEventCallback,
    OrderEventCallback,
)

logger = logging.getLogger(__name__)


class WebSocketListener:
    """WebSocket 리스너
    
    BinanceWsClient를 래핑하여 메시지 수신 → Event 저장을 자동화.
    상태 변경 시 이벤트 생성 및 콜백 호출.
    
    Args:
        ws_base_url: WebSocket 베이스 URL
        rest_client: REST 클라이언트 (listenKey 관리용)
        event_store: 이벤트 저장소
        scope: 기본 거래 범위
        target_symbol: 타겟 심볼 (None이면 모든 심볼 처리)
    
    사용 예시:
    ```python
    listener = WebSocketListener(
        ws_base_url=settings.ws_url,
        rest_client=rest_client,
        event_store=event_store,
        scope=scope,
        target_symbol="XRPUSDT",
    )
    
    await listener.start()
    # ... 메인 루프 ...
    await listener.stop()
    ```
    """
    
    def __init__(
        self,
        ws_base_url: str,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        scope: Scope,
        target_symbol: str | None = None,
    ):
        self.ws_base_url = ws_base_url
        self.rest_client = rest_client
        self.event_store = event_store
        self.scope = scope
        self.target_symbol = target_symbol
        
        # 메시지 핸들러
        self._handler = WebSocketMessageHandler(
            event_store=event_store,
            scope=scope,
            target_symbol=target_symbol,
        )
        
        # WebSocket 클라이언트
        self._ws_client = BinanceWsClient(
            ws_base_url=ws_base_url,
            rest_client=rest_client,
            on_message=self._on_message,
            on_state_change=self._on_state_change,
        )
        
        # 외부 상태 변경 콜백 (선택적)
        self._external_state_callback: Any = None
    
    @property
    def state(self) -> WebSocketState:
        """현재 WebSocket 상태"""
        return self._ws_client.state
    
    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._ws_client.state == WebSocketState.CONNECTED
    
    def set_state_callback(self, callback: Any) -> None:
        """외부 상태 변경 콜백 설정
        
        Args:
            callback: async def callback(state: WebSocketState) -> None
        """
        self._external_state_callback = callback
    
    def set_trade_callback(self, callback: TradeEventCallback | None) -> None:
        """체결 이벤트 콜백 설정 (전략 on_trade용)
        
        WebSocket에서 체결 발생 시 즉시 호출됩니다.
        
        Args:
            callback: async def callback(trade: TradeEvent) -> bool
        """
        self._handler.set_trade_callback(callback)
    
    def set_order_callback(self, callback: OrderEventCallback | None) -> None:
        """주문 이벤트 콜백 설정 (전략 on_order_update용)
        
        WebSocket에서 주문 상태 변경 시 즉시 호출됩니다.
        
        Args:
            callback: async def callback(order: OrderEvent) -> bool
        """
        self._handler.set_order_callback(callback)
    
    async def start(self) -> None:
        """WebSocket 연결 시작"""
        logger.info(
            "WebSocket listener starting",
            extra={
                "url": self.ws_base_url,
                "target_symbol": self.target_symbol,
            },
        )
        await self._ws_client.start()
    
    async def stop(self) -> None:
        """WebSocket 연결 종료"""
        logger.info("WebSocket listener stopping")
        await self._ws_client.stop()
    
    async def _on_message(self, message: dict[str, Any]) -> None:
        """메시지 수신 콜백 (내부용)
        
        Args:
            message: WebSocket 메시지 (JSON 파싱됨)
        """
        try:
            await self._handler.handle(message)
        except Exception as e:
            logger.error(
                "메시지 처리 중 예외 발생",
                extra={"error": str(e)},
            )
    
    async def _on_state_change(self, new_state: WebSocketState) -> None:
        """상태 변경 콜백 (내부용)
        
        Args:
            new_state: 새로운 상태
        """
        # 핸들러에 상태 변경 전달 (이벤트 생성)
        await self._handler.on_state_change(new_state)
        
        # 외부 콜백 호출 (있는 경우)
        if self._external_state_callback is not None:
            try:
                await self._external_state_callback(new_state)
            except Exception as e:
                logger.error(
                    "외부 상태 콜백 에러",
                    extra={"error": str(e)},
                )
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "state": self.state.value,
            "handler_stats": self._handler.get_stats(),
        }
    
    # -------------------------------------------------------------------------
    # 컨텍스트 매니저
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "WebSocketListener":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
