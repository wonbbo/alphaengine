"""
ConfigStore 테스트

config_store 테이블 CRUD 테스트
"""

import pytest
from decimal import Decimal
from typing import AsyncGenerator

from adapters.db.sqlite_adapter import SQLiteAdapter, init_schema
from core.storage.config_store import (
    ConfigStore,
    DEFAULT_CONFIGS,
    init_default_configs,
)


@pytest.fixture
async def db() -> AsyncGenerator[SQLiteAdapter, None]:
    """임시 인메모리 DB"""
    adapter = SQLiteAdapter(":memory:")
    await adapter.connect()
    await init_schema(adapter)
    yield adapter
    await adapter.close()


@pytest.fixture
async def config_store(db: SQLiteAdapter) -> ConfigStore:
    """ConfigStore 인스턴스"""
    return ConfigStore(db)


class TestConfigStoreGet:
    """get() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_returns_default_when_not_exists(
        self,
        config_store: ConfigStore,
    ) -> None:
        """존재하지 않는 키는 기본값 반환"""
        result = await config_store.get("risk")
        
        assert result == DEFAULT_CONFIGS["risk"]
    
    @pytest.mark.asyncio
    async def test_get_returns_stored_value(
        self,
        config_store: ConfigStore,
    ) -> None:
        """저장된 값 반환"""
        test_value = {"max_position_size": "500", "daily_loss_limit": "100"}
        await config_store.set("risk", test_value)
        
        result = await config_store.get("risk")
        
        assert result == test_value
    
    @pytest.mark.asyncio
    async def test_get_uses_cache(
        self,
        config_store: ConfigStore,
    ) -> None:
        """캐시 사용 확인"""
        test_value = {"test": "value"}
        await config_store.set("test_key", test_value)
        
        # 첫 번째 조회 (DB에서 읽음)
        result1 = await config_store.get("test_key")
        assert result1 == test_value
        
        # 캐시에 있어야 함
        assert "test_key" in config_store._cache
        
        # 두 번째 조회 (캐시에서 읽음)
        result2 = await config_store.get("test_key")
        assert result2 == test_value
    
    @pytest.mark.asyncio
    async def test_get_bypass_cache(
        self,
        config_store: ConfigStore,
        db: SQLiteAdapter,
    ) -> None:
        """캐시 무시하고 DB에서 직접 읽기"""
        test_value = {"test": "value"}
        await config_store.set("test_key", test_value)
        await config_store.get("test_key")  # 캐시에 저장
        
        # DB에서 직접 수정
        import json
        await db.execute(
            "UPDATE config_store SET value_json = ? WHERE config_key = ?",
            (json.dumps({"test": "modified"}), "test_key"),
        )
        await db.commit()
        
        # 캐시 무시하고 읽기
        result = await config_store.get("test_key", use_cache=False)
        
        assert result == {"test": "modified"}


class TestConfigStoreSet:
    """set() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_set_creates_new_config(
        self,
        config_store: ConfigStore,
    ) -> None:
        """새 설정 생성"""
        test_value = {"key1": "value1", "key2": 123}
        
        result = await config_store.set("new_config", test_value)
        
        assert result is True
        
        stored = await config_store.get("new_config", use_cache=False)
        assert stored == test_value
    
    @pytest.mark.asyncio
    async def test_set_updates_existing_config(
        self,
        config_store: ConfigStore,
    ) -> None:
        """기존 설정 업데이트"""
        await config_store.set("test", {"version": 1})
        await config_store.set("test", {"version": 2})
        
        result = await config_store.get("test", use_cache=False)
        
        assert result == {"version": 2}
    
    @pytest.mark.asyncio
    async def test_set_invalidates_cache(
        self,
        config_store: ConfigStore,
    ) -> None:
        """설정 후 캐시 무효화"""
        await config_store.set("test", {"v": 1})
        await config_store.get("test")  # 캐시에 저장
        assert "test" in config_store._cache
        
        await config_store.set("test", {"v": 2})
        
        # 캐시에서 제거되어야 함
        assert "test" not in config_store._cache


