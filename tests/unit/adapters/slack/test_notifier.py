"""
Slack Notifier 테스트

SlackNotifier 단위 테스트.
httpx를 모킹하여 실제 네트워크 호출 없이 테스트.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from adapters.slack.notifier import SlackNotifier, LEVEL_EMOJI, LEVEL_COLOR
from adapters.interfaces import INotifier


class TestSlackNotifierProtocol:
    """SlackNotifier Protocol 준수 테스트"""
    
    def test_implements_inotifier_protocol(self) -> None:
        """INotifier Protocol 구현 확인"""
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        assert isinstance(notifier, INotifier)


class TestSlackNotifierInit:
    """SlackNotifier 초기화 테스트"""
    
    def test_init_with_webhook_url(self) -> None:
        """webhook_url로 초기화"""
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        
        assert notifier.webhook_url == "https://hooks.slack.com/test"
        assert notifier.channel is None
        assert notifier.username == "AlphaEngine"
        assert notifier.timeout == 10.0
    
    def test_init_with_all_options(self) -> None:
        """모든 옵션으로 초기화"""
        notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
            username="TestBot",
            timeout=5.0,
        )
        
        assert notifier.webhook_url == "https://hooks.slack.com/test"
        assert notifier.channel == "#alerts"
        assert notifier.username == "TestBot"
        assert notifier.timeout == 5.0
    
    def test_init_without_webhook_url_raises(self) -> None:
        """webhook_url 없으면 에러"""
        with pytest.raises(ValueError, match="webhook_url은 필수입니다"):
            SlackNotifier(webhook_url="")


class TestSlackNotifierSend:
    """SlackNotifier.send() 테스트"""
    
    @pytest.fixture
    def notifier(self) -> SlackNotifier:
        """Notifier 픽스처"""
        return SlackNotifier(webhook_url="https://hooks.slack.com/test")
    
    @pytest.mark.asyncio
    async def test_send_success(self, notifier: SlackNotifier) -> None:
        """알림 전송 성공"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send("테스트 메시지", level="INFO")
            
            assert result is True
            mock_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_with_extra_data(self, notifier: SlackNotifier) -> None:
        """extra 데이터와 함께 전송"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send(
                "테스트 메시지",
                level="WARNING",
                extra={"key": "value", "count": 42},
            )
            
            assert result is True
            
            # 호출된 payload 확인
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            
            # fields가 포함되어 있어야 함
            fields = payload["attachments"][0].get("fields", [])
            assert len(fields) == 2
    
    @pytest.mark.asyncio
    async def test_send_with_channel_override(self) -> None:
        """채널 오버라이드"""
        notifier = SlackNotifier(
            webhook_url="https://hooks.slack.com/test",
            channel="#custom-channel",
        )
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            await notifier.send("테스트")
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            
            assert payload["channel"] == "#custom-channel"
    
    @pytest.mark.asyncio
    async def test_send_failure_status_code(self, notifier: SlackNotifier) -> None:
        """전송 실패 (HTTP 에러)"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send("테스트")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_timeout(self, notifier: SlackNotifier) -> None:
        """전송 타임아웃"""
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("timeout")
            mock_get_client.return_value = mock_client
            
            result = await notifier.send("테스트")
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_send_http_error(self, notifier: SlackNotifier) -> None:
        """HTTP 에러"""
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPError("connection error")
            mock_get_client.return_value = mock_client
            
            result = await notifier.send("테스트")
            
            assert result is False


class TestSlackNotifierSendTradeAlert:
    """SlackNotifier.send_trade_alert() 테스트"""
    
    @pytest.fixture
    def notifier(self) -> SlackNotifier:
        """Notifier 픽스처"""
        return SlackNotifier(webhook_url="https://hooks.slack.com/test")
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_buy(self, notifier: SlackNotifier) -> None:
        """매수 알림"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send_trade_alert(
                symbol="XRPUSDT",
                side="BUY",
                quantity="100",
                price="0.5123",
            )
            
            assert result is True
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            
            # 제목에 BUY 포함
            title = payload["attachments"][0]["title"]
            assert "BUY" in title
            assert "XRPUSDT" in title
            
            # 녹색 계열
            color = payload["attachments"][0]["color"]
            assert color == "#36A64F"
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_sell(self, notifier: SlackNotifier) -> None:
        """매도 알림"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send_trade_alert(
                symbol="XRPUSDT",
                side="SELL",
                quantity="50",
                price="0.6000",
            )
            
            assert result is True
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            
            # 제목에 SELL 포함
            title = payload["attachments"][0]["title"]
            assert "SELL" in title
            
            # 빨간색 계열
            color = payload["attachments"][0]["color"]
            assert color == "#FF6B6B"
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_with_pnl(self, notifier: SlackNotifier) -> None:
        """PnL 포함 알림"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send_trade_alert(
                symbol="XRPUSDT",
                side="SELL",
                quantity="100",
                price="0.6000",
                pnl="50.00",
            )
            
            assert result is True
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs["json"]
            
            # PnL 필드 확인
            fields = payload["attachments"][0]["fields"]
            pnl_field = next((f for f in fields if f["title"] == "PnL"), None)
            
            assert pnl_field is not None
            assert "50.00" in pnl_field["value"]
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_with_negative_pnl(self, notifier: SlackNotifier) -> None:
        """음수 PnL 알림"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch.object(notifier, "_get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_get_client.return_value = mock_client
            
            result = await notifier.send_trade_alert(
                symbol="XRPUSDT",
                side="SELL",
                quantity="100",
                price="0.4000",
                pnl="-25.50",
            )
            
            assert result is True


class TestSlackNotifierLevelMapping:
    """레벨 매핑 테스트"""
    
    def test_level_emoji_mapping(self) -> None:
        """레벨별 이모지"""
        assert LEVEL_EMOJI["INFO"] == ":white_check_mark:"
        assert LEVEL_EMOJI["WARNING"] == ":warning:"
        assert LEVEL_EMOJI["ERROR"] == ":x:"
        assert LEVEL_EMOJI["CRITICAL"] == ":rotating_light:"
    
    def test_level_color_mapping(self) -> None:
        """레벨별 색상"""
        assert LEVEL_COLOR["INFO"] == "#36A64F"
        assert LEVEL_COLOR["WARNING"] == "#FFA500"
        assert LEVEL_COLOR["ERROR"] == "#FF0000"
        assert LEVEL_COLOR["CRITICAL"] == "#8B0000"


class TestSlackNotifierContextManager:
    """Context Manager 테스트"""
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self) -> None:
        """async with 지원"""
        async with SlackNotifier(webhook_url="https://hooks.slack.com/test") as notifier:
            assert notifier.webhook_url == "https://hooks.slack.com/test"
        
        # 종료 후 클라이언트 정리 확인
        assert notifier._client is None
    
    @pytest.mark.asyncio
    async def test_close_without_client(self) -> None:
        """클라이언트 없이 close 호출"""
        notifier = SlackNotifier(webhook_url="https://hooks.slack.com/test")
        
        # 예외 없이 close 가능
        await notifier.close()
