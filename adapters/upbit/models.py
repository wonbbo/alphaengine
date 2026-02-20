"""
Upbit API 응답 모델

Upbit REST API 응답을 파싱하여 데이터클래스로 변환.
모든 금액은 Decimal 사용.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class UpbitAccount:
    """Upbit 계좌 잔고
    
    Attributes:
        currency: 자산 코드 (예: KRW, TRX)
        balance: 사용 가능 잔고
        locked: 거래 중인 잔고
        avg_buy_price: 매수 평균가
    """
    
    currency: str
    balance: Decimal
    locked: Decimal
    avg_buy_price: Decimal
    
    @property
    def total(self) -> Decimal:
        """총 잔고 (사용 가능 + 잠김)"""
        return self.balance + self.locked
    
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UpbitAccount":
        """API 응답에서 생성"""
        return cls(
            currency=data["currency"],
            balance=Decimal(str(data["balance"])),
            locked=Decimal(str(data["locked"])),
            avg_buy_price=Decimal(str(data.get("avg_buy_price", "0"))),
        )


@dataclass(frozen=True)
class UpbitTicker:
    """Upbit 시세 정보
    
    Attributes:
        market: 마켓 코드 (예: KRW-TRX)
        trade_price: 현재가
        change: 전일 대비 변화 (RISE/EVEN/FALL)
        change_rate: 전일 대비 변화율
        signed_change_price: 전일 대비 변화 금액
    """
    
    market: str
    trade_price: Decimal
    change: str
    change_rate: Decimal
    signed_change_price: Decimal
    
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UpbitTicker":
        """API 응답에서 생성"""
        return cls(
            market=data["market"],
            trade_price=Decimal(str(data["trade_price"])),
            change=data.get("change", "EVEN"),
            change_rate=Decimal(str(data.get("change_rate", "0"))),
            signed_change_price=Decimal(str(data.get("signed_change_price", "0"))),
        )


@dataclass(frozen=True)
class UpbitOrder:
    """Upbit 주문 정보
    
    Attributes:
        uuid: 주문 고유 ID
        side: 주문 타입 (bid=매수, ask=매도)
        ord_type: 주문 방식 (limit=지정가, price=시장가매수, market=시장가매도)
        price: 주문 가격
        state: 주문 상태 (wait, watch, done, cancel)
        market: 마켓 ID
        volume: 주문 수량
        remaining_volume: 미체결 수량
        executed_volume: 체결 수량
        trades_count: 체결 횟수
        created_at: 주문 생성 시각
    """
    
    uuid: str
    side: str
    ord_type: str
    price: Decimal | None
    state: str
    market: str
    volume: Decimal
    remaining_volume: Decimal
    executed_volume: Decimal
    trades_count: int
    created_at: datetime
    
    @property
    def is_buy(self) -> bool:
        """매수 주문인지 여부"""
        return self.side == "bid"
    
    @property
    def is_filled(self) -> bool:
        """완전 체결 여부"""
        return self.state == "done"
    
    @property
    def is_cancelled(self) -> bool:
        """취소 여부"""
        return self.state == "cancel"
    
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UpbitOrder":
        """API 응답에서 생성"""
        price = data.get("price")
        if price is not None:
            price = Decimal(str(price))
        
        created_at = data.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_at = datetime.now()
            
        return cls(
            uuid=data["uuid"],
            side=data["side"],
            ord_type=data["ord_type"],
            price=price,
            state=data["state"],
            market=data["market"],
            volume=Decimal(str(data.get("volume", "0"))),
            remaining_volume=Decimal(str(data.get("remaining_volume", "0"))),
            executed_volume=Decimal(str(data.get("executed_volume", "0"))),
            trades_count=int(data.get("trades_count", 0)),
            created_at=created_at,
        )


@dataclass(frozen=True)
class UpbitWithdraw:
    """Upbit 출금 정보
    
    Attributes:
        uuid: 출금 고유 ID
        currency: 자산 코드
        txid: 블록체인 트랜잭션 ID
        state: 상태 (submitting, submitted, almost_accepted, rejected, 
               accepted, processing, done, canceled)
        amount: 출금 수량
        fee: 출금 수수료
        created_at: 출금 요청 시각
        done_at: 출금 완료 시각
    """
    
    uuid: str
    currency: str
    txid: str | None
    state: str
    amount: Decimal
    fee: Decimal
    created_at: datetime
    done_at: datetime | None
    
    @property
    def is_done(self) -> bool:
        """출금 완료 여부"""
        return self.state == "done"
    
    @property
    def is_failed(self) -> bool:
        """출금 실패 여부"""
        return self.state in ("rejected", "canceled")
    
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UpbitWithdraw":
        """API 응답에서 생성"""
        created_at = data.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_at = datetime.now()
        
        done_at = data.get("done_at")
        if isinstance(done_at, str) and done_at:
            done_at = datetime.fromisoformat(done_at.replace("Z", "+00:00"))
        else:
            done_at = None
            
        return cls(
            uuid=data["uuid"],
            currency=data["currency"],
            txid=data.get("txid"),
            state=data["state"],
            amount=Decimal(str(data.get("amount", "0"))),
            fee=Decimal(str(data.get("fee", "0"))),
            created_at=created_at,
            done_at=done_at,
        )


@dataclass(frozen=True)
class UpbitDeposit:
    """Upbit 입금 정보
    
    Attributes:
        uuid: 입금 고유 ID
        currency: 자산 코드
        txid: 블록체인 트랜잭션 ID (코인 입금인 경우)
        state: 상태 (submitting, submitted, almost_accepted, rejected,
               accepted, processing, done, canceled)
        amount: 입금 수량
        fee: 입금 수수료
        created_at: 입금 시각
        done_at: 입금 완료 시각
    """
    
    uuid: str
    currency: str
    txid: str | None
    state: str
    amount: Decimal
    fee: Decimal
    created_at: datetime
    done_at: datetime | None
    
    @property
    def is_done(self) -> bool:
        """입금 완료 여부"""
        return self.state == "done"
    
    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "UpbitDeposit":
        """API 응답에서 생성"""
        created_at = data.get("created_at", "")
        if isinstance(created_at, str) and created_at:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        else:
            created_at = datetime.now()
        
        done_at = data.get("done_at")
        if isinstance(done_at, str) and done_at:
            done_at = datetime.fromisoformat(done_at.replace("Z", "+00:00"))
        else:
            done_at = None
            
        return cls(
            uuid=data["uuid"],
            currency=data["currency"],
            txid=data.get("txid"),
            state=data["state"],
            amount=Decimal(str(data.get("amount", "0"))),
            fee=Decimal(str(data.get("fee", "0"))),
            created_at=created_at,
            done_at=done_at,
        )
