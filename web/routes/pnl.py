"""
PnL API 라우트

수익 및 수익률 관련 API
"""

from fastapi import APIRouter, Depends, Query

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.pnl_service import PnLService

router = APIRouter(prefix="/api/pnl", tags=["PnL"])


@router.get("/summary")
async def get_pnl_summary(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """PnL 요약 조회
    
    일일/주간/월간/전체 손익 및 수익률
    """
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_pnl_summary(mode)


@router.get("/daily-series")
async def get_daily_pnl_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 수익 시계열
    
    차트 데이터용
    """
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_daily_pnl_series(mode, days)


@router.get("/cumulative-series")
async def get_cumulative_pnl_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """누적 수익 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_cumulative_pnl_series(mode, days)


@router.get("/returns/daily-series")
async def get_daily_returns_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 수익률 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_daily_returns_series(mode, days)


@router.get("/returns/cumulative-series")
async def get_cumulative_returns_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """누적 수익률 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_cumulative_returns_series(mode, days)
