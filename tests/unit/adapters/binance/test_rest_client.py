"""
Binance REST 클라이언트 테스트

BinanceRestClient HTTP 요청 테스트 (httpx mock 사용).
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.rate_limiter import RateLimitError, BinanceApiError, OrderError
from adapters.models import OrderRequest


class TestBinanceRestClientSignature:
    """서명 생성 테스트"""
    
    def test_generate_signature(self) -> None:
        """HMAC-SHA256 서명 생성"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_api_key",
            api_secret="test_secret_key",
        )
        
        query_string = "symbol=XRPUSDT&timestamp=1234567890"
        signature = client._generate_signature(query_string)
        
        # 서명은 64자 hex 문자열
        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)
    
    def test_signature_consistency(self) -> None:
        """동일 입력에 대해 동일 서명"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_api_key",
            api_secret="test_secret_key",
        )
        
        query_string = "test=value"
        sig1 = client._generate_signature(query_string)
        sig2 = client._generate_signature(query_string)
        
        assert sig1 == sig2
    
    def test_different_input_different_signature(self) -> None:
        """다른 입력에 대해 다른 서명"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_api_key",
            api_secret="test_secret_key",
        )
        
        sig1 = client._generate_signature("input1")
        sig2 = client._generate_signature("input2")
        
        assert sig1 != sig2


class TestBinanceRestClientListenKey:
    """listenKey 관리 테스트"""
    
    @pytest.mark.asyncio
    async def test_create_listen_key_success(self) -> None:
        """listenKey 생성 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        # HTTP 응답 모킹
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"listenKey": "test_listen_key_12345"}
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            listen_key = await client.create_listen_key()
            
            assert listen_key == "test_listen_key_12345"
            assert client._listen_key == "test_listen_key_12345"
    
    @pytest.mark.asyncio
    async def test_extend_listen_key_success(self) -> None:
        """listenKey 갱신 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            # 에러 없이 완료
            await client.extend_listen_key()


