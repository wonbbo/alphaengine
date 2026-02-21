"""
복식부기 API 라우트

View 기반 고성능 조회 API
"""

from fastapi import APIRouter, Depends, Query

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from core.ledger.store import LedgerStore
from web.dependencies import get_db, get_app_settings

router = APIRouter(prefix="/api/ledger", tags=["Ledger"])


@router.get("/trade-summary")
async def get_trade_summary(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """거래 요약 조회 (v_trade_summary)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_trade_summary(mode, symbol, limit, offset)


@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 손익 시계열 (v_daily_pnl)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_daily_pnl_series(mode, days)


@router.get("/pnl-stats")
async def get_pnl_statistics(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """PnL 통계 요약"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_pnl_statistics(mode)


@router.get("/portfolio")
async def get_portfolio(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """포트폴리오 현황 (v_portfolio)
    
    잔액이 0인 계정 및 UNKNOWN 코인은 제외.
    """
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    portfolio = await store.get_portfolio(mode)
    
    # 잔액이 0인 계정 및 UNKNOWN 코인 필터링
    return [
        p for p in portfolio
        if (p.get("balance") or 0) != 0 and p.get("asset") != "UNKNOWN"
    ]


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(default=10, ge=1, le=50),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """최근 거래 (v_recent_trades)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_recent_trades(mode, limit)


@router.get("/symbol-pnl")
async def get_symbol_pnl(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """심볼별 손익 (v_symbol_pnl)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_symbol_pnl(mode)


@router.get("/fee-summary")
async def get_fee_summary(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """수수료 요약 (v_fee_summary)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_fee_summary(mode, start_date, end_date)


@router.get("/funding-history")
async def get_funding_history(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """펀딩 내역 (v_funding_history)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_funding_history(mode, limit, offset)


@router.get("/trial-balance")
async def get_trial_balance(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """시산표 조회
    
    잔액이 0인 계정은 제외.
    """
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    trial_balance = await store.get_trial_balance(mode)
    
    # 잔액이 0인 계정 필터링
    return [
        item for item in trial_balance
        if (item.get("balance") or 0) != 0
    ]


@router.get("/account-ledger/{account_id:path}")
async def get_account_ledger(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """계정별 원장 (v_account_ledger)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_account_ledger(account_id, mode, limit, offset)
