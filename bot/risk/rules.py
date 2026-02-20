"""
Risk Rules

개별 리스크 규칙 구현
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.domain.commands import Command, CommandTypes

logger = logging.getLogger(__name__)


@dataclass
class RiskCheckResult:
    """리스크 검사 결과"""
    passed: bool
    rule_name: str
    reason: str | None = None
    details: dict[str, Any] | None = None


class RiskRule(ABC):
    """리스크 규칙 추상 클래스
    
    모든 리스크 규칙은 이 클래스를 상속하여 구현.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """규칙 이름"""
        pass
    
    @abstractmethod
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        """리스크 검사
        
        Args:
            command: 검사할 Command
            context: 현재 상태 컨텍스트 (포지션, 잔고, 설정 등)
            
        Returns:
            RiskCheckResult
        """
        pass
    
    def applies_to(self, command_type: str) -> bool:
        """해당 Command 타입에 적용되는지 여부
        
        Args:
            command_type: Command 타입
            
        Returns:
            적용 여부
        """
        return True  # 기본: 모든 Command에 적용


class MaxPositionSizeRule(RiskRule):
    """최대 포지션 크기 규칙
    
    새 주문이 최대 포지션 크기를 초과하지 않는지 검사.
    
    Context 필요:
    - config.max_position_size: Decimal - 최대 포지션 크기
    - position.qty: Decimal - 현재 포지션 수량
    - position.side: str - 현재 포지션 방향
    """
    
    @property
    def name(self) -> str:
        return "MaxPositionSize"
    
    def applies_to(self, command_type: str) -> bool:
        return command_type == CommandTypes.PLACE_ORDER
    
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        config = context.get("config", {})
        max_size = Decimal(str(config.get("max_position_size", "0")))
        
        if max_size <= 0:
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Max position size not configured",
            )
        
        # 현재 포지션
        position = context.get("position", {})
        current_qty = Decimal(str(position.get("qty", "0")))
        current_side = position.get("side")
        
        # 주문 정보
        order_qty = Decimal(str(command.payload.get("quantity", "0")))
        order_side = command.payload.get("side")
        reduce_only = command.payload.get("reduce_only", False)
        
        # 청산 주문은 허용
        if reduce_only:
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Reduce-only order allowed",
            )
        
        # 새 포지션 크기 계산
        if current_side is None or current_qty == 0:
            new_qty = order_qty
        elif (current_side == "LONG" and order_side == "BUY") or \
             (current_side == "SHORT" and order_side == "SELL"):
            new_qty = current_qty + order_qty
        else:
            new_qty = abs(current_qty - order_qty)
        
        if new_qty > max_size:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Position size {new_qty} exceeds max {max_size}",
                details={
                    "current_qty": str(current_qty),
                    "order_qty": str(order_qty),
                    "new_qty": str(new_qty),
                    "max_size": str(max_size),
                },
            )
        
        return RiskCheckResult(
            passed=True,
            rule_name=self.name,
        )


class DailyLossLimitRule(RiskRule):
    """일일 손실 한도 규칙
    
    일일 손실이 한도를 초과하면 새 주문 거부.
    
    Context 필요:
    - config.daily_loss_limit: Decimal - 일일 손실 한도
    - daily_pnl: Decimal - 오늘 실현 손익
    """
    
    @property
    def name(self) -> str:
        return "DailyLossLimit"
    
    def applies_to(self, command_type: str) -> bool:
        return command_type == CommandTypes.PLACE_ORDER
    
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        config = context.get("config", {})
        daily_loss_limit = Decimal(str(config.get("daily_loss_limit", "0")))
        
        if daily_loss_limit <= 0:
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Daily loss limit not configured",
            )
        
        daily_pnl = Decimal(str(context.get("daily_pnl", "0")))
        
        # 손실이 한도 초과 (손실은 음수이므로 절대값 비교)
        if daily_pnl < 0 and abs(daily_pnl) >= daily_loss_limit:
            # 청산 주문은 허용
            if command.payload.get("reduce_only", False):
                return RiskCheckResult(
                    passed=True,
                    rule_name=self.name,
                    reason="Reduce-only order allowed despite daily loss limit",
                )
            
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Daily loss {abs(daily_pnl)} reached limit {daily_loss_limit}",
                details={
                    "daily_pnl": str(daily_pnl),
                    "daily_loss_limit": str(daily_loss_limit),
                },
            )
        
        return RiskCheckResult(
            passed=True,
            rule_name=self.name,
        )


