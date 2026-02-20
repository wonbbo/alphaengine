"""
어댑터 인터페이스 정의

Protocol 기반으로 정의하여 의존성 주입 및 Mock 교체 가능.
모든 구현체는 이 Protocol을 준수해야 함.
"""

from typing import Protocol, Callable, Awaitable, Any, runtime_checkable

from core.types import WebSocketState


@runtime_checkable
class IExchangeRestClient(Protocol):
    """거래소 REST API 클라이언트 인터페이스
    
    모든 거래소 REST 클라이언트는 이 Protocol을 구현해야 함.
    금액/수량은 반드시 Decimal 타입 사용.
    """
    
    # -------------------------------------------------------------------------
    # listenKey 관리 (WebSocket User Data Stream용)
    # -------------------------------------------------------------------------
    
    async def create_listen_key(self) -> str:
        """listenKey 생성
        
        Returns:
            listenKey 문자열
        """
        ...
    
    async def extend_listen_key(self) -> None:
        """listenKey 유효기간 연장 (30분마다 호출 필요)"""
        ...
    
    async def delete_listen_key(self) -> None:
        """listenKey 삭제 (선택적)"""
        ...
    
    # -------------------------------------------------------------------------
    # 계좌 조회
    # -------------------------------------------------------------------------
    
    async def get_balances(self) -> list["Balance"]:
        """계좌 잔고 목록 조회
        
        Returns:
            잔고가 0보다 큰 자산 목록
        """
        ...
    
    async def get_position(self, symbol: str) -> "Position | None":
        """특정 심볼의 포지션 조회
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            
        Returns:
            포지션 정보 또는 None (포지션 없음)
        """
        ...
    
    async def get_open_orders(self, symbol: str | None = None) -> list["Order"]:
        """오픈 주문 목록 조회
        
        Args:
            symbol: 거래 심볼 (None이면 전체)
            
        Returns:
            오픈 주문 목록
        """
        ...
    
    async def get_trades(
        self,
        symbol: str,
        limit: int = 500,
        start_time: int | None = None,
    ) -> list["Trade"]:
        """체결 내역 조회
        
        Args:
            symbol: 거래 심볼
            limit: 조회 개수 (최대 1000)
            start_time: 시작 시간 (밀리초 타임스탬프)
            
        Returns:
            체결 내역 목록
        """
        ...
    
    # -------------------------------------------------------------------------
    # 주문 실행
    # -------------------------------------------------------------------------
    
    async def place_order(self, request: "OrderRequest") -> "Order":
        """주문 생성
        
        Args:
            request: 주문 요청 정보
            
        Returns:
            생성된 주문 정보
            
        Raises:
            OrderError: 주문 실패 시
        """
        ...
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> "Order":
        """주문 취소
        
        Args:
            symbol: 거래 심볼
            order_id: 거래소 주문 ID (둘 중 하나 필수)
            client_order_id: 클라이언트 주문 ID (둘 중 하나 필수)
            
        Returns:
            취소된 주문 정보
            
        Raises:
            OrderError: 취소 실패 시
        """
        ...
    
    async def cancel_all_orders(self, symbol: str) -> int:
        """특정 심볼의 모든 주문 취소
        
        Args:
            symbol: 거래 심볼
            
        Returns:
            취소된 주문 수
        """
        ...
    
    # -------------------------------------------------------------------------
    # 설정
    # -------------------------------------------------------------------------
    
    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """레버리지 설정
        
        Args:
            symbol: 거래 심볼
            leverage: 레버리지 배율 (1~125)
            
        Returns:
            설정 결과
        """
        ...
    
    async def get_exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        """거래소 정보 조회 (심볼 정보, 거래 규칙 등)
        
        Args:
            symbol: 특정 심볼 (None이면 전체)
            
        Returns:
            거래소 정보
        """
        ...


@runtime_checkable
class IExchangeWsClient(Protocol):
    """거래소 WebSocket 클라이언트 인터페이스
    
    User Data Stream을 통해 실시간 계좌/주문/포지션 변경을 수신.
    """
    
    @property
    def state(self) -> WebSocketState:
        """현재 연결 상태"""
        ...
    
    async def start(self) -> None:
        """WebSocket 연결 시작
        
        listenKey 생성 → WebSocket 연결 → 메시지 수신 시작
        """
        ...
    
    async def stop(self) -> None:
        """WebSocket 연결 종료
        
        keepalive 중지 → 연결 종료 → 상태 업데이트
        """
        ...


# WebSocket 콜백 타입 정의
MessageCallback = Callable[[dict[str, Any]], Awaitable[None]]
StateChangeCallback = Callable[[WebSocketState], Awaitable[None]]


@runtime_checkable
class INotifier(Protocol):
    """알림 서비스 인터페이스
    
    거래 알림, 에러 알림 등을 외부 서비스로 전송.
    """
    
    async def send(
        self,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """알림 전송
        
        Args:
            message: 알림 메시지
            level: 알림 레벨 (INFO, WARNING, ERROR, CRITICAL)
            extra: 추가 데이터 (선택)
            
        Returns:
            전송 성공 여부
        """
        ...
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        pnl: str | None = None,
    ) -> bool:
        """거래 알림 전송 (포맷팅된 메시지)
        
        Args:
            symbol: 거래 심볼
            side: 매수/매도
            quantity: 수량
            price: 가격
            pnl: 손익 (선택)
            
        Returns:
            전송 성공 여부
        """
        ...


# 순환 참조 방지를 위한 타입 힌트 (런타임에는 문자열로 유지)
# 실제 타입은 adapters.models에서 정의
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.models import Balance, Position, Order, Trade, OrderRequest
