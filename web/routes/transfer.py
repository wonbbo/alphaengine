"""
이체 API 라우터

입출금 관련 API 엔드포인트.
"""

import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from web.dependencies import get_db, get_transfer_manager, is_transfer_available
from web.services.transfer_service import TransferService, TransferResponse

logger = logging.getLogger(__name__)


# =========================================================================
# 입출금 기능 가용성 체크
# =========================================================================


class TransferUnavailableResponse(BaseModel):
    """입출금 기능 비활성화 응답"""
    
    available: bool = False
    reason: str


def check_transfer_available():
    """입출금 기능 사용 가능 여부 체크
    
    Raises:
        HTTPException: 입출금 기능 비활성화 시 503 반환
    """
    if not is_transfer_available():
        raise HTTPException(
            status_code=503,
            detail={
                "available": False,
                "reason": "입출금 기능이 비활성화되어 있습니다. (Testnet 모드)",
            },
        )

router = APIRouter(prefix="/api/transfer", tags=["Transfer"])


# =========================================================================
# Request/Response 모델
# =========================================================================


class DepositRequest(BaseModel):
    """입금 요청"""
    
    amount_krw: str = Field(..., description="입금 금액 (KRW)")


class WithdrawRequest(BaseModel):
    """출금 요청"""
    
    amount_usdt: str = Field(..., description="출금 금액 (USDT)")


class DepositStatusResponse(BaseModel):
    """입금 가능 상태 응답"""
    
    can_deposit: bool
    krw_balance: str
    trx_balance: str
    trx_price_krw: str
    trx_value_krw: str
    fee_trx: str
    fee_krw: str
    min_deposit_krw: str
    pending_deposit: bool
    pending_transfer_id: str | None


class WithdrawStatusResponse(BaseModel):
    """출금 가능 상태 응답"""
    
    can_withdraw: bool
    usdt_balance: str
    has_position: bool
    position_count: int
    min_withdraw_usdt: str
    warning: str | None
    pending_withdraw: bool
    pending_transfer_id: str | None


class TransferResponseModel(BaseModel):
    """이체 응답"""
    
    transfer_id: str
    transfer_type: str
    status: str
    requested_amount: str
    requested_at: str
    current_step: int
    total_steps: int
    actual_amount: str | None
    error_message: str | None
    completed_at: str | None


class TransferHistoryResponse(BaseModel):
    """이체 내역 응답"""
    
    transfers: list[TransferResponseModel]
    total: int
    limit: int
    offset: int


# =========================================================================
# 입금 API
# =========================================================================


