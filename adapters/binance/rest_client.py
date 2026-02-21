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
    # 시장 데이터
    # -------------------------------------------------------------------------
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = "5m",
        limit: int = 100,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """캔들스틱(Kline) 데이터 조회
        
        Args:
            symbol: 거래 심볼 (예: XRPUSDT)
            interval: 시간 간격 (1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M)
            limit: 조회 개수 (기본 100, 최대 1500)
            start_time: 시작 시간 (밀리초 타임스탬프)
            end_time: 종료 시간 (밀리초 타임스탬프)
            
        Returns:
            캔들스틱 데이터 리스트
            각 항목: {
                "open_time": int,      # 시작 시간 (ms)
                "open": str,           # 시가
                "high": str,           # 고가
                "low": str,            # 저가
                "close": str,          # 종가
                "volume": str,         # 거래량
                "close_time": int,     # 종료 시간 (ms)
                "quote_volume": str,   # 거래대금
                "trades": int,         # 거래 횟수
                "taker_buy_volume": str,      # Taker 매수 거래량
                "taker_buy_quote_volume": str # Taker 매수 거래대금
            }
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1500),
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._request("GET", "/fapi/v1/klines", params=params)
        
        # Binance klines 응답 포맷:
        # [
        #   [open_time, open, high, low, close, volume, close_time, 
        #    quote_volume, trades, taker_buy_volume, taker_buy_quote_volume, ignore]
        # ]
        klines = []
        for item in data:
            klines.append({
                "open_time": item[0],
                "open": item[1],
                "high": item[2],
                "low": item[3],
                "close": item[4],
                "volume": item[5],
                "close_time": item[6],
                "quote_volume": item[7],
                "trades": item[8],
                "taker_buy_volume": item[9],
                "taker_buy_quote_volume": item[10],
            })
        
        return klines
    
    async def get_ticker_price(self, symbol: str | None = None) -> dict[str, str] | list[dict[str, str]]:
        """현재가 조회
        
        Args:
            symbol: 거래 심볼 (None이면 전체)
            
        Returns:
            심볼 지정 시: {"symbol": "XRPUSDT", "price": "0.5123"}
            전체 조회 시: [{"symbol": "...", "price": "..."}, ...]
        """
        params = {"symbol": symbol} if symbol else None
        data = await self._request("GET", "/fapi/v1/ticker/price", params=params)
        return data
    
    # -------------------------------------------------------------------------
    # Spot API (입출금용)
    # -------------------------------------------------------------------------
    
    async def _spot_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        """Spot/SAPI 요청 실행 (base_url 무시, api.binance.com 사용)
        
        Args:
            method: HTTP 메서드
            path: API 경로 (예: /api/v3/account, /sapi/v1/asset/transfer)
            params: 요청 파라미터
            signed: 서명 필요 여부
            
        Returns:
            JSON 응답
        """
        # Spot API는 항상 production URL 사용
        # (testnet은 Spot 기능 제한적)
        spot_base_url = "https://api.binance.com"
        
        original_params = dict(params) if params else {}
        headers = {"X-MBX-APIKEY": self.api_key}
        url = f"{spot_base_url}{path}"
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            request_params = dict(original_params)
            
            if signed:
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
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 30))
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(retry_after=retry_after)
                
                if response.status_code >= 400:
                    try:
                        error_data = response.json()
                        code = error_data.get("code", response.status_code)
                        message = error_data.get("msg", response.text)
                    except Exception:
                        code = response.status_code
                        message = response.text
                    
                    if code in (-1021, -1022) and attempt < self.max_retries - 1:
                        await self.sync_time()
                        continue
                    
                    raise BinanceApiError(code=code, message=message)
                
                return response.json()
                
            except httpx.TimeoutException:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise
            except httpx.RequestError:
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
                raise
        
        raise BinanceApiError(code=-1, message="All retries failed")
    
    async def get_spot_balances(self) -> dict[str, dict[str, str]]:
        """Spot 계좌 잔고 조회
        
        Returns:
            자산별 잔고 딕셔너리: {"USDT": {"free": "100.0", "locked": "0"}, ...}
        """
        data = await self._spot_request(
            "GET",
            "/api/v3/account",
            signed=True,
        )
        
        balances = {}
        for item in data.get("balances", []):
            free = item.get("free", "0")
            locked = item.get("locked", "0")
            # 잔고가 있는 것만 반환
            if float(free) > 0 or float(locked) > 0:
                balances[item["asset"]] = {
                    "free": free,
                    "locked": locked,
                }
        
        return balances
    
    async def get_spot_balance(self, asset: str) -> dict[str, str]:
        """특정 자산의 Spot 잔고 조회
        
        Args:
            asset: 자산 코드 (예: TRX, USDT)
            
        Returns:
            {"free": "100.0", "locked": "0"}
        """
        balances = await self.get_spot_balances()
        return balances.get(asset.upper(), {"free": "0", "locked": "0"})
    
    async def spot_market_buy(
        self,
        symbol: str,
        quote_qty: str,
    ) -> dict[str, Any]:
        """Spot 시장가 매수 (USDT로 코인 매수)
        
        Args:
            symbol: 심볼 (예: TRXUSDT)
            quote_qty: 사용할 USDT 금액
            
        Returns:
            주문 결과
        """
        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quoteOrderQty": quote_qty,
        }
        
        data = await self._spot_request(
            "POST",
            "/api/v3/order",
            params=params,
            signed=True,
        )
        
        logger.info(
            "Spot 시장가 매수 완료",
            extra={
                "symbol": symbol,
                "quote_qty": quote_qty,
                "executed_qty": data.get("executedQty"),
            },
        )
        
        return data
    
    async def spot_market_sell(
        self,
        symbol: str,
        quantity: str,
    ) -> dict[str, Any]:
        """Spot 시장가 매도 (코인을 USDT로 환전)
        
        Args:
            symbol: 심볼 (예: TRXUSDT)
            quantity: 매도 수량
            
        Returns:
            주문 결과
        """
        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": quantity,
        }
        
        data = await self._spot_request(
            "POST",
            "/api/v3/order",
            params=params,
            signed=True,
        )
        
        logger.info(
            "Spot 시장가 매도 완료",
            extra={
                "symbol": symbol,
                "quantity": quantity,
                "executed_qty": data.get("executedQty"),
            },
        )
        
        return data
    
    async def internal_transfer(
        self,
        asset: str,
        amount: str,
        from_account: str,
        to_account: str,
    ) -> dict[str, Any]:
        """내부 이체 (Spot ↔ Futures)
        
        Args:
            asset: 자산 코드 (예: USDT)
            amount: 이체 금액
            from_account: 출발 계좌 (SPOT, FUTURES, COIN_FUTURE, MARGIN, ...)
            to_account: 도착 계좌
            
        Returns:
            이체 결과 {"tranId": 123456789}
        """
        # 이체 타입 매핑
        # Spot -> Futures: type=1
        # Futures -> Spot: type=2
        type_mapping = {
            ("SPOT", "FUTURES"): "MAIN_UMFUTURE",
            ("SPOT", "UMFUTURE"): "MAIN_UMFUTURE",
            ("FUTURES", "SPOT"): "UMFUTURE_MAIN",
            ("UMFUTURE", "SPOT"): "UMFUTURE_MAIN",
            ("UMFUTURE", "MAIN"): "UMFUTURE_MAIN",
            ("MAIN", "UMFUTURE"): "MAIN_UMFUTURE",
        }
        
        transfer_type = type_mapping.get(
            (from_account.upper(), to_account.upper())
        )
        
        if not transfer_type:
            raise ValueError(
                f"Unsupported transfer: {from_account} -> {to_account}"
            )
        
        params = {
            "type": transfer_type,
            "asset": asset.upper(),
            "amount": amount,
        }
        
        data = await self._spot_request(
            "POST",
            "/sapi/v1/asset/transfer",
            params=params,
            signed=True,
        )
        
        logger.info(
            "내부 이체 완료",
            extra={
                "asset": asset,
                "amount": amount,
                "from": from_account,
                "to": to_account,
                "tran_id": data.get("tranId"),
            },
        )
        
        return data
    
    async def withdraw_coin(
        self,
        coin: str,
        address: str,
        amount: str,
        network: str | None = None,
        address_tag: str | None = None,
    ) -> dict[str, Any]:
        """코인 출금 요청
        
        Args:
            coin: 코인 코드 (예: TRX)
            address: 출금 주소
            amount: 출금 금액
            network: 네트워크 (예: TRX, ETH, BSC)
            address_tag: 메모/태그 (필요한 경우)
            
        Returns:
            출금 결과 {"id": "xxx"}
        """
        params: dict[str, Any] = {
            "coin": coin.upper(),
            "address": address,
            "amount": amount,
        }
        
        if network:
            params["network"] = network
        if address_tag:
            params["addressTag"] = address_tag
        
        data = await self._spot_request(
            "POST",
            "/sapi/v1/capital/withdraw/apply",
            params=params,
            signed=True,
        )
        
        logger.info(
            "코인 출금 요청 완료",
            extra={
                "coin": coin,
                "address": address,
                "amount": amount,
                "withdraw_id": data.get("id"),
            },
        )
        
        return data
    
    async def get_deposit_history(
        self,
        coin: str | None = None,
        status: int | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """입금 내역 조회
        
        Args:
            coin: 코인 코드 (선택)
            status: 상태 필터 (0:pending, 6:credited, 1:success)
            start_time: 시작 시간 (밀리초)
            end_time: 종료 시간 (밀리초)
            limit: 조회 개수
            
        Returns:
            입금 내역 리스트
        """
        params: dict[str, Any] = {"limit": limit}
        
        if coin:
            params["coin"] = coin.upper()
        if status is not None:
            params["status"] = status
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/capital/deposit/hisrec",
            params=params,
            signed=True,
        )
        
        return data
    
    async def get_withdraw_history(
        self,
        coin: str | None = None,
        status: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """출금 내역 조회
        
        Args:
            coin: 코인 코드 (선택)
            status: 상태 필터 (0:email sent, 1:cancelled, 2:awaiting, 
                    3:rejected, 4:processing, 5:failure, 6:completed)
            limit: 조회 개수
            
        Returns:
            출금 내역 리스트
        """
        params: dict[str, Any] = {"limit": limit}
        
        if coin:
            params["coin"] = coin.upper()
        if status is not None:
            params["status"] = status
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/capital/withdraw/history",
            params=params,
            signed=True,
        )
        
        return data
    
    async def wait_deposit_confirmed(
        self,
        coin: str,
        min_amount: float,
        timeout: float = 600.0,
        poll_interval: float = 30.0,
    ) -> dict[str, Any] | None:
        """입금 확인 대기
        
        특정 코인의 입금이 확인될 때까지 대기.
        
        Args:
            coin: 코인 코드
            min_amount: 최소 입금 금액
            timeout: 최대 대기 시간 (초)
            poll_interval: 폴링 간격 (초)
            
        Returns:
            입금 정보 또는 None (타임아웃)
        """
        start_time = int(time.time() * 1000) - 60000  # 1분 전부터
        
        elapsed = 0.0
        while elapsed < timeout:
            deposits = await self.get_deposit_history(
                coin=coin,
                status=1,  # success
                start_time=start_time,
            )
            
            # min_amount 이상인 입금 찾기
            for deposit in deposits:
                amount = float(deposit.get("amount", 0))
                if amount >= min_amount:
                    logger.info(
                        "입금 확인됨",
                        extra={
                            "coin": coin,
                            "amount": amount,
                            "txId": deposit.get("txId"),
                        },
                    )
                    return deposit
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        logger.warning(
            "입금 대기 타임아웃",
            extra={"coin": coin, "timeout": timeout},
        )
        return None
    
    # -------------------------------------------------------------------------
    # 과거 데이터 복구용 API
    # -------------------------------------------------------------------------
    
    async def get_account_snapshot(
        self,
        account_type: str,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 7,
    ) -> dict[str, Any]:
        """Daily Account Snapshot 조회
        
        일별 계좌 스냅샷을 조회합니다. 과거 특정 날짜의 자산 상태 확인용.
        
        Args:
            account_type: 계좌 유형 ("SPOT", "MARGIN", "FUTURES")
            start_time: 조회 시작 시간 (밀리초 타임스탬프)
            end_time: 조회 종료 시간 (밀리초 타임스탬프)
            limit: 조회 개수 (7-30, 기본 7)
            
        Returns:
            스냅샷 응답:
            {
                "code": 200,
                "msg": "",
                "snapshotVos": [
                    {
                        "type": "spot|futures",
                        "updateTime": 1576281599000,
                        "data": {...}
                    }
                ]
            }
            
        Note:
            - Weight: 2400 (매우 높음)
            - 최대 30일 전까지만 조회 가능
            - 초기화 시 1회만 호출 권장
        """
        params: dict[str, Any] = {
            "type": account_type.upper(),
            "limit": min(max(limit, 7), 30),
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/accountSnapshot",
            params=params,
            signed=True,
        )
        
        return data
    
    async def get_income_history(
        self,
        symbol: str | None = None,
        income_type: str | None = None,
        start_time: int | None = None,
        end_time: int | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Futures Income History 조회
        
        손익, 수수료, 펀딩비 등 모든 수익/비용 이력을 조회합니다.
        
        Args:
            symbol: 특정 심볼 필터 (선택)
            income_type: 수익 유형 필터 (선택)
                - TRANSFER: 내부 이체
                - REALIZED_PNL: 실현 손익
                - FUNDING_FEE: 펀딩비
                - COMMISSION: 거래 수수료
                - COMMISSION_REBATE: 수수료 리베이트
            start_time: 조회 시작 시간 (밀리초 타임스탬프)
            end_time: 조회 종료 시간 (밀리초 타임스탬프)
            limit: 조회 개수 (기본 100, 최대 1000)
            
        Returns:
            Income 이력 리스트:
            [
                {
                    "symbol": "BTCUSDT",
                    "incomeType": "REALIZED_PNL",
                    "income": "1.23456789",
                    "asset": "USDT",
                    "info": "",
                    "time": 1570636800000,
                    "tranId": 9689322392,
                    "tradeId": ""
                }
            ]
            
        Note:
            - Weight: 100 (IP)
            - 페이지네이션: startTime 기준 limit건 반환
        """
        params: dict[str, Any] = {
            "limit": min(limit, 1000),
        }
        
        if symbol:
            params["symbol"] = symbol
        if income_type:
            params["incomeType"] = income_type
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._request(
            "GET",
            "/fapi/v1/income",
            params=params,
            signed=True,
        )
        
        return data
    
    async def get_transfer_history(
        self,
        transfer_type: str,
        start_time: int | None = None,
        end_time: int | None = None,
        current: int = 1,
        size: int = 100,
    ) -> dict[str, Any]:
        """SPOT ↔ FUTURES 이체 이력 조회
        
        Args:
            transfer_type: 이체 유형
                - MAIN_UMFUTURE: SPOT → USDT-M Futures
                - UMFUTURE_MAIN: USDT-M Futures → SPOT
            start_time: 조회 시작 시간 (밀리초 타임스탬프)
            end_time: 조회 종료 시간 (밀리초 타임스탬프)
            current: 페이지 번호 (기본 1)
            size: 페이지 크기 (기본 10, 최대 100)
            
        Returns:
            이체 이력:
            {
                "total": 2,
                "rows": [
                    {
                        "asset": "USDT",
                        "amount": "100.00000000",
                        "type": "MAIN_UMFUTURE",
                        "status": "CONFIRMED",
                        "tranId": 11415955596,
                        "timestamp": 1544433328000
                    }
                ]
            }
            
        Note:
            - Weight: 1 (IP)
            - 최대 6개월 전까지 조회 가능
            - startTime/endTime 미지정 시 최근 7일 반환
        """
        params: dict[str, Any] = {
            "type": transfer_type,
            "current": current,
            "size": min(size, 100),
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/asset/transfer",
            params=params,
            signed=True,
        )
        
        return data
    
    async def get_convert_history(
        self,
        start_time: int,
        end_time: int,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Convert(간편 전환) 거래 이력 조회
        
        Args:
            start_time: 조회 시작 시간 (밀리초 타임스탬프, 필수)
            end_time: 조회 종료 시간 (밀리초 타임스탬프, 필수)
            limit: 조회 개수 (기본 100, 최대 1000)
            
        Returns:
            Convert 거래 이력:
            {
                "list": [
                    {
                        "quoteId": "f3b91c525b2644c7bc1e1cd31b6e1aa6",
                        "orderId": 940708407462087195,
                        "orderStatus": "SUCCESS",
                        "fromAsset": "USDT",
                        "fromAmount": "100.00000000",
                        "toAsset": "BNB",
                        "toAmount": "0.38500000",
                        "ratio": "0.00385000",
                        "inverseRatio": "259.74025974",
                        "createTime": 1623381330000
                    }
                ],
                "startTime": 1623381330000,
                "endTime": 1623470000000,
                "limit": 100,
                "moreData": false
            }
            
        Note:
            - Weight: 3000 (UID) - 높음
            - startTime, endTime 모두 필수
            - 조회 간격 최대 30일
        """
        params: dict[str, Any] = {
            "startTime": start_time,
            "endTime": end_time,
            "limit": min(limit, 1000),
        }
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/convert/tradeFlow",
            params=params,
            signed=True,
        )
        
        return data
    
    async def get_dust_log(
        self,
        account_type: str = "SPOT",
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, Any]:
        """Dust(소액 자산) → BNB 전환 이력 조회
        
        Args:
            account_type: 계좌 유형 ("SPOT" 또는 "MARGIN", 기본 SPOT)
            start_time: 조회 시작 시간 (밀리초 타임스탬프)
            end_time: 조회 종료 시간 (밀리초 타임스탬프)
            
        Returns:
            Dust 전환 이력:
            {
                "total": 8,
                "userAssetDribblets": [
                    {
                        "operateTime": 1615985535000,
                        "totalTransferedAmount": "0.00132256",
                        "totalServiceChargeAmount": "0.00002654",
                        "transId": 45178372831,
                        "userAssetDribbletDetails": [
                            {
                                "transId": 4359321,
                                "serviceChargeAmount": "0.000009",
                                "amount": "0.0009",
                                "operateTime": 1615985535000,
                                "transferedAmount": "0.000441",
                                "fromAsset": "ATOM"
                            }
                        ]
                    }
                ]
            }
            
        Note:
            - Weight: 1 (IP)
            - 2020/12/01 이후 기록만 반환
            - 최근 100건만 반환
        """
        params: dict[str, Any] = {
            "accountType": account_type.upper(),
        }
        
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        
        data = await self._spot_request(
            "GET",
            "/sapi/v1/asset/dribblet",
            params=params,
            signed=True,
        )
        
        return data
    
    # -------------------------------------------------------------------------
    # 컨텍스트 매니저
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "BinanceRestClient":
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