class MaxOpenOrdersRule(RiskRule):
    """동시 오픈 주문 수 제한 규칙
    
    오픈 주문 수가 한도를 초과하면 새 주문 거부.
    
    Context 필요:
    - config.max_open_orders: int - 최대 오픈 주문 수
    - open_orders_count: int - 현재 오픈 주문 수
    """
    
    @property
    def name(self) -> str:
        return "MaxOpenOrders"
    
    def applies_to(self, command_type: str) -> bool:
        return command_type == CommandTypes.PLACE_ORDER
    
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        config = context.get("config", {})
        max_orders = int(config.get("max_open_orders", 0))
        
        if max_orders <= 0:
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Max open orders not configured",
            )
        
        current_count = int(context.get("open_orders_count", 0))
        
        if current_count >= max_orders:
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Open orders {current_count} reached limit {max_orders}",
                details={
                    "current_count": current_count,
                    "max_orders": max_orders,
                },
            )
        
        return RiskCheckResult(
            passed=True,
            rule_name=self.name,
        )


class EngineModeRule(RiskRule):
    """엔진 모드 규칙
    
    엔진 상태에 따라 Command 허용/거부.
    
    - PAUSED: 모든 거래 Command 거부
    - SAFE: 신규 주문 거부, 청산만 허용
    - RUNNING: 모두 허용
    
    Context 필요:
    - engine_mode: str - 현재 엔진 모드
    """
    
    @property
    def name(self) -> str:
        return "EngineMode"
    
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        engine_mode = context.get("engine_mode", "RUNNING")
        command_type = command.command_type
        
        # 엔진 제어 Command는 항상 허용
        if command_type in CommandTypes.engine_types():
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Engine control command always allowed",
            )
        
        # PAUSED: 거래 Command 거부
        if engine_mode == "PAUSED":
            if command_type in CommandTypes.trading_types():
                return RiskCheckResult(
                    passed=False,
                    rule_name=self.name,
                    reason="Engine is paused, trading commands blocked",
                )
        
        # SAFE: 신규 주문 거부, 청산은 허용
        if engine_mode == "SAFE":
            if command_type == CommandTypes.PLACE_ORDER:
                if command.payload.get("reduce_only", False):
                    return RiskCheckResult(
                        passed=True,
                        rule_name=self.name,
                        reason="Close-only order allowed in SAFE mode",
                    )
                return RiskCheckResult(
                    passed=False,
                    rule_name=self.name,
                    reason="New orders blocked in SAFE mode",
                )
        
        return RiskCheckResult(
            passed=True,
            rule_name=self.name,
        )


class MinBalanceRule(RiskRule):
    """최소 잔고 규칙
    
    주문 후 예상 잔고가 최소 잔고 이하면 거부.
    
    Context 필요:
    - config.min_balance: Decimal - 최소 잔고
    - balance.free: Decimal - 사용 가능 잔고
    """
    
    @property
    def name(self) -> str:
        return "MinBalance"
    
    def applies_to(self, command_type: str) -> bool:
        return command_type == CommandTypes.PLACE_ORDER
    
    async def check(
        self,
        command: Command,
        context: dict[str, Any],
    ) -> RiskCheckResult:
        config = context.get("config", {})
        min_balance = Decimal(str(config.get("min_balance", "0")))
        
        if min_balance <= 0:
            return RiskCheckResult(
                passed=True,
                rule_name=self.name,
                reason="Min balance not configured",
            )
        
        balance = context.get("balance", {})
        free_balance = Decimal(str(balance.get("free", "0")))
        
        if free_balance < min_balance:
            # 청산 주문은 허용
            if command.payload.get("reduce_only", False):
                return RiskCheckResult(
                    passed=True,
                    rule_name=self.name,
                    reason="Reduce-only order allowed despite low balance",
                )
            
            return RiskCheckResult(
                passed=False,
                rule_name=self.name,
                reason=f"Balance {free_balance} below minimum {min_balance}",
                details={
                    "free_balance": str(free_balance),
                    "min_balance": str(min_balance),
                },
            )
        
        return RiskCheckResult(
            passed=True,
            rule_name=self.name,
        )
