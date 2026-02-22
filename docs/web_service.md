## 정보

- 홈페이지: http://alphaengine.wonbbo.kro.kr/
- NginX 설정: /etc/nginx/conf.d/flask_app.conf

## 체크

- 서비스로 운영되는 웹
  - sudo systemctl [start, stop, restart, status] [service name]

- 웹서비스 오류 체크
  - sudo systemctl status flask_app
- 웹서비스 nginx
  - sudo systemctl status nginx

```bash

sudo vi /etc/systemd/system/alphaengine-bot.service
sudo vi /etc/systemd/system/alphaengine-web.service

sudo systemctl daemon-reload
sudo systemctl enable alphaengine-bot
sudo systemctl enable alphaengine-web

sudo systemctl start alphaengine-bot
sudo systemctl restart alphaengine-bot
sudo systemctl status alphaengine-bot

sudo systemctl start alphaengine-web
sudo systemctl restart alphaengine-web
sudo systemctl status alphaengine-web

sudo journalctl -u alphaengine-bot -f
sudo journalctl -u alphaengine-web -f

# Nginx 로그
sudo tail -f /var/log/nginx/alphaengine_access.log
sudo tail -f /var/log/nginx/alphaengine_error.log

```
