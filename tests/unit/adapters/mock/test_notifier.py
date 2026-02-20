"""
Mock Notifier 테스트

MockNotifier 테스트.
"""

import pytest

from adapters.mock.notifier import MockNotifier


class TestMockNotifier:
    """MockNotifier 테스트"""
    
    @pytest.fixture
    def notifier(self) -> MockNotifier:
        """Notifier 픽스처"""
        return MockNotifier()
    
    @pytest.mark.asyncio
    async def test_send_success(self, notifier: MockNotifier) -> None:
        """알림 전송 성공"""
        result = await notifier.send("테스트 메시지", level="INFO")
        
        assert result is True
        assert len(notifier.notifications) == 1
    
    @pytest.mark.asyncio
    async def test_send_records_message(self, notifier: MockNotifier) -> None:
        """메시지 기록 확인"""
        await notifier.send("테스트 메시지", level="WARNING", extra={"key": "value"})
        
        record = notifier.notifications[0]
        
        assert record.message == "테스트 메시지"
        assert record.level == "WARNING"
        assert record.extra == {"key": "value"}
        assert record.sent is True
        assert record.timestamp is not None
    
    @pytest.mark.asyncio
    async def test_send_fail_mode(self) -> None:
        """실패 모드"""
        notifier = MockNotifier(should_fail=True)
        
        result = await notifier.send("테스트 메시지")
        
        assert result is False
        assert notifier.notifications[0].sent is False
    
    @pytest.mark.asyncio
    async def test_send_trade_alert(self, notifier: MockNotifier) -> None:
        """거래 알림 전송"""
        result = await notifier.send_trade_alert(
            symbol="XRPUSDT",
            side="BUY",
            quantity="100",
            price="0.5123",
            pnl="50.00",
        )
        
        assert result is True
        
        record = notifier.notifications[0]
        assert "XRPUSDT" in record.message
        assert "BUY" in record.message
        assert "100" in record.message
        assert "PnL" in record.message
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_without_pnl(self, notifier: MockNotifier) -> None:
        """PnL 없는 거래 알림"""
        await notifier.send_trade_alert(
            symbol="XRPUSDT",
            side="SELL",
            quantity="50",
            price="0.6000",
        )
        
        record = notifier.notifications[0]
        assert "PnL" not in record.message
    
    @pytest.mark.asyncio
    async def test_clear(self, notifier: MockNotifier) -> None:
        """기록 초기화"""
        await notifier.send("메시지 1")
        await notifier.send("메시지 2")
        
        assert len(notifier.notifications) == 2
        
        notifier.clear()
        
        assert len(notifier.notifications) == 0
    
    @pytest.mark.asyncio
    async def test_get_by_level(self, notifier: MockNotifier) -> None:
        """레벨별 조회"""
        await notifier.send("정보", level="INFO")
        await notifier.send("경고", level="WARNING")
        await notifier.send("에러", level="ERROR")
        await notifier.send("정보2", level="INFO")
        
        info_records = notifier.get_by_level("INFO")
        
        assert len(info_records) == 2
    
    @pytest.mark.asyncio
    async def test_get_errors(self, notifier: MockNotifier) -> None:
        """에러 조회"""
        await notifier.send("정보", level="INFO")
        await notifier.send("에러1", level="ERROR")
        await notifier.send("에러2", level="ERROR")
        
        errors = notifier.get_errors()
        
        assert len(errors) == 2
    
    @pytest.mark.asyncio
    async def test_get_warnings(self, notifier: MockNotifier) -> None:
        """경고 조회"""
        await notifier.send("경고", level="WARNING")
        
        warnings = notifier.get_warnings()
        
        assert len(warnings) == 1
    
    @pytest.mark.asyncio
    async def test_last_notification(self, notifier: MockNotifier) -> None:
        """마지막 알림"""
        await notifier.send("첫번째")
        await notifier.send("두번째")
        await notifier.send("세번째")
        
        last = notifier.last_notification
        
        assert last is not None
        assert last.message == "세번째"
    
    @pytest.mark.asyncio
    async def test_last_notification_empty(self, notifier: MockNotifier) -> None:
        """알림 없을 때"""
        assert notifier.last_notification is None
    
    @pytest.mark.asyncio
    async def test_message_count(self, notifier: MockNotifier) -> None:
        """알림 수"""
        await notifier.send("1")
        await notifier.send("2")
        await notifier.send("3")
        
        assert notifier.message_count == 3
    
    @pytest.mark.asyncio
    async def test_sent_and_failed_count(self) -> None:
        """성공/실패 카운트"""
        notifier = MockNotifier()
        await notifier.send("성공1")
        await notifier.send("성공2")
        
        notifier.should_fail = True
        await notifier.send("실패1")
        await notifier.send("실패2")
        await notifier.send("실패3")
        
        assert notifier.sent_count == 2
        assert notifier.failed_count == 3
