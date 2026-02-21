"""
요청 스키마 (Pydantic)

Web API 요청 데이터 검증
"""

from typing import Any

from pydantic import BaseModel, Field


class ScopeRequest(BaseModel):
    """거래 범위 요청"""
    
    exchange: str = Field(default="BINANCE", description="거래소")
    venue: str = Field(default="FUTURES", description="거래 장소")
    account_id: str = Field(default="main", description="계좌 ID")
    symbol: str | None = Field(default=None, description="심볼")


class CommandCreateRequest(BaseModel):
    """Command 생성 요청
    
    Web에서 Bot으로 Command를 발행할 때 사용.
    """
    
    command_type: str = Field(..., description="명령 타입 (PlaceOrder, ClosePosition 등)")
    scope: ScopeRequest = Field(default_factory=ScopeRequest, description="거래 범위")
    payload: dict[str, Any] = Field(default_factory=dict, description="명령 페이로드")
    priority: int = Field(default=50, ge=0, le=100, description="우선순위 (높을수록 먼저)")
    idempotency_key: str | None = Field(default=None, description="멱등성 키")
    correlation_id: str | None = Field(default=None, description="상관 ID")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "command_type": "ClosePosition",
                    "scope": {
                        "exchange": "BINANCE",
                        "venue": "FUTURES",
                        "account_id": "main",
                        "symbol": "XRPUSDT",
                    },
                    "payload": {},
                    "priority": 100,
                },
                {
                    "command_type": "CancelAll",
                    "scope": {
                        "exchange": "BINANCE",
                        "venue": "FUTURES",
                        "account_id": "main",
                        "symbol": "XRPUSDT",
                    },
                    "payload": {},
                    "priority": 100,
                },
            ]
        }
    }


class ConfigUpdateRequest(BaseModel):
    """설정 변경 요청"""
    
    value: dict[str, Any] = Field(..., description="새로운 설정 값")
    expected_version: int | None = Field(
        default=None,
        description="예상 버전 (낙관적 락, None이면 무시)"
    )
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "value": {
                        "trading": {"symbol": "XRPUSDT"},
                        "strategy": {"name": "sma_cross", "params": {"fast": 10, "slow": 20}},
                    },
                    "expected_version": 1,
                }
            ]
        }
    }
