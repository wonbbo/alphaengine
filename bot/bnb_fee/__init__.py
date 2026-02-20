"""
BNB 수수료 자동 관리 모듈

Futures에서 BNB 수수료 할인을 위해 BNB 잔고를 자동으로 유지.
"""

from bot.bnb_fee.manager import BnbFeeManager

__all__ = [
    "BnbFeeManager",
]
