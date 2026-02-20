"""
Event Projector

Event Stream을 읽어 Projection 테이블 업데이트.
Checkpoint 기반으로 마지막 처리 위치 기억.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.domain.events import Event
from core.storage.event_store import EventStore
from bot.projector.handlers.base import ProjectionHandler
from bot.projector.handlers.balance import BalanceProjectionHandler
from bot.projector.handlers.position import PositionProjectionHandler
from bot.projector.handlers.order import OrderProjectionHandler

logger = logging.getLogger(__name__)


class EventProjector:
    """Event Projector
    
    Event Store에서 이벤트를 읽어 Projection 업데이트.
    checkpoint_store를 사용하여 마지막 처리 위치 기억.
    
    Args:
        adapter: SQLite 어댑터
        event_store: 이벤트 저장소
        checkpoint_name: 체크포인트 이름 (기본: projector)
        
    사용 예시:
    ```python
    projector = EventProjector(adapter, event_store)
    
    # 메인 루프에서 주기적 호출
    processed = await projector.apply_pending_events()
    print(f"Processed {processed} events")
    
    # 전체 재구축
    await projector.rebuild_all()
    ```
    """
    
    CHECKPOINT_NAME = "projector"
    
    def __init__(
        self,
        adapter: SQLiteAdapter,
        event_store: EventStore,
        checkpoint_name: str = CHECKPOINT_NAME,
    ):
        self.adapter = adapter
        self.event_store = event_store
        self.checkpoint_name = checkpoint_name
        
        # 핸들러 레지스트리
        self._handlers: dict[str, ProjectionHandler] = {}
        
        # 기본 핸들러 등록
        self._register_default_handlers()
        
        # 통계
        self._processed_count = 0
        self._error_count = 0
    
    def _register_default_handlers(self) -> None:
        """기본 핸들러 등록"""
        # Balance 핸들러
        balance_handler = BalanceProjectionHandler(self.adapter)
        for event_type in balance_handler.handled_event_types:
            self._handlers[event_type] = balance_handler
        
        # Position 핸들러
        position_handler = PositionProjectionHandler(self.adapter)
        for event_type in position_handler.handled_event_types:
            self._handlers[event_type] = position_handler
        
        # Order 핸들러
        order_handler = OrderProjectionHandler(self.adapter)
        for event_type in order_handler.handled_event_types:
            self._handlers[event_type] = order_handler
    
    def register_handler(self, handler: ProjectionHandler) -> None:
        """핸들러 등록
        
        Args:
            handler: Projection 핸들러
        """
        for event_type in handler.handled_event_types:
            self._handlers[event_type] = handler
            logger.debug(f"Projection handler registered: {event_type}")
    
    async def apply_pending_events(self, batch_size: int = 100) -> int:
        """대기 중인 이벤트 처리
        
        마지막 체크포인트 이후의 이벤트를 처리하고 Projection 업데이트.
        
        Args:
            batch_size: 한 번에 처리할 최대 이벤트 수
            
        Returns:
            처리된 이벤트 수
        """
        # 마지막 체크포인트 조회
        last_seq = await self._get_checkpoint()
        
        # 새 이벤트 조회
        events = await self.event_store.get_since(last_seq, limit=batch_size)
        
        if not events:
            return 0
        
        processed = 0
        last_processed_seq = last_seq
        
        for event in events:
            handler = self._handlers.get(event.event_type)
            
            if handler:
                try:
                    success = await handler.handle(event)
                    if success:
                        processed += 1
                        self._processed_count += 1
                    else:
                        self._error_count += 1
                except Exception as e:
                    self._error_count += 1
                    logger.error(
                        f"Projection handler error: {e}",
                        extra={
                            "event_id": event.event_id,
                            "event_type": event.event_type,
                        },
                    )
            
            # 핸들러가 없어도 체크포인트는 진행
            last_processed_seq = event.seq
        
        # 체크포인트 업데이트
        if last_processed_seq > last_seq:
            await self._set_checkpoint(last_processed_seq)
        
        if processed > 0:
            logger.debug(f"Projected {processed} events, last_seq: {last_processed_seq}")
        
        return processed
    
    async def apply_all_pending(self) -> int:
        """모든 대기 이벤트 처리
        
        Returns:
            처리된 총 이벤트 수
        """
        total = 0
        
        while True:
            processed = await self.apply_pending_events()
            total += processed
            
            if processed == 0:
                break
        
        return total
    
    async def rebuild_all(self) -> int:
        """Projection 전체 재구축
        
        체크포인트를 0으로 리셋하고 처음부터 모든 이벤트 재처리.
        
        Returns:
            처리된 이벤트 수
        """
        logger.info("Starting projection rebuild...")
        
        # 체크포인트 리셋
        await self._set_checkpoint(0)
        
        # Projection 테이블 초기화
        await self._clear_projections()
        
        # 전체 재처리
        total = await self.apply_all_pending()
        
        logger.info(f"Projection rebuild completed: {total} events")
        return total
    
    async def _get_checkpoint(self) -> int:
        """체크포인트 조회"""
        sql = """
            SELECT last_seq
            FROM checkpoint_store
            WHERE checkpoint_type = ?
        """
        
        row = await self.adapter.fetchone(sql, (self.checkpoint_name,))
        return row[0] if row else 0
    
    async def _set_checkpoint(self, seq: int) -> None:
        """체크포인트 설정"""
        sql = """
            INSERT INTO checkpoint_store (checkpoint_type, last_seq, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(checkpoint_type)
            DO UPDATE SET
                last_seq = excluded.last_seq,
                updated_at = excluded.updated_at
        """
        
        now = datetime.now(timezone.utc).isoformat()
        await self.adapter.execute(sql, (self.checkpoint_name, seq, now))
        await self.adapter.commit()
    
    async def _clear_projections(self) -> None:
        """Projection 테이블 초기화"""
        tables = [
            "projection_balance",
            "projection_position",
            "projection_order",
        ]
        
        for table in tables:
            try:
                await self.adapter.execute(f"DELETE FROM {table}")
            except Exception:
                pass  # 테이블이 없으면 무시
        
        await self.adapter.commit()
        logger.info("Projection tables cleared")
    
    async def get_balance(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        asset: str,
    ) -> dict[str, Any] | None:
        """잔고 조회 (편의 메서드)"""
        handler = self._handlers.get("BalanceChanged")
        if isinstance(handler, BalanceProjectionHandler):
            return await handler.get_balance(
                exchange, venue, account_id, mode, asset
            )
        return None
    
    async def get_position(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str,
    ) -> dict[str, Any] | None:
        """포지션 조회 (편의 메서드)"""
        handler = self._handlers.get("PositionChanged")
        if isinstance(handler, PositionProjectionHandler):
            return await handler.get_position(
                exchange, venue, account_id, mode, symbol
            )
        return None
    
    async def get_open_orders(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> list[dict[str, Any]]:
        """오픈 주문 조회 (편의 메서드)"""
        handler = self._handlers.get("OrderPlaced")
        if isinstance(handler, OrderProjectionHandler):
            return await handler.get_open_orders(
                exchange, venue, account_id, mode, symbol
            )
        return []
    
    def get_stats(self) -> dict[str, Any]:
        """통계 반환"""
        return {
            "processed_count": self._processed_count,
            "error_count": self._error_count,
            "handled_event_types": list(self._handlers.keys()),
        }
    
    def reset_stats(self) -> None:
        """통계 초기화"""
        self._processed_count = 0
        self._error_count = 0
