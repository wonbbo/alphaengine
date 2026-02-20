"""
Config 라우트

설정 조회 및 변경 API
"""

from fastapi import APIRouter, Depends, HTTPException, Path

from adapters.db.sqlite_adapter import SQLiteAdapter
from web.dependencies import get_db, get_db_write
from web.models.requests import ConfigUpdateRequest
from web.models.responses import ConfigResponse
from web.services.config_service import ConfigService

router = APIRouter(prefix="/api", tags=["Config"])


@router.get("/config", response_model=list[ConfigResponse])
async def get_all_configs(
    db: SQLiteAdapter = Depends(get_db),
) -> list[ConfigResponse]:
    """모든 설정 조회"""
    service = ConfigService(db)
    
    configs = await service.get_all_configs()
    
    return [
        ConfigResponse(
            key=c["key"],
            value=c["value"],
            version=c["version"],
            updated_at=c["updated_at"],
            updated_by=c["updated_by"],
        )
        for c in configs
    ]


@router.get("/config/{key}", response_model=ConfigResponse)
async def get_config(
    key: str = Path(..., description="설정 키"),
    db: SQLiteAdapter = Depends(get_db),
) -> ConfigResponse:
    """설정 조회"""
    service = ConfigService(db)
    
    config = await service.get_config(key)
    
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Config not found: {key}"
        )
    
    return ConfigResponse(
        key=config["key"],
        value=config["value"],
        version=config["version"],
        updated_at=config["updated_at"],
        updated_by=config["updated_by"],
    )


@router.put("/config/{key}", response_model=ConfigResponse)
async def update_config(
    request: ConfigUpdateRequest,
    key: str = Path(..., description="설정 키"),
    db: SQLiteAdapter = Depends(get_db_write),
) -> ConfigResponse:
    """설정 변경
    
    낙관적 락을 사용하여 동시 수정 충돌 방지.
    expected_version을 지정하면 해당 버전일 때만 업데이트.
    """
    service = ConfigService(db)
    
    try:
        config = await service.update_config(
            key=key,
            value=request.value,
            updated_by="web:admin",
            expected_version=request.expected_version,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )
    
    return ConfigResponse(
        key=config["key"],
        value=config["value"],
        version=config["version"],
        updated_at=config["updated_at"],
        updated_by=config["updated_by"],
    )


@router.delete("/config/{key}")
async def delete_config(
    key: str = Path(..., description="설정 키"),
    db: SQLiteAdapter = Depends(get_db_write),
) -> dict[str, str]:
    """설정 삭제"""
    service = ConfigService(db)
    
    deleted = await service.delete_config(key)
    
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Config not found: {key}"
        )
    
    return {"message": f"Config deleted: {key}"}
