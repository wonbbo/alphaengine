"""
스토리지 모듈

Event Store, Command Store 등 데이터 저장소 인터페이스 제공
"""

from core.storage.event_store import EventStore

__all__ = ["EventStore"]
