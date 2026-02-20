"""
예제 전략 모듈

- SmaCrossStrategy: 교육용 단순 예제 (고정 수량)
- AtrRiskManagedStrategy: 권장 예제 (리스크 기반 동적 수량)
"""

from strategies.examples.sma_cross import SmaCrossStrategy
from strategies.examples.atr_risk_strategy import AtrRiskManagedStrategy

__all__ = [
    "SmaCrossStrategy",
    "AtrRiskManagedStrategy",
]
