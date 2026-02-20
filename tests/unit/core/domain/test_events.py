"""
core/domain/events.py 테스트

Event 생성, 직렬화, EventTypes 검증
"""

from datetime import datetime, timezone

from core.domain.events import Event, EventTypes
from core.types import Scope, EventSource, EntityKind


class TestEventCreate:
    """Event.create 테스트"""

    def test_basic_creation(self) -> None:
        """기본 생성"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="XRPUSDT",
            mode="testnet",
        )
        event = Event.create(
            event_type=EventTypes.TRADE_EXECUTED,
            source=EventSource.WEBSOCKET.value,
            entity_kind=EntityKind.TRADE.value,
            entity_id="trade-123",
            scope=scope,
            dedup_key="BINANCE:FUTURES:XRPUSDT:trade:123",
            payload={"price": "0.5", "qty": "100"},
        )

        assert event.event_type == "TradeExecuted"
        assert event.source == "WEBSOCKET"
        assert event.entity_kind == "TRADE"
        assert event.entity_id == "trade-123"
        assert event.scope == scope
        assert event.dedup_key == "BINANCE:FUTURES:XRPUSDT:trade:123"
        assert event.payload == {"price": "0.5", "qty": "100"}

    def test_auto_generated_fields(self) -> None:
        """자동 생성 필드 확인"""
        scope = Scope.create()
        event = Event.create(
            event_type=EventTypes.ENGINE_STARTED,
            source=EventSource.BOT.value,
            entity_kind=EntityKind.ENGINE.value,
            entity_id="engine-1",
            scope=scope,
            dedup_key="engine:started:123",
            payload={},
        )

        # event_id는 UUID 형식
        assert len(event.event_id) == 36
        assert event.event_id.count("-") == 4

        # correlation_id도 자동 생성
        assert len(event.correlation_id) == 36

        # ts는 UTC
        assert event.ts.tzinfo == timezone.utc

        # causation_id, command_id는 None
        assert event.causation_id is None
        assert event.command_id is None

    def test_with_correlation_id(self) -> None:
        """correlation_id 지정"""
        scope = Scope.create()
        event = Event.create(
            event_type=EventTypes.ORDER_PLACED,
            source=EventSource.BOT.value,
            entity_kind=EntityKind.ORDER.value,
            entity_id="order-1",
            scope=scope,
            dedup_key="BINANCE:FUTURES:XRPUSDT:order:1",
            payload={},
            correlation_id="my-correlation-id",
        )

        assert event.correlation_id == "my-correlation-id"

    def test_with_command_id(self) -> None:
        """command_id 지정"""
        scope = Scope.create()
        event = Event.create(
            event_type=EventTypes.ORDER_PLACED,
            source=EventSource.BOT.value,
            entity_kind=EntityKind.ORDER.value,
            entity_id="order-1",
            scope=scope,
            dedup_key="BINANCE:FUTURES:XRPUSDT:order:1",
            payload={},
            command_id="cmd-123",
        )

        assert event.command_id == "cmd-123"

    def test_with_causation_id(self) -> None:
        """causation_id 지정"""
        scope = Scope.create()
        event = Event.create(
            event_type=EventTypes.POSITION_CHANGED,
            source=EventSource.WEBSOCKET.value,
            entity_kind=EntityKind.POSITION.value,
            entity_id="pos-1",
            scope=scope,
            dedup_key="BINANCE:FUTURES:XRPUSDT:position:LONG:100:0.5",
            payload={},
            causation_id="previous-event-id",
        )

        assert event.causation_id == "previous-event-id"


class TestEventToDict:
    """Event.to_dict 테스트"""

    def test_serialization(self) -> None:
        """딕셔너리 직렬화"""
        scope = Scope(
            exchange="BINANCE",
            venue="FUTURES",
            account_id="main",
            symbol="BTCUSDT",
            mode="production",
        )
        event = Event.create(
            event_type=EventTypes.BALANCE_CHANGED,
            source=EventSource.REST.value,
            entity_kind=EntityKind.BALANCE.value,
            entity_id="balance-usdt",
            scope=scope,
            dedup_key="BINANCE:FUTURES:main:USDT:1000:0",
            payload={"asset": "USDT", "free": "1000", "locked": "0"},
        )

        data = event.to_dict()

        assert data["event_id"] == event.event_id
        assert data["event_type"] == "BalanceChanged"
        assert data["source"] == "REST"
        assert data["entity_kind"] == "BALANCE"
        assert data["dedup_key"] == "BINANCE:FUTURES:main:USDT:1000:0"
        assert data["scope"]["exchange"] == "BINANCE"
        assert data["scope"]["venue"] == "FUTURES"
        assert data["scope"]["symbol"] == "BTCUSDT"
        assert data["scope"]["mode"] == "production"
        assert data["payload"]["asset"] == "USDT"

    def test_ts_is_iso_format(self) -> None:
        """ts가 ISO 형식 문자열"""
        scope = Scope.create()
        event = Event.create(
            event_type=EventTypes.ENGINE_STARTED,
            source=EventSource.BOT.value,
            entity_kind=EntityKind.ENGINE.value,
            entity_id="engine-1",
            scope=scope,
            dedup_key="engine:started:123",
            payload={},
        )

        data = event.to_dict()

        # ISO 형식 확인
        assert isinstance(data["ts"], str)
        assert "T" in data["ts"]
        # 파싱 가능해야 함
        parsed = datetime.fromisoformat(data["ts"])
        assert parsed.tzinfo is not None


class TestEventFromDict:
    """Event.from_dict 테스트"""

    def test_deserialization(self) -> None:
        """딕셔너리에서 복원"""
        data = {
            "event_id": "123e4567-e89b-12d3-a456-426614174000",
            "event_type": "TradeExecuted",
            "ts": "2026-02-20T12:00:00+00:00",
            "correlation_id": "corr-123",
            "causation_id": None,
            "command_id": "cmd-456",
            "source": "WEBSOCKET",
            "entity_kind": "TRADE",
            "entity_id": "trade-789",
            "scope": {
                "exchange": "BINANCE",
                "venue": "FUTURES",
                "account_id": "main",
                "symbol": "XRPUSDT",
                "mode": "testnet",
            },
            "dedup_key": "BINANCE:FUTURES:XRPUSDT:trade:789",
            "payload": {"price": "0.5123", "qty": "100"},
        }

        event = Event.from_dict(data)

        assert event.event_id == "123e4567-e89b-12d3-a456-426614174000"
        assert event.event_type == "TradeExecuted"
        assert event.ts.year == 2026
        assert event.correlation_id == "corr-123"
        assert event.causation_id is None
        assert event.command_id == "cmd-456"
        assert event.source == "WEBSOCKET"
        assert event.entity_kind == "TRADE"
        assert event.scope.symbol == "XRPUSDT"
        assert event.payload["price"] == "0.5123"

    def test_roundtrip(self) -> None:
        """직렬화 → 역직렬화 왕복"""
        scope = Scope.create(symbol="ETHUSDT", mode="production")
        original = Event.create(
            event_type=EventTypes.ORDER_CANCELLED,
            source=EventSource.BOT.value,
            entity_kind=EntityKind.ORDER.value,
            entity_id="order-abc",
            scope=scope,
            dedup_key="BINANCE:FUTURES:ETHUSDT:order:abc",
            payload={"reason": "user_requested"},
            command_id="cmd-xyz",
        )

        data = original.to_dict()
        restored = Event.from_dict(data)

        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.correlation_id == original.correlation_id
        assert restored.command_id == original.command_id
        assert restored.scope == original.scope
        assert restored.dedup_key == original.dedup_key
        assert restored.payload == original.payload


class TestEventTypes:
    """EventTypes 상수 테스트"""

    def test_engine_events(self) -> None:
        """Engine 이벤트 확인"""
        assert EventTypes.ENGINE_STARTED == "EngineStarted"
        assert EventTypes.ENGINE_STOPPED == "EngineStopped"
        assert EventTypes.ENGINE_PAUSED == "EnginePaused"
        assert EventTypes.ENGINE_RESUMED == "EngineResumed"
        assert EventTypes.ENGINE_MODE_CHANGED == "EngineModeChanged"

    def test_websocket_events(self) -> None:
        """WebSocket 이벤트 확인"""
        assert EventTypes.WS_CONNECTED == "WebSocketConnected"
        assert EventTypes.WS_DISCONNECTED == "WebSocketDisconnected"
        assert EventTypes.WS_RECONNECTED == "WebSocketReconnected"

    def test_order_events(self) -> None:
        """주문 이벤트 확인"""
        assert EventTypes.ORDER_PLACED == "OrderPlaced"
        assert EventTypes.ORDER_REJECTED == "OrderRejected"
        assert EventTypes.ORDER_CANCELLED == "OrderCancelled"
        assert EventTypes.ORDER_UPDATED == "OrderUpdated"
        assert EventTypes.TRADE_EXECUTED == "TradeExecuted"

    def test_position_balance_events(self) -> None:
        """포지션/잔고 이벤트 확인"""
        assert EventTypes.POSITION_CHANGED == "PositionChanged"
        assert EventTypes.BALANCE_CHANGED == "BalanceChanged"
        assert EventTypes.FEE_CHARGED == "FeeCharged"
        assert EventTypes.FUNDING_APPLIED == "FundingApplied"

    def test_reconciliation_events(self) -> None:
        """Reconciliation 이벤트 확인"""
        assert EventTypes.DRIFT_DETECTED == "DriftDetected"
        assert EventTypes.RECONCILIATION_PERFORMED == "ReconciliationPerformed"

    def test_all_types(self) -> None:
        """all_types 메서드"""
        all_types = EventTypes.all_types()
        assert isinstance(all_types, list)
        assert len(all_types) > 20  # 최소 20개 이상
        assert "TradeExecuted" in all_types
        assert "EngineStarted" in all_types

    def test_is_valid_type(self) -> None:
        """is_valid_type 메서드"""
        assert EventTypes.is_valid_type("TradeExecuted") is True
        assert EventTypes.is_valid_type("OrderPlaced") is True
        assert EventTypes.is_valid_type("InvalidEvent") is False
        assert EventTypes.is_valid_type("") is False


class TestEventEquality:
    """Event 동등성 테스트"""

    def test_same_event_id(self) -> None:
        """같은 event_id면 같은 이벤트"""
        scope = Scope.create()
        event1 = Event(
            event_id="same-id",
            event_type="Test",
            ts=datetime.now(timezone.utc),
            correlation_id="corr",
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="eng-1",
            scope=scope,
            dedup_key="test:1",
            payload={},
        )
        event2 = Event(
            event_id="same-id",
            event_type="Test",
            ts=datetime.now(timezone.utc),
            correlation_id="corr",
            causation_id=None,
            command_id=None,
            source="BOT",
            entity_kind="ENGINE",
            entity_id="eng-1",
            scope=scope,
            dedup_key="test:1",
            payload={},
        )

        assert event1.event_id == event2.event_id
