"""
Projection Handler 기본 클래스

모든 Projection Handler가 구현해야 할 인터페이스 정의
"""

from abc import ABC, abstractmethod
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event


class ProjectionHandler(ABC):
    """Projection Handler 추상 클래스
    
    이벤트 타입별로 이 클래스를 상속하여 Projection 업데이트 로직 구현.
    
    Args:
        adapter: SQLite 어댑터
    """
    
    def __init__(self, adapter: SQLiteAdapter):
        self.adapter = adapter
    
    @abstractmethod
    async def handle(self, event: Event) -> bool:
        """이벤트 처리하여 Projection 업데이트
        
        Args:
            event: 처리할 이벤트
            
        Returns:
            True: 성공
            False: 실패
        """
        pass
    
    @property
    @abstractmethod
    def handled_event_types(self) -> list[str]:
        """처리하는 이벤트 타입 목록"""
        pass
    
    async def initialize(self) -> None:
        """핸들러 초기화 (테이블 생성 등)
        
        하위 클래스에서 필요 시 오버라이드.
        Projector 시작 시 호출됨.
        """
        pass
