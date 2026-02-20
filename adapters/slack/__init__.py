"""
Slack 어댑터

Slack Webhook을 통한 알림 전송.
INotifier Protocol 준수.
"""

from adapters.slack.notifier import SlackNotifier

__all__ = [
    "SlackNotifier",
]
