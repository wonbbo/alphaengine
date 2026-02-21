"""
Trading Edge 라우트

성과 분석 페이지 및 API
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.trading_edge_service import TradingEdgeService

router = APIRouter(tags=["TradingEdge"])

# 템플릿 설정
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================================================================
# 페이지 라우트
# =========================================================================


@router.get("/trading-edge", response_class=HTMLResponse)
async def trading_edge_page(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    """Trading Edge 페이지"""
    return templates.TemplateResponse("trading_edge.html", {
        "request": request,
        "active_page": "trading_edge",
        "mode": settings.mode.value.upper(),
    })


# =========================================================================
# API 라우트
# =========================================================================


@router.get("/api/trading-edge/summary")
async def get_edge_summary(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """Trading Edge 요약"""
    service = TradingEdgeService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_edge_summary(mode)


@router.get("/api/trading-edge/symbols")
async def get_symbol_performance(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """심볼별 성과"""
    service = TradingEdgeService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_symbol_performance(mode)


@router.get("/api/trading-edge/daily-series")
async def get_daily_edge_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 Edge 시계열"""
    service = TradingEdgeService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_daily_edge_series(mode, days)
