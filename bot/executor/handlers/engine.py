"""
Engine 제어 Command Handler

PauseEngine, ResumeEngine, SetEngineMode 등 엔진 제어 Command 처리
"""

import logging
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from core.domain.commands import Command, CommandTypes
from core.domain.events import Event, EventTypes
from core.storage.event_store import EventStore
from core.utils.dedup import make_engine_event_dedup_key
from bot.executor.handlers.base import CommandHandler

if TYPE_CHECKING:
    from core.storage.config_store import ConfigStore

logger = logging.getLogger(__name__)


class PauseEngineHandler(CommandHandler):
    """PauseEngine Command 핸들러
    
    엔진을 PAUSED 상태로 전환.
    새로운 주문 발행 중지, 기존 주문은 유지.
    
    Args:
        event_store: 이벤트 저장소
        engine_state_setter: 엔진 상태 변경 함수
    """
    
    def __init__(
        self,
        event_store: EventStore,
        engine_state_setter: Any,
    ):
        self.event_store = event_store
        self.engine_state_setter = engine_state_setter
    
    @property
    def command_type(self) -> str:
        return CommandTypes.PAUSE_ENGINE
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """엔진 일시정지"""
        events: list[Event] = []
        
        try:
            reason = command.payload.get("reason", "Manual pause")
            
            # 엔진 상태 변경
            if self.engine_state_setter:
                await self.engine_state_setter("PAUSED")
            
            # 이벤트 생성
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            event = Event.create(
                event_type=EventTypes.ENGINE_PAUSED,
                source="BOT",
                entity_kind="ENGINE",
                entity_id="main",
                scope=command.scope,
                dedup_key=make_engine_event_dedup_key("paused", now_ms),
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "reason": reason,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                    "paused_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            events.append(event)
            
            await self.event_store.append(event)
            
            logger.info(
                f"Engine paused: {reason}",
                extra={
                    "command_id": command.command_id,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                },
            )
            
            return True, {"status": "PAUSED"}, None, events
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"PauseEngine failed: {error_msg}")
            return False, {}, error_msg, events


class ResumeEngineHandler(CommandHandler):
    """ResumeEngine Command 핸들러
    
    엔진을 RUNNING 상태로 복귀.
    
    Args:
        event_store: 이벤트 저장소
        engine_state_setter: 엔진 상태 변경 함수
    """
    
    def __init__(
        self,
        event_store: EventStore,
        engine_state_setter: Any,
    ):
        self.event_store = event_store
        self.engine_state_setter = engine_state_setter
    
    @property
    def command_type(self) -> str:
        return CommandTypes.RESUME_ENGINE
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """엔진 재개"""
        events: list[Event] = []
        
        try:
            reason = command.payload.get("reason", "Manual resume")
            
            # 엔진 상태 변경
            if self.engine_state_setter:
                await self.engine_state_setter("RUNNING")
            
            # 이벤트 생성
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            event = Event.create(
                event_type=EventTypes.ENGINE_RESUMED,
                source="BOT",
                entity_kind="ENGINE",
                entity_id="main",
                scope=command.scope,
                dedup_key=make_engine_event_dedup_key("resumed", now_ms),
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "reason": reason,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                    "resumed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            events.append(event)
            
            await self.event_store.append(event)
            
            logger.info(
                f"Engine resumed: {reason}",
                extra={
                    "command_id": command.command_id,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                },
            )
            
            return True, {"status": "RUNNING"}, None, events
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"ResumeEngine failed: {error_msg}")
            return False, {}, error_msg, events


class SetEngineModeHandler(CommandHandler):
    """SetEngineMode Command 핸들러
    
    엔진 모드 변경 (RUNNING, PAUSED, SAFE).
    SAFE 모드: 새 주문 금지, 청산만 허용.
    
    Args:
        event_store: 이벤트 저장소
        engine_state_setter: 엔진 상태 변경 함수
    """
    
    def __init__(
        self,
        event_store: EventStore,
        engine_state_setter: Any,
    ):
        self.event_store = event_store
        self.engine_state_setter = engine_state_setter
    
    @property
    def command_type(self) -> str:
        return CommandTypes.SET_ENGINE_MODE
    
    async def execute(
        self,
        command: Command,
    ) -> tuple[bool, dict[str, Any], str | None, list[Event]]:
        """엔진 모드 설정"""
        events: list[Event] = []
        
        try:
            new_mode = command.payload.get("mode")
            if not new_mode:
                return False, {}, "mode is required", events
            
            valid_modes = ["RUNNING", "PAUSED", "SAFE"]
            if new_mode not in valid_modes:
                return False, {}, f"Invalid mode: {new_mode}. Valid: {valid_modes}", events
            
            reason = command.payload.get("reason", f"Set mode to {new_mode}")
            
            # 엔진 상태 변경
            if self.engine_state_setter:
                await self.engine_state_setter(new_mode)
            
            # 이벤트 생성
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            
            event = Event.create(
                event_type=EventTypes.ENGINE_MODE_CHANGED,
                source="BOT",
                entity_kind="ENGINE",
                entity_id="main",
                scope=command.scope,
                dedup_key=make_engine_event_dedup_key("mode_changed", now_ms),
                command_id=command.command_id,
                correlation_id=command.correlation_id,
                payload={
                    "new_mode": new_mode,
                    "reason": reason,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                    "changed_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            events.append(event)
            
            await self.event_store.append(event)
            
            logger.info(
                f"Engine mode changed to {new_mode}: {reason}",
                extra={
                    "command_id": command.command_id,
                    "actor": f"{command.actor.kind}:{command.actor.id}",
                },
            )
            
            return True, {"status": new_mode}, None, events
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"SetEngineMode failed: {error_msg}")
            return False, {}, error_msg, events
