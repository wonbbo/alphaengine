"""
Event 도메인 모델

모든 상태 변경은 Event로 기록됨 (Event Sourcing 원칙)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from core.types import Scope


@dataclass
class Event:
    """이벤트

    모든 상태 변경을 기록하는 불변 데이터 구조.
    dedup_key로 중복 이벤트를 방지함.
    """

    event_id: str
    event_type: str
    ts: datetime
    correlation_id: str
    causation_id: str | None
    command_id: str | None
    source: str
    entity_kind: str
    entity_id: str
    scope: Scope
    dedup_key: str
    payload: dict[str, Any]
    seq: int | None = None  # DB에서 조회 시 자동 할당되는 시퀀스 번호

    @staticmethod
    def create(
        event_type: str,
        source: str,
        entity_kind: str,
        entity_id: str,
        scope: Scope,
        dedup_key: str,
        payload: dict[str, Any],
        correlation_id: str | None = None,
        causation_id: str | None = None,
        command_id: str | None = None,
    ) -> "Event":
        """새 이벤트 생성

        Args:
            event_type: 이벤트 타입 (예: TradeExecuted)
            source: 이벤트 출처 (WEBSOCKET, REST, BOT, WEB)
            entity_kind: 엔티티 종류 (ORDER, TRADE, POSITION 등)
            entity_id: 엔티티 ID
            scope: 거래 범위
            dedup_key: 중복 제거 키
            payload: 이벤트 상세 데이터
            correlation_id: 상관 ID (없으면 자동 생성)
            causation_id: 인과 ID (이 이벤트를 발생시킨 이전 이벤트 ID)
            command_id: 관련 Command ID

        Returns:
            새 Event 인스턴스
        """
        return Event(
            event_id=str(uuid4()),
            event_type=event_type,
            ts=datetime.now(timezone.utc),
            correlation_id=correlation_id or str(uuid4()),
            causation_id=causation_id,
            command_id=command_id,
            source=source,
            entity_kind=entity_kind,
            entity_id=entity_id,
            scope=scope,
            dedup_key=dedup_key,
            payload=payload,
        )

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환 (직렬화용)"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "ts": self.ts.isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "command_id": self.command_id,
            "source": self.source,
            "entity_kind": self.entity_kind,
            "entity_id": self.entity_id,
            "scope": {
                "exchange": self.scope.exchange,
                "venue": self.scope.venue,
                "account_id": self.scope.account_id,
                "symbol": self.scope.symbol,
                "mode": self.scope.mode,
            },
            "dedup_key": self.dedup_key,
            "payload": self.payload,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Event":
        """딕셔너리에서 생성 (역직렬화용)"""
        ts = data["ts"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        scope_data = data["scope"]
        scope = Scope(
            exchange=scope_data["exchange"],
            venue=scope_data["venue"],
            account_id=scope_data["account_id"],
            symbol=scope_data.get("symbol"),
            mode=scope_data["mode"],
        )

        return Event(
            event_id=data["event_id"],
            event_type=data["event_type"],
            ts=ts,
            correlation_id=data["correlation_id"],
            causation_id=data.get("causation_id"),
            command_id=data.get("command_id"),
            source=data["source"],
            entity_kind=data["entity_kind"],
            entity_id=data["entity_id"],
            scope=scope,
            dedup_key=data["dedup_key"],
            payload=data.get("payload", {}),
        )


class EventTypes:
    """Event Type 상수

    TRD 문서에 정의된 모든 이벤트 타입
    """

    # Engine / Control
    ENGINE_STARTED: str = "EngineStarted"
    ENGINE_STOPPED: str = "EngineStopped"
    ENGINE_PAUSED: str = "EnginePaused"
    ENGINE_RESUMED: str = "EngineResumed"
    ENGINE_MODE_CHANGED: str = "EngineModeChanged"
    MANUAL_OVERRIDE_EXECUTED: str = "ManualOverrideExecuted"
    RISK_GUARD_REJECTED: str = "RiskGuardRejected"
    CONFIG_CHANGED: str = "ConfigChanged"

    # WebSocket Connection
    WS_CONNECTED: str = "WebSocketConnected"
    WS_DISCONNECTED: str = "WebSocketDisconnected"
    WS_RECONNECTED: str = "WebSocketReconnected"

    # Orders / Trades
    ORDER_PLACED: str = "OrderPlaced"
    ORDER_REJECTED: str = "OrderRejected"
    ORDER_CANCELLED: str = "OrderCancelled"
    ORDER_UPDATED: str = "OrderUpdated"
    TRADE_EXECUTED: str = "TradeExecuted"

    # Position / Balance / Fee
    POSITION_CHANGED: str = "PositionChanged"
    BALANCE_CHANGED: str = "BalanceChanged"
    FEE_CHARGED: str = "FeeCharged"
    FUNDING_APPLIED: str = "FundingApplied"

    # Internal Transfer
    INTERNAL_TRANSFER_REQUESTED: str = "InternalTransferRequested"
    INTERNAL_TRANSFER_COMPLETED: str = "InternalTransferCompleted"
    INTERNAL_TRANSFER_FAILED: str = "InternalTransferFailed"

    # External Deposit / Withdraw (기존)
    DEPOSIT_DETECTED: str = "DepositDetected"
    WITHDRAW_REQUESTED: str = "WithdrawRequested"
    WITHDRAW_COMPLETED: str = "WithdrawCompleted"
    WITHDRAW_FAILED: str = "WithdrawFailed"

    # Deposit (Upbit KRW -> Binance Futures USDT)
    DEPOSIT_INITIATED: str = "DepositInitiated"  # 입금 요청 시작
    DEPOSIT_TRX_PURCHASED: str = "DepositTrxPurchased"  # Upbit TRX 매수 완료
    DEPOSIT_TRX_SENT: str = "DepositTrxSent"  # Upbit -> Binance 전송
    DEPOSIT_TRX_RECEIVED: str = "DepositTrxReceived"  # Binance Spot 입금 확인
    DEPOSIT_USDT_CONVERTED: str = "DepositUsdtConverted"  # TRX -> USDT 환전
    DEPOSIT_SPOT_TRANSFERRED: str = "DepositSpotTransferred"  # Spot -> Futures 이체
    DEPOSIT_COMPLETED: str = "DepositCompleted"  # 입금 완료

    # Withdraw (Binance Futures USDT -> Upbit KRW)
    WITHDRAW_INITIATED: str = "WithdrawInitiated"  # 출금 요청 시작
    WITHDRAW_FUTURES_TRANSFERRED: str = "WithdrawFuturesTransferred"  # Futures -> Spot 이체
    WITHDRAW_USDT_CONVERTED: str = "WithdrawUsdtConverted"  # USDT -> TRX 환전
    WITHDRAW_TRX_SENT: str = "WithdrawTrxSent"  # Binance -> Upbit 전송
    WITHDRAW_TRX_RECEIVED: str = "WithdrawTrxReceived"  # Upbit TRX 입금 확인
    WITHDRAW_KRW_CONVERTED: str = "WithdrawKrwConverted"  # TRX -> KRW 환전
    WITHDRAW_COMPLETED: str = "WithdrawCompleted"  # 출금 완료

    # Reconciliation / Audit
    DRIFT_DETECTED: str = "DriftDetected"
    RECONCILIATION_PERFORMED: str = "ReconciliationPerformed"
    QUARANTINE_STARTED: str = "QuarantineStarted"
    QUARANTINE_COMPLETED: str = "QuarantineCompleted"
    
    # Strategy
    STRATEGY_LOADED: str = "StrategyLoaded"
    STRATEGY_STARTED: str = "StrategyStarted"
    STRATEGY_STOPPED: str = "StrategyStopped"
    STRATEGY_ERROR: str = "StrategyError"

    # BNB Fee Management
    BNB_BALANCE_LOW: str = "BnbBalanceLow"
    BNB_REPLENISH_STARTED: str = "BnbReplenishStarted"
    BNB_REPLENISH_COMPLETED: str = "BnbReplenishCompleted"
    BNB_REPLENISH_FAILED: str = "BnbReplenishFailed"

    # Initial Capital (과거 데이터 복구용)
    INITIAL_CAPITAL_ESTABLISHED: str = "InitialCapitalEstablished"

    # Convert (간편 전환)
    CONVERT_EXECUTED: str = "ConvertExecuted"

    # Commission Rebate (수수료 리베이트)
    COMMISSION_REBATE_RECEIVED: str = "CommissionRebateReceived"

    # Dust (소액 자산 전환)
    DUST_CONVERTED: str = "DustConverted"

    # Opening Balance Adjustment (기초 잔액 조정)
    OPENING_BALANCE_ADJUSTED: str = "OpeningBalanceAdjusted"

    @classmethod
    def all_types(cls) -> list[str]:
        """모든 이벤트 타입 목록 반환"""
        return [
            value
            for name, value in vars(cls).items()
            if not name.startswith("_") and isinstance(value, str) and name.isupper()
        ]

    @classmethod
    def is_valid_type(cls, event_type: str) -> bool:
        """유효한 이벤트 타입인지 확인"""
        return event_type in cls.all_types()
