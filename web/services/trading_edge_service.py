"""
Trading Edge 서비스

View 기반 성과 분석
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger.store import LedgerStore
from web.services.position_service import PositionService


class TradingEdgeService:
    """Trading Edge 분석 서비스
    
    LedgerStore의 View 기반 메서드를 활용.
    """
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
        self.position_service = PositionService(db)
    
    async def get_symbol_performance(self, mode: str) -> list[dict[str, Any]]:
        """심볼별 성과 조회
        
        v_symbol_pnl View 활용.
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            심볼별 손익 데이터
        """
        return await self.ledger_store.get_symbol_pnl(mode)
    
    async def get_edge_summary(self, mode: str) -> dict[str, Any]:
        """Edge 요약 통계
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            전체 Edge 통계
        """
        symbols = await self.ledger_store.get_symbol_pnl(mode)
        stats = await self.ledger_store.get_pnl_statistics(mode)
        
        # 평균 거래당 수익
        total_pnl = stats["total"]["pnl"] or 0
        total_trades = stats["total"]["trades"] or 0
        avg_pnl_per_trade = round(total_pnl / total_trades, 2) if total_trades > 0 else 0
        
        # Profit Factor (총 이익 / 총 손실)
        profit_factor = await self._calculate_profit_factor(mode)
        
        # 최고/최저 수익일 조회
        best_day, worst_day = await self._get_best_worst_days(mode)
        
        return {
            "symbols": symbols,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "total_fees": stats["total"]["fees"] or 0,
            "win_rate": stats["total"]["win_rate"],
            "avg_pnl_per_trade": avg_pnl_per_trade,
            "profit_factor": profit_factor,
            "best_day": best_day,
            "worst_day": worst_day,
            "symbol_count": len(symbols),
        }
    
    async def get_daily_edge_series(
        self, 
        mode: str, 
        days: int = 30,
    ) -> dict[str, Any]:
        """일별 Edge 시계열
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            days: 조회 일수
            
        Returns:
            labels, values, cumulative 포함 차트 데이터
        """
        return await self.ledger_store.get_daily_pnl_series(mode, days)
    
    async def _get_best_worst_days(self, mode: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """최고/최저 수익일 조회
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            (best_day, worst_day) 튜플
        """
        try:
            # 최고 수익일
            best_row = await self.db.fetchone(
                """
                SELECT trade_date, daily_pnl, trade_count
                FROM v_daily_pnl
                WHERE scope_mode = ? AND daily_pnl IS NOT NULL
                ORDER BY daily_pnl DESC
                LIMIT 1
                """,
                (mode,),
            )
            
            # 최저 수익일
            worst_row = await self.db.fetchone(
                """
                SELECT trade_date, daily_pnl, trade_count
                FROM v_daily_pnl
                WHERE scope_mode = ? AND daily_pnl IS NOT NULL
                ORDER BY daily_pnl ASC
                LIMIT 1
                """,
                (mode,),
            )
            
            best_day = None
            worst_day = None
            
            if best_row:
                best_day = {
                    "date": best_row[0],
                    "pnl": best_row[1],
                    "trade_count": best_row[2],
                }
            
            if worst_row:
                worst_day = {
                    "date": worst_row[0],
                    "pnl": worst_row[1],
                    "trade_count": worst_row[2],
                }
            
            # 같은 날인 경우 (데이터가 하루뿐) worst_day는 None
            if best_day and worst_day and best_day["date"] == worst_day["date"]:
                worst_day = None
            
            return best_day, worst_day
            
        except Exception:
            return None, None
    
    async def _calculate_profit_factor(self, mode: str) -> float:
        """Profit Factor 계산
        
        Profit Factor = 총 이익 / |총 손실|
        1 이상이면 수익 시스템
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            
        Returns:
            Profit Factor
        """
        try:
            # 이익/손실 집계
            row = await self.db.fetchone(
                """
                SELECT 
                    SUM(CASE WHEN daily_pnl > 0 THEN daily_pnl ELSE 0 END) as total_profit,
                    SUM(CASE WHEN daily_pnl < 0 THEN daily_pnl ELSE 0 END) as total_loss
                FROM v_daily_pnl
                WHERE scope_mode = ?
                """,
                (mode,),
            )
            
            if row:
                total_profit = row[0] or 0
                total_loss = abs(row[1] or 0)
                
                if total_loss > 0:
                    return round(total_profit / total_loss, 2)
                elif total_profit > 0:
                    # 손실 없이 이익만 있는 경우 (무한대 대신 9999 반환)
                    return 9999.0
            return 0.0
            
        except Exception:
            return 0.0
    
    async def get_per_trade_edge_series(
        self,
        mode: str,
        limit: int = 60,
        window: int = 20,
    ) -> dict[str, Any]:
        """거래별 Trading Edge 시계열
        
        Trading Edge = (승률 × 평균수익) - (패률 × 평균손실)
        누적 방식으로 계산 (처음부터 현재 거래까지의 모든 데이터 사용).
        
        Args:
            mode: TESTNET 또는 PRODUCTION
            limit: 조회할 거래 수
            window: 미사용 (하위 호환성 유지)
            
        Returns:
            labels, edges, pnls, final_edge 포함 차트 데이터
        """
        positions = await self.position_service.get_closed_positions(mode, limit)
        
        if not positions:
            return {"labels": [], "edges": [], "pnls": [], "final_edge": 0}
        
        labels = []
        edges = []
        pnls = []
        
        for i, pos in enumerate(positions):
            # 처음부터 현재 거래까지 모든 데이터 사용 (누적 방식)
            cumulative_positions = positions[:i + 1]
            
            # 승/패 분류
            wins = [p["realized_pnl"] for p in cumulative_positions if p["realized_pnl"] > 0]
            losses = [p["realized_pnl"] for p in cumulative_positions if p["realized_pnl"] < 0]
            
            total_trades = len(cumulative_positions)
            win_count = len(wins)
            loss_count = len(losses)
            
            # 승률, 패률
            win_rate = win_count / total_trades if total_trades > 0 else 0
            loss_rate = loss_count / total_trades if total_trades > 0 else 0
            
            # 평균 수익, 평균 손실
            avg_win = sum(wins) / win_count if win_count > 0 else 0
            avg_loss = abs(sum(losses) / loss_count) if loss_count > 0 else 0
            
            # Trading Edge 계산
            edge = (win_rate * avg_win) - (loss_rate * avg_loss)
            
            # 라벨: 거래 번호
            labels.append(f"#{i + 1}")
            edges.append(round(edge, 4))
            pnls.append(pos["realized_pnl"])
        
        # 마지막 Edge 값 (전체 거래 기준)
        final_edge = edges[-1] if edges else 0
        
        return {
            "labels": labels,
            "edges": edges,
            "pnls": pnls,
            "final_edge": final_edge,
        }
