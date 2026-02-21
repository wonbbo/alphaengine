"""
FastAPI 애플리케이션

라우터 등록 및 앱 설정.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config.loader import get_settings
from web.routes import (
    health,
    dashboard,
    events,
    commands,
    config,
    transfer,
    pnl,
    ledger,
    positions,
    transactions,
    assets,
    trading_edge,
)

# 경로 설정
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작 시
    yield
    # 종료 시


app = FastAPI(
    title="AlphaEngine API",
    description="Binance Futures 자동 매매 시스템 API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 설정 (개발용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 및 템플릿 설정
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR)) if TEMPLATES_DIR.exists() else None

# =========================================================================
# API 라우터 등록
# =========================================================================

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(events.router)
app.include_router(commands.router)
app.include_router(config.router)
app.include_router(transfer.router)
app.include_router(pnl.router)
app.include_router(ledger.router)
app.include_router(positions.router)
app.include_router(transactions.router)
app.include_router(assets.router)
app.include_router(trading_edge.router)


# =========================================================================
# 페이지 라우트 (HTML)
# =========================================================================

def _get_mode() -> str:
    """현재 모드 반환"""
    try:
        settings = get_settings()
        return settings.mode.value.upper()
    except Exception:
        return "TESTNET"


@app.get("/", include_in_schema=False)
async def home(request: Request):
    """홈페이지 (대시보드로 리다이렉트)"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request):
    """대시보드 페이지"""
    if templates is None:
        return {"error": "Templates not configured"}
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "active_page": "dashboard", "mode": _get_mode()},
    )


@app.get("/transfer", include_in_schema=False)
async def transfer_page(request: Request):
    """입출금 페이지"""
    if templates is None:
        return {"error": "Templates not configured"}
    return templates.TemplateResponse(
        "transfer.html",
        {"request": request, "active_page": "transfer", "mode": _get_mode()},
    )


@app.get("/events", include_in_schema=False)
async def events_page(request: Request):
    """이벤트 페이지"""
    if templates is None:
        return {"error": "Templates not configured"}
    return templates.TemplateResponse(
        "events.html",
        {"request": request, "active_page": "events", "mode": _get_mode()},
    )


@app.get("/config", include_in_schema=False)
async def config_page(request: Request):
    """설정 페이지"""
    if templates is None:
        return {"error": "Templates not configured"}
    return templates.TemplateResponse(
        "config.html",
        {"request": request, "active_page": "config", "mode": _get_mode()},
    )


@app.get("/commands", include_in_schema=False)
async def commands_page(request: Request):
    """Commands 페이지"""
    if templates is None:
        return {"error": "Templates not configured"}
    return templates.TemplateResponse(
        "commands.html",
        {"request": request, "active_page": "commands", "mode": _get_mode()},
    )
