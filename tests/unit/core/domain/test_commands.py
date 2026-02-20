"""
core/domain/commands.py 테스트

Command 생성, 상태 전이, 직렬화, CommandTypes 검증
"""

from datetime import datetime, timezone

from core.domain.commands import Command, CommandTypes, CommandPriority
from core.types import Scope, Actor, CommandStatus


class TestCommandCreate:
    """Command.create 테스트"""

    def test_basic_creation(self) -> None:
        """기본 생성"""
        actor = Actor.strategy("sma_cross")
        scope = Scope.create(symbol="XRPUSDT")
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={
                "side": "BUY",
                "order_type": "MARKET",
                "qty": "100",
            },
        )

        assert command.command_type == "PlaceOrder"
        assert command.actor == actor
        assert command.scope == scope
        assert command.status == "NEW"
        assert command.priority == 0
        assert command.payload["side"] == "BUY"

    def test_auto_generated_fields(self) -> None:
        """자동 생성 필드 확인"""
        actor = Actor.user("admin")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PAUSE_ENGINE,
            actor=actor,
            scope=scope,
            payload={"reason": "maintenance"},
        )

        # command_id는 UUID 형식
        assert len(command.command_id) == 36
        assert command.command_id.count("-") == 4

        # correlation_id도 자동 생성
        assert len(command.correlation_id) == 36

        # idempotency_key 기본값은 command_id
        assert command.idempotency_key == command.command_id

        # ts는 UTC
        assert command.ts.tzinfo == timezone.utc

        # 초기 상태
        assert command.status == CommandStatus.NEW.value
        assert command.result is None
        assert command.last_error is None
        assert command.causation_id is None

    def test_with_priority(self) -> None:
        """우선순위 지정"""
        actor = Actor.web("dashboard")
        scope = Scope.create(symbol="BTCUSDT")
        command = Command.create(
            command_type=CommandTypes.CANCEL_ALL,
            actor=actor,
            scope=scope,
            payload={"reason": "emergency"},
            priority=CommandPriority.WEB_URGENT,
        )

        assert command.priority == 100

    def test_with_custom_idempotency_key(self) -> None:
        """사용자 정의 idempotency_key"""
        actor = Actor.user("admin")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.CANCEL_ALL,
            actor=actor,
            scope=scope,
            payload={},
            idempotency_key="user:admin:cancel_all:2026-02-20",
        )

        assert command.idempotency_key == "user:admin:cancel_all:2026-02-20"

    def test_with_correlation_id(self) -> None:
        """correlation_id 지정"""
        actor = Actor.system("reconciler")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.RUN_RECONCILE,
            actor=actor,
            scope=scope,
            payload={},
            correlation_id="my-correlation-id",
        )

        assert command.correlation_id == "my-correlation-id"


class TestCommandClientOrderId:
    """Command.client_order_id 테스트"""

    def test_format(self) -> None:
        """client_order_id 형식"""
        actor = Actor.strategy("test")
        scope = Scope.create(symbol="XRPUSDT")
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={"side": "BUY", "qty": "10"},
        )

        client_order_id = command.client_order_id()

        assert client_order_id.startswith("ae-")
        assert client_order_id == f"ae-{command.command_id}"

    def test_deterministic(self) -> None:
        """동일 command_id → 동일 client_order_id"""
        actor = Actor.strategy("test")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={},
        )

        id1 = command.client_order_id()
        id2 = command.client_order_id()

        assert id1 == id2


class TestCommandStatusTransition:
    """Command 상태 전이 테스트"""

    def test_with_status(self) -> None:
        """상태 변경"""
        actor = Actor.strategy("test")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={},
        )

        sent = command.with_status(CommandStatus.SENT)
        assert sent.status == "SENT"
        assert command.status == "NEW"  # 원본 불변

    def test_with_status_string(self) -> None:
        """문자열로 상태 변경"""
        actor = Actor.strategy("test")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={},
        )

        ack = command.with_status("ACK")
        assert ack.status == "ACK"

    def test_with_result(self) -> None:
        """결과 설정"""
        actor = Actor.strategy("test")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={},
        )

        result = {"order_id": "123", "status": "FILLED"}
        with_result = command.with_result(result)

        assert with_result.result == result
        assert command.result is None  # 원본 불변

    def test_with_error(self) -> None:
        """에러 설정"""
        actor = Actor.strategy("test")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=actor,
            scope=scope,
            payload={},
        )

        with_error = command.with_error("Insufficient balance")

        assert with_error.last_error == "Insufficient balance"
        assert command.last_error is None  # 원본 불변


class TestCommandToDict:
    """Command.to_dict 테스트"""

    def test_serialization(self) -> None:
        """딕셔너리 직렬화"""
        actor = Actor.strategy("sma_cross")
        scope = Scope.create(symbol="ETHUSDT", mode="production")
        command = Command.create(
            command_type=CommandTypes.CLOSE_POSITION,
            actor=actor,
            scope=scope,
            payload={"mode": "MARKET", "reason": "sl_triggered"},
            priority=CommandPriority.STRATEGY,
        )

        data = command.to_dict()

        assert data["command_id"] == command.command_id
        assert data["command_type"] == "ClosePosition"
        assert data["actor"]["kind"] == "STRATEGY"
        assert data["actor"]["id"] == "strategy:sma_cross"
        assert data["scope"]["symbol"] == "ETHUSDT"
        assert data["scope"]["mode"] == "production"
        assert data["status"] == "NEW"
        assert data["priority"] == 0
        assert data["payload"]["mode"] == "MARKET"

    def test_ts_is_iso_format(self) -> None:
        """ts가 ISO 형식 문자열"""
        actor = Actor.user("admin")
        scope = Scope.create()
        command = Command.create(
            command_type=CommandTypes.PAUSE_ENGINE,
            actor=actor,
            scope=scope,
            payload={},
        )

        data = command.to_dict()

        assert isinstance(data["ts"], str)
        assert "T" in data["ts"]


