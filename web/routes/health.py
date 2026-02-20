"""
헬스 체크 엔드포인트

GET /health - 서버 상태 확인
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    
    status: str
    mode: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """서버 상태 확인
    
    Returns:
        HealthResponse: status, mode, version 정보
    """
    from core.config.loader import get_settings
    
    settings = get_settings()
    
    return HealthResponse(
        status="ok",
        mode=settings.mode.value,
        version="2.0.0",
    )
