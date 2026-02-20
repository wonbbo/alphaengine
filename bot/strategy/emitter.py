"""
Command Emitter 구현

전략에서 Command를 발행하기 위한 구현체
"""

import logging
from decimal import Decimal
from typing import Any

from core.domain.commands import Command, CommandTypes, CommandPriority
from core.storage.command_store import CommandStore
from core.types import Scope, Actor
from strategies.base import CommandEmitter

logger = logging.getLogger(__name__)


class CommandEmitterImpl:
    """Command Emitter 구현체
    
    전략에서 호출하는 emit.place_order() 등의 실제 구현.
    RiskGuard를 통과한 후 CommandStore에 저장.
    
    Args:
        command_store: Command 저장소
        scope: 거래 범위
        strategy_name: 전략 이름 (Actor ID용)
        risk_guard: 리스크 검증기 (선택)
        
    구현 노트:
    - 모든 메서드는 CommandEmitter 프로토콜을 구현
    - RiskGuard 검증 실패 시 빈 문자열 반환
    """
    
    def __init__(
        self,
        command_store: CommandStore,
        scope: Scope,
        strategy_name: str,
        risk_guard: Any = None,
    ):
        self.command_store = command_store
        self.scope = scope
        self.strategy_name = strategy_name
        self.risk_guard = risk_guard
        
        # Actor 정보
        self._actor = Actor(kind="STRATEGY", id=strategy_name)
    
    async def place_order(
        self,
        side: str,
        order_type: str,
        quantity: str | Decimal,
        price: str | Decimal | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        position_side: str = "BOTH",
    ) -> str:
        """주문 Command 발행"""
        payload = {
            "symbol": self.scope.symbol,
            "side": side.upper(),
            "order_type": order_type.upper(),
            "quantity": str(quantity),
            "time_in_force": time_in_force,
            "reduce_only": reduce_only,
            "position_side": position_side,
        }
        
        if price is not None:
            payload["price"] = str(price)
        
        command = Command.create(
            command_type=CommandTypes.PLACE_ORDER,
            actor=self._actor,
            scope=self.scope,
            payload=payload,
            priority=CommandPriority.STRATEGY,
        )
        
        # RiskGuard 검증
        if self.risk_guard:
            passed, reason = await self.risk_guard.check(command)
            if not passed:
                logger.warning(
                    f"Strategy order rejected: {reason}",
                    extra={
                        "strategy": self.strategy_name,
                        "side": side,
                        "quantity": str(quantity),
                    },
                )
                return ""
        
        # CommandStore에 저장
        await self.command_store.insert(command)
        
        logger.info(
            f"Strategy order submitted: {side} {quantity} {self.scope.symbol}",
            extra={
                "command_id": command.command_id,
                "strategy": self.strategy_name,
            },
        )
        
        return command.command_id
    
    async def cancel_order(
        self,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> str:
        """주문 취소 Command 발행"""
        if not exchange_order_id and not client_order_id:
            logger.warning("cancel_order requires exchange_order_id or client_order_id")
            return ""
        
        payload = {
            "symbol": self.scope.symbol,
        }
        
        if exchange_order_id:
            payload["exchange_order_id"] = exchange_order_id
        if client_order_id:
            payload["client_order_id"] = client_order_id
        
        command = Command.create(
            command_type=CommandTypes.CANCEL_ORDER,
            actor=self._actor,
            scope=self.scope,
            payload=payload,
            priority=CommandPriority.STRATEGY,
        )
        
        await self.command_store.insert(command)
        
        logger.info(
            f"Strategy cancel submitted",
            extra={
                "command_id": command.command_id,
                "exchange_order_id": exchange_order_id,
            },
        )
        
        return command.command_id
    
    async def close_position(self, reduce_only: bool = True) -> str:
        """포지션 청산 Command 발행
        
        현재 포지션을 시장가로 청산.
        """
        command = Command.create(
            command_type=CommandTypes.CLOSE_POSITION,
            actor=self._actor,
            scope=self.scope,
            payload={
                "symbol": self.scope.symbol,
                "reduce_only": reduce_only,
            },
            priority=CommandPriority.STRATEGY,
        )
        
        await self.command_store.insert(command)
        
        logger.info(
            f"Strategy close position submitted",
            extra={
                "command_id": command.command_id,
                "symbol": self.scope.symbol,
            },
        )
        
        return command.command_id
    
    async def cancel_all_orders(self) -> str:
        """모든 오픈 주문 취소 Command 발행"""
        command = Command.create(
            command_type=CommandTypes.CANCEL_ALL,
            actor=self._actor,
            scope=self.scope,
            payload={
                "symbol": self.scope.symbol,
            },
            priority=CommandPriority.STRATEGY,
        )
        
        await self.command_store.insert(command)
        
        logger.info(
            f"Strategy cancel all submitted",
            extra={
                "command_id": command.command_id,
                "symbol": self.scope.symbol,
            },
        )
        
        return command.command_id


# CommandEmitter 프로토콜 구현 확인
def _verify_protocol() -> None:
    """프로토콜 구현 확인 (타입 체커용)"""
    emitter: CommandEmitter = CommandEmitterImpl(
        command_store=None,  # type: ignore
        scope=None,  # type: ignore
        strategy_name="test",
    )
    _ = emitter  # 사용
