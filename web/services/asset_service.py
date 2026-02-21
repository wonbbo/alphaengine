"""
자산 서비스

View 기반 자산 조회
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.store import LedgerStore


class AssetService:
    """자산 현황 서비스
    
    LedgerStore의 View 기반 메서드를 활용.
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_portfolio(self, mode: str) -> list[dict[str, Any]]:
        """포트폴리오 현황 조회
        
        v_portfolio View 활용.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            Venue/Asset별 잔액 현황
        """
        return await self.ledger_store.get_portfolio(mode)
    
    async def get_portfolio_summary(self, mode: str) -> dict[str, Any]:
        """포트폴리오 요약
        
        Venue별 USDT 합계.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            assets, spot_total_usdt, futures_total_usdt, total_usdt 포함 응답
        """
        portfolio = await self.ledger_store.get_portfolio(mode)
        
        # Venue별 USDT 합계
        spot_total = sum(
            p["balance"] or 0
            for p in portfolio 
            if p.get("venue") == "BINANCE_SPOT" and p.get("asset") == "USDT"
        )
        futures_total = sum(
            p["balance"] or 0
            for p in portfolio 
            if p.get("venue") == "BINANCE_FUTURES" and p.get("asset") == "USDT"
        )
        
        return {
            "assets": portfolio,
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
            "total_usdt": spot_total + futures_total,
        }
    
    async def get_trial_balance(self, mode: str) -> list[dict[str, Any]]:
        """시산표 조회
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            계정별 잔액
        """
        return await self.ledger_store.get_trial_balance(mode)
