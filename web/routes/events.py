"""
Events 라우트

이벤트 히스토리 조회 API
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query, HTTPException

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from core.domain.events import EventTypes
from web.dependencies import get_db, get_app_settings
from web.models.responses import (
    EventListResponse,
    EventResponse,
    ScopeResponse,
)
from web.services.event_service import EventService

router = APIRouter(prefix="/api", tags=["Events"])


@router.get("/events", response_model=EventListResponse)
async def get_events(
    event_type: str | None = Query(default=None, description="이벤트 타입 필터"),
    entity_kind: str | None = Query(default=None, description="엔티티 종류 필터"),
    entity_id: str | None = Query(default=None, description="엔티티 ID 필터"),
    symbol: str | None = Query(default=None, description="심볼 필터"),
    from_ts: datetime | None = Query(default=None, description="시작 시간 (UTC)"),
    to_ts: datetime | None = Query(default=None, description="종료 시간 (UTC)"),
    limit: int = Query(default=100, ge=1, le=500, description="조회 제한"),
    offset: int = Query(default=0, ge=0, description="조회 시작 위치"),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> EventListResponse:
    """이벤트 목록 조회
    
    필터링, 페이지네이션 지원.
    """
    service = EventService(db)
    mode = settings.mode.value.upper()
    
    # 이벤트 조회
    events_data = await service.get_events(
        mode=mode,
        event_type=event_type,
        entity_kind=entity_kind,
        entity_id=entity_id,
        symbol=symbol,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
    )
    
    events = [
        EventResponse(
            event_id=e["event_id"],
            event_type=e["event_type"],
            ts=e["ts"],
            source=e["source"],
            entity_kind=e["entity_kind"],
            entity_id=e["entity_id"],
            scope=ScopeResponse(
                exchange=e["scope"]["exchange"],
                venue=e["scope"]["venue"],
                account_id=e["scope"]["account_id"],
                symbol=e["scope"].get("symbol"),
                mode=e["scope"]["mode"],
            ),
            payload=e["payload"],
        )
        for e in events_data
    ]
    
    # 전체 개수
    total_count = await service.get_event_count(
        mode=mode,
        event_type=event_type,
        entity_kind=entity_kind,
        symbol=symbol,
    )
    
    return EventListResponse(
        events=events,
        total_count=total_count,
        limit=limit,
        offset=offset,
    )


@router.get("/events/types", response_model=list[str])
async def get_event_types(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[str]:
    """사용 가능한 이벤트 타입 목록 조회
    
    DB에 존재하는 이벤트 타입만 반환.
    """
    service = EventService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_event_types(mode)


@router.get("/events/all-types", response_model=list[str])
async def get_all_event_types() -> list[str]:
    """정의된 모든 이벤트 타입 목록
    
    TRD에 정의된 전체 이벤트 타입.
    """
    return EventTypes.all_types()
