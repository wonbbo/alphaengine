"""
스토리지 모듈

Event Store, Command Store, Config Store 등 데이터 저장소 인터페이스 제공
"""

from core.storage.event_store import EventStore
from core.storage.config_store import ConfigStore, init_default_configs

__all__ = [
    "EventStore",
    "ConfigStore",
    "init_default_configs",
]