class TestBinanceRestClientBalances:
    """잔고 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_balances_returns_decimal(
        self,
        binance_balance_response: dict,
    ) -> None:
        """잔고 조회 - Decimal 반환 확인"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        # 시간 동기화 건너뛰기 (테스트용)
        client._time_synced = True
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [binance_balance_response]
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            balances = await client.get_balances()
            
            assert len(balances) == 1
            assert isinstance(balances[0].wallet_balance, Decimal)
            assert balances[0].asset == "USDT"
    
    @pytest.mark.asyncio
    async def test_get_balances_filters_zero(self) -> None:
        """잔고 조회 - 0 잔고 필터링"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        # 시간 동기화 건너뛰기 (테스트용)
        client._time_synced = True
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"asset": "USDT", "balance": "100", "availableBalance": "100"},
            {"asset": "BTC", "balance": "0", "availableBalance": "0"},
        ]
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            balances = await client.get_balances()
            
            # 0 잔고인 BTC는 제외
            assert len(balances) == 1
            assert balances[0].asset == "USDT"


class TestBinanceRestClientOrders:
    """주문 관련 테스트"""
    
    @pytest.mark.asyncio
    async def test_place_order_with_client_order_id(
        self,
        binance_order_response: dict,
    ) -> None:
        """주문 생성 - client_order_id 전달"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        # 시간 동기화 건너뛰기 (테스트용)
        client._time_synced = True
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = binance_order_response
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            request = OrderRequest.market(
                symbol="XRPUSDT",
                side="BUY",
                quantity=Decimal("100"),
                client_order_id="ae-test-order-001",
            )
            
            order = await client.place_order(request)
            
            assert order.client_order_id == "ae-test-order-001"
    
    @pytest.mark.asyncio
    async def test_place_order_api_error(self) -> None:
        """주문 생성 - API 에러"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "code": -2010,
            "msg": "Order would immediately match",
        }
        mock_response.headers = {}
        mock_response.text = '{"code": -2010, "msg": "Order would immediately match"}'
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            request = OrderRequest.market(
                symbol="XRPUSDT",
                side="BUY",
                quantity=Decimal("100"),
            )
            
            with pytest.raises(OrderError) as exc_info:
                await client.place_order(request)
            
            assert exc_info.value.code == -2010


class TestBinanceRestClientRateLimit:
    """Rate Limit 테스트"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_429_retry(self) -> None:
        """429 에러 시 재시도"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
            max_retries=2,
        )
        
        # 첫 번째 응답: 429
        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {"Retry-After": "1"}
        
        # 두 번째 응답: 성공
        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"serverTime": 1234567890}
        mock_response_ok.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.side_effect = [
                mock_response_429,
                mock_response_ok,
            ]
            mock_get_client.return_value = mock_http_client
            
            # 재시도 후 성공
            result = await client.get_server_time()
            
            assert result == 1234567890
            assert mock_http_client.request.call_count == 2
    
    @pytest.mark.asyncio
    async def test_rate_limit_updates_tracker(self) -> None:
        """응답 헤더에서 Rate Limit 정보 추적"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"serverTime": 1234567890}
        mock_response.headers = {
            "X-MBX-USED-WEIGHT-1m": "500",
            "X-MBX-ORDER-COUNT-1m": "10",
        }
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            await client.get_server_time()
            
            # Rate tracker 업데이트 확인
            assert client.rate_tracker.used_weight_1m == 500
            assert client.rate_tracker.order_count_1m == 10
    
    @pytest.mark.asyncio
    async def test_rate_limit_threshold_blocks_request(self) -> None:
        """임계값 초과 시 요청 차단"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        # 임계값 초과 설정
        client.rate_tracker.used_weight_1m = 3000  # WEIGHT_STOP 이상
        
        with pytest.raises(RateLimitError):
            await client.get_server_time()


class TestBinanceRestClientContextManager:
    """컨텍스트 매니저 테스트"""
    
    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self) -> None:
        """컨텍스트 매니저 종료 시 클라이언트 닫힘"""
        async with BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        ) as client:
            assert client is not None
        
        # 종료 후 클라이언트 None 확인
        assert client._client is None


class TestBinanceRestClientKlines:
    """Klines(캔들) 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_klines_success(self) -> None:
        """캔들 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        # Binance klines 응답 형식
        mock_kline_data = [
            [
                1640000000000,  # open_time
                "0.5000",       # open
                "0.5100",       # high
                "0.4900",       # low
                "0.5050",       # close
                "1000000",      # volume
                1640000299999,  # close_time
                "500000",       # quote_volume
                1000,           # trades
                "600000",       # taker_buy_volume
                "300000",       # taker_buy_quote_volume
                "0",            # ignore
            ],
        ]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_kline_data
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            klines = await client.get_klines(symbol="XRPUSDT", interval="5m", limit=100)
            
            assert len(klines) == 1
            assert klines[0]["open_time"] == 1640000000000
            assert klines[0]["open"] == "0.5000"
            assert klines[0]["high"] == "0.5100"
            assert klines[0]["low"] == "0.4900"
            assert klines[0]["close"] == "0.5050"
            assert klines[0]["volume"] == "1000000"
    
    @pytest.mark.asyncio
    async def test_get_klines_with_time_params(self) -> None:
        """시간 파라미터 전달 확인"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            await client.get_klines(
                symbol="XRPUSDT",
                interval="1h",
                limit=500,
                start_time=1640000000000,
                end_time=1640100000000,
            )
            
            # 요청 파라미터 확인
            call_args = mock_http_client.request.call_args
            params = call_args.kwargs["params"]
            
            assert params["symbol"] == "XRPUSDT"
            assert params["interval"] == "1h"
            assert params["limit"] == 500
            assert params["startTime"] == 1640000000000
            assert params["endTime"] == 1640100000000
    
    @pytest.mark.asyncio
    async def test_get_ticker_price_success(self) -> None:
        """현재가 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"symbol": "XRPUSDT", "price": "0.5123"}
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_ticker_price(symbol="XRPUSDT")
            
            assert result["symbol"] == "XRPUSDT"
            assert result["price"] == "0.5123"


class TestBinanceRestClientAccountSnapshot:
    """Daily Account Snapshot 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_account_snapshot_spot_success(self) -> None:
        """SPOT 계좌 스냅샷 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_snapshot_response = {
            "code": 200,
            "msg": "",
            "snapshotVos": [
                {
                    "type": "spot",
                    "updateTime": 1576281599000,
                    "data": {
                        "totalAssetOfBtc": "0.09942700",
                        "balances": [
                            {"asset": "USDT", "free": "100.50", "locked": "0"},
                            {"asset": "BNB", "free": "1.5", "locked": "0"},
                        ]
                    }
                }
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_snapshot_response
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_account_snapshot(account_type="SPOT", limit=7)
            
            assert result["code"] == 200
            assert len(result["snapshotVos"]) == 1
            assert result["snapshotVos"][0]["type"] == "spot"
            
            balances = result["snapshotVos"][0]["data"]["balances"]
            assert len(balances) == 2
            assert balances[0]["asset"] == "USDT"
    
    @pytest.mark.asyncio
    async def test_get_account_snapshot_futures_success(self) -> None:
        """FUTURES 계좌 스냅샷 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_snapshot_response = {
            "code": 200,
            "msg": "",
            "snapshotVos": [
                {
                    "type": "futures",
                    "updateTime": 1576281599000,
                    "data": {
                        "assets": [
                            {
                                "asset": "USDT",
                                "marginBalance": "118.99782335",
                                "walletBalance": "120.23811389"
                            }
                        ],
                        "position": []
                    }
                }
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_snapshot_response
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_account_snapshot(
                account_type="FUTURES",
                start_time=1576000000000,
                end_time=1576300000000,
            )
            
            assert result["code"] == 200
            assets = result["snapshotVos"][0]["data"]["assets"]
            assert assets[0]["walletBalance"] == "120.23811389"


class TestBinanceRestClientIncomeHistory:
    """Income History 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_income_history_success(self) -> None:
        """Income History 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_income_data = [
            {
                "symbol": "BTCUSDT",
                "incomeType": "REALIZED_PNL",
                "income": "1.23456789",
                "asset": "USDT",
                "info": "",
                "time": 1570636800000,
                "tranId": 9689322392,
                "tradeId": ""
            },
            {
                "symbol": "BTCUSDT",
                "incomeType": "FUNDING_FEE",
                "income": "-0.01234567",
                "asset": "USDT",
                "info": "",
                "time": 1570665600000,
                "tranId": 9689322393,
                "tradeId": ""
            },
        ]
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_income_data
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_income_history(limit=100)
            
            assert len(result) == 2
            assert result[0]["incomeType"] == "REALIZED_PNL"
            assert result[1]["incomeType"] == "FUNDING_FEE"
    
    @pytest.mark.asyncio
    async def test_get_income_history_with_filters(self) -> None:
        """Income History 필터 파라미터 전달 확인"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            await client.get_income_history(
                symbol="XRPUSDT",
                income_type="FUNDING_FEE",
                start_time=1640000000000,
                end_time=1640100000000,
                limit=500,
            )
            
            call_args = mock_http_client.request.call_args
            params = call_args.kwargs["params"]
            
            assert params["symbol"] == "XRPUSDT"
            assert params["incomeType"] == "FUNDING_FEE"
            assert params["startTime"] == 1640000000000
            assert params["endTime"] == 1640100000000
            assert params["limit"] == 500


class TestBinanceRestClientTransferHistory:
    """Transfer History 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_transfer_history_success(self) -> None:
        """Transfer History 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_transfer_data = {
            "total": 2,
            "rows": [
                {
                    "asset": "USDT",
                    "amount": "100.00000000",
                    "type": "MAIN_UMFUTURE",
                    "status": "CONFIRMED",
                    "tranId": 11415955596,
                    "timestamp": 1544433328000
                },
                {
                    "asset": "USDT",
                    "amount": "50.00000000",
                    "type": "UMFUTURE_MAIN",
                    "status": "CONFIRMED",
                    "tranId": 11415955597,
                    "timestamp": 1544433329000
                }
            ]
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_transfer_data
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_transfer_history(
                transfer_type="MAIN_UMFUTURE",
                size=100,
            )
            
            assert result["total"] == 2
            assert len(result["rows"]) == 2
            assert result["rows"][0]["type"] == "MAIN_UMFUTURE"


class TestBinanceRestClientConvertHistory:
    """Convert Trade History 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_convert_history_success(self) -> None:
        """Convert History 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_convert_data = {
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
            "moreData": False
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_convert_data
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_convert_history(
                start_time=1623381330000,
                end_time=1623470000000,
            )
            
            assert len(result["list"]) == 1
            convert = result["list"][0]
            assert convert["fromAsset"] == "USDT"
            assert convert["toAsset"] == "BNB"
            assert convert["orderStatus"] == "SUCCESS"


class TestBinanceRestClientDustLog:
    """Dust Log 조회 테스트"""
    
    @pytest.mark.asyncio
    async def test_get_dust_log_success(self) -> None:
        """Dust Log 조회 성공"""
        client = BinanceRestClient(
            base_url="https://fapi.binance.com",
            api_key="test_key",
            api_secret="test_secret",
        )
        client._time_synced = True
        
        mock_dust_data = {
            "total": 1,
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
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_dust_data
        mock_response.headers = {}
        
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http_client = AsyncMock()
            mock_http_client.request.return_value = mock_response
            mock_get_client.return_value = mock_http_client
            
            result = await client.get_dust_log()
            
            assert result["total"] == 1
            dribblet = result["userAssetDribblets"][0]
            assert dribblet["transId"] == 45178372831
            assert len(dribblet["userAssetDribbletDetails"]) == 1
            assert dribblet["userAssetDribbletDetails"][0]["fromAsset"] == "ATOM"
