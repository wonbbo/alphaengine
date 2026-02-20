"""
응답 스키마 (Pydantic)

Web API 응답 데이터 직렬화
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    
    status: str = Field(default="ok", description="서비스 상태")
    mode: str = Field(..., description="거래 모드 (testnet/production)")
    timestamp: datetime = Field(..., description="응답 시간 (UTC)")


class PositionResponse(BaseModel):
    """포지션 응답"""
    
    symbol: str = Field(..., description="심볼")
    side: str | None = Field(default=None, description="포지션 방향 (LONG/SHORT)")
    qty: str = Field(..., description="수량")
    entry_price: str = Field(..., description="진입 가격")
    unrealized_pnl: str = Field(..., description="미실현 손익")
    leverage: int = Field(..., description="레버리지")
    margin_type: str = Field(..., description="마진 타입 (ISOLATED/CROSS)")
    updated_at: str = Field(..., description="마지막 업데이트 시간")


class BalanceResponse(BaseModel):
    """잔고 응답"""
    
    asset: str = Field(..., description="자산")
    free: str = Field(..., description="사용 가능 잔고")
    locked: str = Field(..., description="잠긴 잔고")
    updated_at: str = Field(..., description="마지막 업데이트 시간")


class OpenOrderResponse(BaseModel):
    """오픈 주문 응답"""
    
    symbol: str = Field(..., description="심볼")
    exchange_order_id: str = Field(..., description="거래소 주문 ID")
    client_order_id: str | None = Field(default=None, description="클라이언트 주문 ID")
    order_state: str = Field(..., description="주문 상태")
    side: str = Field(..., description="주문 방향 (BUY/SELL)")
    order_type: str = Field(..., description="주문 유형 (MARKET/LIMIT 등)")
    original_qty: str = Field(..., description="원 주문 수량")
    executed_qty: str = Field(..., description="체결 수량")
    price: str | None = Field(default=None, description="주문 가격")
    stop_price: str | None = Field(default=None, description="스탑 가격")
    created_at: str = Field(..., description="생성 시간")


class TradeResponse(BaseModel):
    """최근 체결 응답"""
    
    event_id: str = Field(..., description="이벤트 ID")
    symbol: str = Field(..., description="심볼")
    side: str = Field(..., description="주문 방향")
    qty: str = Field(..., description="체결 수량")
    price: str = Field(..., description="체결 가격")
    realized_pnl: str | None = Field(default=None, description="실현 손익")
    ts: str = Field(..., description="체결 시간")


class DashboardResponse(BaseModel):
    """대시보드 응답
    
    현재 상태 전체 조회 (포지션, 잔고, 오픈 주문, 최근 체결)
    """
    
    mode: str = Field(..., description="거래 모드")
    symbol: str | None = Field(default=None, description="현재 심볼")
    position: PositionResponse | None = Field(default=None, description="현재 포지션")
    balances: list[BalanceResponse] = Field(default_factory=list, description="잔고 목록")
    open_orders: list[OpenOrderResponse] = Field(default_factory=list, description="오픈 주문 목록")
    recent_trades: list[TradeResponse] = Field(default_factory=list, description="최근 체결 목록")
    event_count: int = Field(default=0, description="총 이벤트 수")
    command_pending_count: int = Field(default=0, description="처리 대기 Command 수")
    timestamp: datetime = Field(..., description="조회 시간 (UTC)")


class ScopeResponse(BaseModel):
    """Scope 응답"""
    
    exchange: str = Field(..., description="거래소")
    venue: str = Field(..., description="거래 장소")
    account_id: str = Field(..., description="계좌 ID")
    symbol: str | None = Field(default=None, description="심볼")
    mode: str = Field(..., description="거래 모드")


class EventResponse(BaseModel):
    """이벤트 응답"""
    
    event_id: str = Field(..., description="이벤트 ID")
    event_type: str = Field(..., description="이벤트 타입")
    ts: str = Field(..., description="이벤트 시간 (UTC)")
    source: str = Field(..., description="이벤트 출처")
    entity_kind: str = Field(..., description="엔티티 종류")
    entity_id: str = Field(..., description="엔티티 ID")
    scope: ScopeResponse = Field(..., description="거래 범위")
    payload: dict[str, Any] = Field(..., description="이벤트 페이로드")


class EventListResponse(BaseModel):
    """이벤트 목록 응답"""
    
    events: list[EventResponse] = Field(default_factory=list, description="이벤트 목록")
    total_count: int = Field(default=0, description="전체 이벤트 수")
    limit: int = Field(default=100, description="조회 제한")
    offset: int = Field(default=0, description="조회 시작 위치")


class ActorResponse(BaseModel):
    """행위자 응답"""
    
    kind: str = Field(..., description="행위자 종류")
    id: str = Field(..., description="행위자 ID")


class CommandResponse(BaseModel):
    """Command 생성 응답"""
    
    command_id: str = Field(..., description="Command ID")
    status: str = Field(..., description="Command 상태")
    message: str = Field(default="Command accepted", description="응답 메시지")


class CommandDetailResponse(BaseModel):
    """Command 상세 응답"""
    
    command_id: str = Field(..., description="Command ID")
    command_type: str = Field(..., description="명령 타입")
    ts: str = Field(..., description="생성 시간 (UTC)")
    actor: ActorResponse = Field(..., description="행위자")
    scope: ScopeResponse = Field(..., description="거래 범위")
    status: str = Field(..., description="상태 (NEW/SENT/ACK/FAILED)")
    priority: int = Field(..., description="우선순위")
    payload: dict[str, Any] = Field(..., description="명령 페이로드")
    result: dict[str, Any] | None = Field(default=None, description="실행 결과")
    last_error: str | None = Field(default=None, description="마지막 에러")


class CommandListResponse(BaseModel):
    """Command 목록 응답"""
    
    commands: list[CommandDetailResponse] = Field(default_factory=list, description="Command 목록")
    total_count: int = Field(default=0, description="전체 Command 수")


class ConfigResponse(BaseModel):
    """설정 응답"""
    
    key: str = Field(..., description="설정 키")
    value: dict[str, Any] = Field(..., description="설정 값")
    version: int = Field(..., description="버전")
    updated_at: str = Field(..., description="마지막 업데이트 시간")
    updated_by: str = Field(..., description="마지막 업데이트 주체")
