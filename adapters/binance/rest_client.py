"""
Binance Futures REST API 클라이언트

HMAC-SHA256 서명, Rate Limit 추적, Decimal 사용.
IExchangeRestClient Protocol 준수.
"""

import asyncio
import hashlib
import hmac
import logging
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from adapters.models import Balance, Position, Order, Trade, OrderRequest
from adapters.binance.rate_limiter import (
    RateLimitTracker,
    RateLimitError,
    BinanceApiError,
    OrderError,
)
from adapters.binance.models import (
    parse_balance,
    parse_position,
    parse_order,
    parse_trade,
    is_zero_balance,
    is_zero_position,
)

logger = logging.getLogger(__name__)


class BinanceRestClient:
    """Binance Futures REST API 클라이언트
    
    IExchangeRestClient Protocol 구현.
    모든 금액/수량은 Decimal 타입으로 반환.
    
    Args:
        base_url: REST API 베이스 URL
        api_key: API 키
        api_secret: API 시크릿
        timeout: 요청 타임아웃 (초)
        max_retries: 최대 재시도 횟수 (429 에러 시)
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self.max_retries = max_retries
        
        self.rate_tracker = RateLimitTracker()
        self._client: httpx.AsyncClient | None = None
        self._listen_key: str | None = None
        
        # 서버 시간 동기화용 오프셋 (밀리초)
        self._time_offset: int = 0
        self._time_synced: bool = False
    
    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 가져오기 (lazy initialization)"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _generate_signature(self, query_string: str) -> str:
        """HMAC-SHA256 서명 생성
        
        Args:
            query_string: URL 인코딩된 파라미터 문자열
            
        Returns:
            16진수 서명 문자열
        """
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    
    def _get_timestamp(self) -> int:
        """서버 시간 오프셋이 적용된 타임스탬프 반환 (밀리초)"""
        return int(time.time() * 1000) + self._time_offset
    
    async def sync_time(self) -> int:
        """서버 시간과 동기화
        
        로컬 시간과 서버 시간의 차이를 계산하여 오프셋 저장.
        
        Returns:
            계산된 시간 오프셋 (밀리초)
        """
        local_time = int(time.time() * 1000)
        server_time = await self.get_server_time()
        self._time_offset = server_time - local_time
        self._time_synced = True
        
        logger.info(
            "서버 시간 동기화 완료",
            extra={"offset_ms": self._time_offset},
        )
        
        return self._time_offset
    
    async def _ensure_time_synced(self) -> None:
        """시간 동기화가 필요하면 수행"""
        if not self._time_synced:
            await self.sync_time()
    
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        """API 요청 실행
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, DELETE)
            path: API 경로 (예: /fapi/v1/order)
            params: 요청 파라미터
            signed: 서명 필요 여부
            
        Returns:
            JSON 응답
            
        Raises:
            RateLimitError: 429 응답 시
            BinanceApiError: API 에러 응답 시
        """
        # Rate Limit 체크
        if self.rate_tracker.should_stop:
            logger.warning(
                "Rate limit threshold reached",
                extra={"rate_info": self.rate_tracker.to_dict()},
            )
            raise RateLimitError(
                retry_after=60,
                message="Request weight threshold reached",
            )
        
        # 원본 params 보존 (재시도 시 재사용)
        original_params = dict(params) if params else {}
        headers = {"X-MBX-APIKEY": self.api_key}
        url = f"{self.base_url}{path}"
        client = await self._get_client()
        
        # 재시도 로직
        for attempt in range(self.max_retries):
            # 매 시도마다 params 새로 생성 (타임스탬프 갱신)
            request_params = dict(original_params)
            
            # 서명이 필요한 경우
            if signed:
                # 시간 동기화 확인
                if not self._time_synced:
                    await self._ensure_time_synced()
                
                request_params["timestamp"] = self._get_timestamp()
                request_params["recvWindow"] = 5000
                query_string = urlencode(request_params)
                signature = self._generate_signature(query_string)
                request_params["signature"] = signature
            try:
                response = await client.request(
                    method,
                    url,
                    params=request_params,
                    headers=headers,
                )
                
                # Rate Limit 헤더 추적
                self.rate_tracker.update_from_headers(dict(response.headers))
                
                # 429 처리
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 30))
                    logger.warning(
                        "Rate limited by Binance",
                        extra={"retry_after": retry_after, "attempt": attempt + 1},
                    )
                    
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    
                    raise RateLimitError(retry_after=retry_after)
                
                # 기타 HTTP 에러
                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        code = error_data.get("code", response.status_code)
                        message = error_data.get("msg", response.text)
                    except Exception:
                        code = response.status_code
                        message = response.text
                    
                    # 타임스탬프 오류 시 시간 재동기화 후 재시도
                    if code in (-1021, -1022) and attempt < self.max_retries - 1:
                        logger.warning(
                            "타임스탬프 오류, 시간 재동기화",
                            extra={"code": code, "attempt": attempt + 1},
                        )
                        await self.sync_time()
                        continue
                    
                    raise BinanceApiError(code=code, message=message)
                
                return response.json()
                
            except httpx.TimeoutException as e:
                logger.warning(
                    "Request timeout",
                    extra={"path": path, "attempt": attempt + 1},
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise
            
            except httpx.RequestError as e:
                logger.error(
                    "Request error",
                    extra={"path": path, "error": str(e), "attempt": attempt + 1},
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise
        
        # 모든 재시도 실패
        raise BinanceApiError(code=-1, message="All retries failed")
    
    # -------------------------------------------------------------------------
    # listenKey 관리
    # -------------------------------------------------------------------------
    
    async def create_listen_key(self) -> str:
        """listenKey 생성"""
        data = await self._request("POST", "/fapi/v1/listenKey")
        self._listen_key = data["listenKey"]
        logger.info("listenKey created")
        return self._listen_key
    
    async def extend_listen_key(self) -> None:
        """listenKey 유효기간 연장"""
        await self._request("PUT", "/fapi/v1/listenKey")
        logger.debug("listenKey extended")
    
    async def delete_listen_key(self) -> None:
        """listenKey 삭제"""
        await self._request("DELETE", "/fapi/v1/listenKey")
        self._listen_key = None
        logger.info("listenKey deleted")
    
    # -------------------------------------------------------------------------
    # 계좌 조회
    # -------------------------------------------------------------------------
    
    async def get_balances(self) -> list[Balance]:
        """계좌 잔고 목록 조회 (잔고 > 0인 것만)"""
        data = await self._request("GET", "/fapi/v2/balance", signed=True)
        
        balances = []
        for item in data:
            if not is_zero_balance(item):
                balances.append(parse_balance(item))
        
        return balances
    
    async def get_position(self, symbol: str) -> Position | None:
        """특정 심볼의 포지션 조회"""
        data = await self._request(
            "GET",
            "/fapi/v2/positionRisk",
            params={"symbol": symbol},
            signed=True,
        )
        
        for item in data:
            if item["symbol"] == symbol and not is_zero_position(item):
                return parse_position(item)
        
        return None
    
    async def get_all_positions(self) -> list[Position]:
        """모든 포지션 조회 (포지션 > 0인 것만)"""
        data = await self._request(
            "GET",
            "/fapi/v2/positionRisk",
            signed=True,
        )
        
        positions = []
        for item in data:
            if not is_zero_position(item):
                positions.append(parse_position(item))
        
        return positions
    
    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """오픈 주문 목록 조회"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        data = await self._request(
            "GET",
            "/fapi/v1/openOrders",
            params=params if params else None,
            signed=True,
        )
        
        return [parse_order(item) for item in data]
    
    async def get_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """특정 주문 조회"""
        params: dict[str, Any] = {"symbol": symbol}
        
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("order_id or client_order_id required")
        
        data = await self._request(
            "GET",
            "/fapi/v1/order",
            params=params,
            signed=True,
        )
        
        return parse_order(data)
    
    async def get_trades(
        self,
        symbol: str,
        limit: int = 500,
        start_time: int | None = None,
    ) -> list[Trade]:
        """체결 내역 조회"""
        params: dict[str, Any] = {"symbol": symbol, "limit": min(limit, 1000)}
        
        if start_time:
            params["startTime"] = start_time
        
        data = await self._request(
            "GET",
            "/fapi/v1/userTrades",
            params=params,
            signed=True,
        )
        
        return [parse_trade(item) for item in data]
    
    # -------------------------------------------------------------------------
    # 주문 실행
    # -------------------------------------------------------------------------
    
    async def place_order(self, request: OrderRequest) -> Order:
        """주문 생성"""
        params = request.to_dict()
        
        try:
            data = await self._request(
                "POST",
                "/fapi/v1/order",
                params=params,
                signed=True,
            )
            
            order = parse_order(data)
            logger.info(
                "주문 생성 완료",
                extra={
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "type": order.order_type,
                    "qty": str(order.original_qty),
                },
            )
            return order
            
        except BinanceApiError as e:
            logger.error(
                "주문 생성 실패",
                extra={
                    "error_code": e.code,
                    "error_message": e.message,
                    "request": params,
                },
            )
            raise OrderError(code=e.code, message=e.message)
    
    async def cancel_order(
        self,
        symbol: str,
        order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """주문 취소"""
        params: dict[str, Any] = {"symbol": symbol}
        
        if order_id:
            params["orderId"] = order_id
        elif client_order_id:
            params["origClientOrderId"] = client_order_id
        else:
            raise ValueError("order_id or client_order_id required")
        
        try:
            data = await self._request(
                "DELETE",
                "/fapi/v1/order",
                params=params,
                signed=True,
            )
            
            order = parse_order(data)
            logger.info(
                "주문 취소 완료",
                extra={
                    "order_id": order.order_id,
                    "client_order_id": order.client_order_id,
                },
            )
            return order
            
        except BinanceApiError as e:
            logger.error(
                "주문 취소 실패",
                extra={
                    "error_code": e.code,
                    "error_message": e.message,
                    "symbol": symbol,
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                },
            )
            raise OrderError(code=e.code, message=e.message)
    
    async def cancel_all_orders(self, symbol: str) -> int:
        """특정 심볼의 모든 주문 취소"""
        try:
            data = await self._request(
                "DELETE",
                "/fapi/v1/allOpenOrders",
                params={"symbol": symbol},
                signed=True,
            )
            
            # 응답에서 취소된 주문 수 추출
            # code 200이면 성공, msg에 정보 포함
            if isinstance(data, dict):
                code = data.get("code", 200)
                if code == 200:
                    logger.info(
                        "모든 주문 취소 완료",
                        extra={"symbol": symbol},
                    )
                    return 1  # 성공 시 최소 1 반환
            
            return 0
            
        except BinanceApiError as e:
            logger.error(
                "모든 주문 취소 실패",
                extra={
                    "error_code": e.code,
                    "error_message": e.message,
                    "symbol": symbol,
                },
            )
            raise
    
    # -------------------------------------------------------------------------
    # 설정
    # -------------------------------------------------------------------------
    
    async def set_leverage(self, symbol: str, leverage: int) -> dict[str, Any]:
        """레버리지 설정"""
        data = await self._request(
            "POST",
            "/fapi/v1/leverage",
            params={"symbol": symbol, "leverage": leverage},
            signed=True,
        )
        
        logger.info(
            "레버리지 설정 완료",
            extra={"symbol": symbol, "leverage": leverage},
        )
        
        return data
    
    async def get_exchange_info(self, symbol: str | None = None) -> dict[str, Any]:
        """거래소 정보 조회"""
        data = await self._request("GET", "/fapi/v1/exchangeInfo")
        
        if symbol:
            # 특정 심볼만 필터링
            symbols = [s for s in data.get("symbols", []) if s["symbol"] == symbol]
            return {"symbols": symbols}
        
        return data
    
    async def get_server_time(self) -> int:
        """서버 시간 조회 (밀리초 타임스탬프)"""
        data = await self._request("GET", "/fapi/v1/time")
        return data["serverTime"]
    
    # -------------------------------------------------------------------------
    # 컨텍스트 매니저
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "BinanceRestClient":
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
