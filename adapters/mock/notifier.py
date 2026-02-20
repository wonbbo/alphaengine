"""
Mock 알림 서비스

테스트용 Mock Notifier.
INotifier Protocol 준수.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class NotificationRecord:
    """알림 기록"""
    
    message: str
    level: str
    extra: dict[str, Any] | None
    timestamp: datetime
    sent: bool


class MockNotifier:
    """Mock 알림 서비스
    
    INotifier Protocol 구현.
    발송된 모든 알림을 기록하여 테스트에서 검증 가능.
    
    사용 예시:
    ```python
    notifier = MockNotifier()
    
    await notifier.send("테스트 메시지", level="INFO")
    
    # 발송 기록 확인
    assert len(notifier.notifications) == 1
    assert notifier.notifications[0].message == "테스트 메시지"
    ```
    """
    
    def __init__(self, should_fail: bool = False):
        """
        Args:
            should_fail: True면 모든 발송 실패 (에러 시나리오 테스트용)
        """
        self.should_fail = should_fail
        self.notifications: list[NotificationRecord] = []
    
    async def send(
        self,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """알림 전송"""
        record = NotificationRecord(
            message=message,
            level=level,
            extra=extra,
            timestamp=datetime.now(timezone.utc),
            sent=not self.should_fail,
        )
        
        self.notifications.append(record)
        
        return not self.should_fail
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        pnl: str | None = None,
    ) -> bool:
        """거래 알림 전송"""
        # 메시지 포맷팅
        if pnl:
            message = f"[{side}] {symbol} {quantity} @ {price} (PnL: {pnl})"
        else:
            message = f"[{side}] {symbol} {quantity} @ {price}"
        
        return await self.send(
            message=message,
            level="INFO",
            extra={
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
                "pnl": pnl,
            },
        )
    
    # -------------------------------------------------------------------------
    # 테스트 헬퍼 메서드
    # -------------------------------------------------------------------------
    
    def clear(self) -> None:
        """알림 기록 초기화"""
        self.notifications.clear()
    
    def get_by_level(self, level: str) -> list[NotificationRecord]:
        """특정 레벨의 알림 조회"""
        return [n for n in self.notifications if n.level == level]
    
    def get_errors(self) -> list[NotificationRecord]:
        """에러 레벨 알림 조회"""
        return self.get_by_level("ERROR")
    
    def get_warnings(self) -> list[NotificationRecord]:
        """경고 레벨 알림 조회"""
        return self.get_by_level("WARNING")
    
    @property
    def last_notification(self) -> NotificationRecord | None:
        """마지막 알림 조회"""
        return self.notifications[-1] if self.notifications else None
    
    @property
    def message_count(self) -> int:
        """전체 알림 수"""
        return len(self.notifications)
    
    @property
    def sent_count(self) -> int:
        """성공적으로 발송된 알림 수"""
        return sum(1 for n in self.notifications if n.sent)
    
    @property
    def failed_count(self) -> int:
        """발송 실패한 알림 수"""
        return sum(1 for n in self.notifications if not n.sent)
