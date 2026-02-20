"""
Command 도메인 모델

모든 행위 요청은 Command로 표현됨.
Command는 idempotent해야 하며, 실행 결과는 반드시 Event로 기록됨.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.types import Scope, Actor, CommandStatus
from core.utils.idempotency import make_client_order_id


@dataclass
class Command:
    """명령

    행위 요청을 나타내는 데이터 구조.
    모든 Command는 idempotent해야 함.
    """

    command_id: str
    command_type: str
    ts: datetime
    correlation_id: str
    causation_id: str | None
    actor: Actor
    scope: Scope
    idempotency_key: str
    status: str
    priority: int
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    last_error: str | None = None

    @staticmethod
    def create(
        command_type: str,
        actor: Actor,
        scope: Scope,
        payload: dict[str, Any],
        priority: int = 0,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> "Command":
        """새 Command 생성

        Args:
            command_type: 명령 타입 (예: PlaceOrder)
            actor: 행위자 (전략, 사용자, 시스템)
            scope: 거래 범위
            payload: 명령 상세 데이터
            priority: 우선순위 (높을수록 먼저 처리, 기본 0)
            correlation_id: 상관 ID (없으면 자동 생성)
            causation_id: 인과 ID
            idempotency_key: 멱등성 키 (없으면 command_id 사용)

        Returns:
            새 Command 인스턴스 (status=NEW)
        """
        command_id = str(uuid4())
        return Command(
            command_id=command_id,
            command_type=command_type,
            ts=datetime.now(timezone.utc),
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            actor=actor,
            scope=scope,
            idempotency_key=idempotency_key or command_id,
            status=CommandStatus.NEW.value,
            priority=priority,
            payload=payload,
            result=None,
            last_error=None,
        )

    def client_order_id(self) -> str:
        """결정적 client_order_id 생성

        주문 Command의 경우 거래소에 전달할 client_order_id 생성.
        규칙: ae-{command_id}

        Returns:
            client_order_id
        """
        return make_client_order_id(self.command_id)

    def with_status(self, status: str | CommandStatus) -> "Command":
        """상태 변경된 새 Command 반환

        Command는 불변 원칙을 따르므로 새 인스턴스 반환
        """
        new_status = status.value if isinstance(status, CommandStatus) else status
        return Command(
            command_id=self.command_id,
            command_type=self.command_type,
            ts=self.ts,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            actor=self.actor,
            scope=self.scope,
            idempotency_key=self.idempotency_key,
            status=new_status,
            priority=self.priority,
            payload=self.payload,
            result=self.result,
            last_error=self.last_error,
        )

    def with_result(self, result: dict[str, Any]) -> "Command":
        """결과 설정된 새 Command 반환"""
        return Command(
            command_id=self.command_id,
            command_type=self.command_type,
            ts=self.ts,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            actor=self.actor,
            scope=self.scope,
            idempotency_key=self.idempotency_key,
            status=self.status,
            priority=self.priority,
            payload=self.payload,
            result=result,
            last_error=self.last_error,
        )

    def with_error(self, error: str) -> "Command":
        """에러 설정된 새 Command 반환"""
        return Command(
            command_id=self.command_id,
            command_type=self.command_type,
            ts=self.ts,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            actor=self.actor,
            scope=self.scope,
            idempotency_key=self.idempotency_key,
            status=self.status,
            priority=self.priority,
            payload=self.payload,
            result=self.result,
            last_error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (직렬화용)"""
        return {
            "command_id": self.command_id,
            "command_type": self.command_type,
            "ts": self.ts.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "actor": {
                "kind": self.actor.kind,
                "id": self.actor.id,
            },
            "scope": {
                "exchange": self.scope.exchange,
                "venue": self.scope.venue,
                "account_id": self.scope.account_id,
                "symbol": self.scope.symbol,
                "mode": self.scope.mode,
            },
            "idempotency_key": self.idempotency_key,
            "status": self.status,
            "priority": self.priority,
            "payload": self.payload,
            "result": self.result,
            "last_error": self.last_error,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Command":
        """딕셔너리에서 생성 (역직렬화용)"""
        ts = data["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        actor_data = data["actor"]
        actor = Actor(kind=actor_data["kind"], id=actor_data["id"])

        scope_data = data["scope"]
        scope = Scope(
            exchange=scope_data["exchange"],
            venue=scope_data["venue"],
            account_id=scope_data["account_id"],
            symbol=scope_data.get("symbol"),
            mode=scope_data["mode"],
        )

        return Command(
            command_id=data["command_id"],
            command_type=data["command_type"],
            ts=ts,
            correlation_id=data["correlation_id"],
            causation_id=data.get("causation_id"),
            actor=actor,
            scope=scope,
            idempotency_key=data["idempotency_key"],
            status=data["status"],
            priority=data.get("priority", 0),
            payload=data.get("payload", {}),
            result=data.get("result"),
            last_error=data.get("last_error"),
        )


class CommandTypes:
    """Command Type 상수

    TRD 문서에 정의된 모든 명령 타입
    """

    # Engine / Control
    PAUSE_ENGINE: str = "PauseEngine"
    RESUME_ENGINE: str = "ResumeEngine"
    SET_ENGINE_MODE: str = "SetEngineMode"
    CANCEL_ALL: str = "CancelAll"
    RUN_RECONCILE: str = "RunReconcile"
    REBUILD_PROJECTION: str = "RebuildProjection"
    UPDATE_CONFIG: str = "UpdateConfig"

    # Trading
    PLACE_ORDER: str = "PlaceOrder"
    CANCEL_ORDER: str = "CancelOrder"
    CLOSE_POSITION: str = "ClosePosition"
    SET_LEVERAGE: str = "SetLeverage"

    # Transfers
    INTERNAL_TRANSFER: str = "InternalTransfer"
    WITHDRAW: str = "Withdraw"

    @classmethod
    def all_types(cls) -> list[str]:
        """모든 명령 타입 목록 반환"""
        return [
            value
            for name, value in vars(cls).items()
            if not name.startswith("_") and isinstance(value, str) and name.isupper()
        ]

    @classmethod
    def is_valid_type(cls, command_type: str) -> bool:
        """유효한 명령 타입인지 확인"""
        return command_type in cls.all_types()

    @classmethod
    def trading_types(cls) -> list[str]:
        """거래 관련 명령 타입"""
        return [cls.PLACE_ORDER, cls.CANCEL_ORDER, cls.CLOSE_POSITION, cls.SET_LEVERAGE]

    @classmethod
    def engine_types(cls) -> list[str]:
        """엔진 제어 관련 명령 타입"""
        return [
            cls.PAUSE_ENGINE,
            cls.RESUME_ENGINE,
            cls.SET_ENGINE_MODE,
            cls.CANCEL_ALL,
            cls.RUN_RECONCILE,
            cls.REBUILD_PROJECTION,
            cls.UPDATE_CONFIG,
        ]


class CommandPriority:
    """Command 우선순위 상수

    높을수록 먼저 처리됨
    """

    WEB_URGENT: int = 100  # 사용자 긴급 청산, CancelAll
    WEB_NORMAL: int = 50  # 사용자 일반 명령
    SYSTEM: int = 10  # 시스템 자동 명령 (Reconcile 등)
    STRATEGY: int = 0  # 전략 자동 명령
