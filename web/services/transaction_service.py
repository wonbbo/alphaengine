"""
거래 내역 서비스

View 기반 거래 조회
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.store import LedgerStore


class TransactionService:
    """거래 내역 서비스
    
    LedgerStore의 View 기반 메서드를 활용.
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_transactions(
        self,
        mode: str,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """거래 목록 조회
        
        v_trade_summary View 활용.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            symbol: 심볼 필터 (선택)
            limit: 조회 개수 제한
            offset: 시작 위치
            
        Returns:
            transactions, total_count, limit, offset 포함 응답
        """
        trades = await self.ledger_store.get_trade_summary(
            scope_mode=mode,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )
        
        # 총 개수 조회
        count_sql = "SELECT COUNT(*) FROM v_trade_summary WHERE scope_mode = ?"
        params: list[Any] = [mode]
        if symbol:
            count_sql += " AND symbol = ?"
            params.append(symbol)
        
        count_row = await self.db.fetchone(count_sql, tuple(params))
        total_count = count_row[0] if count_row else 0
        
        return {
            "transactions": trades,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    
    async def get_recent_trades(
        self, 
        mode: str, 
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """최근 거래 조회
        
        v_recent_trades View 활용.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            limit: 조회 개수 제한
            
        Returns:
            최근 거래 목록
        """
        return await self.ledger_store.get_recent_trades(mode, limit)
