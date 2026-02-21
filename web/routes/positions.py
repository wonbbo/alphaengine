"""
포지션 라우트

포지션 히스토리 및 상세 조회
"""

from fastapi import APIRouter, Depends, Query, Path, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path as FilePath

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.position_service import PositionService

router = APIRouter(tags=["Positions"])

# 템플릿 설정
TEMPLATES_DIR = FilePath(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================================================================
# 페이지 라우트
# =========================================================================


@router.get("/positions", response_class=HTMLResponse)
async def positions_page(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    """포지션 히스토리 페이지"""
    return templates.TemplateResponse("positions.html", {
        "request": request,
        "active_page": "positions",
        "mode": settings.mode.value.upper(),
    })


@router.get("/positions/{session_id}", response_class=HTMLResponse)
async def position_detail_page(
    request: Request,
    session_id: str = Path(...),
    settings: Settings = Depends(get_app_settings),
):
    """포지션 상세 페이지"""
    return templates.TemplateResponse("position_detail.html", {
        "request": request,
        "active_page": "positions",
        "mode": settings.mode.value.upper(),
        "session_id": session_id,
    })


# =========================================================================
# API 라우트
# =========================================================================


@router.get("/api/positions")
async def get_positions(
    status: str | None = Query(default=None, description="OPEN or CLOSED"),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """포지션 목록 조회"""
    service = PositionService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_positions(mode, status, symbol, limit, offset)


@router.get("/api/positions/{session_id}")
async def get_position_detail(
    session_id: str = Path(...),
    db: SQLiteAdapter = Depends(get_db),
):
    """포지션 상세 조회"""
    service = PositionService(db)
    result = await service.get_position_detail(session_id)
    
    if result is None:
        raise HTTPException(status_code=404, detail="Position not found")
    
    return result


@router.get("/api/positions/{session_id}/trades")
async def get_position_trades(
    session_id: str = Path(...),
    db: SQLiteAdapter = Depends(get_db),
):
    """포지션 내 거래 목록"""
    service = PositionService(db)
    return await service.get_position_trades(session_id)
