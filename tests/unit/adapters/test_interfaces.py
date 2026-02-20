"""
Protocol 인터페이스 테스트

Protocol 타입 검증 및 구현 확인.
"""

import pytest

from adapters.interfaces import (
    IExchangeRestClient,
    IExchangeWsClient,
    INotifier,
)
from adapters.mock.exchange_client import MockExchangeRestClient, MockExchangeWsClient
from adapters.mock.notifier import MockNotifier


class TestIExchangeRestClient:
    """IExchangeRestClient Protocol 테스트"""
    
    def test_mock_client_implements_protocol(self) -> None:
        """Mock 클라이언트가 Protocol을 구현하는지 확인"""
        client = MockExchangeRestClient()
        
        # Protocol 체크
        assert isinstance(client, IExchangeRestClient)
    
    def test_protocol_has_required_methods(self) -> None:
        """Protocol에 필수 메서드가 정의되어 있는지 확인"""
        # Protocol 메서드 목록 (typing.get_type_hints 대신 직접 확인)
        required_methods = [
            "create_listen_key",
            "extend_listen_key",
            "delete_listen_key",
            "get_balances",
            "get_position",
            "get_open_orders",
            "get_trades",
            "place_order",
            "cancel_order",
            "cancel_all_orders",
            "set_leverage",
            "get_exchange_info",
        ]
        
        client = MockExchangeRestClient()
        
        for method_name in required_methods:
            assert hasattr(client, method_name), f"Missing method: {method_name}"
            assert callable(getattr(client, method_name))


class TestIExchangeWsClient:
    """IExchangeWsClient Protocol 테스트"""
    
    def test_mock_client_implements_protocol(self) -> None:
        """Mock WebSocket 클라이언트가 Protocol을 구현하는지 확인"""
        async def dummy_callback(msg: dict) -> None:
            pass
        
        client = MockExchangeWsClient(on_message=dummy_callback)
        
        assert isinstance(client, IExchangeWsClient)
    
    def test_protocol_has_required_properties_and_methods(self) -> None:
        """Protocol에 필수 속성과 메서드가 있는지 확인"""
        async def dummy_callback(msg: dict) -> None:
            pass
        
        client = MockExchangeWsClient(on_message=dummy_callback)
        
        # state 속성
        assert hasattr(client, "state")
        
        # 메서드
        assert hasattr(client, "start")
        assert hasattr(client, "stop")


class TestINotifier:
    """INotifier Protocol 테스트"""
    
    def test_mock_notifier_implements_protocol(self) -> None:
        """Mock Notifier가 Protocol을 구현하는지 확인"""
        notifier = MockNotifier()
        
        assert isinstance(notifier, INotifier)
    
    def test_protocol_has_required_methods(self) -> None:
        """Protocol에 필수 메서드가 있는지 확인"""
        notifier = MockNotifier()
        
        assert hasattr(notifier, "send")
        assert hasattr(notifier, "send_trade_alert")
