"""
Slack 알림 E2E 테스트

실제 Slack Webhook으로 메시지 전송 테스트.
secrets.yaml에 slack.webhook_url 설정 필요.
"""

import pytest
import pytest_asyncio
import yaml
from collections.abc import AsyncGenerator
from pathlib import Path

from core.constants import Paths
from adapters.slack.notifier import SlackNotifier


# -------------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------------


@pytest.fixture(scope="module")
def slack_config() -> dict[str, str]:
    """Slack 설정 로드
    
    Raises:
        pytest.skip: webhook_url이 설정되지 않은 경우
    """
    secrets_path = Paths.SECRETS_FILE
    
    if not secrets_path.exists():
        pytest.skip(f"secrets.yaml 파일을 찾을 수 없음: {secrets_path}")
    
    with open(secrets_path, encoding="utf-8") as f:
        raw_config = yaml.safe_load(f)
    
    slack = raw_config.get("slack", {})
    webhook_url = slack.get("webhook_url", "")
    
    if not webhook_url:
        pytest.skip("slack.webhook_url이 설정되지 않음")
    
    return {
        "webhook_url": webhook_url,
        "channel": slack.get("channel", ""),
    }


@pytest_asyncio.fixture
async def slack_notifier(
    slack_config: dict[str, str],
) -> AsyncGenerator[SlackNotifier, None]:
    """SlackNotifier 인스턴스"""
    channel = slack_config["channel"] if slack_config["channel"] else None
    
    notifier = SlackNotifier(
        webhook_url=slack_config["webhook_url"],
        channel=channel,
        username="AlphaEngine E2E Test",
    )
    
    yield notifier
    
    await notifier.close()


# -------------------------------------------------------------------------
# E2E 테스트
# -------------------------------------------------------------------------


@pytest.mark.e2e
class TestSlackNotificationE2E:
    """Slack 알림 E2E 테스트"""
    
    @pytest.mark.asyncio
    async def test_send_info_message(self, slack_notifier: SlackNotifier) -> None:
        """INFO 레벨 메시지 전송"""
        result = await slack_notifier.send(
            message="E2E 테스트: INFO 메시지 전송 성공",
            level="INFO",
        )
        
        assert result is True, "Slack 메시지 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_warning_message(self, slack_notifier: SlackNotifier) -> None:
        """WARNING 레벨 메시지 전송"""
        result = await slack_notifier.send(
            message="E2E 테스트: WARNING 메시지 전송",
            level="WARNING",
        )
        
        assert result is True, "Slack 메시지 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_error_message(self, slack_notifier: SlackNotifier) -> None:
        """ERROR 레벨 메시지 전송"""
        result = await slack_notifier.send(
            message="E2E 테스트: ERROR 메시지 전송 (테스트용)",
            level="ERROR",
        )
        
        assert result is True, "Slack 메시지 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_with_extra_data(self, slack_notifier: SlackNotifier) -> None:
        """추가 데이터와 함께 전송"""
        result = await slack_notifier.send(
            message="E2E 테스트: 추가 데이터 포함",
            level="INFO",
            extra={
                "테스트명": "test_send_with_extra_data",
                "환경": "E2E",
                "상태": "실행 중",
            },
        )
        
        assert result is True, "Slack 메시지 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_buy(self, slack_notifier: SlackNotifier) -> None:
        """매수 거래 알림 전송"""
        result = await slack_notifier.send_trade_alert(
            symbol="XRPUSDT",
            side="BUY",
            quantity="100",
            price="0.5123",
        )
        
        assert result is True, "거래 알림 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_sell_with_pnl(self, slack_notifier: SlackNotifier) -> None:
        """매도 거래 알림 (PnL 포함) 전송"""
        result = await slack_notifier.send_trade_alert(
            symbol="XRPUSDT",
            side="SELL",
            quantity="100",
            price="0.5500",
            pnl="+3.77",
        )
        
        assert result is True, "거래 알림 전송 실패"
    
    @pytest.mark.asyncio
    async def test_send_trade_alert_with_negative_pnl(self, slack_notifier: SlackNotifier) -> None:
        """손실 거래 알림 전송"""
        result = await slack_notifier.send_trade_alert(
            symbol="XRPUSDT",
            side="SELL",
            quantity="50",
            price="0.4800",
            pnl="-1.62",
        )
        
        assert result is True, "거래 알림 전송 실패"