@router.get("/deposit/status", response_model=DepositStatusResponse)
async def get_deposit_status(
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """입금 가능 상태 조회
    
    Upbit 잔고와 TRX 시세를 조합하여 입금 가능 여부를 반환합니다.
    
    Returns:
        입금 상태 정보
    """
    check_transfer_available()
    
    try:
        status = await transfer_manager.get_deposit_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get deposit status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deposit", response_model=TransferResponseModel)
async def request_deposit(
    request: DepositRequest,
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """입금 요청
    
    Upbit KRW -> Binance Futures USDT 입금을 시작합니다.
    
    Args:
        request: 입금 요청 (금액)
        
    Returns:
        생성된 이체 정보
    """
    check_transfer_available()
    
    try:
        amount = Decimal(request.amount_krw)
        
        if amount < Decimal("5000"):
            raise HTTPException(
                status_code=400,
                detail="최소 입금 금액은 5,000원입니다.",
            )
        
        transfer = await transfer_manager.request_deposit(
            amount_krw=amount,
            requested_by="WEB:user",
        )
        
        return TransferResponse.from_transfer(transfer).to_dict()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to request deposit: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# 출금 API
# =========================================================================


@router.get("/withdraw/status", response_model=WithdrawStatusResponse)
async def get_withdraw_status(
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """출금 가능 상태 조회
    
    Binance Futures 잔고와 포지션 정보를 반환합니다.
    
    Returns:
        출금 상태 정보
    """
    check_transfer_available()
    
    try:
        status = await transfer_manager.get_withdraw_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get withdraw status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/withdraw", response_model=TransferResponseModel)
async def request_withdraw(
    request: WithdrawRequest,
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """출금 요청
    
    Binance Futures USDT -> Upbit KRW 출금을 시작합니다.
    
    Args:
        request: 출금 요청 (금액)
        
    Returns:
        생성된 이체 정보
    """
    check_transfer_available()
    
    try:
        amount = Decimal(request.amount_usdt)
        
        if amount < Decimal("10"):
            raise HTTPException(
                status_code=400,
                detail="최소 출금 금액은 10 USDT입니다.",
            )
        
        transfer = await transfer_manager.request_withdraw(
            amount_usdt=amount,
            requested_by="WEB:user",
        )
        
        return TransferResponse.from_transfer(transfer).to_dict()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to request withdraw: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# 조회 API
# =========================================================================


@router.get("/{transfer_id}", response_model=TransferResponseModel)
async def get_transfer(
    transfer_id: str,
    db=Depends(get_db),
) -> dict[str, Any]:
    """특정 이체 조회
    
    Args:
        transfer_id: 이체 ID
        
    Returns:
        이체 정보
    """
    service = TransferService(db)
    transfer = await service.get_transfer(transfer_id)
    
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    
    return transfer.to_dict()


@router.get("/", response_model=TransferHistoryResponse)
async def get_history(
    transfer_type: str | None = Query(None, description="DEPOSIT 또는 WITHDRAW"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
) -> dict[str, Any]:
    """이체 내역 조회
    
    Args:
        transfer_type: 이체 유형 필터
        limit: 조회 개수
        offset: 시작 위치
        
    Returns:
        이체 내역 목록
    """
    service = TransferService(db)
    transfers = await service.get_history(
        transfer_type=transfer_type,
        limit=limit,
        offset=offset,
    )
    
    return {
        "transfers": [t.to_dict() for t in transfers],
        "total": len(transfers),
        "limit": limit,
        "offset": offset,
    }


@router.get("/pending/list")
async def get_pending_transfers(
    db=Depends(get_db),
) -> dict[str, Any]:
    """진행 중인 이체 목록
    
    Returns:
        진행 중인 이체 목록
    """
    service = TransferService(db)
    transfers = await service.get_pending_transfers()
    
    return {
        "transfers": [t.to_dict() for t in transfers],
        "count": len(transfers),
    }


# =========================================================================
# 취소/재시도 API
# =========================================================================


@router.post("/{transfer_id}/cancel", response_model=TransferResponseModel)
async def cancel_transfer(
    transfer_id: str,
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """이체 취소
    
    진행 중인 이체를 취소합니다.
    블록체인 전송 이후에는 취소할 수 없습니다.
    
    Args:
        transfer_id: 이체 ID
        
    Returns:
        업데이트된 이체 정보
    """
    check_transfer_available()
    
    try:
        transfer = await transfer_manager.cancel_transfer(transfer_id)
        return TransferResponse.from_transfer(transfer).to_dict()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel transfer: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{transfer_id}/retry", response_model=TransferResponseModel)
async def retry_transfer(
    transfer_id: str,
    transfer_manager=Depends(get_transfer_manager),
) -> dict[str, Any]:
    """실패한 이체 재시도
    
    FAILED 상태의 이체를 현재 단계부터 재시도합니다.
    
    Args:
        transfer_id: 이체 ID
        
    Returns:
        업데이트된 이체 정보
    """
    check_transfer_available()
    
    try:
        transfer = await transfer_manager.retry_transfer(transfer_id)
        return TransferResponse.from_transfer(transfer).to_dict()
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to retry transfer: {e}")
        raise HTTPException(status_code=500, detail=str(e))
