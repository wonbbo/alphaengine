"""
Risk Guard

Command 발행 전/실행 전 리스크 검증.
여러 규칙을 체인으로 연결하여 검사.
"""

import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from core.domain.commands import Command
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.types import Scope
from bot.risk.rules import (
    RiskRule,
    RiskCheckResult,
    MaxPositionSizeRule,
    DailyLossLimitRule,
    MaxOpenOrdersRule,
    EngineModeRule,
    MinBalanceRule,
)
from bot.risk.pnl_calculator import PnLCalculator

if TYPE_CHECKING:
    from bot.projector.projector import EventProjector
    from core.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)


class RiskGuard:
    """Risk Guard
    
    Command 발행 전/실행 전 리스크 검증.
    모든 규칙을 통과해야 Command 허용.
    
    검증 시점:
    1. 전략 on_tick() 후: Command 발행 전 검증 (Strategy → RiskGuard → CommandStore)
    2. Executor 실행 전: 최종 검증 (상태 변경 대비)
    
    Args:
        event_store: 이벤트 저장소 (거부 이벤트 기록용)
        projector: Projection 조회용 (선택)
        config_getter: 설정 조회 함수 (선택)
        
    사용 예시:
    ```python
    guard = RiskGuard(event_store)
    guard.add_rule(MaxPositionSizeRule())
    guard.add_rule(DailyLossLimitRule())
    
    passed, reason = await guard.check(command)
    if not passed:
        print(f"Rejected: {reason}")
    ```
    """
    
    def __init__(
        self,
        event_store: EventStore,
        projector: "EventProjector | None" = None,
        config_getter: Any = None,
        engine_mode_getter: Any = None,
    ):
        self.event_store = event_store
        self.projector = projector
        self.config_getter = config_getter
        self.engine_mode_getter = engine_mode_getter
        
        # PnL Calculator
        self.pnl_calculator = PnLCalculator(event_store)
        
        # 규칙 목록
        self._rules: list[RiskRule] = []
        
        # 기본 규칙 추가
        self._add_default_rules()
        
        # 통계
        self._check_count = 0
        self._passed_count = 0
        self._rejected_count = 0
    
    def _add_default_rules(self) -> None:
        """기본 규칙 추가"""
        self.add_rule(EngineModeRule())
        self.add_rule(MaxPositionSizeRule())
        self.add_rule(DailyLossLimitRule())
        self.add_rule(MaxOpenOrdersRule())
        self.add_rule(MinBalanceRule())
    
    def add_rule(self, rule: RiskRule) -> None:
        """규칙 추가
        
        Args:
            rule: 리스크 규칙
        """
        self._rules.append(rule)
        logger.debug(f"Risk rule added: {rule.name}")
    
    def remove_rule(self, rule_name: str) -> bool:
        """규칙 제거
        
        Args:
            rule_name: 규칙 이름
            
        Returns:
            제거 성공 여부
        """
        for rule in self._rules:
            if rule.name == rule_name:
                self._rules.remove(rule)
                return True
        return False
    
    async def check(self, command: Command) -> tuple[bool, str | None]:
        """Command 리스크 검사
        
        Args:
            command: 검사할 Command
            
        Returns:
            (passed, reason) 튜플
            - passed: True면 통과
            - reason: 거부 사유 (거부 시)
        """
        self._check_count += 1
        
        # 컨텍스트 구성
        context = await self._build_context(command)
        
        # 모든 규칙 검사
        for rule in self._rules:
            # 해당 Command 타입에 적용되는지 확인
            if not rule.applies_to(command.command_type):
                continue
            
            try:
                result = await rule.check(command, context)
                
                if not result.passed:
                    self._rejected_count += 1
                    
                    # 거부 이벤트 기록
                    await self._record_rejection(command, result)
                    
                    logger.warning(
                        f"Command rejected by {result.rule_name}: {result.reason}",
                        extra={
                            "command_id": command.command_id,
                            "command_type": command.command_type,
                        },
                    )
                    
                    return False, result.reason
                    
            except Exception as e:
                logger.error(
                    f"Risk rule error: {rule.name}",
                    extra={"error": str(e)},
                )
                # 규칙 에러 시 보수적으로 거부
                return False, f"Risk check error: {rule.name}"
        
        self._passed_count += 1
        return True, None
    
    async def _build_context(self, command: Command) -> dict[str, Any]:
        """검사 컨텍스트 구성
        
        Args:
            command: Command
            
        Returns:
            컨텍스트 딕셔너리
        """
        context: dict[str, Any] = {}
        
        # 엔진 모드
        if self.engine_mode_getter:
            try:
                context["engine_mode"] = await self.engine_mode_getter()
            except Exception:
                context["engine_mode"] = "RUNNING"
        else:
            context["engine_mode"] = "RUNNING"
        
        # 설정
        if self.config_getter:
            try:
                context["config"] = await self.config_getter()
            except Exception:
                context["config"] = {}
        else:
            context["config"] = {}
        
        # Projection 데이터
        if self.projector and command.scope.symbol:
            try:
                # 포지션
                position = await self.projector.get_position(
                    exchange=command.scope.exchange,
                    venue=command.scope.venue,
                    account_id=command.scope.account_id,
                    mode=command.scope.mode,
                    symbol=command.scope.symbol,
                )
                context["position"] = position or {}
                
                # 잔고 (USDT)
                balance = await self.projector.get_balance(
                    exchange=command.scope.exchange,
                    venue=command.scope.venue,
                    account_id=command.scope.account_id,
                    mode=command.scope.mode,
                    asset="USDT",
                )
                context["balance"] = balance or {}
                
                # 오픈 주문 수
                open_orders = await self.projector.get_open_orders(
                    exchange=command.scope.exchange,
                    venue=command.scope.venue,
                    account_id=command.scope.account_id,
                    mode=command.scope.mode,
                    symbol=command.scope.symbol,
                )
                context["open_orders_count"] = len(open_orders)
                
            except Exception as e:
                logger.warning(f"Failed to get projection data: {e}")
        
        # 일일 PnL 계산
        try:
            daily_pnl = await self.pnl_calculator.get_daily_pnl(
                exchange=command.scope.exchange,
                venue=command.scope.venue,
                account_id=command.scope.account_id,
                mode=command.scope.mode,
                symbol=command.scope.symbol,
            )
            context["daily_pnl"] = str(daily_pnl)
        except Exception as e:
            logger.warning(f"Failed to calculate daily PnL: {e}")
            context["daily_pnl"] = "0"
        
        return context
    
    async def _record_rejection(
        self,
        command: Command,
        result: RiskCheckResult,
    ) -> None:
        """거부 이벤트 기록
        
        Args:
            command: 거부된 Command
            result: 검사 결과
        """
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        event = Event.create(
            event_type=EventTypes.RISK_GUARD_REJECTED,
            source="BOT",
            entity_kind="COMMAND",
            entity_id=command.command_id,
            scope=command.scope,
            dedup_key=f"risk:rejected:{command.command_id}:{now_ms}",
            command_id=command.command_id,
            correlation_id=command.correlation_id,
            payload={
                "command_type": command.command_type,
                "rule_name": result.rule_name,
                "reason": result.reason,
                "details": result.details,
                "rejected_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        
        await self.event_store.append(event)
    
    def set_engine_mode_getter(self, getter: Any) -> None:
        """엔진 모드 조회 함수 설정"""
        self.engine_mode_getter = getter
    
    def set_config_getter(self, getter: Any) -> None:
        """설정 조회 함수 설정"""
        self.config_getter = getter
    
    def set_projector(self, projector: "EventProjector") -> None:
        """Projector 설정"""
        self.projector = projector
    
    @property
    def rules(self) -> list[str]:
        """등록된 규칙 목록"""
        return [rule.name for rule in self._rules]
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "check_count": self._check_count,
            "passed_count": self._passed_count,
            "rejected_count": self._rejected_count,
            "rules": self.rules,
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._check_count = 0
        self._passed_count = 0
        self._rejected_count = 0
