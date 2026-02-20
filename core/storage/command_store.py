"""
Command Store

Command CRUD 및 상태 관리.
Bot은 NEW 상태 Command를 클레임하여 처리.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.commands import Command
from core.types import CommandStatus, Scope, Actor

logger = logging.getLogger(__name__)


class CommandStore:
    """Command 저장소
    
    Command를 SQLite에 저장하고 상태 관리.
    Bot은 NEW 상태 Command를 우선순위 순으로 클레임하여 처리.
    
    Args:
        adapter: SQLite 어댑터
        
    사용 예시:
    ```python
    store = CommandStore(adapter)
    
    # Command 저장
    await store.insert(command)
    
    # NEW 상태 Command 클레임
    cmd = await store.claim_one()
    if cmd:
        # 처리...
        await store.update_status(cmd.command_id, "ACK")
    ```
    """
    
    def __init__(self, adapter: SQLiteAdapter):
        self.adapter = adapter
    
    async def insert(self, command: Command) -> bool:
        """Command 저장
        
        idempotency_key가 이미 존재하면 무시 (INSERT OR IGNORE).
        
        Args:
            command: 저장할 Command
            
        Returns:
            True: 새로 저장됨
            False: 이미 존재 (중복)
        """
        payload_json = json.dumps(command.payload, ensure_ascii=False)
        result_json = json.dumps(command.result) if command.result else None
        
        sql = """
            INSERT OR IGNORE INTO command_store (
                command_id, command_type, ts,
                correlation_id, causation_id,
                actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                idempotency_key, status, priority,
                payload_json, result_json, last_error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        params = (
            command.command_id,
            command.command_type,
            command.ts.isoformat(),
            command.correlation_id,
            command.causation_id,
            command.actor.kind,
            command.actor.id,
            command.scope.exchange,
            command.scope.venue,
            command.scope.account_id,
            command.scope.symbol,
            command.scope.mode,
            command.idempotency_key,
            command.status,
            command.priority,
            payload_json,
            result_json,
            command.last_error,
        )
        
        cursor = await self.adapter.execute(sql, params)
        await self.adapter.commit()
        
        inserted = cursor.rowcount > 0
        
        if inserted:
            logger.debug(
                f"Command inserted: {command.command_type}",
                extra={
                    "command_id": command.command_id,
                    "status": command.status,
                    "priority": command.priority,
                },
            )
        else:
            logger.debug(
                f"Command duplicate: {command.idempotency_key}",
            )
        
        return inserted
    
    async def get_by_id(self, command_id: str) -> Command | None:
        """ID로 Command 조회"""
        sql = """
            SELECT 
                command_id, command_type, ts,
                correlation_id, causation_id,
                actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                idempotency_key, status, priority,
                payload_json, result_json, last_error
            FROM command_store
            WHERE command_id = ?
        """
        
        row = await self.adapter.fetchone(sql, (command_id,))
        if row:
            return self._row_to_command(row)
        return None
    
    async def get_by_idempotency_key(self, key: str) -> Command | None:
        """idempotency_key로 Command 조회"""
        sql = """
            SELECT 
                command_id, command_type, ts,
                correlation_id, causation_id,
                actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                idempotency_key, status, priority,
                payload_json, result_json, last_error
            FROM command_store
            WHERE idempotency_key = ?
        """
        
        row = await self.adapter.fetchone(sql, (key,))
        if row:
            return self._row_to_command(row)
        return None
    
    async def find_by_status(
        self,
        status: str | CommandStatus,
        limit: int = 100,
    ) -> list[Command]:
        """상태별 Command 조회 (우선순위 높은 순)
        
        Args:
            status: 상태
            limit: 최대 조회 수
            
        Returns:
            Command 리스트 (우선순위 DESC, ts ASC 정렬)
        """
        status_str = status.value if isinstance(status, CommandStatus) else status
        
        sql = """
            SELECT 
                command_id, command_type, ts,
                correlation_id, causation_id,
                actor_kind, actor_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                idempotency_key, status, priority,
                payload_json, result_json, last_error
            FROM command_store
            WHERE status = ?
            ORDER BY priority DESC, ts ASC
            LIMIT ?
        """
        
        rows = await self.adapter.fetchall(sql, (status_str, limit))
        return [self._row_to_command(row) for row in rows]
    
    async def claim_one(self) -> Command | None:
        """NEW 상태 Command 하나 클레임
        
        우선순위 높은 순으로 가장 오래된 NEW 상태 Command를 
        SENT로 변경하고 반환.
        
        Returns:
            클레임된 Command 또는 None
        """
        # 1. NEW 상태 Command 조회
        sql_select = """
            SELECT command_id
            FROM command_store
            WHERE status = ?
            ORDER BY priority DESC, ts ASC
            LIMIT 1
        """
        
        row = await self.adapter.fetchone(sql_select, (CommandStatus.NEW.value,))
        if not row:
            return None
        
        command_id = row[0]
        
        # 2. SENT로 상태 변경 (클레임)
        now = datetime.now(timezone.utc).isoformat()
        sql_update = """
            UPDATE command_store
            SET status = ?, claimed_at = ?, updated_at = ?
            WHERE command_id = ? AND status = ?
        """
        
        cursor = await self.adapter.execute(
            sql_update,
            (CommandStatus.SENT.value, now, now, command_id, CommandStatus.NEW.value),
        )
        await self.adapter.commit()
        
        # 다른 프로세스가 먼저 클레임했을 수 있음
        if cursor.rowcount == 0:
            return await self.claim_one()  # 재시도
        
        # 3. 전체 Command 조회하여 반환
        return await self.get_by_id(command_id)
    
    async def update_status(
        self,
        command_id: str,
        status: str | CommandStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """상태 업데이트
        
        Args:
            command_id: Command ID
            status: 새로운 상태
            result: 실행 결과 (선택)
            error: 에러 메시지 (선택)
            
        Returns:
            업데이트 성공 여부
        """
        status_str = status.value if isinstance(status, CommandStatus) else status
        now = datetime.now(timezone.utc).isoformat()
        
        # ACK 또는 FAILED면 completed_at도 설정
        is_completed = status_str in (CommandStatus.ACK.value, CommandStatus.FAILED.value)
        
        if result:
            result_json = json.dumps(result, ensure_ascii=False)
        else:
            result_json = None
        
        if is_completed:
            sql = """
                UPDATE command_store
                SET status = ?, updated_at = ?, completed_at = ?,
                    result_json = COALESCE(?, result_json),
                    last_error = COALESCE(?, last_error)
                WHERE command_id = ?
            """
            params = (status_str, now, now, result_json, error, command_id)
        else:
            sql = """
                UPDATE command_store
                SET status = ?, updated_at = ?,
                    result_json = COALESCE(?, result_json),
                    last_error = COALESCE(?, last_error)
                WHERE command_id = ?
            """
            params = (status_str, now, result_json, error, command_id)
        
        cursor = await self.adapter.execute(sql, params)
        await self.adapter.commit()
        
        updated = cursor.rowcount > 0
        
        if updated:
            logger.debug(
                f"Command status updated",
                extra={
                    "command_id": command_id,
                    "status": status_str,
                },
            )
        
        return updated
    
    async def count_by_status(self, status: str | CommandStatus) -> int:
        """상태별 Command 수 조회"""
        status_str = status.value if isinstance(status, CommandStatus) else status
        
        sql = """
            SELECT COUNT(*) as cnt
            FROM command_store
            WHERE status = ?
        """
        
        row = await self.adapter.fetchone(sql, (status_str,))
        return row[0] if row else 0
    
    async def get_pending_count(self) -> int:
        """처리 대기 중인 Command 수 (NEW + SENT)"""
        sql = """
            SELECT COUNT(*) as cnt
            FROM command_store
            WHERE status IN (?, ?)
        """
        
        row = await self.adapter.fetchone(
            sql,
            (CommandStatus.NEW.value, CommandStatus.SENT.value),
        )
        return row[0] if row else 0
    
    async def get_recent_commands(
        self,
        limit: int = 50,
        include_completed: bool = True,
    ) -> list[Command]:
        """최근 Command 조회 (Web UI용)
        
        Args:
            limit: 최대 조회 수
            include_completed: 완료된 것도 포함할지
            
        Returns:
            최근 Command 리스트 (ts DESC 정렬)
        """
        if include_completed:
            sql = """
                SELECT 
                    command_id, command_type, ts,
                    correlation_id, causation_id,
                    actor_kind, actor_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    idempotency_key, status, priority,
                    payload_json, result_json, last_error
                FROM command_store
                ORDER BY ts DESC
                LIMIT ?
            """
            rows = await self.adapter.fetchall(sql, (limit,))
        else:
            sql = """
                SELECT 
                    command_id, command_type, ts,
                    correlation_id, causation_id,
                    actor_kind, actor_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    idempotency_key, status, priority,
                    payload_json, result_json, last_error
                FROM command_store
                WHERE status IN (?, ?)
                ORDER BY ts DESC
                LIMIT ?
            """
            rows = await self.adapter.fetchall(
                sql,
                (CommandStatus.NEW.value, CommandStatus.SENT.value, limit),
            )
        
        return [self._row_to_command(row) for row in rows]
    
    async def delete_old_completed(self, days: int = 30) -> int:
        """오래된 완료된 Command 삭제 (정리용)
        
        Args:
            days: 보관 기간 (일)
            
        Returns:
            삭제된 수
        """
        sql = """
            DELETE FROM command_store
            WHERE status IN (?, ?)
            AND completed_at < datetime('now', ?)
        """
        
        cursor = await self.adapter.execute(
            sql,
            (
                CommandStatus.ACK.value,
                CommandStatus.FAILED.value,
                f"-{days} days",
            ),
        )
        await self.adapter.commit()
        
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"Deleted {deleted} old commands")
        
        return deleted
    
    def _row_to_command(self, row: tuple[Any, ...]) -> Command:
        """DB 행 → Command 객체 변환"""
        (
            command_id, command_type, ts,
            correlation_id, causation_id,
            actor_kind, actor_id,
            scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
            idempotency_key, status, priority,
            payload_json, result_json, last_error,
        ) = row
        
        ts_dt = datetime.fromisoformat(ts)
        
        actor = Actor(kind=actor_kind, id=actor_id)
        
        scope = Scope(
            exchange=scope_exchange,
            venue=scope_venue,
            account_id=scope_account_id,
            symbol=scope_symbol,
            mode=scope_mode,
        )
        
        payload = json.loads(payload_json) if payload_json else {}
        result = json.loads(result_json) if result_json else None
        
        return Command(
            command_id=command_id,
            command_type=command_type,
            ts=ts_dt,
            correlation_id=correlation_id,
            causation_id=causation_id,
            actor=actor,
            scope=scope,
            idempotency_key=idempotency_key,
            status=status,
            priority=priority,
            payload=payload,
            result=result,
            last_error=last_error,
        )
