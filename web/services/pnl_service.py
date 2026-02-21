"""
PnL 서비스

복식부기 View 기반 손익 계산
"""

import json
import logging
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.store import LedgerStore

logger = logging.getLogger(__name__)


class PnLService:
    """PnL 계산 서비스
    
    LedgerStore의 View 기반 메서드를 활용하여 손익 정보 제공.
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_pnl_summary(self, mode: str) -> dict[str, Any]:
        """PnL 요약
        
        일일/주간/월간/전체 손익 및 수익률
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            PnL 요약 데이터
        """
        stats = await self.ledger_store.get_pnl_statistics(mode)
        
        # 초기 자본 조회
        initial_capital = await self._get_initial_capital()
        
        # 현재 자산 조회
        current_equity = await self._get_current_equity(mode)
        
        # 수익률 계산
        def calc_return(pnl: float) -> float:
            if initial_capital > 0:
                return round((pnl / initial_capital) * 100, 2)
            return 0.0
        
        daily_pnl = stats["daily"]["pnl"] or 0
        weekly_pnl = stats["weekly"]["pnl"] or 0
        monthly_pnl = stats["monthly"]["pnl"] or 0
        total_pnl = stats["total"]["pnl"] or 0
        
        return {
            "daily_pnl": str(daily_pnl),
            "weekly_pnl": str(weekly_pnl),
            "monthly_pnl": str(monthly_pnl),
            "total_pnl": str(total_pnl),
            "daily_return_pct": str(calc_return(daily_pnl)),
            "weekly_return_pct": str(calc_return(weekly_pnl)),
            "monthly_return_pct": str(calc_return(monthly_pnl)),
            "total_return_pct": str(calc_return(total_pnl)),
            "initial_capital": str(initial_capital),
            "current_equity": str(current_equity),
            "trade_count_today": stats["daily"]["trades"] or 0,
            "winning_trades_today": stats["daily"]["wins"] or 0,
            "losing_trades_today": stats["daily"]["losses"] or 0,
            "win_rate_today": str(stats["daily"]["win_rate"] or 0),
            "total_fees": str(stats["total"]["fees"] or 0),
        }
    
    async def get_daily_pnl_series(
        self, 
        mode: str, 
        days: int = 30,
    ) -> dict[str, Any]:
        """일별 PnL 시계열
        
        차트 데이터용
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values 포함 차트 데이터
        """
        series = await self.ledger_store.get_daily_pnl_series(mode, days)
        return {
            "labels": series["labels"],
            "values": series["values"],
        }
    
    async def get_cumulative_pnl_series(
        self, 
        mode: str, 
        days: int = 30,
    ) -> dict[str, Any]:
        """누적 PnL 시계열
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values 포함 차트 데이터
        """
        series = await self.ledger_store.get_daily_pnl_series(mode, days)
        return {
            "labels": series["labels"],
            "values": series["cumulative"],
        }
    
    async def get_daily_returns_series(
        self, 
        mode: str, 
        days: int = 30,
    ) -> dict[str, Any]:
        """일별 수익률 시계열
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values 포함 차트 데이터 (%)
        """
        series = await self.ledger_store.get_daily_pnl_series(mode, days)
        initial_capital = await self._get_initial_capital()
        
        if initial_capital <= 0:
            return {
                "labels": series["labels"],
                "values": [0] * len(series["values"]),
            }
        
        returns = [
            round((pnl / initial_capital) * 100, 2)
            for pnl in series["values"]
        ]
        
        return {
            "labels": series["labels"],
            "values": returns,
        }
    
    async def get_cumulative_returns_series(
        self, 
        mode: str, 
        days: int = 30,
    ) -> dict[str, Any]:
        """누적 수익률 시계열
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values 포함 차트 데이터 (%)
        """
        series = await self.ledger_store.get_daily_pnl_series(mode, days)
        initial_capital = await self._get_initial_capital()
        
        if initial_capital <= 0:
            return {
                "labels": series["labels"],
                "values": [0] * len(series["cumulative"]),
            }
        
        returns = [
            round((pnl / initial_capital) * 100, 2)
            for pnl in series["cumulative"]
        ]
        
        return {
            "labels": series["labels"],
            "values": returns,
        }
    
    async def _get_initial_capital(self) -> float:
        """초기 자본 조회
        
        config_store에서 initial_capital 조회.
        없으면 기본값 5000 USDT 반환.
        """
        try:
            row = await self.db.fetchone(
                "SELECT value_json FROM config_store WHERE config_key = 'initial_capital'"
            )
            if row:
                config = json.loads(row[0])
                return float(config.get("USDT", 5000))
        except Exception as e:
            logger.debug(f"Failed to get initial capital: {e}")
        return 5000.0
    
    async def _get_current_equity(self, mode: str) -> float:
        """현재 총 자산
        
        ASSET 계정 중 Binance 관련 계정의 합계.
        """
        try:
            portfolio = await self.ledger_store.get_portfolio(mode)
            
            # USDT 합계 (SPOT + FUTURES)
            total = sum(
                p["balance"] or 0
                for p in portfolio
                if p["asset"] == "USDT"
            )
            return total
        except Exception as e:
            logger.debug(f"Failed to get current equity: {e}")
        return 0.0
