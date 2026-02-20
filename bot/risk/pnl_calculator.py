"""
PnL Calculator

일일 손익(PnL) 계산.
EventStore에서 당일 체결 이벤트를 조회하여 실현 손익 계산.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.storage.event_store import EventStore

logger = logging.getLogger(__name__)


class PnLCalculator:
    """PnL 계산기
    
    EventStore의 체결 이벤트(TradeExecuted)에서 일일 실현 손익을 계산.
    
    Args:
        event_store: 이벤트 저장소
        
    사용 예시:
    ```python
    calculator = PnLCalculator(event_store)
    
    daily_pnl = await calculator.get_daily_pnl(
        exchange="BINANCE",
        venue="FUTURES",
        account_id="default",
        mode="TESTNET",
        symbol="XRPUSDT",
    )
    print(f"오늘 실현 손익: {daily_pnl}")
    ```
    """
    
    def __init__(self, event_store: "EventStore"):
        self.event_store = event_store
    
    async def get_daily_pnl(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> Decimal:
        """일일 실현 손익 조회
        
        오늘 00:00 UTC부터 현재까지의 체결 이벤트에서 실현 손익 합산.
        
        Args:
            exchange: 거래소
            venue: 장소 (FUTURES, SPOT)
            account_id: 계좌 ID
            mode: 모드 (TESTNET, PRODUCTION)
            symbol: 심볼 (None이면 전체)
            
        Returns:
            일일 실현 손익 (Decimal)
        """
        # 오늘 시작 시간 (00:00 UTC)
        now = datetime.now(timezone.utc)
        today_start = datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=timezone.utc,
        )
        
        # 밀리초 타임스탬프
        start_ts = int(today_start.timestamp() * 1000)
        
        try:
            # TradeExecuted 이벤트 조회
            events = await self.event_store.get_events_by_type(
                event_type="TradeExecuted",
                after_ts=start_ts,
            )
            
            total_pnl = Decimal("0")
            
            for event in events:
                # Scope 필터링
                scope = event.scope
                if scope.exchange != exchange:
                    continue
                if scope.venue != venue:
                    continue
                if scope.account_id != account_id:
                    continue
                if scope.mode != mode:
                    continue
                if symbol and scope.symbol != symbol:
                    continue
                
                # payload에서 realized_pnl 추출
                payload = event.payload or {}
                realized_pnl_str = payload.get("realized_pnl", "0")
                
                try:
                    realized_pnl = Decimal(str(realized_pnl_str))
                    total_pnl += realized_pnl
                except (ValueError, TypeError, InvalidOperation):
                    # 잘못된 값은 무시하고 계속 진행
                    continue
            
            logger.debug(
                f"Daily PnL calculated: {total_pnl}",
                extra={
                    "symbol": symbol,
                    "event_count": len(events),
                },
            )
            
            return total_pnl
            
        except Exception as e:
            logger.error(f"Failed to calculate daily PnL: {e}")
            return Decimal("0")
    
    async def get_weekly_pnl(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> Decimal:
        """주간 실현 손익 조회
        
        7일 전 00:00 UTC부터 현재까지의 실현 손익 합산.
        """
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=7)
        week_start = datetime(
            year=week_start.year,
            month=week_start.month,
            day=week_start.day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=timezone.utc,
        )
        
        start_ts = int(week_start.timestamp() * 1000)
        
        try:
            events = await self.event_store.get_events_by_type(
                event_type="TradeExecuted",
                after_ts=start_ts,
            )
            
            total_pnl = Decimal("0")
            
            for event in events:
                scope = event.scope
                if scope.exchange != exchange:
                    continue
                if scope.venue != venue:
                    continue
                if scope.account_id != account_id:
                    continue
                if scope.mode != mode:
                    continue
                if symbol and scope.symbol != symbol:
                    continue
                
                payload = event.payload or {}
                realized_pnl_str = payload.get("realized_pnl", "0")
                
                try:
                    realized_pnl = Decimal(str(realized_pnl_str))
                    total_pnl += realized_pnl
                except (ValueError, TypeError, InvalidOperation):
                    continue
            
            return total_pnl
            
        except Exception as e:
            logger.error(f"Failed to calculate weekly PnL: {e}")
            return Decimal("0")
    
    async def get_pnl_summary(
        self,
        exchange: str,
        venue: str,
        account_id: str,
        mode: str,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        """PnL 요약 조회
        
        Returns:
            {
                "daily_pnl": Decimal,
                "weekly_pnl": Decimal,
                "trade_count_today": int,
                "winning_trades_today": int,
                "losing_trades_today": int,
            }
        """
        now = datetime.now(timezone.utc)
        today_start = datetime(
            year=now.year,
            month=now.month,
            day=now.day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=timezone.utc,
        )
        start_ts = int(today_start.timestamp() * 1000)
        
        try:
            events = await self.event_store.get_events_by_type(
                event_type="TradeExecuted",
                after_ts=start_ts,
            )
            
            daily_pnl = Decimal("0")
            trade_count = 0
            winning_trades = 0
            losing_trades = 0
            
            for event in events:
                scope = event.scope
                if scope.exchange != exchange:
                    continue
                if scope.venue != venue:
                    continue
                if scope.account_id != account_id:
                    continue
                if scope.mode != mode:
                    continue
                if symbol and scope.symbol != symbol:
                    continue
                
                payload = event.payload or {}
                realized_pnl_str = payload.get("realized_pnl", "0")
                
                try:
                    realized_pnl = Decimal(str(realized_pnl_str))
                    daily_pnl += realized_pnl
                    trade_count += 1
                    
                    if realized_pnl > 0:
                        winning_trades += 1
                    elif realized_pnl < 0:
                        losing_trades += 1
                        
                except (ValueError, TypeError, InvalidOperation):
                    continue
            
            # 주간 PnL
            weekly_pnl = await self.get_weekly_pnl(
                exchange, venue, account_id, mode, symbol,
            )
            
            return {
                "daily_pnl": daily_pnl,
                "weekly_pnl": weekly_pnl,
                "trade_count_today": trade_count,
                "winning_trades_today": winning_trades,
                "losing_trades_today": losing_trades,
            }
            
        except Exception as e:
            logger.error(f"Failed to get PnL summary: {e}")
            return {
                "daily_pnl": Decimal("0"),
                "weekly_pnl": Decimal("0"),
                "trade_count_today": 0,
                "winning_trades_today": 0,
                "losing_trades_today": 0,
            }
