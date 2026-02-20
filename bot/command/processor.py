"""
Command Processor

클레임된 Command를 Executor에 전달하여 처리.
처리 결과에 따라 상태 업데이트 및 이벤트 기록.
"""

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from core.domain.commands import Command, CommandTypes
from core.storage.command_store import CommandStore
from core.types import CommandStatus
from bot.command.claimer import CommandClaimer

if TYPE_CHECKING:
    from bot.executor.executor import CommandExecutor
    from bot.risk.guard import RiskGuard

logger = logging.getLogger(__name__)


class CommandProcessor:
    """Command 프로세서
    
    Command를 클레임하고 Executor를 통해 실행.
    RiskGuard 검증 → Executor 실행 → 상태 업데이트 흐름.
    
    Args:
        command_store: Command 저장소
        executor: Command 실행기
        risk_guard: 리스크 검증기 (선택)
        
    사용 예시:
    ```python
    processor = CommandProcessor(
        command_store=command_store,
        executor=executor,
        risk_guard=risk_guard,
    )
    
    # 단일 처리
    processed = await processor.process_one()
    
    # 배치 처리 (메인 루프에서 호출)
    count = await processor.process_batch(max_count=10)
    ```
    """
    
    def __init__(
        self,
        command_store: CommandStore,
        executor: "CommandExecutor",
        risk_guard: "RiskGuard | None" = None,
    ):
        self.command_store = command_store
        self.executor = executor
        self.risk_guard = risk_guard
        self.claimer = CommandClaimer(command_store)
        
        # 통계
        self._processed_count = 0
        self._success_count = 0
        self._failed_count = 0
        self._rejected_count = 0  # RiskGuard 거부
    
    async def process_one(self) -> bool:
        """Command 하나 처리
        
        Returns:
            True: Command를 처리함
            False: 처리할 Command 없음
        """
        # 1. Command 클레임
        command = await self.claimer.claim_one()
        if not command:
            return False
        
        self._processed_count += 1
        
        try:
            # 2. RiskGuard 검증 (실행 직전 최종 검증)
            if self.risk_guard:
                passed, reject_reason = await self.risk_guard.check(command)
                if not passed:
                    self._rejected_count += 1
                    await self._handle_rejection(command, reject_reason)
                    return True
            
            # 3. Executor 실행
            success, result, error = await self.executor.execute(command)
            
            # 4. 상태 업데이트
            if success:
                self._success_count += 1
                await self.command_store.update_status(
                    command.command_id,
                    CommandStatus.ACK,
                    result=result,
                )
                logger.info(
                    f"Command executed: {command.command_type}",
                    extra={
                        "command_id": command.command_id,
                        "status": "ACK",
                    },
                )
            else:
                self._failed_count += 1
                await self.command_store.update_status(
                    command.command_id,
                    CommandStatus.FAILED,
                    error=error,
                )
                logger.warning(
                    f"Command failed: {command.command_type}",
                    extra={
                        "command_id": command.command_id,
                        "error": error,
                    },
                )
            
            return True
            
        except Exception as e:
            self._failed_count += 1
            error_msg = str(e)
            
            await self.command_store.update_status(
                command.command_id,
                CommandStatus.FAILED,
                error=error_msg,
            )
            
            logger.error(
                f"Command processing error: {command.command_type}",
                extra={
                    "command_id": command.command_id,
                    "error": error_msg,
                },
            )
            
            return True
    
    async def process_batch(self, max_count: int = 10) -> int:
        """Command 배치 처리
        
        Args:
            max_count: 최대 처리 수
            
        Returns:
            실제 처리된 수
        """
        count = 0
        
        for _ in range(max_count):
            processed = await self.process_one()
            if processed:
                count += 1
            else:
                break
        
        return count
    
    async def process_all_pending(self) -> int:
        """모든 대기 중인 Command 처리
        
        Returns:
            처리된 Command 수
        """
        total = 0
        
        while True:
            processed = await self.process_one()
            if processed:
                total += 1
            else:
                break
        
        return total
    
    async def _handle_rejection(
        self,
        command: Command,
        reason: str | None,
    ) -> None:
        """RiskGuard 거부 처리
        
        Args:
            command: 거부된 Command
            reason: 거부 사유
        """
        error_msg = f"RiskGuard rejected: {reason}"
        
        await self.command_store.update_status(
            command.command_id,
            CommandStatus.FAILED,
            error=error_msg,
        )
        
        logger.warning(
            f"Command rejected by RiskGuard: {command.command_type}",
            extra={
                "command_id": command.command_id,
                "reason": reason,
            },
        )
    
    async def get_pending_count(self) -> int:
        """처리 대기 중인 Command 수"""
        return await self.claimer.get_pending_count()
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "processed_count": self._processed_count,
            "success_count": self._success_count,
            "failed_count": self._failed_count,
            "rejected_count": self._rejected_count,
            "claimer_stats": self.claimer.get_stats(),
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._processed_count = 0
        self._success_count = 0
        self._failed_count = 0
        self._rejected_count = 0
        self.claimer.reset_stats()
