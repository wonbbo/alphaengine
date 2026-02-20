"""
의존성 주입

FastAPI의 Depends를 사용한 의존성 관리.
"""

from typing import AsyncGenerator

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings, get_settings


def get_app_settings() -> Settings:
    """애플리케이션 설정 반환"""
    return get_settings()


async def get_db() -> AsyncGenerator[SQLiteAdapter, None]:
    """DB 세션 반환 (읽기 전용)
    
    Web은 대부분 읽기 작업만 수행.
    Command 삽입, Config 수정은 readonly=False로 별도 처리.
    """
    settings = get_settings()
    async with SQLiteAdapter(settings.db_path, readonly=True) as db:
        yield db


async def get_db_write() -> AsyncGenerator[SQLiteAdapter, None]:
    """DB 세션 반환 (쓰기 가능)
    
    Command 삽입, Config 수정 시 사용.
    """
    settings = get_settings()
    async with SQLiteAdapter(settings.db_path, readonly=False) as db:
        yield db
