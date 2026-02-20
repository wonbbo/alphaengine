"""
Commands 라우트

Command 발행 및 조회 API
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Path

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from core.types import Scope
from core.domain.commands import CommandTypes
from web.dependencies import get_db, get_db_write, get_app_settings
from web.models.requests import CommandCreateRequest
from web.models.responses import (
    CommandResponse,
    CommandDetailResponse,
    CommandListResponse,
    ActorResponse,
    ScopeResponse,
)
from web.services.command_service import CommandService

router = APIRouter(prefix="/api", tags=["Commands"])


@router.post("/commands", response_model=CommandResponse)
async def create_command(
    request: CommandCreateRequest,
    db: SQLiteAdapter = Depends(get_db_write),
    settings: Settings = Depends(get_app_settings),
) -> CommandResponse:
    """Command 발행
    
    Web에서 Bot으로 Command를 발행.
    Bot이 주기적으로 NEW 상태 Command를 조회하여 처리.
    
    **지원 명령 타입**:
    - ClosePosition: 포지션 청산
    - CancelAll: 모든 주문 취소
    - CancelOrder: 특정 주문 취소
    - PauseEngine: 엔진 일시 정지
    - ResumeEngine: 엔진 재개
    - SetLeverage: 레버리지 설정
    - UpdateConfig: 설정 변경
    """
    service = CommandService(db)
    mode = settings.mode.value.upper()
    
    # 명령 타입 검증
    if not CommandTypes.is_valid_type(request.command_type):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid command type: {request.command_type}. "
                   f"Valid types: {CommandTypes.all_types()}"
        )
    
    # Scope 생성
    scope = Scope(
        exchange=request.scope.exchange,
        venue=request.scope.venue,
        account_id=request.scope.account_id,
        symbol=request.scope.symbol,
        mode=mode,
    )
    
    # Command 생성
    result = await service.create_command(
        command_type=request.command_type,
        scope=scope,
        payload=request.payload,
        priority=request.priority,
        actor_id="web:admin",
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
    )
    
    return CommandResponse(
        command_id=result["command_id"],
        status=result["status"],
        message=result["message"],
    )


@router.get("/commands", response_model=CommandListResponse)
async def get_commands(
    status: str | None = Query(default=None, description="상태 필터 (NEW/SENT/ACK/FAILED)"),
    limit: int = Query(default=50, ge=1, le=200, description="조회 제한"),
    include_completed: bool = Query(default=True, description="완료된 것도 포함"),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> CommandListResponse:
    """Command 목록 조회"""
    service = CommandService(db)
    mode = settings.mode.value.upper()
    
    commands_data = await service.get_commands(
        mode=mode,
        status=status,
        limit=limit,
        include_completed=include_completed,
    )
    
    commands = [
        CommandDetailResponse(
            command_id=c["command_id"],
            command_type=c["command_type"],
            ts=c["ts"],
            actor=ActorResponse(
                kind=c["actor"]["kind"],
                id=c["actor"]["id"],
            ),
            scope=ScopeResponse(
                exchange=c["scope"]["exchange"],
                venue=c["scope"]["venue"],
                account_id=c["scope"]["account_id"],
                symbol=c["scope"].get("symbol"),
                mode=c["scope"]["mode"],
            ),
            status=c["status"],
            priority=c["priority"],
            payload=c["payload"],
            result=c.get("result"),
            last_error=c.get("last_error"),
        )
        for c in commands_data
    ]
    
    total_count = await service.get_command_count(mode, status)
    
    return CommandListResponse(
        commands=commands,
        total_count=total_count,
    )


@router.get("/commands/{command_id}", response_model=CommandDetailResponse)
async def get_command(
    command_id: str = Path(..., description="Command ID"),
    db: SQLiteAdapter = Depends(get_db),
) -> CommandDetailResponse:
    """Command 상세 조회"""
    service = CommandService(db)
    
    command = await service.get_command(command_id)
    
    if not command:
        raise HTTPException(
            status_code=404,
            detail=f"Command not found: {command_id}"
        )
    
    return CommandDetailResponse(
        command_id=command["command_id"],
        command_type=command["command_type"],
        ts=command["ts"],
        actor=ActorResponse(
            kind=command["actor"]["kind"],
            id=command["actor"]["id"],
        ),
        scope=ScopeResponse(
            exchange=command["scope"]["exchange"],
            venue=command["scope"]["venue"],
            account_id=command["scope"]["account_id"],
            symbol=command["scope"].get("symbol"),
            mode=command["scope"]["mode"],
        ),
        status=command["status"],
        priority=command["priority"],
        payload=command["payload"],
        result=command.get("result"),
        last_error=command.get("last_error"),
    )


@router.get("/commands/types/all", response_model=list[str])
async def get_all_command_types() -> list[str]:
    """지원되는 모든 Command 타입 목록"""
    return CommandTypes.all_types()
