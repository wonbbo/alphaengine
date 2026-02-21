"""
Config 서비스

ConfigStore CRUD
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)

# 읽기 전용 설정 키 (시스템에서만 변경 가능, Web API에서 수정/삭제 불가)
READONLY_CONFIG_KEYS = frozenset({
    "bot_status",  # Bot 프로세스 상태 (heartbeat 등)
})


class ConfigService:
    """Config 서비스
    
    config_store 테이블 CRUD.
    런타임 설정 관리.
    
    Args:
        db: SQLite 어댑터 (쓰기 가능)
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_config(self, key: str) -> dict[str, Any] | None:
        """설정 조회
        
        Args:
            key: 설정 키
            
        Returns:
            설정 정보 또는 None
        """
        sql = """
            SELECT config_key, value_json, version, updated_at, updated_by
            FROM config_store
            WHERE config_key = ?
        """
        
        row = await self.db.fetchone(sql, (key,))
        
        if row:
            value = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            return {
                "key": row[0],
                "value": value,
                "version": row[2],
                "updated_at": row[3],
                "updated_by": row[4],
            }
        
        return None
    
    async def update_config(
        self,
        key: str,
        value: dict[str, Any],
        updated_by: str = "web:admin",
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        """설정 업데이트 (UPSERT)
        
        Args:
            key: 설정 키
            value: 새로운 설정 값
            updated_by: 업데이트 주체
            expected_version: 예상 버전 (낙관적 락)
            
        Returns:
            업데이트된 설정 정보
            
        Raises:
            ValueError: 버전 충돌 시
            PermissionError: 읽기 전용 설정 수정 시도 시
        """
        # 읽기 전용 설정 체크
        if key in READONLY_CONFIG_KEYS:
            raise PermissionError(f"'{key}'는 읽기 전용 설정입니다. 시스템에서만 변경 가능합니다.")
        
        now = datetime.now(timezone.utc).isoformat()
        value_json = json.dumps(value, ensure_ascii=False)
        
        # 버전 체크 (낙관적 락)
        if expected_version is not None:
            existing = await self.get_config(key)
            if existing and existing["version"] != expected_version:
                raise ValueError(
                    f"Version conflict: expected {expected_version}, got {existing['version']}"
                )
        
        # UPSERT 쿼리
        sql = """
            INSERT INTO config_store (config_key, value_json, version, updated_by, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?, ?)
            ON CONFLICT(config_key) DO UPDATE SET
                value_json = excluded.value_json,
                version = config_store.version + 1,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
        """
        
        await self.db.execute(sql, (key, value_json, updated_by, now, now))
        await self.db.commit()
        
        logger.info(
            f"Config updated: {key}",
            extra={"updated_by": updated_by},
        )
        
        # 업데이트된 설정 반환
        return await self.get_config(key)
    
    async def get_all_configs(self) -> list[dict[str, Any]]:
        """모든 설정 조회"""
        sql = """
            SELECT config_key, value_json, version, updated_at, updated_by
            FROM config_store
            ORDER BY config_key
        """
        
        rows = await self.db.fetchall(sql)
        
        configs = []
        for row in rows:
            value = json.loads(row[1]) if isinstance(row[1], str) else row[1]
            configs.append({
                "key": row[0],
                "value": value,
                "version": row[2],
                "updated_at": row[3],
                "updated_by": row[4],
            })
        
        return configs
    
    async def delete_config(self, key: str) -> bool:
        """설정 삭제
        
        Args:
            key: 설정 키
            
        Returns:
            삭제 성공 여부
            
        Raises:
            PermissionError: 읽기 전용 설정 삭제 시도 시
        """
        # 읽기 전용 설정 체크
        if key in READONLY_CONFIG_KEYS:
            raise PermissionError(f"'{key}'는 읽기 전용 설정입니다. 삭제할 수 없습니다.")
        
        sql = "DELETE FROM config_store WHERE config_key = ?"
        
        cursor = await self.db.execute(sql, (key,))
        await self.db.commit()
        
        deleted = cursor.rowcount > 0
        
        if deleted:
            logger.info(f"Config deleted: {key}")
        
        return deleted
