"""
어댑터 레이어

외부 서비스(거래소, DB, 알림 등)와의 연동을 담당.
Protocol 기반 인터페이스로 Mock 교체 가능.
"""

from adapters.interfaces import (
    IExchangeRestClient,
    IExchangeWsClient,
    INotifier,
)
from adapters.models import (
    Balance,
    Position,
    Order,
    Trade,
    OrderRequest,
)

__all__ = [
    # Interfaces
    "IExchangeRestClient",
    "IExchangeWsClient",
    "INotifier",
    # Models
    "Balance",
    "Position",
    "Order",
    "Trade",
    "OrderRequest",
]
