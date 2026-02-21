"""
의존성 주입

FastAPI의 Depends를 사용한 의존성 관리.
"""

from typing import Any, AsyncGenerator

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


# =========================================================================
# TransferManager (Bot과 공유)
# =========================================================================

# Bot 프로세스에서 설정되는 전역 TransferManager 인스턴스
# Web과 Bot이 같은 프로세스에서 실행될 때 사용
_transfer_manager: Any = None


def set_transfer_manager(manager: Any) -> None:
    """TransferManager 설정
    
    Bot 부트스트랩 시 호출하여 전역 인스턴스 설정.
    
    Args:
        manager: TransferManager 인스턴스
    """
    global _transfer_manager
    _transfer_manager = manager


def get_transfer_manager() -> Any | None:
    """TransferManager 반환
    
    Returns:
        TransferManager 인스턴스 또는 None (설정되지 않은 경우)
    """
    return _transfer_manager


def is_transfer_available() -> bool:
    """입출금 기능 사용 가능 여부
    
    Returns:
        True: TransferManager가 초기화된 경우
        False: 초기화되지 않은 경우 (Testnet, Upbit 미설정 등)
    """
    return _transfer_manager is not None
