"""
Upbit REST API 클라이언트

Upbit API와 통신하는 클라이언트.
JWT 인증, 잔고 조회, 시세 조회, 주문, 출금 기능 제공.

주의: Upbit API는 KRW 마켓 기준으로 시장가 매수 시 'price' 파라미터에 총 금액을 전달해야 함
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from adapters.upbit.models import (
    UpbitAccount,
    UpbitDeposit,
    UpbitOrder,
    UpbitTicker,
    UpbitWithdraw,
)

logger = logging.getLogger(__name__)


class UpbitApiError(Exception):
    """Upbit API 에러"""

    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


class UpbitRestClient:
    """Upbit REST API 클라이언트

    Upbit API와 통신하는 클라이언트.
    모든 API 호출은 JWT 인증을 사용.

    Args:
        api_key: Upbit API 키
        api_secret: Upbit API 시크릿
        timeout: HTTP 요청 타임아웃 (초)

    사용 예시:
    ```python
    client = UpbitRestClient(api_key="xxx", api_secret="xxx")
    accounts = await client.get_accounts()
    ```
    """

    BASE_URL = "https://api.upbit.com/v1"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        timeout: float = 30.0,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 반환 (lazy init)"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _generate_token(self, params: dict[str, Any] | None = None) -> str:
        """JWT 토큰 생성

        Args:
            params: 쿼리 파라미터 (있으면 해시에 포함)

        Returns:
            JWT 토큰 문자열
        """
        payload: dict[str, Any] = {
            "access_key": self.api_key,
            "nonce": str(uuid.uuid4()),
        }

        # 파라미터가 있으면 쿼리 스트링 해시 추가
        if params:
            query_string = urlencode(params)
            m = hashlib.sha512()
            m.update(query_string.encode())
            payload["query_hash"] = m.hexdigest()
            payload["query_hash_alg"] = "SHA512"

        return jwt.encode(payload, self.api_secret, algorithm="HS256")

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        """API 요청 실행

        Args:
            method: HTTP 메서드
            endpoint: API 엔드포인트 (예: /accounts)
            params: 쿼리 파라미터
            body: 요청 본문 (POST용)

        Returns:
            API 응답 JSON

        Raises:
            UpbitApiError: API 에러 발생 시
        """
        client = await self._ensure_client()
        url = f"{self.BASE_URL}{endpoint}"

        # JWT 토큰 생성 (params 또는 body 사용)
        token_params = params or body
        token = self._generate_token(token_params)

        headers = {"Authorization": f"Bearer {token}"}

        try:
            if method == "GET":
                response = await client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = await client.post(url, json=body, headers=headers)
            elif method == "DELETE":
                response = await client.delete(url, params=params, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # 에러 처리
            if response.status_code >= 400:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get("error", {}).get("message", response.text)
                error_code = error_data.get("error", {}).get("name")
                logger.error(
                    f"Upbit API error: {response.status_code} - {error_msg}",
                    extra={"endpoint": endpoint, "error_code": error_code},
                )
                raise UpbitApiError(error_msg, error_code)

            return response.json() if response.content else {}

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e}")
            raise UpbitApiError(str(e))
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise UpbitApiError(str(e))

    # =========================================================================
    # 잔고 조회
    # =========================================================================

    async def get_accounts(self) -> list[UpbitAccount]:
        """전체 계좌 잔고 조회

        Returns:
            계좌 잔고 목록
        """
        data = await self._request("GET", "/accounts")
        return [UpbitAccount.from_api(item) for item in data]

    async def get_account(self, currency: str) -> UpbitAccount | None:
        """특정 자산 잔고 조회

        Args:
            currency: 자산 코드 (예: KRW, TRX)

        Returns:
            계좌 잔고 (없으면 None)
        """
        accounts = await self.get_accounts()
        for account in accounts:
            if account.currency.upper() == currency.upper():
                return account
        return None

    # =========================================================================
    # 시세 조회
    # =========================================================================

    async def get_ticker(self, market: str) -> UpbitTicker:
        """현재가 조회

        Args:
            market: 마켓 코드 (예: KRW-TRX)

        Returns:
            시세 정보
        """
        data = await self._request("GET", "/ticker", params={"markets": market})
        if not data:
            raise UpbitApiError(f"No ticker data for {market}")
        return UpbitTicker.from_api(data[0])

    async def get_trx_price(self) -> Decimal:
        """TRX 현재가 조회 (KRW 기준)

        Returns:
            TRX/KRW 현재가
        """
        ticker = await self.get_ticker("KRW-TRX")
        return ticker.trade_price

    # =========================================================================
    # 입금 내역 조회
    # =========================================================================

    async def get_deposits(
        self,
        currency: str | None = None,
        limit: int = 100,
    ) -> list[UpbitDeposit]:
        """입금 내역 조회

        Args:
            currency: 자산 코드 (선택)
            limit: 조회 개수

        Returns:
            입금 내역 목록
        """
        params: dict[str, Any] = {"limit": limit}
        if currency:
            params["currency"] = currency

        data = await self._request("GET", "/deposits", params=params)
        return [UpbitDeposit.from_api(item) for item in data]

    async def get_krw_deposits(
        self,
        since: datetime | None = None,
    ) -> list[UpbitDeposit]:
        """KRW 입금 내역 조회

        Args:
            since: 이 시각 이후의 입금만 필터링

        Returns:
            KRW 입금 내역 목록
        """
        deposits = await self.get_deposits(currency="KRW")

        if since:
            # UTC로 변환하여 비교
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            deposits = [d for d in deposits if d.created_at >= since]

        return deposits

    # =========================================================================
    # 주문 (매수/매도)
    # =========================================================================

    async def place_market_buy_order(
        self,
        market: str,
        price: Decimal,
    ) -> UpbitOrder:
        """시장가 매수 주문

        Upbit에서 시장가 매수는 '총 금액'을 지정해야 함 (수량 X)

        Args:
            market: 마켓 코드 (예: KRW-TRX)
            price: 매수 총 금액 (KRW)

        Returns:
            주문 정보
        """
        body = {
            "market": market,
            "side": "bid",
            "ord_type": "price",  # 시장가 매수
            "price": str(price),
        }
        data = await self._request("POST", "/orders", body=body)
        return UpbitOrder.from_api(data)

    async def place_market_sell_order(
        self,
        market: str,
        volume: Decimal,
    ) -> UpbitOrder:
        """시장가 매도 주문

        Args:
            market: 마켓 코드 (예: KRW-TRX)
            volume: 매도 수량

        Returns:
            주문 정보
        """
        body = {
            "market": market,
            "side": "ask",
            "ord_type": "market",  # 시장가 매도
            "volume": str(volume),
        }
        data = await self._request("POST", "/orders", body=body)
        return UpbitOrder.from_api(data)

    async def get_order(self, order_id: str) -> UpbitOrder:
        """주문 조회

        Args:
            order_id: 주문 UUID

        Returns:
            주문 정보
        """
        data = await self._request("GET", "/order", params={"uuid": order_id})
        return UpbitOrder.from_api(data)

    async def wait_order_filled(
        self,
        order_id: str,
        timeout: float = 60.0,
        poll_interval: float = 1.0,
    ) -> UpbitOrder:
        """주문 체결 대기

        Args:
            order_id: 주문 UUID
            timeout: 최대 대기 시간 (초)
            poll_interval: 폴링 간격 (초)

        Returns:
            체결된 주문 정보

        Raises:
            UpbitApiError: 타임아웃 또는 주문 취소 시
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()

        while True:
            order = await self.get_order(order_id)

            if order.is_filled:
                return order

            if order.is_cancelled:
                raise UpbitApiError(
                    f"Order {order_id} was cancelled",
                    error_code="ORDER_CANCELLED",
                )

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise UpbitApiError(
                    f"Order {order_id} not filled within {timeout}s",
                    error_code="ORDER_TIMEOUT",
                )

            await asyncio.sleep(poll_interval)

    # =========================================================================
    # 출금
    # =========================================================================

    async def get_withdraw_addresses(self, currency: str) -> list[dict[str, Any]]:
        """출금 가능 주소 목록 조회

        Args:
            currency: 자산 코드

        Returns:
            등록된 출금 주소 목록
        """
        return await self._request(
            "GET",
            "/withdraws/coin/addresses",
            params={"currency": currency},
        )

    async def withdraw_coin(
        self,
        currency: str,
        amount: Decimal,
        address: str,
        secondary_address: str | None = None,
        transaction_type: str = "default",
    ) -> UpbitWithdraw:
        """코인 출금 요청

        Args:
            currency: 자산 코드 (예: TRX)
            amount: 출금 수량
            address: 출금 주소
            secondary_address: 보조 주소 (태그, 메모 등)
            transaction_type: 출금 유형 (default, internal)

        Returns:
            출금 정보
        """
        body: dict[str, Any] = {
            "currency": currency,
            "amount": str(amount),
            "address": address,
            "transaction_type": transaction_type,
        }

        if secondary_address:
            body["secondary_address"] = secondary_address

        data = await self._request("POST", "/withdraws/coin", body=body)
        return UpbitWithdraw.from_api(data)

    async def get_withdraw(self, withdraw_id: str) -> UpbitWithdraw:
        """출금 상태 조회

        Args:
            withdraw_id: 출금 UUID

        Returns:
            출금 정보
        """
        data = await self._request("GET", "/withdraw", params={"uuid": withdraw_id})
        return UpbitWithdraw.from_api(data)

    async def get_withdraws(
        self,
        currency: str | None = None,
        limit: int = 100,
    ) -> list[UpbitWithdraw]:
        """출금 내역 조회

        Args:
            currency: 자산 코드 (선택)
            limit: 조회 개수

        Returns:
            출금 내역 목록
        """
        params: dict[str, Any] = {"limit": limit}
        if currency:
            params["currency"] = currency

        data = await self._request("GET", "/withdraws", params=params)
        return [UpbitWithdraw.from_api(item) for item in data]

    async def wait_withdraw_done(
        self,
        withdraw_id: str,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
    ) -> UpbitWithdraw:
        """출금 완료 대기

        블록체인 전송은 시간이 걸리므로 긴 타임아웃 사용

        Args:
            withdraw_id: 출금 UUID
            timeout: 최대 대기 시간 (초, 기본 10분)
            poll_interval: 폴링 간격 (초)

        Returns:
            완료된 출금 정보

        Raises:
            UpbitApiError: 타임아웃 또는 출금 실패 시
        """
        import asyncio

        start_time = asyncio.get_event_loop().time()

        while True:
            withdraw = await self.get_withdraw(withdraw_id)

            if withdraw.is_done:
                return withdraw

            if withdraw.is_failed:
                raise UpbitApiError(
                    f"Withdraw {withdraw_id} failed: {withdraw.state}",
                    error_code="WITHDRAW_FAILED",
                )

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise UpbitApiError(
                    f"Withdraw {withdraw_id} not done within {timeout}s",
                    error_code="WITHDRAW_TIMEOUT",
                )

            await asyncio.sleep(poll_interval)

    # =========================================================================
    # 입출금 상태 조회 (종합)
    # =========================================================================

    async def get_deposit_status(self) -> dict[str, Any]:
        """입금 가능 상태 조회

        KRW, TRX 잔고와 TRX 시세를 조합하여 입금 가능 여부 판단

        Returns:
            입금 상태 정보 딕셔너리
        """
        # 잔고 조회
        krw_account = await self.get_account("KRW")
        trx_account = await self.get_account("TRX")

        krw_balance = krw_account.balance if krw_account else Decimal("0")
        trx_balance = trx_account.balance if trx_account else Decimal("0")

        # TRX 시세 조회
        trx_price = await self.get_trx_price()
        trx_value_krw = trx_balance * trx_price

        # TRX 출금 수수료 (1 TRX)
        trx_fee = Decimal("1")
        trx_fee_krw = trx_fee * trx_price

        # 입금 가능 여부 판단
        # 조건: KRW >= 5000 AND (TRX >= 1 OR KRW로 1TRX 수수료 커버 가능)
        min_deposit_krw = Decimal("5000")
        has_enough_krw = krw_balance >= min_deposit_krw
        has_enough_trx_fee = trx_balance >= trx_fee
        can_buy_trx_fee = (krw_balance - min_deposit_krw) >= trx_fee_krw

        can_deposit = has_enough_krw and (has_enough_trx_fee or can_buy_trx_fee)

        return {
            "can_deposit": can_deposit,
            "krw_balance": str(krw_balance),
            "trx_balance": str(trx_balance),
            "trx_price_krw": str(trx_price),
            "trx_value_krw": str(trx_value_krw),
            "fee_trx": str(trx_fee),
            "fee_krw": str(trx_fee_krw),
            "min_deposit_krw": str(min_deposit_krw),
            "has_enough_krw": has_enough_krw,
            "has_enough_trx_fee": has_enough_trx_fee,
        }
