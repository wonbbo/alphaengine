"""
거래 내역 라우트

거래 내역 페이지 및 API
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.transaction_service import TransactionService

router = APIRouter(tags=["Transactions"])

# 템플릿 설정
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# =========================================================================
# 페이지 라우트
# =========================================================================


@router.get("/transactions", response_class=HTMLResponse)
async def transactions_page(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    """거래 내역 페이지"""
    return templates.TemplateResponse("transactions.html", {
        "request": request,
        "active_page": "transactions",
        "mode": settings.mode.value.upper(),
    })


# =========================================================================
# API 라우트
# =========================================================================


@router.get("/api/transactions")
async def get_transactions(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """거래 내역 목록 조회"""
    service = TransactionService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_transactions(mode, symbol, limit, offset)
