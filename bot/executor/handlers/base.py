"""
Command Handler 기본 클래스

모든 Command Handler가 구현해야 할 인터페이스 정의
"""

from abc import ABC, abstractmethod
from typing import Any

from core.domain.commands import Command
from core.domain.events import Event


class CommandHandler(ABC):
    """Command Handler 추상 클래스
    
    각 Command 타입별로 이 클래스를 상속하여 구현.
    
    Returns:
        execute() 반환값:
        - success: bool - 성공 여부
        - result: dict - 실행 결과 (성공 시)
        - error: str | None - 에러 메시지 (실패 시)
        - events: list[Event] - 생성된 이벤트 리스트
    """
    
    @abstractmethod
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """Command 실행
        
        Args:
            command: 실행할 Command
            
        Returns:
            (success, result, error, events) 튜플
        """
        pass
    
    @property
    @abstractmethod
    def command_type(self) -> str:
        """처리하는 Command 타입"""
        pass
