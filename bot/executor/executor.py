"""
Command Executor

Command를 실행하고 결과 이벤트 생성.
Command 타입별 Handler를 등록하여 실행 위임.
"""

import logging
from typing import Any

from adapters.binance.rest_client import BinanceRestClient
from core.domain.commands import Command, CommandTypes
from core.domain.events import Event
from core.storage.event_store import EventStore
from bot.executor.handlers.base import CommandHandler
from bot.executor.handlers.order import PlaceOrderHandler, CancelOrderHandler
from bot.executor.handlers.engine import (
    PauseEngineHandler,
    ResumeEngineHandler,
    SetEngineModeHandler,
)

logger = logging.getLogger(__name__)


class CommandExecutor:
    """Command Executor
    
    Command 타입별 핸들러를 등록하고 실행.
    각 핸들러는 거래소 API 호출 및 결과 이벤트 생성 담당.
    
    Args:
        rest_client: REST API 클라이언트
        event_store: 이벤트 저장소
        engine_state_setter: 엔진 상태 변경 함수 (선택)
        
    사용 예시:
    ```python
    executor = CommandExecutor(
        rest_client=rest_client,
        event_store=event_store,
    )
    
    success, result, error = await executor.execute(command)
    ```
    """
    
    def __init__(
        self,
        rest_client: BinanceRestClient,
        event_store: EventStore,
        engine_state_setter: Any = None,
        strategy_resume_callback: Any = None,
    ):
        self.rest_client = rest_client
        self.event_store = event_store
        self.engine_state_setter = engine_state_setter
        self.strategy_resume_callback = strategy_resume_callback
        
        # 핸들러 레지스트리
        self._handlers: dict[str, CommandHandler] = {}
        
        # 기본 핸들러 등록
        self._register_default_handlers()
        
        # 통계
        self._execute_count = 0
        self._success_count = 0
        self._failed_count = 0
    
    def _register_default_handlers(self) -> None:
        """기본 핸들러 등록"""
        # Order 핸들러
        self.register_handler(PlaceOrderHandler(
            rest_client=self.rest_client,
            event_store=self.event_store,
        ))
        self.register_handler(CancelOrderHandler(
            rest_client=self.rest_client,
            event_store=self.event_store,
        ))
        
        # Engine 핸들러
        self.register_handler(PauseEngineHandler(
            event_store=self.event_store,
            engine_state_setter=self.engine_state_setter,
        ))
        self.register_handler(ResumeEngineHandler(
            event_store=self.event_store,
            engine_state_setter=self.engine_state_setter,
            strategy_resume_callback=self.strategy_resume_callback,
        ))
        self.register_handler(SetEngineModeHandler(
            event_store=self.event_store,
            engine_state_setter=self.engine_state_setter,
        ))
    
    def register_handler(self, handler: CommandHandler) -> None:
        """핸들러 등록
        
        Args:
            handler: Command 핸들러
        """
        self._handlers[handler.command_type] = handler
        logger.debug(f"Handler registered: {handler.command_type}")
    
    def get_handler(self, command_type: str) -> CommandHandler | None:
        """핸들러 조회"""
        return self._handlers.get(command_type)
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Command 실행
        
        Args:
            command: 실행할 Command
            
        Returns:
            (success, result, error) 튜플
            - success: 성공 여부
            - result: 실행 결과 (성공 시)
            - error: 에러 메시지 (실패 시)
        """
        self._execute_count += 1
        
        handler = self._handlers.get(command.command_type)
        
        if not handler:
            error_msg = f"No handler for command type: {command.command_type}"
            logger.error(error_msg)
            self._failed_count += 1
            return False, None, error_msg
        
        try:
            # 핸들러 실행
            success, result, error, events = await handler.execute(command)
            
            if success:
                self._success_count += 1
                logger.debug(
                    f"Command executed: {command.command_type}",
                    extra={
                        "command_id": command.command_id,
                        "result": result,
                    },
                )
            else:
                self._failed_count += 1
                logger.warning(
                    f"Command failed: {command.command_type}",
                    extra={
                        "command_id": command.command_id,
                        "error": error,
                    },
                )
            
            return success, result, error
            
        except Exception as e:
            self._failed_count += 1
            error_msg = str(e)
            
            logger.error(
                f"Command execution error: {command.command_type}",
                extra={
                    "command_id": command.command_id,
                    "error": error_msg,
                },
            )
            
            return False, None, error_msg
    
    def set_engine_state_setter(self, setter: Any) -> None:
        """엔진 상태 변경 함수 설정
        
        Engine 핸들러들에 상태 변경 함수 전달.
        
        Args:
            setter: async def setter(state: str) -> None
        """
        self.engine_state_setter = setter
        
        # Engine 핸들러들 업데이트
        for handler in self._handlers.values():
            if hasattr(handler, "engine_state_setter"):
                handler.engine_state_setter = setter
    
    @property
    def supported_commands(self) -> list[str]:
        """지원하는 Command 타입 목록"""
        return list(self._handlers.keys())
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "execute_count": self._execute_count,
            "success_count": self._success_count,
            "failed_count": self._failed_count,
            "supported_commands": self.supported_commands,
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._execute_count = 0
        self._success_count = 0
        self._failed_count = 0
