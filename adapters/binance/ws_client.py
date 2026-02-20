"""
Binance Futures WebSocket 클라이언트

User Data Stream을 통해 실시간 계좌/주문/포지션 변경 수신.
IExchangeWsClient Protocol 준수.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Awaitable

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

from core.types import WebSocketState

logger = logging.getLogger(__name__)


# 콜백 타입 정의
MessageCallback = Callable[[dict[str, Any]], Awaitable[None]]
StateChangeCallback = Callable[[WebSocketState], Awaitable[None]]


class BinanceWsClient:
    """Binance Futures WebSocket 클라이언트
    
    User Data Stream을 통해 실시간 이벤트 수신:
    - ACCOUNT_UPDATE: 잔고/포지션 변경
    - ORDER_TRADE_UPDATE: 주문 상태/체결 변경
    - MARGIN_CALL: 마진 콜 알림
    
    Args:
        ws_base_url: WebSocket 베이스 URL (예: wss://fstream.binance.com)
        rest_client: REST 클라이언트 (listenKey 관리용)
        on_message: 메시지 수신 콜백
        on_state_change: 상태 변경 콜백
    """
    
    # 상수
    KEEPALIVE_INTERVAL = 30 * 60  # 30분 (listenKey 갱신 주기)
    RECONNECT_MIN_DELAY = 1  # 최소 재연결 대기 (초)
    RECONNECT_MAX_DELAY = 30  # 최대 재연결 대기 (초)
    PING_INTERVAL = 30  # ping 간격 (초)
    PING_TIMEOUT = 10  # ping 타임아웃 (초)
    
    def __init__(
        self,
        ws_base_url: str,
        rest_client: Any,  # BinanceRestClient (순환 참조 방지)
        on_message: MessageCallback,
        on_state_change: StateChangeCallback | None = None,
    ):
        self.ws_base_url = ws_base_url.rstrip("/")
        self.rest_client = rest_client
        self.on_message = on_message
        self.on_state_change = on_state_change
        
        self._state = WebSocketState.DISCONNECTED
        self._listen_key: str | None = None
        self._ws: WebSocketClientProtocol | None = None
        
        # 태스크 관리
        self._receive_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._should_reconnect = False
    
    @property
    def state(self) -> WebSocketState:
        """현재 연결 상태"""
        return self._state
    
    async def start(self) -> None:
        """WebSocket 연결 시작"""
        self._should_reconnect = True
        await self._connect()
    
    async def stop(self) -> None:
        """WebSocket 연결 종료"""
        self._should_reconnect = False
        await self._disconnect()
    
    async def _connect(self) -> None:
        """내부 연결 수행"""
        try:
            await self._set_state(WebSocketState.CONNECTING)
            
            # listenKey 생성
            self._listen_key = await self.rest_client.create_listen_key()
            
            # WebSocket 연결
            ws_url = f"{self.ws_base_url}/ws/{self._listen_key}"
            
            self._ws = await websockets.connect(
                ws_url,
                ping_interval=self.PING_INTERVAL,
                ping_timeout=self.PING_TIMEOUT,
            )
            
            await self._set_state(WebSocketState.CONNECTED)
            logger.info("WebSocket 연결 성공", extra={"url": ws_url})
            
            # 백그라운드 태스크 시작
            self._receive_task = asyncio.create_task(self._receive_loop())
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            
        except Exception as e:
            logger.error("WebSocket 연결 실패", extra={"error": str(e)})
            await self._handle_error(e)
    
    async def _disconnect(self) -> None:
        """내부 연결 종료"""
        # 태스크 취소
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
        
        if self._receive_task is not None:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
            self._receive_task = None
        
        # WebSocket 종료
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        
        # listenKey 삭제 (선택적)
        try:
            if self._listen_key is not None:
                await self.rest_client.delete_listen_key()
        except Exception:
            pass
        self._listen_key = None
        
        await self._set_state(WebSocketState.DISCONNECTED)
        logger.info("WebSocket 연결 종료")
    
    async def _receive_loop(self) -> None:
        """메시지 수신 루프"""
        if self._ws is None:
            return
        
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    await self.on_message(data)
                except json.JSONDecodeError as e:
                    logger.warning(
                        "메시지 파싱 실패",
                        extra={"error": str(e), "message": message[:100]},
                    )
                except Exception as e:
                    logger.error(
                        "메시지 처리 중 에러",
                        extra={"error": str(e)},
                    )
        except ConnectionClosed as e:
            logger.warning(
                "WebSocket 연결 끊김",
                extra={"code": e.code, "reason": e.reason},
            )
            await self._handle_disconnect()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("수신 루프 에러", extra={"error": str(e)})
            await self._handle_error(e)
    
    async def _keepalive_loop(self) -> None:
        """listenKey 갱신 루프 (30분마다)"""
        try:
            while self._state == WebSocketState.CONNECTED:
                await asyncio.sleep(self.KEEPALIVE_INTERVAL)
                
                if self._state != WebSocketState.CONNECTED:
                    break
                
                try:
                    await self.rest_client.extend_listen_key()
                    logger.debug("listenKey 갱신 완료")
                except Exception as e:
                    logger.error(
                        "listenKey 갱신 실패, 재연결 시도",
                        extra={"error": str(e)},
                    )
                    await self._handle_error(e)
                    break
        except asyncio.CancelledError:
            raise
    
    async def _handle_disconnect(self) -> None:
        """연결 끊김 처리"""
        if not self._should_reconnect:
            await self._set_state(WebSocketState.DISCONNECTED)
            return
        
        await self._set_state(WebSocketState.RECONNECTING)
        await self._reconnect_with_backoff()
    
    async def _handle_error(self, error: Exception) -> None:
        """에러 처리 (재연결 시도)"""
        if not self._should_reconnect:
            await self._set_state(WebSocketState.DISCONNECTED)
            return
        
        await self._set_state(WebSocketState.RECONNECTING)
        await self._reconnect_with_backoff()
    
    async def _reconnect_with_backoff(self) -> None:
        """지수 백오프로 재연결"""
        delay = self.RECONNECT_MIN_DELAY
        
        while self._should_reconnect and self._state == WebSocketState.RECONNECTING:
            try:
                logger.info(
                    "WebSocket 재연결 시도",
                    extra={"delay": delay},
                )
                
                # 기존 연결 정리
                if self._ws is not None:
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                
                # 재연결
                await self._connect()
                return
                
            except Exception as e:
                logger.warning(
                    "재연결 실패",
                    extra={"error": str(e), "next_delay": delay},
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.RECONNECT_MAX_DELAY)
    
    async def _set_state(self, new_state: WebSocketState) -> None:
        """상태 변경 및 콜백 호출"""
        old_state = self._state
        self._state = new_state
        
        if old_state != new_state:
            logger.info(
                "WebSocket 상태 변경",
                extra={"old_state": old_state.value, "new_state": new_state.value},
            )
            
            if self.on_state_change is not None:
                try:
                    await self.on_state_change(new_state)
                except Exception as e:
                    logger.error(
                        "상태 변경 콜백 에러",
                        extra={"error": str(e)},
                    )
    
    # -------------------------------------------------------------------------
    # 컨텍스트 매니저
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "BinanceWsClient":
        await self.start()
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
