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
from core.logging import setup_logging

# 로깅 설정 (콘솔 + 파일)
setup_logging("web")

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
    import logging
    import yaml
    
    from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
    from core.constants import Paths
    from web.dependencies import set_transfer_manager, get_transfer_manager
    
    logger = logging.getLogger(__name__)
    settings = get_settings()
    
    # 시작 시 - DB 스키마 자동 초기화
    async with SQLiteAdapter(settings.db_path) as db:
        await init_schema(db)
    
    # TransferManager 초기화 (Bot과 별도 프로세스일 때를 위해)
    transfer_manager = None
    upbit_client = None
    binance_client = None
    
    db_for_transfer = None
    
    if get_transfer_manager() is None:
        transfer_manager, upbit_client, binance_client, db_for_transfer = await _init_transfer_manager_for_web(
            settings, logger
        )
        if transfer_manager:
            set_transfer_manager(transfer_manager)
            logger.info("Web: TransferManager 초기화 완료")
    
    yield
    
    # 종료 시 - 리소스 정리
    if upbit_client:
        try:
            await upbit_client.close()
        except Exception:
            pass
    if binance_client:
        try:
            await binance_client.close()
        except Exception:
            pass
    if db_for_transfer:
        try:
            await db_for_transfer.close()
            logger.info("Web: DB 연결 종료 완료")
        except Exception:
            pass


async def _init_transfer_manager_for_web(settings, logger):
    """Web용 TransferManager 초기화
    
    Bot과 별도 프로세스로 실행될 때 Web에서 직접 초기화.
    
    Returns:
        (TransferManager | None, UpbitRestClient | None, BinanceRestClient | None, SQLiteAdapter | None)
    """
    import yaml
    
    from adapters.db.sqlite_adapter import SQLiteAdapter
    from adapters.binance.rest_client import BinanceRestClient
    from adapters.upbit.rest_client import UpbitRestClient
    from bot.transfer.manager import TransferManager
    from core.storage.event_store import EventStore
    from core.types import Scope
    from core.constants import Paths, BinanceEndpoints, Defaults
    
    # secrets.yaml에서 설정 로드
    config = {
        "upbit_api_key": "",
        "upbit_api_secret": "",
        "upbit_trx_address": "",
        "binance_trx_address": "",
        "binance_api_key": "",
        "binance_api_secret": "",
    }
    
    try:
        if not Paths.SECRETS_FILE.exists():
            logger.info("Web: secrets.yaml 없음, 입출금 기능 비활성화")
            return None, None, None, None
        
        with open(Paths.SECRETS_FILE, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        # Upbit 설정
        upbit_config = data.get("upbit", {})
        config["upbit_api_key"] = upbit_config.get("api_key", "")
        config["upbit_api_secret"] = upbit_config.get("api_secret", "")
        config["upbit_trx_address"] = upbit_config.get("trx_deposit_address", "")
        
        # Binance 설정
        binance_config = data.get("binance", {})
        config["binance_trx_address"] = binance_config.get("trx_deposit_address", "")
        
        # Binance API 키 (mode에 따라)
        mode = settings.mode.value
        mode_config = data.get(mode, {})
        config["binance_api_key"] = mode_config.get("api_key", "")
        config["binance_api_secret"] = mode_config.get("api_secret", "")
        
    except Exception as e:
        logger.warning(f"Web: 입출금 설정 로드 실패: {e}")
        return None, None, None, None
    
    # 필수 설정 확인
    if not config["upbit_api_key"] or not config["upbit_api_secret"]:
        logger.info("Web: Upbit API 설정 없음, 입출금 기능 비활성화")
        return None, None, None, None
    
    if not config["upbit_trx_address"]:
        logger.info("Web: Upbit TRX 주소 없음, 입출금 기능 비활성화")
        return None, None, None, None
    
    if not config["binance_trx_address"]:
        logger.info("Web: Binance TRX 주소 없음, 입출금 기능 비활성화")
        return None, None, None, None
    
    if not config["binance_api_key"] or not config["binance_api_secret"]:
        logger.info("Web: Binance API 설정 없음, 입출금 기능 비활성화")
        return None, None, None, None
    
    try:
        # Binance REST 클라이언트 생성
        if settings.mode.value == "testnet":
            base_url = BinanceEndpoints.TEST_REST_URL
        else:
            base_url = BinanceEndpoints.PROD_REST_URL
        
        binance_client = BinanceRestClient(
            base_url=base_url,
            api_key=config["binance_api_key"],
            api_secret=config["binance_api_secret"],
        )
        
        # Upbit 클라이언트 생성
        upbit_client = UpbitRestClient(
            api_key=config["upbit_api_key"],
            api_secret=config["upbit_api_secret"],
        )
        
        # DB 및 EventStore 생성
        db = SQLiteAdapter(settings.db_path)
        await db.connect()
        event_store = EventStore(db)
        
        # Scope 생성
        scope = Scope(
            exchange=Defaults.EXCHANGE,
            venue=Defaults.VENUE,
            account_id=Defaults.ACCOUNT_ID,
            symbol=None,
            mode=settings.mode.value.upper(),
        )
        
        # TransferManager 생성
        transfer_manager = TransferManager(
            db=db,
            upbit=upbit_client,
            binance=binance_client,
            event_store=event_store,
            scope=scope,
            binance_trx_address=config["binance_trx_address"],
            upbit_trx_address=config["upbit_trx_address"],
        )
        
        return transfer_manager, upbit_client, binance_client, db
        
    except Exception as e:
        logger.warning(f"Web: TransferManager 초기화 실패: {e}")
        return None, None, None, None


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
