# AlphaEngine 모니터링 설정

로그 관리, 헬스 체크, 알림 설정 가이드입니다.

## 로그 관리

### journalctl 로그 확인

```bash
# Bot 로그 (실시간)
journalctl -u alphaengine-bot -f

# Web 로그 (실시간)
journalctl -u alphaengine-web -f

# 특정 기간 로그
journalctl -u alphaengine-bot --since "1 hour ago"
journalctl -u alphaengine-bot --since "2024-01-01" --until "2024-01-02"

# 에러만 필터
journalctl -u alphaengine-bot -p err

# JSON 형식 출력
journalctl -u alphaengine-bot -o json-pretty
```

### logrotate 설정 (선택)

파일 로그 사용 시 `/etc/logrotate.d/alphaengine`:

```
/opt/alphaengine/logs/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 alphaengine alphaengine
    postrotate
        systemctl reload alphaengine-bot alphaengine-web 2>/dev/null || true
    endscript
}
```

### journald 디스크 사용량 관리

```bash
# 현재 디스크 사용량
journalctl --disk-usage

# 오래된 로그 정리 (1주 이상)
sudo journalctl --vacuum-time=7d

# 크기 제한 (500MB)
sudo journalctl --vacuum-size=500M
```

## 헬스 체크

### 엔드포인트

| 엔드포인트 | 설명 |
|------------|------|
| `GET /health` | Web API 상태 |
| 프로세스 상태 | systemd 서비스 상태 |

### 헬스 체크 스크립트

```bash
#!/bin/bash
# /opt/alphaengine/scripts/health_check.sh

set -e

BOT_SERVICE="alphaengine-bot"
WEB_SERVICE="alphaengine-web"
WEB_URL="http://127.0.0.1:8000/health"

check_service() {
    local service=$1
    if systemctl is-active --quiet "$service"; then
        echo "OK: $service is running"
        return 0
    else
        echo "FAIL: $service is not running"
        return 1
    fi
}

check_web_api() {
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$WEB_URL" 2>/dev/null)
    if [ "$response" = "200" ]; then
        echo "OK: Web API is responding (HTTP $response)"
        return 0
    else
        echo "FAIL: Web API returned HTTP $response"
        return 1
    fi
}

echo "=== AlphaEngine Health Check ==="
echo "Time: $(date)"
echo ""

errors=0

check_service "$BOT_SERVICE" || ((errors++))
check_service "$WEB_SERVICE" || ((errors++))
check_web_api || ((errors++))

echo ""
if [ $errors -eq 0 ]; then
    echo "All checks passed!"
    exit 0
else
    echo "ALERT: $errors check(s) failed!"
    exit 1
fi
```

### Cron 헬스 체크

```cron
# 5분마다 헬스 체크
*/5 * * * * /opt/alphaengine/scripts/health_check.sh >> /opt/alphaengine/logs/health.log 2>&1
```

## 알림 설정

### Slack Webhook

```bash
#!/bin/bash
# /opt/alphaengine/scripts/notify_slack.sh

WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
MESSAGE="$1"
SEVERITY="${2:-info}"  # info, warning, error

case $SEVERITY in
    error)
        EMOJI=":x:"
        COLOR="#FF0000"
        ;;
    warning)
        EMOJI=":warning:"
        COLOR="#FFA500"
        ;;
    *)
        EMOJI=":white_check_mark:"
        COLOR="#36A64F"
        ;;
esac

curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{
        \"attachments\": [{
            \"color\": \"$COLOR\",
            \"text\": \"$EMOJI *AlphaEngine*: $MESSAGE\",
            \"footer\": \"$(hostname) | $(date '+%Y-%m-%d %H:%M:%S')\"
        }]
    }"
```

### Discord Webhook

```bash
#!/bin/bash
# /opt/alphaengine/scripts/notify_discord.sh

WEBHOOK_URL="https://discord.com/api/webhooks/YOUR/WEBHOOK/URL"
MESSAGE="$1"
SEVERITY="${2:-info}"

case $SEVERITY in
    error)
        COLOR=15158332  # Red
        ;;
    warning)
        COLOR=16776960  # Yellow
        ;;
    *)
        COLOR=3066993   # Green
        ;;
esac

curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{
        \"embeds\": [{
            \"title\": \"AlphaEngine Alert\",
            \"description\": \"$MESSAGE\",
            \"color\": $COLOR,
            \"footer\": {\"text\": \"$(hostname) | $(date '+%Y-%m-%d %H:%M:%S')\"}
        }]
    }"
```

### 장애 감지 알림

```bash
#!/bin/bash
# /opt/alphaengine/scripts/monitor.sh

SCRIPT_DIR="$(dirname "$0")"
HEALTH_CHECK="$SCRIPT_DIR/health_check.sh"
NOTIFY="$SCRIPT_DIR/notify_slack.sh"
STATE_FILE="/tmp/alphaengine_health_state"

# 현재 상태 확인
if $HEALTH_CHECK > /dev/null 2>&1; then
    current_state="healthy"
else
    current_state="unhealthy"
fi

# 이전 상태 확인
previous_state=$(cat "$STATE_FILE" 2>/dev/null || echo "unknown")

# 상태 저장
echo "$current_state" > "$STATE_FILE"

# 상태 변경 시 알림
if [ "$current_state" != "$previous_state" ]; then
    if [ "$current_state" = "unhealthy" ]; then
        $NOTIFY "서비스 장애 감지! 상태 확인 필요" "error"
    elif [ "$current_state" = "healthy" ] && [ "$previous_state" = "unhealthy" ]; then
        $NOTIFY "서비스 복구됨" "info"
    fi
fi
```

## 메트릭 수집 (선택)

### Prometheus 메트릭

FastAPI에 Prometheus 메트릭 추가:

```python
# web/app.py
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
```

### 시스템 메트릭

```bash
# CPU, 메모리 확인
top -b -n 1 | head -20

# 디스크 사용량
df -h /opt/alphaengine/

# 프로세스 리소스
ps aux | grep alphaengine
```

## 대시보드 설정 (선택)

### Grafana + Loki

1. Loki 설치 (로그 수집)
2. Grafana 설치 (시각화)
3. journald → Loki 연동

### 간단한 상태 페이지

```bash
#!/bin/bash
# 상태 리포트 생성

echo "=== AlphaEngine Status Report ==="
echo "Generated: $(date)"
echo ""

echo "### Services ###"
systemctl status alphaengine-bot --no-pager | head -5
systemctl status alphaengine-web --no-pager | head -5

echo ""
echo "### Resources ###"
echo "Memory:"
free -h | head -2

echo "Disk:"
df -h /opt/alphaengine/

echo ""
echo "### Recent Events ###"
curl -s http://127.0.0.1:8000/api/events?limit=5 | python3 -m json.tool

echo ""
echo "### Pending Commands ###"
curl -s http://127.0.0.1:8000/api/commands?include_completed=false | python3 -m json.tool
```

## 경고 임계값

| 메트릭 | 경고 | 위험 |
|--------|------|------|
| 메모리 사용량 | 70% | 90% |
| 디스크 사용량 | 80% | 95% |
| 서비스 재시작 횟수 | 3회/시간 | 5회/시간 |
| API 응답 시간 | 1초 | 5초 |
| 연속 에러 | 10회 | 50회 |

## 관련 문서

- [초기 설정](setup.md)
- [systemd 설정](systemd.md)
- [문제 해결](troubleshooting.md)
