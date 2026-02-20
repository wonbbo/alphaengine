"""
State Machines

Order, Position, Engine 등 핵심 엔티티의 상태 전이 관리.
TRD 문서에 정의된 상태 머신 구현.
"""

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class StateMachineError(Exception):
    """상태 전이 오류"""
    pass


class OrderState(str, Enum):
    """주문 상태
    
    전이 규칙:
    - NEW → SUBMITTED: 주문 제출
    - SUBMITTED → ACKNOWLEDGED: 거래소 확인
    - SUBMITTED → FAILED: 제출 실패
    - ACKNOWLEDGED → PARTIALLY_FILLED: 부분 체결
    - ACKNOWLEDGED → FILLED: 완전 체결
    - ACKNOWLEDGED → CANCELLED: 취소
    - ACKNOWLEDGED → REJECTED: 거부
    - PARTIALLY_FILLED → FILLED: 완전 체결
    - PARTIALLY_FILLED → CANCELLED: 취소
    - FAILED → ACKNOWLEDGED: 재시도 후 성공 확인
    - FAILED → REJECTED: 최종 거부
    """
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class PositionState(str, Enum):
    """포지션 상태
    
    전이 규칙:
    - FLAT → OPEN: 포지션 진입
    - OPEN → FLAT: 포지션 청산
    """
    FLAT = "FLAT"
    OPEN = "OPEN"


class EngineState(str, Enum):
    """엔진 상태
    
    전이 규칙:
    - BOOTING → RUNNING: 초기화 완료
    - RUNNING → PAUSED: 일시정지
    - RUNNING → SAFE: 안전 모드 (신규 주문 금지)
    - PAUSED → RUNNING: 재개
    - SAFE → RUNNING: 정상 모드 복귀
    """
    BOOTING = "BOOTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SAFE = "SAFE"


class CommandState(str, Enum):
    """Command 상태
    
    전이 규칙:
    - NEW → SENT: 클레임됨
    - SENT → ACK: 성공
    - SENT → FAILED: 실패
    """
    NEW = "NEW"
    SENT = "SENT"
    ACK = "ACK"
    FAILED = "FAILED"


class WebSocketConnectionState(str, Enum):
    """WebSocket 연결 상태
    
    전이 규칙:
    - DISCONNECTED → CONNECTING: 연결 시도
    - CONNECTING → CONNECTED: 연결 성공
    - CONNECTING → DISCONNECTED: 연결 실패
    - CONNECTED → RECONNECTING: 연결 끊김
    - RECONNECTING → CONNECTED: 재연결 성공
    - RECONNECTING → DISCONNECTED: 재연결 포기
    """
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"


class StateMachine:
    """상태 머신 기본 클래스
    
    Args:
        initial_state: 초기 상태
        transitions: 허용된 전이 정의 {from_state: [to_states]}
        name: 머신 이름 (로깅용)
    """
    
    def __init__(
        self,
        initial_state: str | Enum,
        transitions: dict[str, list[str]],
        name: str = "StateMachine",
    ):
        self._state = initial_state.value if isinstance(initial_state, Enum) else initial_state
        self._transitions = transitions
        self._name = name
        self._history: list[tuple[str, str]] = []
    
    @property
    def state(self) -> str:
        """현재 상태"""
        return self._state
    
    def can_transition(self, to_state: str | Enum) -> bool:
        """전이 가능 여부 확인
        
        Args:
            to_state: 목표 상태
            
        Returns:
            전이 가능 여부
        """
        target = to_state.value if isinstance(to_state, Enum) else to_state
        allowed = self._transitions.get(self._state, [])
        return target in allowed
    
    def transition(self, to_state: str | Enum) -> str:
        """상태 전이
        
        Args:
            to_state: 목표 상태
            
        Returns:
            새 상태
            
        Raises:
            StateMachineError: 허용되지 않은 전이
        """
        target = to_state.value if isinstance(to_state, Enum) else to_state
        
        if not self.can_transition(target):
            allowed = self._transitions.get(self._state, [])
            raise StateMachineError(
                f"{self._name}: Cannot transition from {self._state} to {target}. "
                f"Allowed: {allowed}"
            )
        
        old_state = self._state
        self._state = target
        self._history.append((old_state, target))
        
        logger.debug(
            f"{self._name}: {old_state} → {target}",
        )
        
        return target
    
    def force_state(self, state: str | Enum) -> None:
        """강제 상태 설정 (복구용)
        
        Args:
            state: 새 상태
        """
        target = state.value if isinstance(state, Enum) else state
        old_state = self._state
        self._state = target
        self._history.append((old_state, target))
        
        logger.warning(
            f"{self._name}: Force state {old_state} → {target}",
        )
    
    @property
    def history(self) -> list[tuple[str, str]]:
        """상태 전이 이력"""
        return self._history.copy()