class TestCommandFromDict:
    """Command.from_dict 테스트"""

    def test_deserialization(self) -> None:
        """딕셔너리에서 복원"""
        data = {
            "command_id": "123e4567-e89b-12d3-a456-426614174000",
            "command_type": "PlaceOrder",
            "ts": "2026-02-20T12:00:00+00:00",
            "correlation_id": "corr-123",
            "causation_id": None,
            "actor": {"kind": "STRATEGY", "id": "strategy:test"},
            "scope": {
                "exchange": "BINANCE",
                "venue": "FUTURES",
                "account_id": "main",
                "symbol": "XRPUSDT",
                "mode": "testnet",
            },
            "idempotency_key": "123e4567-e89b-12d3-a456-426614174000",
            "status": "SENT",
            "priority": 10,
            "payload": {"side": "BUY", "qty": "100"},
            "result": None,
            "last_error": None,
        }

        command = Command.from_dict(data)

        assert command.command_id == "123e4567-e89b-12d3-a456-426614174000"
        assert command.command_type == "PlaceOrder"
        assert command.ts.year == 2026
        assert command.actor.kind == "STRATEGY"
        assert command.scope.symbol == "XRPUSDT"
        assert command.status == "SENT"
        assert command.priority == 10

    def test_roundtrip(self) -> None:
        """직렬화 → 역직렬화 왕복"""
        actor = Actor.web("dashboard")
        scope = Scope.create(symbol="BTCUSDT")
        original = Command.create(
            command_type=CommandTypes.SET_LEVERAGE,
            actor=actor,
            scope=scope,
            payload={"leverage": 10},
            priority=CommandPriority.WEB_NORMAL,
        )

        data = original.to_dict()
        restored = Command.from_dict(data)

        assert restored.command_id == original.command_id
        assert restored.command_type == original.command_type
        assert restored.actor == original.actor
        assert restored.scope == original.scope
        assert restored.priority == original.priority
        assert restored.payload == original.payload


class TestCommandTypes:
    """CommandTypes 상수 테스트"""

    def test_engine_commands(self) -> None:
        """엔진 제어 명령 확인"""
        assert CommandTypes.PAUSE_ENGINE == "PauseEngine"
        assert CommandTypes.RESUME_ENGINE == "ResumeEngine"
        assert CommandTypes.SET_ENGINE_MODE == "SetEngineMode"
        assert CommandTypes.CANCEL_ALL == "CancelAll"
        assert CommandTypes.RUN_RECONCILE == "RunReconcile"
        assert CommandTypes.REBUILD_PROJECTION == "RebuildProjection"
        assert CommandTypes.UPDATE_CONFIG == "UpdateConfig"

    def test_trading_commands(self) -> None:
        """거래 명령 확인"""
        assert CommandTypes.PLACE_ORDER == "PlaceOrder"
        assert CommandTypes.CANCEL_ORDER == "CancelOrder"
        assert CommandTypes.CLOSE_POSITION == "ClosePosition"
        assert CommandTypes.SET_LEVERAGE == "SetLeverage"

    def test_transfer_commands(self) -> None:
        """이체 명령 확인"""
        assert CommandTypes.INTERNAL_TRANSFER == "InternalTransfer"
        assert CommandTypes.WITHDRAW == "Withdraw"

    def test_all_types(self) -> None:
        """all_types 메서드"""
        all_types = CommandTypes.all_types()
        assert isinstance(all_types, list)
        assert len(all_types) >= 12
        assert "PlaceOrder" in all_types
        assert "PauseEngine" in all_types

    def test_is_valid_type(self) -> None:
        """is_valid_type 메서드"""
        assert CommandTypes.is_valid_type("PlaceOrder") is True
        assert CommandTypes.is_valid_type("CancelOrder") is True
        assert CommandTypes.is_valid_type("InvalidCommand") is False
        assert CommandTypes.is_valid_type("") is False

    def test_trading_types(self) -> None:
        """trading_types 메서드"""
        trading = CommandTypes.trading_types()
        assert "PlaceOrder" in trading
        assert "CancelOrder" in trading
        assert "PauseEngine" not in trading

    def test_engine_types(self) -> None:
        """engine_types 메서드"""
        engine = CommandTypes.engine_types()
        assert "PauseEngine" in engine
        assert "RunReconcile" in engine
        assert "PlaceOrder" not in engine


class TestCommandPriority:
    """CommandPriority 상수 테스트"""

    def test_values(self) -> None:
        """우선순위 값 확인"""
        assert CommandPriority.WEB_URGENT == 100
        assert CommandPriority.WEB_NORMAL == 50
        assert CommandPriority.SYSTEM == 10
        assert CommandPriority.STRATEGY == 0

    def test_ordering(self) -> None:
        """우선순위 순서"""
        assert (
            CommandPriority.WEB_URGENT
            > CommandPriority.WEB_NORMAL
            > CommandPriority.SYSTEM
            > CommandPriority.STRATEGY
        )
