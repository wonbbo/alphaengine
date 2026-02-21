"""
EventStore - 이벤트 저장소

모든 상태 변경은 Event로 기록됨 (Event Sourcing 원칙).
dedup_key로 중복 이벤트를 방지하고, append-only 방식으로 저장.
"""

import json
import logging
from datetime import datetime
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event
from core.types import Scope

logger = logging.getLogger(__name__)


class EventStore:
    """이벤트 저장소
    
    Event Sourcing 패턴의 핵심 컴포넌트.
    모든 이벤트를 append-only로 저장하고, dedup_key로 중복 방지.
    
    Args:
        db: SQLiteAdapter 인스턴스
    
    사용 예시:
    ```python
    async with SQLiteAdapter(db_path) as db:
        event_store = EventStore(db)
        
        # 이벤트 저장
        saved = await event_store.append(event)
        
        # 이벤트 조회
        events = await event_store.get_since(0)
    ```
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def append(self, event: Event) -> bool:
        """이벤트 저장 (dedup_key로 중복 제거)
        
        Args:
            event: 저장할 Event 인스턴스
            
        Returns:
            True: 저장 성공 (신규 이벤트)
            False: 중복으로 무시됨
        """
        # payload를 JSON 문자열로 직렬화
        payload_json = json.dumps(event.payload, ensure_ascii=False)
        
        # ts를 ISO 8601 문자열로 변환
        ts_str = event.ts.isoformat()
        
        try:
            # INSERT OR IGNORE로 중복 방지 (dedup_key UNIQUE 제약)
            await self.db.execute(
                """
                INSERT OR IGNORE INTO event_store (
                    event_id, event_type, ts,
                    correlation_id, causation_id, command_id, source,
                    entity_kind, entity_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    dedup_key, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    ts_str,
                    event.correlation_id,
                    event.causation_id,
                    event.command_id,
                    event.source,
                    event.entity_kind,
                    event.entity_id,
                    event.scope.exchange,
                    event.scope.venue,
                    event.scope.account_id,
                    event.scope.symbol,
                    event.scope.mode,
                    event.dedup_key,
                    payload_json,
                ),
            )
            await self.db.commit()
            
            # rowcount로 실제 삽입 여부 확인
            # INSERT OR IGNORE는 중복 시 rowcount=0
            cursor = await self.db.execute(
                "SELECT seq FROM event_store WHERE event_id = ?",
                (event.event_id,),
            )
            row = await cursor.fetchone()
            
            if row:
                logger.debug(
                    "이벤트 저장 완료",
                    extra={"event_id": event.event_id, "event_type": event.event_type},
                )
                return True
            else:
                logger.debug(
                    "이벤트 중복 (무시됨)",
                    extra={"dedup_key": event.dedup_key},
                )
                return False
                
        except Exception as e:
            logger.error(
                "이벤트 저장 실패",
                extra={"event_id": event.event_id, "error": str(e)},
            )
            raise
    
    async def get_by_id(self, event_id: str) -> Event | None:
        """ID로 이벤트 조회
        
        Args:
            event_id: 이벤트 ID (UUID)
            
        Returns:
            Event 인스턴스 또는 None
        """
        row = await self.db.fetchone(
            """
            SELECT 
                seq, event_id, event_type, ts,
                correlation_id, causation_id, command_id, source,
                entity_kind, entity_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                dedup_key, payload_json
            FROM event_store
            WHERE event_id = ?
            """,
            (event_id,),
        )
        
        if row is None:
            return None
        
        return self._row_to_event(row)
    
    async def get_since(self, last_seq: int, limit: int = 1000) -> list[Event]:
        """특정 seq 이후 이벤트 조회
        
        Args:
            last_seq: 마지막으로 처리한 seq (이 값보다 큰 seq의 이벤트 조회)
            limit: 최대 조회 개수 (기본 1000)
            
        Returns:
            Event 리스트 (seq 순서로 정렬)
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                seq, event_id, event_type, ts,
                correlation_id, causation_id, command_id, source,
                entity_kind, entity_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                dedup_key, payload_json
            FROM event_store
            WHERE seq > ?
            ORDER BY seq ASC
            LIMIT ?
            """,
            (last_seq, limit),
        )
        
        return [self._row_to_event(row) for row in rows]
    
    async def get_by_entity(
        self,
        entity_kind: str,
        entity_id: str,
        limit: int = 100,
    ) -> list[Event]:
        """엔티티별 이벤트 조회
        
        Args:
            entity_kind: 엔티티 종류 (ORDER, TRADE, POSITION 등)
            entity_id: 엔티티 ID
            limit: 최대 조회 개수 (기본 100)
            
        Returns:
            Event 리스트 (ts 순서로 정렬)
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                seq, event_id, event_type, ts,
                correlation_id, causation_id, command_id, source,
                entity_kind, entity_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                dedup_key, payload_json
            FROM event_store
            WHERE entity_kind = ? AND entity_id = ?
            ORDER BY ts ASC
            LIMIT ?
            """,
            (entity_kind, entity_id, limit),
        )
        
        return [self._row_to_event(row) for row in rows]
    
    async def get_by_type(
        self,
        event_type: str,
        limit: int = 100,
    ) -> list[Event]:
        """이벤트 타입별 조회
        
        Args:
            event_type: 이벤트 타입 (BalanceChanged, TradeExecuted 등)
            limit: 최대 조회 개수 (기본 100)
            
        Returns:
            Event 리스트 (ts 순서로 정렬)
        """
        rows = await self.db.fetchall(
            """
            SELECT 
                seq, event_id, event_type, ts,
                correlation_id, causation_id, command_id, source,
                entity_kind, entity_id,
                scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                dedup_key, payload_json
            FROM event_store
            WHERE event_type = ?
            ORDER BY ts DESC
            LIMIT ?
            """,
            (event_type, limit),
        )
        
        return [self._row_to_event(row) for row in rows]
    
    async def get_events_by_type(
        self,
        event_type: str,
        after_ts: int | None = None,
        limit: int = 1000,
    ) -> list[Event]:
        """이벤트 타입별 조회 (시간 필터 지원)
        
        Args:
            event_type: 이벤트 타입 (BalanceChanged, TradeExecuted 등)
            after_ts: 이 타임스탬프(밀리초) 이후 이벤트만 조회 (None이면 전체)
            limit: 최대 조회 개수 (기본 1000)
            
        Returns:
            Event 리스트 (ts 순서로 오름차순 정렬)
        """
        if after_ts is not None:
            # 밀리초 타임스탬프를 ISO 문자열로 변환
            from datetime import datetime, timezone
            after_dt = datetime.fromtimestamp(after_ts / 1000, tz=timezone.utc)
            after_ts_str = after_dt.isoformat()
            
            rows = await self.db.fetchall(
                """
                SELECT 
                    seq, event_id, event_type, ts,
                    correlation_id, causation_id, command_id, source,
                    entity_kind, entity_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    dedup_key, payload_json
                FROM event_store
                WHERE event_type = ? AND ts >= ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (event_type, after_ts_str, limit),
            )
        else:
            rows = await self.db.fetchall(
                """
                SELECT 
                    seq, event_id, event_type, ts,
                    correlation_id, causation_id, command_id, source,
                    entity_kind, entity_id,
                    scope_exchange, scope_venue, scope_account_id, scope_symbol, scope_mode,
                    dedup_key, payload_json
                FROM event_store
                WHERE event_type = ?
                ORDER BY ts ASC
                LIMIT ?
                """,
                (event_type, limit),
            )
        
        return [self._row_to_event(row) for row in rows]
    
    async def count_all(self) -> int:
        """전체 이벤트 개수 조회"""
        row = await self.db.fetchone(
            "SELECT COUNT(*) as event_count FROM event_store"
        )
        return row[0] if row else 0
    
    async def get_last_seq(self) -> int:
        """마지막 seq 조회"""
        row = await self.db.fetchone(
            "SELECT MAX(seq) as max_seq FROM event_store"
        )
        return row[0] if row and row[0] else 0
    
    def _row_to_event(self, row: tuple[Any, ...]) -> Event:
        """DB 행을 Event 객체로 변환
        
        컬럼 순서:
        0: seq, 1: event_id, 2: event_type, 3: ts,
        4: correlation_id, 5: causation_id, 6: command_id, 7: source,
        8: entity_kind, 9: entity_id,
        10: scope_exchange, 11: scope_venue, 12: scope_account_id, 13: scope_symbol, 14: scope_mode,
        15: dedup_key, 16: payload_json
        """
        # ts 파싱 (ISO 8601 문자열 -> datetime)
        ts = row[3]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        
        # payload 파싱 (JSON 문자열 -> dict)
        payload = row[16]
        if isinstance(payload, str):
            payload = json.loads(payload)
        
        # Scope 생성
        scope = Scope(
            exchange=row[10],
            venue=row[11],
            account_id=row[12],
            symbol=row[13],
            mode=row[14],
        )
        
        return Event(
            event_id=row[1],
            event_type=row[2],
            ts=ts,
            correlation_id=row[4],
            causation_id=row[5],
            command_id=row[6],
            source=row[7],
            entity_kind=row[8],
            entity_id=row[9],
            scope=scope,
            dedup_key=row[15],
            payload=payload,
            seq=row[0],  # DB 시퀀스 번호
        )
