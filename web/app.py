"""
FastAPI 애플리케이션

라우터 등록 및 앱 설정.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from web.routes import health


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

# 라우터 등록
app.include_router(health.router)
