"""
Dashboard 라우트

현재 상태 조회 API (포지션, 잔고, 오픈 주문, 최근 체결)
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.models.responses import (
    DashboardResponse,
    PositionResponse,
    BalanceResponse,
    OpenOrderResponse,
    TradeResponse,
    BotStatusResponse,
)
from web.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    symbol: str | None = Query(default=None, description="심볼 (기본값: 설정된 심볼)"),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> DashboardResponse:
    """현재 상태 대시보드 조회
    
    포지션, 잔고, 오픈 주문, 최근 체결 등 전체 상태를 한 번에 조회.
    """
    service = DashboardService(db)
    
    # 설정에서 기본값 가져오기
    mode = settings.mode.value.upper()
    exchange = "BINANCE"
    venue = "FUTURES"
    account_id = "main"
    
    # 심볼이 지정되지 않으면 설정에서 가져오기 (설정이 없으면 None)
    target_symbol = symbol
    
    # 포지션 조회
    position_data = None
    if target_symbol:
        position_data = await service.get_position(
            exchange, venue, account_id, mode, target_symbol
        )
    
    position = None
    if position_data:
        position = PositionResponse(
            symbol=position_data["symbol"],
            side=position_data.get("side"),
            qty=position_data["qty"],
            entry_price=position_data["entry_price"],
            unrealized_pnl=position_data["unrealized_pnl"],
            leverage=position_data["leverage"],
            margin_type=position_data["margin_type"],
            updated_at=position_data["updated_at"],
        )
    
    # 잔고 조회
    balance_data = await service.get_balances(exchange, venue, account_id, mode)
    balances = [
        BalanceResponse(
            asset=b["asset"],
            free=b["free"],
            locked=b["locked"],
            updated_at=b["updated_at"],
        )
        for b in balance_data
    ]
    
    # 오픈 주문 조회
    orders_data = await service.get_open_orders(
        exchange, venue, account_id, mode, target_symbol
    )
    open_orders = [
        OpenOrderResponse(
            symbol=o["symbol"],
            exchange_order_id=o["exchange_order_id"],
            client_order_id=o.get("client_order_id"),
            order_state=o["order_state"],
            side=o["side"],
            order_type=o["order_type"],
            original_qty=o["original_qty"],
            executed_qty=o["executed_qty"],
            price=o.get("price"),
            stop_price=o.get("stop_price"),
            created_at=o["created_at"],
        )
        for o in orders_data
    ]
    
    # 최근 체결 조회
    trades_data = await service.get_recent_trades(
        exchange, venue, account_id, mode, target_symbol, limit=10
    )
    recent_trades = [
        TradeResponse(
            event_id=t["event_id"],
            symbol=t.get("symbol") or "",
            side=t.get("side") or "",
            qty=t.get("qty") or "0",
            price=t.get("price") or "0",
            realized_pnl=t.get("realized_pnl"),
            ts=t["ts"],
        )
        for t in trades_data
    ]
    
    # 이벤트 수, 대기 Command 수
    event_count = await service.get_event_count(mode)
    command_pending_count = await service.get_pending_command_count(mode)
    
    # Bot/전략 상태 조회
    bot_status_data = await service.get_bot_status()
    bot_status = BotStatusResponse(
        is_running=bot_status_data["is_running"],
        strategy_name=bot_status_data["strategy_name"],
        strategy_running=bot_status_data["strategy_running"],
        last_heartbeat=bot_status_data["last_heartbeat"],
        is_stale=bot_status_data["is_stale"],
    )
    
    return DashboardResponse(
        mode=mode,
        symbol=target_symbol,
        bot_status=bot_status,
        position=position,
        balances=balances,
        open_orders=open_orders,
        recent_trades=recent_trades,
        event_count=event_count,
        command_pending_count=command_pending_count,
        timestamp=datetime.now(timezone.utc),
    )
