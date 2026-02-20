# AlphaEngine nginx 설정

nginx를 리버스 프록시로 사용하여 HTTPS 및 외부 접근을 관리합니다.

## 1. nginx 설치

```bash
sudo apt update
sudo apt install -y nginx
```

## 2. 기본 설정

### /etc/nginx/sites-available/alphaengine

```nginx
upstream alphaengine_web {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;

    # Let's Encrypt 인증용
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    # HTTP → HTTPS 리다이렉트
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL 인증서 (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 설정
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # 보안 헤더
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # 로그
    access_log /var/log/nginx/alphaengine_access.log;
    error_log /var/log/nginx/alphaengine_error.log;

    # API 프록시
    location /api/ {
        proxy_pass http://alphaengine_web;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Health check
    location /health {
        proxy_pass http://alphaengine_web;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # API 문서
    location /docs {
        proxy_pass http://alphaengine_web;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /redoc {
        proxy_pass http://alphaengine_web;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # OpenAPI JSON
    location /openapi.json {
        proxy_pass http://alphaengine_web;
        proxy_http_version 1.1;
    }

    # 기본 차단
    location / {
        return 404;
    }
}
```

## 3. 설정 적용

```bash
# 심볼릭 링크 생성
sudo ln -s /etc/nginx/sites-available/alphaengine /etc/nginx/sites-enabled/

# 기본 사이트 비활성화 (선택)
sudo rm /etc/nginx/sites-enabled/default

# 설정 검증
sudo nginx -t

# nginx 재시작
sudo systemctl reload nginx
```

## 4. Let's Encrypt SSL 인증서

### certbot 설치

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 인증서 발급

```bash
# 도메인 인증서 발급
sudo certbot --nginx -d your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run
```

### 자동 갱신 확인

```bash
# cron 작업 확인
sudo systemctl status certbot.timer
```

## 5. IP 기반 접근 제한 (선택)

특정 IP만 접근 허용하려면:

```nginx
server {
    # ...

    # API 접근 제한
    location /api/ {
        # 허용 IP
        allow 1.2.3.4;
        allow 10.0.0.0/8;
        deny all;

        proxy_pass http://alphaengine_web;
        # ...
    }
}
```

## 6. Basic Auth 설정 (선택)

### 비밀번호 파일 생성

```bash
# htpasswd 설치
sudo apt install -y apache2-utils

# 사용자 추가
sudo htpasswd -c /etc/nginx/.htpasswd admin
```

### nginx 설정에 추가

```nginx
location /api/ {
    auth_basic "AlphaEngine API";
    auth_basic_user_file /etc/nginx/.htpasswd;

    proxy_pass http://alphaengine_web;
    # ...
}
```

## 7. Rate Limiting (선택)

```nginx
# http 블록에 추가
http {
    # Rate limit 존 정의
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    
    # ...
}

# server 블록에서 사용
location /api/ {
    limit_req zone=api_limit burst=20 nodelay;
    
    proxy_pass http://alphaengine_web;
    # ...
}
```

## 8. 트러블슈팅

### 502 Bad Gateway

```bash
# 백엔드 서비스 확인
curl http://127.0.0.1:8000/health

# 서비스 상태 확인
sudo systemctl status alphaengine-web
```

### 권한 문제

```bash
# nginx 사용자 확인
ps aux | grep nginx

# 소켓 파일 권한 (Unix Socket 사용 시)
ls -la /run/alphaengine/
```

### SSL 문제

```bash
# 인증서 만료 확인
sudo certbot certificates

# 강제 갱신
sudo certbot renew --force-renewal
```

## 9. 로그 확인

```bash
# 접근 로그
tail -f /var/log/nginx/alphaengine_access.log

# 에러 로그
tail -f /var/log/nginx/alphaengine_error.log
```

## 관련 문서

- [초기 설정](setup.md)
- [systemd 설정](systemd.md)
- [모니터링](monitoring.md)
