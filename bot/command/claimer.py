"""
Command Claimer

NEW 상태 Command를 클레임하여 SENT로 전환.
Bot 메인 루프에서 주기적으로 호출.
"""

import logging
from typing import Any

from core.storage.command_store import CommandStore
from core.domain.commands import Command
from core.types import CommandStatus

logger = logging.getLogger(__name__)


class CommandClaimer:
    """Command 클레이머
    
    CommandStore에서 NEW 상태 Command를 클레임하여 반환.
    우선순위 높은 순으로 가장 오래된 Command부터 클레임.
    
    Args:
        command_store: Command 저장소
        
    사용 예시:
    ```python
    claimer = CommandClaimer(command_store)
    
    # 하나씩 클레임
    cmd = await claimer.claim_one()
    if cmd:
        # 처리...
        
    # 배치 클레임
    commands = await claimer.claim_batch(max_count=5)
    for cmd in commands:
        # 처리...
    ```
    """
    
    def __init__(self, command_store: CommandStore):
        self.command_store = command_store
        
        # 통계
        self._claimed_count = 0
    
    async def claim_one(self) -> Command | None:
        """Command 하나 클레임
        
        NEW → SENT 상태 전환 후 반환.
        
        Returns:
            클레임된 Command 또는 None
        """
        command = await self.command_store.claim_one()
        
        if command:
            self._claimed_count += 1
            logger.info(
                f"Command claimed: {command.command_type}",
                extra={
                    "command_id": command.command_id,
                    "priority": command.priority,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                },
            )
        
        return command
    
    async def claim_batch(self, max_count: int = 10) -> list[Command]:
        """Command 배치 클레임
        
        최대 max_count 개까지 클레임.
        
        Args:
            max_count: 최대 클레임 수
            
        Returns:
            클레임된 Command 리스트
        """
        commands: list[Command] = []
        
        for _ in range(max_count):
            command = await self.claim_one()
            if command:
                commands.append(command)
            else:
                break
        
        return commands
    
    async def get_pending_count(self) -> int:
        """처리 대기 중인 Command 수
        
        Returns:
            NEW + SENT 상태 Command 수
        """
        return await self.command_store.get_pending_count()
    
    async def get_new_count(self) -> int:
        """NEW 상태 Command 수"""
        return await self.command_store.count_by_status(CommandStatus.NEW)
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "claimed_count": self._claimed_count,
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._claimed_count = 0
