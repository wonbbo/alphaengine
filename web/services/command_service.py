"""
Command 서비스

CommandStore CRUD 및 Command 발행
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.types import Actor, Scope, CommandStatus

logger = logging.getLogger(__name__)


class CommandService:
    """Command 서비스
    
    command_store 테이블 CRUD.
    Web에서 Command를 발행하면 Bot이 처리.
    
    Args:
        db: SQLite 어댑터 (쓰기 가능)
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def create_command(
        self,
        command_type: str,
        scope: Scope,
        payload: dict[str, Any],
        priority: int = 50,
        actor_id: str = "web:admin",
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Command 생성 (Web → Bot 큐잉)
        
        Args:
            command_type: 명령 타입
            scope: 거래 범위
            payload: 명령 페이로드
            priority: 우선순위 (기본 50)
            actor_id: 행위자 ID
            idempotency_key: 멱등성 키
            correlation_id: 상관 ID
            
        Returns:
            생성된 Command 정보
        """
        command_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        # 멱등성 키가 없으면 command_id 사용
        if not idempotency_key:
            idempotency_key = command_id
        
        if not correlation_id:
            correlation_id = str(uuid4())
        
        payload_json = json.dumps(payload, ensure_ascii=False)
        
        sql = """
            INSERT INTO command_store (
                command_id, command_type, ts,
                correlation_id, causation_id,
                actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                idempotency_key, status, priority,
                payload_json, result_json, last_error,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        await self.db.execute(sql, (
            command_id,
            command_type,
            now,
            correlation_id,
            None,  # causation_id
            "USER",  # actor_kind
            actor_id,
            scope.exchange,
            scope.venue,
            scope.account_id,
            scope.symbol,
            scope.mode,
            idempotency_key,
            CommandStatus.NEW.value,
            priority,
            payload_json,
            None,  # result_json
            None,  # last_error
            now,
            now,
        ))
        await self.db.commit()
        
        logger.info(
            f"Command created: {command_type}",
            extra={"command_id": command_id, "priority": priority},
        )
        
        return {
            "command_id": command_id,
            "status": CommandStatus.NEW.value,
            "message": "Command accepted",
        }
    
    async def get_command(self, command_id: str) -> dict[str, Any] | None:
        """Command 조회"""
        sql = """
            SELECT 
                command_id, command_type, ts,
                correlation_id, actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                status, priority, payload_json, result_json, last_error
            FROM command_store
            WHERE command_id = ?
        """
        
        row = await self.db.fetchone(sql, (command_id,))
        
        if row:
            return self._row_to_command(row)
        
        return None
    
    async def get_commands(
        self,
        mode: str,
        status: str | None = None,
        limit: int = 50,
        include_completed: bool = True,
    ) -> list[dict[str, Any]]:
        """Command 목록 조회
        
        Args:
            mode: 거래 모드
            status: 상태 필터 (None이면 전체)
            limit: 조회 제한
            include_completed: 완료된 것도 포함
            
        Returns:
            Command 목록
        """
        if status:
            sql = """
                SELECT 
                    command_id, command_type, ts,
                    correlation_id, actor_kind, actor_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    status, priority, payload_json, result_json, last_error
                FROM command_store
                WHERE scope_mode = ? AND status = ?
                ORDER BY ts DESC
                LIMIT ?
            """
            rows = await self.db.fetchall(sql, (mode, status, limit))
        elif not include_completed:
            sql = """
                SELECT 
                    command_id, command_type, ts,
                    correlation_id, actor_kind, actor_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    status, priority, payload_json, result_json, last_error
                FROM command_store
                WHERE scope_mode = ? AND status IN ('NEW', 'SENT')
                ORDER BY ts DESC
                LIMIT ?
            """
            rows = await self.db.fetchall(sql, (mode, limit))
        else:
            sql = """
                SELECT 
                    command_id, command_type, ts,
                    correlation_id, actor_kind, actor_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    status, priority, payload_json, result_json, last_error
                FROM command_store
                WHERE scope_mode = ?
                ORDER BY ts DESC
                LIMIT ?
            """
            rows = await self.db.fetchall(sql, (mode, limit))
        
        return [self._row_to_command(row) for row in rows]
    
    async def get_command_count(self, mode: str, status: str | None = None) -> int:
        """Command 수 조회"""
        if status:
            sql = """
                SELECT COUNT(*) as cmd_cnt
                FROM command_store
                WHERE scope_mode = ? AND status = ?
            """
            row = await self.db.fetchone(sql, (mode, status))
        else:
            sql = """
                SELECT COUNT(*) as cmd_cnt
                FROM command_store
                WHERE scope_mode = ?
            """
            row = await self.db.fetchone(sql, (mode,))
        
        return row[0] if row else 0
    
    def _row_to_command(self, row: tuple[Any, ...]) -> dict[str, Any]:
        """DB 행 → Command dict 변환"""
        payload = json.loads(row[13]) if row[13] else {}
        result = json.loads(row[14]) if row[14] else None
        
        return {
            "command_id": row[0],
            "command_type": row[1],
            "ts": row[2],
            "correlation_id": row[3],
            "actor": {
                "kind": row[4],
                "id": row[5],
            },
            "scope": {
                "exchange": row[6],
                "venue": row[7],
                "account_id": row[8],
                "symbol": row[9],
                "mode": row[10],
            },
            "status": row[11],
            "priority": row[12],
            "payload": payload,
            "result": result,
            "last_error": row[15],
        }
