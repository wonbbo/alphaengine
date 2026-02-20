"""
MarketDataProvider 테스트

캔들 데이터 조회 및 변환 테스트.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from bot.market_data.provider import MarketDataProvider


class TestMarketDataProviderInit:
    """MarketDataProvider 초기화 테스트"""
    
    def test_init_with_defaults(self) -> None:
        """기본값으로 초기화"""
        mock_client = MagicMock()
        provider = MarketDataProvider(rest_client=mock_client)
        
        assert provider.default_timeframe == "5m"
        assert provider.default_limit == 100
        assert provider.cache_ttl_seconds == 60
    
    def test_init_with_custom_values(self) -> None:
        """커스텀 값으로 초기화"""
        mock_client = MagicMock()
        provider = MarketDataProvider(
            rest_client=mock_client,
            default_timeframe="15m",
            default_limit=50,
            cache_ttl_seconds=120,
        )
        
        assert provider.default_timeframe == "15m"
        assert provider.default_limit == 50
        assert provider.cache_ttl_seconds == 120


class TestMarketDataProviderGetBars:
    """MarketDataProvider.get_bars() 테스트"""
    
    @pytest.fixture
    def mock_rest_client(self) -> MagicMock:
        """Mock REST 클라이언트"""
        client = MagicMock()
        client.get_klines = AsyncMock()
        client.get_ticker_price = AsyncMock()
        return client
    
    @pytest.fixture
    def provider(self, mock_rest_client: MagicMock) -> MarketDataProvider:
        """Provider 픽스처"""
        return MarketDataProvider(
            rest_client=mock_rest_client,
            cache_ttl_seconds=60,
        )
    
    @pytest.mark.asyncio
    async def test_get_bars_success(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """캔들 데이터 조회 성공"""
        # Mock 응답
        mock_rest_client.get_klines.return_value = [
            {
                "open_time": 1640000000000,
                "open": "0.5000",
                "high": "0.5100",
                "low": "0.4900",
                "close": "0.5050",
                "volume": "1000000",
            },
            {
                "open_time": 1640000300000,
                "open": "0.5050",
                "high": "0.5150",
                "low": "0.5000",
                "close": "0.5100",
                "volume": "1200000",
            },
        ]
        
        bars = await provider.get_bars(symbol="XRPUSDT", timeframe="5m", limit=100)
        
        assert len(bars) == 2
        assert bars[0]["open"] == "0.5000"
        assert bars[0]["close"] == "0.5050"
        assert bars[1]["open"] == "0.5050"
        assert bars[1]["close"] == "0.5100"
        
        # ts가 datetime 타입인지 확인
        assert isinstance(bars[0]["ts"], datetime)
    
    @pytest.mark.asyncio
    async def test_get_bars_uses_default_values(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """기본값 사용 확인"""
        mock_rest_client.get_klines.return_value = []
        
        await provider.get_bars(symbol="XRPUSDT")
        
        mock_rest_client.get_klines.assert_called_once_with(
            symbol="XRPUSDT",
            interval="5m",
            limit=100,
        )
    
    @pytest.mark.asyncio
    async def test_get_bars_with_custom_values(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """커스텀 값 사용"""
        mock_rest_client.get_klines.return_value = []
        
        await provider.get_bars(symbol="BTCUSDT", timeframe="1h", limit=50)
        
        mock_rest_client.get_klines.assert_called_once_with(
            symbol="BTCUSDT",
            interval="1h",
            limit=50,
        )
    
    @pytest.mark.asyncio
    async def test_get_bars_invalid_timeframe_uses_default(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """유효하지 않은 timeframe은 기본값 사용"""
        mock_rest_client.get_klines.return_value = []
        
        await provider.get_bars(symbol="XRPUSDT", timeframe="invalid")
        
        mock_rest_client.get_klines.assert_called_once_with(
            symbol="XRPUSDT",
            interval="5m",  # 기본값
            limit=100,
        )
    
    @pytest.mark.asyncio
    async def test_get_bars_caching(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """캐싱 동작 확인"""
        mock_rest_client.get_klines.return_value = [
            {"open_time": 1640000000000, "open": "0.5", "high": "0.5", "low": "0.5", "close": "0.5", "volume": "100"},
        ]
        
        # 첫 번째 호출
        bars1 = await provider.get_bars(symbol="XRPUSDT", timeframe="5m")
        
        # 두 번째 호출 (캐시 히트)
        bars2 = await provider.get_bars(symbol="XRPUSDT", timeframe="5m")
        
        # API는 한 번만 호출
        assert mock_rest_client.get_klines.call_count == 1
        assert bars1 == bars2
    
    @pytest.mark.asyncio
    async def test_get_bars_error_returns_empty(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """에러 시 빈 리스트 반환"""
        mock_rest_client.get_klines.side_effect = Exception("API Error")
        
        bars = await provider.get_bars(symbol="XRPUSDT")
        
        assert bars == []


class TestMarketDataProviderGetCurrentPrice:
    """MarketDataProvider.get_current_price() 테스트"""
    
    @pytest.fixture
    def mock_rest_client(self) -> MagicMock:
        client = MagicMock()
        client.get_klines = AsyncMock()
        client.get_ticker_price = AsyncMock()
        return client
    
    @pytest.fixture
    def provider(self, mock_rest_client: MagicMock) -> MarketDataProvider:
        return MarketDataProvider(rest_client=mock_rest_client)
    
    @pytest.mark.asyncio
    async def test_get_current_price_success(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """현재가 조회 성공"""
        mock_rest_client.get_ticker_price.return_value = {
            "symbol": "XRPUSDT",
            "price": "0.5123",
        }
        
        price = await provider.get_current_price("XRPUSDT")
        
        assert price == Decimal("0.5123")
    
    @pytest.mark.asyncio
    async def test_get_current_price_error_returns_none(self, provider: MarketDataProvider, mock_rest_client: MagicMock) -> None:
        """에러 시 None 반환"""
        mock_rest_client.get_ticker_price.side_effect = Exception("API Error")
        
        price = await provider.get_current_price("XRPUSDT")
        
        assert price is None


class TestMarketDataProviderCache:
    """캐시 관련 테스트"""
    
    @pytest.fixture
    def mock_rest_client(self) -> MagicMock:
        client = MagicMock()
        client.get_klines = AsyncMock(return_value=[])
        return client
    
    @pytest.fixture
    def provider(self, mock_rest_client: MagicMock) -> MarketDataProvider:
        return MarketDataProvider(rest_client=mock_rest_client)
    
    def test_clear_cache(self, provider: MarketDataProvider) -> None:
        """캐시 초기화"""
        provider._cache["test:key"] = (0, [])
        
        provider.clear_cache()
        
        assert len(provider._cache) == 0
    
    def test_invalidate_cache_specific(self, provider: MarketDataProvider) -> None:
        """특정 캐시 무효화"""
        provider._cache["XRPUSDT:5m"] = (0, [])
        provider._cache["XRPUSDT:1h"] = (0, [])
        provider._cache["BTCUSDT:5m"] = (0, [])
        
        provider.invalidate_cache("XRPUSDT", "5m")
        
        assert "XRPUSDT:5m" not in provider._cache
        assert "XRPUSDT:1h" in provider._cache
        assert "BTCUSDT:5m" in provider._cache
    
    def test_invalidate_cache_all_timeframes(self, provider: MarketDataProvider) -> None:
        """심볼의 모든 timeframe 캐시 무효화"""
        provider._cache["XRPUSDT:5m"] = (0, [])
        provider._cache["XRPUSDT:1h"] = (0, [])
        provider._cache["BTCUSDT:5m"] = (0, [])
        
        provider.invalidate_cache("XRPUSDT")
        
        assert "XRPUSDT:5m" not in provider._cache
        assert "XRPUSDT:1h" not in provider._cache
        assert "BTCUSDT:5m" in provider._cache
