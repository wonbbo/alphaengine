"""
Bot Bootstrap

설정 로드, 의존성 주입, 메인 루프 관리.
EngineStarted/EngineStopped 이벤트로 생명주기 관리.
"""

import asyncio
import logging
import sys
from datetime import datetime, timezone
from uuid import uuid4

from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from core.config.loader import get_settings
from core.constants import Defaults
from core.domain.events import Event
from core.storage.event_store import EventStore
from core.types import Scope

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bot")


def create_scope(settings) -> Scope:
    """기본 Scope 생성"""
    return Scope(
        exchange=Defaults.EXCHANGE,
        venue=Defaults.VENUE,
        account_id=Defaults.ACCOUNT_ID,
        symbol=None,
        mode=settings.mode.value.upper(),
    )


def create_engine_started_event(scope: Scope) -> Event:
    """EngineStarted 이벤트 생성"""
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    
    return Event(
        event_id=event_id,
        event_type="EngineStarted",
        ts=now,
        correlation_id=event_id,
        causation_id=None,
        command_id=None,
        source="BOT",
        entity_kind="ENGINE",
        entity_id="main",
        scope=scope,
        dedup_key=f"engine:started:{now.isoformat()}",
        payload={
            "version": "2.0.0",
            "started_at": now.isoformat(),
        },
    )


def create_engine_stopped_event(scope: Scope, reason: str = "graceful") -> Event:
    """EngineStopped 이벤트 생성"""
    now = datetime.now(timezone.utc)
    event_id = str(uuid4())
    
    return Event(
        event_id=event_id,
        event_type="EngineStopped",
        ts=now,
        correlation_id=event_id,
        causation_id=None,
        command_id=None,
        source="BOT",
        entity_kind="ENGINE",
        entity_id="main",
        scope=scope,
        dedup_key=f"engine:stopped:{now.isoformat()}",
        payload={
            "reason": reason,
            "stopped_at": now.isoformat(),
        },
    )


async def run_main_loop(shutdown_event: asyncio.Event) -> None:
    """메인 루프
    
    Phase 5에서 실제 로직 구현:
    - WebSocket 이벤트 처리
    - Command 처리
    - 전략 실행
    - Reconcile
    """
    tick_interval = 0.1  # 100ms
    tick_count = 0
    
    while not shutdown_event.is_set():
        tick_count += 1
        
        # 10초마다 heartbeat 로그
        if tick_count % 100 == 0:
            logger.debug(f"Heartbeat: tick={tick_count}")
        
        # TODO: Phase 5에서 구현할 로직들
        # - projector.apply_pending_events()
        # - command_claimer.claim_one()
        # - strategy_runner.on_tick(ctx)
        # - reconciler.tick()
        
        await asyncio.sleep(tick_interval)


async def main() -> None:
    """Bot 메인 함수"""
    logger.info("=" * 60)
    logger.info("AlphaEngine Bot v2.0.0 시작")
    logger.info("=" * 60)
    
    # 1. 설정 로드
    try:
        settings = get_settings()
    except Exception as e:
        logger.error(f"설정 로드 실패: {e}")
        sys.exit(1)
    
    logger.info(f"Mode: {settings.mode.value}")
    logger.info(f"DB: {settings.db_path}")
    
    scope = create_scope(settings)
    
    # 2. DB 연결 및 스키마 초기화
    async with SQLiteAdapter(settings.db_path) as db:
        # 스키마가 없으면 생성
        await init_schema(db)
        
        event_store = EventStore(db)
        
        # 3. EngineStarted 이벤트 저장
        started_event = create_engine_started_event(scope)
        await event_store.append(started_event)
        logger.info("EngineStarted 이벤트 저장 완료")
        
        # 4. 종료 이벤트 설정
        shutdown_event = asyncio.Event()
        
        # Windows는 signal handler를 지원하지 않으므로 KeyboardInterrupt로 처리
        logger.info("Bot 메인 루프 시작 (종료: Ctrl+C)")
        
        try:
            await run_main_loop(shutdown_event)
        except asyncio.CancelledError:
            logger.info("메인 루프 취소됨")
        except KeyboardInterrupt:
            logger.info("Ctrl+C 감지")
        finally:
            # 5. EngineStopped 이벤트 저장
            stopped_event = create_engine_stopped_event(scope)
            await event_store.append(stopped_event)
            logger.info("EngineStopped 이벤트 저장 완료")
    
    logger.info("=" * 60)
    logger.info("AlphaEngine Bot 정상 종료")
    logger.info("=" * 60)
