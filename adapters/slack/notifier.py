"""
Slack 알림 서비스

Slack Webhook을 통해 알림을 전송.
INotifier Protocol 준수.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# 레벨별 이모지 매핑
LEVEL_EMOJI = {
    "INFO": ":white_check_mark:",
    "WARNING": ":warning:",
    "ERROR": ":x:",
    "CRITICAL": ":rotating_light:",
}

# 레벨별 색상 매핑 (Slack attachment color)
LEVEL_COLOR = {
    "INFO": "#36A64F",      # 녹색
    "WARNING": "#FFA500",   # 주황색
    "ERROR": "#FF0000",     # 빨간색
    "CRITICAL": "#8B0000",  # 진한 빨간색
}


class SlackNotifier:
    """Slack 알림 서비스
    
    INotifier Protocol 구현.
    Slack Webhook URL을 통해 메시지 전송.
    
    사용 예시:
    ```python
    notifier = SlackNotifier(webhook_url="https://hooks.slack.com/...")
    
    await notifier.send("서버 시작됨", level="INFO")
    await notifier.send_trade_alert(
        symbol="XRPUSDT",
        side="BUY",
        quantity="100",
        price="0.5123",
    )
    ```
    """
    
    def __init__(
        self,
        webhook_url: str,
        channel: str | None = None,
        username: str = "AlphaEngine",
        timeout: float = 10.0,
    ):
        """
        Args:
            webhook_url: Slack Incoming Webhook URL
            channel: 채널 오버라이드 (기본값은 Webhook 설정 사용)
            username: 메시지 발송자 이름
            timeout: HTTP 요청 타임아웃 (초)
        """
        if not webhook_url:
            raise ValueError("webhook_url은 필수입니다")
        
        self.webhook_url = webhook_url
        self.channel = channel
        self.username = username
        self.timeout = timeout
        
        # httpx 비동기 클라이언트 (재사용)
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 반환 (lazy initialization)"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client
    
    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def send(
        self,
        message: str,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> bool:
        """알림 전송
        
        Args:
            message: 알림 메시지
            level: 알림 레벨 (INFO, WARNING, ERROR, CRITICAL)
            extra: 추가 데이터 (attachment fields로 표시)
            
        Returns:
            전송 성공 여부
        """
        emoji = LEVEL_EMOJI.get(level, ":bell:")
        color = LEVEL_COLOR.get(level, "#808080")
        
        # 기본 메시지 포맷
        text = f"{emoji} *[{level}]* {message}"
        
        # Slack 페이로드 구성
        payload: dict[str, Any] = {
            "username": self.username,
            "attachments": [
                {
                    "color": color,
                    "text": text,
                    "footer": f"AlphaEngine | {self._format_timestamp()}",
                }
            ],
        }
        
        # 채널 오버라이드
        if self.channel:
            payload["channel"] = self.channel
        
        # extra 데이터가 있으면 fields로 추가
        if extra:
            fields = [
                {"title": key, "value": str(value), "short": True}
                for key, value in extra.items()
            ]
            payload["attachments"][0]["fields"] = fields
        
        return await self._send_payload(payload)
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        pnl: str | None = None,
    ) -> bool:
        """거래 알림 전송 (포맷팅된 메시지)
        
        Args:
            symbol: 거래 심볼
            side: 매수/매도 (BUY/SELL)
            quantity: 수량
            price: 가격
            pnl: 손익 (선택)
            
        Returns:
            전송 성공 여부
        """
        # 매수/매도 이모지
        side_emoji = ":chart_with_upwards_trend:" if side == "BUY" else ":chart_with_downwards_trend:"
        side_color = "#36A64F" if side == "BUY" else "#FF6B6B"
        
        # 메시지 구성
        title = f"{side_emoji} {side} {symbol}"
        
        fields = [
            {"title": "심볼", "value": symbol, "short": True},
            {"title": "방향", "value": side, "short": True},
            {"title": "수량", "value": quantity, "short": True},
            {"title": "가격", "value": price, "short": True},
        ]
        
        if pnl:
            # PnL 색상 (양수: 녹색, 음수: 빨간색)
            pnl_value = pnl
            try:
                pnl_float = float(pnl.replace(",", ""))
                pnl_emoji = ":moneybag:" if pnl_float >= 0 else ":money_with_wings:"
                pnl_value = f"{pnl_emoji} {pnl}"
            except ValueError:
                pass
            fields.append({"title": "PnL", "value": pnl_value, "short": True})
        
        payload: dict[str, Any] = {
            "username": self.username,
            "attachments": [
                {
                    "color": side_color,
                    "title": title,
                    "fields": fields,
                    "footer": f"AlphaEngine | {self._format_timestamp()}",
                }
            ],
        }
        
        if self.channel:
            payload["channel"] = self.channel
        
        return await self._send_payload(payload)
    
    async def _send_payload(self, payload: dict[str, Any]) -> bool:
        """Slack Webhook으로 페이로드 전송
        
        Args:
            payload: Slack 메시지 페이로드
            
        Returns:
            전송 성공 여부
        """
        try:
            client = await self._get_client()
            response = await client.post(self.webhook_url, json=payload)
            
            if response.status_code == 200:
                logger.debug("Slack 알림 전송 성공")
                return True
            else:
                logger.warning(
                    "Slack 알림 전송 실패: status=%s, body=%s",
                    response.status_code,
                    response.text,
                )
                return False
                
        except httpx.TimeoutException:
            logger.error("Slack 알림 전송 타임아웃")
            return False
        except httpx.HTTPError as e:
            logger.error("Slack 알림 전송 HTTP 에러: %s", e)
            return False
        except Exception as e:
            logger.exception("Slack 알림 전송 예외: %s", e)
            return False
    
    def _format_timestamp(self) -> str:
        """현재 시간을 KST로 포맷"""
        # UTC 기준으로 저장하고 표시는 KST로
        utc_now = datetime.now(timezone.utc)
        # KST = UTC + 9시간
        from datetime import timedelta
        kst_now = utc_now + timedelta(hours=9)
        return kst_now.strftime("%Y-%m-%d %H:%M:%S KST")
    
    # -------------------------------------------------------------------------
    # Context Manager 지원
    # -------------------------------------------------------------------------
    
    async def __aenter__(self) -> "SlackNotifier":
        """async with 진입"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """async with 종료 시 클라이언트 정리"""
        await self.close()
