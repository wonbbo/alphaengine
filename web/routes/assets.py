"""
자산 라우트

자산 현황 페이지 및 API
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.asset_service import AssetService

router = APIRouter(tags=["Assets"])

# 템플릿 설정
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================================================================
# 페이지 라우트
# =========================================================================


@router.get("/assets", response_class=HTMLResponse)
async def assets_page(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    """자산 현황 페이지"""
    return templates.TemplateResponse("assets.html", {
        "request": request,
        "active_page": "assets",
        "mode": settings.mode.value.upper(),
    })


# =========================================================================
# API 라우트
# =========================================================================


@router.get("/api/assets")
async def get_assets(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """자산 현황 조회"""
    service = AssetService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_portfolio_summary(mode)


@router.get("/api/assets/trial-balance")
async def get_trial_balance(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """시산표 조회"""
    service = AssetService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_trial_balance(mode)
