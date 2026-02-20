"""
Binance 어댑터

Binance Futures API 연동을 담당.
REST API와 WebSocket User Data Stream 지원.
"""

from adapters.binance.rest_client import BinanceRestClient
from adapters.binance.ws_client import BinanceWsClient
from adapters.binance.rate_limiter import RateLimitTracker, RateLimitError
from adapters.binance.models import (
    parse_balance,
    parse_position,
    parse_order,
    parse_trade,
)

__all__ = [
    "BinanceRestClient",
    "BinanceWsClient",
    "RateLimitTracker",
    "RateLimitError",
    "parse_balance",
    "parse_position",
    "parse_order",
    "parse_trade",
]
