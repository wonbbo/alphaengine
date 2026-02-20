"""
Event 서비스

EventStore에서 이벤트 조회
"""

import json
import logging
from datetime import datetime
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class EventService:
    """Event 서비스
    
    event_store 테이블에서 이벤트 조회.
    
    Args:
        db: SQLite 어댑터 (읽기 전용)
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_events(
        self,
        mode: str,
        event_type: str | None = None,
        entity_kind: str | None = None,
        entity_id: str | None = None,
        symbol: str | None = None,
        from_ts: datetime | None = None,
        to_ts: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """이벤트 목록 조회 (필터 지원)
        
        Args:
            mode: 거래 모드
            event_type: 이벤트 타입 필터
            entity_kind: 엔티티 종류 필터
            entity_id: 엔티티 ID 필터
            symbol: 심볼 필터
            from_ts: 시작 시간
            to_ts: 종료 시간
            limit: 조회 제한
            offset: 조회 시작 위치
            
        Returns:
            이벤트 목록
        """
        # 동적 쿼리 생성
        conditions = ["scope_mode = ?"]
        params: list[Any] = [mode]
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        
        if entity_kind:
            conditions.append("entity_kind = ?")
            params.append(entity_kind)
        
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        
        if symbol:
            conditions.append("scope_symbol = ?")
            params.append(symbol)
        
        if from_ts:
            conditions.append("ts >= ?")
            params.append(from_ts.isoformat())
        
        if to_ts:
            conditions.append("ts <= ?")
            params.append(to_ts.isoformat())
        
        where_clause = " AND ".join(conditions)
        
        sql = f"""
            SELECT 
                event_id, event_type, ts, source,
                entity_kind, entity_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                payload_json
            FROM event_store
            WHERE {where_clause}
            ORDER BY ts DESC
            LIMIT ? OFFSET ?
        """
        
        params.extend([limit, offset])
        
        try:
            rows = await self.db.fetchall(sql, tuple(params))
            
            events = []
            for row in rows:
                payload = json.loads(row[11]) if isinstance(row[11], str) else row[11]
                events.append({
                    "event_id": row[0],
                    "event_type": row[1],
                    "ts": row[2],
                    "source": row[3],
                    "entity_kind": row[4],
                    "entity_id": row[5],
                    "scope": {
                        "exchange": row[6],
                        "venue": row[7],
                        "account_id": row[8],
                        "symbol": row[9],
                        "mode": row[10],
                    },
                    "payload": payload,
                })
            
            return events
        except Exception as e:
            logger.error(f"Event query error: {e}")
            return []
    
    async def get_event_count(
        self,
        mode: str,
        event_type: str | None = None,
        entity_kind: str | None = None,
        symbol: str | None = None,
    ) -> int:
        """이벤트 수 조회"""
        conditions = ["scope_mode = ?"]
        params: list[Any] = [mode]
        
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        
        if entity_kind:
            conditions.append("entity_kind = ?")
            params.append(entity_kind)
        
        if symbol:
            conditions.append("scope_symbol = ?")
            params.append(symbol)
        
        where_clause = " AND ".join(conditions)
        
        sql = f"""
            SELECT COUNT(*) as event_cnt
            FROM event_store
            WHERE {where_clause}
        """
        
        try:
            row = await self.db.fetchone(sql, tuple(params))
            return row[0] if row else 0
        except Exception:
            return 0
    
    async def get_event_types(self, mode: str) -> list[str]:
        """이벤트 타입 목록 조회"""
        sql = """
            SELECT DISTINCT event_type
            FROM event_store
            WHERE scope_mode = ?
            ORDER BY event_type
        """
        
        try:
            rows = await self.db.fetchall(sql, (mode,))
            return [row[0] for row in rows]
        except Exception:
            return []