class OrderStateMachine(StateMachine):
    """주문 상태 머신"""
    
    TRANSITIONS: dict[str, list[str]] = {
        "NEW": ["SUBMITTED"],
        "SUBMITTED": ["ACKNOWLEDGED", "FAILED"],
        "ACKNOWLEDGED": ["PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED", "EXPIRED"],
        "PARTIALLY_FILLED": ["FILLED", "CANCELLED"],
        "FAILED": ["ACKNOWLEDGED", "REJECTED"],
    }
    
    def __init__(self, initial_state: str | OrderState = OrderState.NEW):
        super().__init__(
            initial_state=initial_state,
            transitions=self.TRANSITIONS,
            name="OrderStateMachine",
        )
    
    @property
    def is_terminal(self) -> bool:
        """종료 상태 여부"""
        return self._state in ("FILLED", "CANCELLED", "REJECTED", "EXPIRED")
    
    @property
    def is_active(self) -> bool:
        """활성 상태 여부 (오픈 주문)"""
        return self._state in ("ACKNOWLEDGED", "PARTIALLY_FILLED")


class PositionStateMachine(StateMachine):
    """포지션 상태 머신"""
    
    TRANSITIONS: dict[str, list[str]] = {
        "FLAT": ["OPEN"],
        "OPEN": ["FLAT"],
    }
    
    def __init__(self, initial_state: str | PositionState = PositionState.FLAT):
        super().__init__(
            initial_state=initial_state,
            transitions=self.TRANSITIONS,
            name="PositionStateMachine",
        )
    
    @property
    def has_position(self) -> bool:
        """포지션 보유 여부"""
        return self._state == "OPEN"


class EngineStateMachine(StateMachine):
    """엔진 상태 머신"""
    
    TRANSITIONS: dict[str, list[str]] = {
        "BOOTING": ["RUNNING"],
        "RUNNING": ["PAUSED", "SAFE"],
        "PAUSED": ["RUNNING"],
        "SAFE": ["RUNNING"],
    }
    
    def __init__(self, initial_state: str | EngineState = EngineState.BOOTING):
        super().__init__(
            initial_state=initial_state,
            transitions=self.TRANSITIONS,
            name="EngineStateMachine",
        )
    
    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._state == "RUNNING"
    
    @property
    def can_trade(self) -> bool:
        """거래 가능 여부"""
        return self._state == "RUNNING"
    
    @property
    def can_close_only(self) -> bool:
        """청산만 가능 여부 (SAFE 모드)"""
        return self._state == "SAFE"


class CommandStateMachine(StateMachine):
    """Command 상태 머신"""
    
    TRANSITIONS: dict[str, list[str]] = {
        "NEW": ["SENT"],
        "SENT": ["ACK", "FAILED"],
    }
    
    def __init__(self, initial_state: str | CommandState = CommandState.NEW):
        super().__init__(
            initial_state=initial_state,
            transitions=self.TRANSITIONS,
            name="CommandStateMachine",
        )
    
    @property
    def is_complete(self) -> bool:
        """완료 여부"""
        return self._state in ("ACK", "FAILED")


class WebSocketStateMachine(StateMachine):
    """WebSocket 연결 상태 머신"""
    
    TRANSITIONS: dict[str, list[str]] = {
        "DISCONNECTED": ["CONNECTING"],
        "CONNECTING": ["CONNECTED", "DISCONNECTED"],
        "CONNECTED": ["RECONNECTING", "DISCONNECTED"],
        "RECONNECTING": ["CONNECTED", "DISCONNECTED"],
    }
    
    def __init__(
        self,
        initial_state: str | WebSocketConnectionState = WebSocketConnectionState.DISCONNECTED,
    ):
        super().__init__(
            initial_state=initial_state,
            transitions=self.TRANSITIONS,
            name="WebSocketStateMachine",
        )
    
    @property
    def is_connected(self) -> bool:
        """연결 상태 여부"""
        return self._state == "CONNECTED"
    
    @property
    def is_healthy(self) -> bool:
        """정상 상태 여부 (연결 또는 재연결 중)"""
        return self._state in ("CONNECTED", "RECONNECTING")


def get_order_state_from_binance(status: str) -> OrderState:
    """Binance 주문 상태 → OrderState 변환
    
    Args:
        status: Binance 주문 상태
        
    Returns:
        OrderState
    """
    mapping = {
        "NEW": OrderState.ACKNOWLEDGED,
        "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
        "FILLED": OrderState.FILLED,
        "CANCELED": OrderState.CANCELLED,
        "REJECTED": OrderState.REJECTED,
        "EXPIRED": OrderState.EXPIRED,
    }
    return mapping.get(status, OrderState.ACKNOWLEDGED)
