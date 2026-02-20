"""
Binance WebSocket 클라이언트 테스트

BinanceWsClient 기본 기능 테스트.
연결 테스트는 통합 테스트에서 수행.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.binance.ws_client import BinanceWsClient
from core.types import WebSocketState


class TestBinanceWsClientState:
    """WebSocket 상태 테스트"""
    
    def test_initial_state_disconnected(self) -> None:
        """초기 상태는 DISCONNECTED"""
        mock_rest_client = MagicMock()
        
        async def on_message(msg: dict) -> None:
            pass
        
        client = BinanceWsClient(
            ws_base_url="wss://fstream.binance.com",
            rest_client=mock_rest_client,
            on_message=on_message,
        )
        
        assert client.state == WebSocketState.DISCONNECTED
    
    def test_client_has_callbacks(self) -> None:
        """콜백 설정 확인"""
        mock_rest_client = MagicMock()
        
        async def on_message(msg: dict) -> None:
            pass
        
        async def on_state_change(state: WebSocketState) -> None:
            pass
        
        client = BinanceWsClient(
            ws_base_url="wss://fstream.binance.com",
            rest_client=mock_rest_client,
            on_message=on_message,
            on_state_change=on_state_change,
        )
        
        assert client.on_message is not None
        assert client.on_state_change is not None


class TestBinanceWsClientConstants:
    """상수 테스트"""
    
    def test_keepalive_interval(self) -> None:
        """listenKey 갱신 주기 30분"""
        assert BinanceWsClient.KEEPALIVE_INTERVAL == 30 * 60
    
    def test_reconnect_delays(self) -> None:
        """재연결 딜레이 범위"""
        assert BinanceWsClient.RECONNECT_MIN_DELAY == 1
        assert BinanceWsClient.RECONNECT_MAX_DELAY == 30
    
    def test_ping_settings(self) -> None:
        """ping 설정"""
        assert BinanceWsClient.PING_INTERVAL == 30
        assert BinanceWsClient.PING_TIMEOUT == 10


class TestBinanceWsClientConfiguration:
    """설정 테스트"""
    
    def test_ws_base_url_stored(self) -> None:
        """WebSocket URL 저장"""
        mock_rest_client = MagicMock()
        
        async def on_message(msg: dict) -> None:
            pass
        
        client = BinanceWsClient(
            ws_base_url="wss://stream.binancefuture.com",
            rest_client=mock_rest_client,
            on_message=on_message,
        )
        
        assert client.ws_base_url == "wss://stream.binancefuture.com"
    
    def test_rest_client_stored(self) -> None:
        """REST 클라이언트 저장"""
        mock_rest_client = MagicMock()
        
        async def on_message(msg: dict) -> None:
            pass
        
        client = BinanceWsClient(
            ws_base_url="wss://fstream.binance.com",
            rest_client=mock_rest_client,
            on_message=on_message,
        )
        
        assert client.rest_client is mock_rest_client


class TestBinanceWsClientStateProperty:
    """상태 속성 테스트"""
    
    def test_state_property_returns_current_state(self) -> None:
        """state 속성 반환"""
        mock_rest_client = MagicMock()
        
        async def on_message(msg: dict) -> None:
            pass
        
        client = BinanceWsClient(
            ws_base_url="wss://fstream.binance.com",
            rest_client=mock_rest_client,
            on_message=on_message,
        )
        
        # 초기 상태
        assert client.state == WebSocketState.DISCONNECTED
        
        # 내부 상태 변경 시뮬레이션
        client._state = WebSocketState.CONNECTING
        assert client.state == WebSocketState.CONNECTING
        
        client._state = WebSocketState.CONNECTED
        assert client.state == WebSocketState.CONNECTED
        
        client._state = WebSocketState.RECONNECTING
        assert client.state == WebSocketState.RECONNECTING