class TestConfigStoreGetValue:
    """get_value() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_value_returns_field(
        self,
        config_store: ConfigStore,
    ) -> None:
        """특정 필드 값 반환"""
        await config_store.set("config", {"field1": "value1", "field2": 100})
        
        result = await config_store.get_value("config", "field1")
        
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_get_value_returns_default(
        self,
        config_store: ConfigStore,
    ) -> None:
        """필드가 없으면 기본값 반환"""
        await config_store.set("config", {"field1": "value1"})
        
        result = await config_store.get_value("config", "nonexistent", default="default")
        
        assert result == "default"


class TestConfigStoreUpdateField:
    """update_field() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_update_field_modifies_single_field(
        self,
        config_store: ConfigStore,
    ) -> None:
        """단일 필드만 수정"""
        await config_store.set("config", {"field1": "old", "field2": "keep"})
        
        await config_store.update_field("config", "field1", "new")
        
        result = await config_store.get("config", use_cache=False)
        assert result == {"field1": "new", "field2": "keep"}


class TestConfigStoreGetAll:
    """get_all() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_all_returns_all_configs(
        self,
        config_store: ConfigStore,
    ) -> None:
        """모든 설정 반환"""
        await config_store.set("config1", {"a": 1})
        await config_store.set("config2", {"b": 2})
        
        result = await config_store.get_all()
        
        assert len(result) == 2
        assert result["config1"] == {"a": 1}
        assert result["config2"] == {"b": 2}


class TestConfigStoreEnsureDefaults:
    """ensure_defaults() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_ensure_defaults_creates_missing(
        self,
        config_store: ConfigStore,
    ) -> None:
        """없는 기본 설정 생성"""
        await config_store.ensure_defaults()
        
        # 기본 설정들이 생성되어야 함
        for key in DEFAULT_CONFIGS:
            result = await config_store.get(key, use_cache=False)
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_ensure_defaults_preserves_existing(
        self,
        config_store: ConfigStore,
    ) -> None:
        """기존 설정 유지"""
        custom_risk = {"max_position_size": "999", "custom_field": "value"}
        await config_store.set("risk", custom_risk)
        
        await config_store.ensure_defaults()
        
        # 기존 설정이 유지되어야 함
        result = await config_store.get("risk", use_cache=False)
        assert result == custom_risk


class TestConfigStoreRiskConfig:
    """get_risk_config() 메서드 테스트 (RiskGuard용)"""
    
    @pytest.mark.asyncio
    async def test_get_risk_config(
        self,
        config_store: ConfigStore,
    ) -> None:
        """리스크 설정 조회"""
        risk_config = {
            "max_position_size": "1000",
            "daily_loss_limit": "500",
            "max_open_orders": 10,
            "min_balance": "100",
        }
        await config_store.set("risk", risk_config)
        
        result = await config_store.get_risk_config()
        
        assert result == risk_config
        assert result["max_position_size"] == "1000"
        assert result["daily_loss_limit"] == "500"


class TestConfigStoreEngineMode:
    """get_engine_mode() 메서드 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_engine_mode_default(
        self,
        config_store: ConfigStore,
    ) -> None:
        """기본 엔진 모드 반환"""
        result = await config_store.get_engine_mode()
        
        assert result == "RUNNING"
    
    @pytest.mark.asyncio
    async def test_get_engine_mode_custom(
        self,
        config_store: ConfigStore,
    ) -> None:
        """설정된 엔진 모드 반환"""
        await config_store.set("engine", {"mode": "PAUSED", "poll_interval_sec": 30})
        
        result = await config_store.get_engine_mode()
        
        assert result == "PAUSED"


class TestInitDefaultConfigs:
    """init_default_configs() 함수 테스트"""
    
    @pytest.mark.asyncio
    async def test_init_default_configs(
        self,
        db: SQLiteAdapter,
    ) -> None:
        """기본 설정 초기화 함수"""
        await init_default_configs(db)
        
        config_store = ConfigStore(db)
        
        # 기본 설정들이 존재해야 함
        engine = await config_store.get("engine", use_cache=False)
        risk = await config_store.get("risk", use_cache=False)
        strategy = await config_store.get("strategy", use_cache=False)
        
        assert engine is not None
        assert risk is not None
        assert strategy is not None
