# Web Frontend 구현 가이드

**버전**: 1.0  
**작성일**: 2026-02-21  
**전제조건**: 복식부기 시스템 도입 완료 (`01_double_entry_bookkeeping.md`)

---

## 1. 개요

### 1.1 목표

AlphaEngine Web Frontend 완성:
- 기존 계획 페이지 구현 (대시보드, 이벤트, 설정, Commands)
- 수익/수익률 그래프
- 자산 현황 및 거래 내역
- 포지션 히스토리
- Trading Edge 분석

### 1.2 기술 스택

| 항목 | 기술 |
|------|------|
| **Backend** | FastAPI (기존) |
| **Template** | Jinja2 |
| **CSS** | Bootstrap 5.3.0 |
| **Icons** | Bootstrap Icons 1.11.0 |
| **JavaScript** | Vanilla JS (ES6+) |
| **Charts** | Chart.js 4.x |
| **API 호출** | Fetch API |

### 1.3 현재 상태

| 페이지 | 상태 |
|--------|------|
| 입출금 (`/transfer`) | ✅ 완료 |
| 대시보드 (`/dashboard`) | ❌ 미구현 |
| 이벤트 (`/events`) | ❌ 미구현 |
| 설정 (`/config`) | ❌ 미구현 |
| Commands (`/commands`) | ❌ 미구현 |
| 자산 (`/assets`) | ❌ 신규 |
| 거래 내역 (`/transactions`) | ❌ 신규 |
| 포지션 (`/positions`) | ❌ 신규 |
| Trading Edge (`/trading-edge`) | ❌ 신규 |

---

## 2. 디렉토리 구조

### 2.1 최종 구조

```
web/
├── app.py                     # FastAPI 앱
├── dependencies.py            # 의존성 주입
├── __main__.py
│
├── routes/
│   ├── __init__.py
│   ├── health.py              # 기존
│   ├── dashboard.py           # 기존 (API) + 페이지 추가
│   ├── events.py              # 기존 (API) + 페이지 추가
│   ├── config.py              # 기존 (API) + 페이지 추가
│   ├── commands.py            # 기존 (API) + 페이지 추가
│   ├── transfer.py            # 기존
│   ├── assets.py              # 신규
│   ├── transactions.py        # 신규
│   ├── positions.py           # 신규
│   ├── pnl.py                 # 신규 (PnL/Returns API)
│   ├── ledger.py              # 신규 (복식부기 API)
│   └── trading_edge.py        # 신규
│
├── services/
│   ├── __init__.py
│   ├── dashboard_service.py   # 기존
│   ├── event_service.py       # 기존
│   ├── config_service.py      # 기존
│   ├── command_service.py     # 기존
│   ├── transfer_service.py    # 기존
│   ├── asset_service.py       # 신규
│   ├── transaction_service.py # 신규
│   ├── position_service.py    # 신규
│   ├── pnl_service.py         # 신규
│   ├── ledger_service.py      # 신규
│   └── trading_edge_service.py # 신규
│
├── models/
│   ├── __init__.py
│   ├── requests.py            # 기존 + 확장
│   └── responses.py           # 기존 + 확장
│
├── templates/
│   ├── base.html              # 기존 (수정)
│   ├── transfer.html          # 기존
│   ├── dashboard.html         # 신규
│   ├── events.html            # 신규
│   ├── config.html            # 신규
│   ├── commands.html          # 신규
│   ├── assets.html            # 신규
│   ├── transactions.html      # 신규
│   ├── positions.html         # 신규
│   ├── position_detail.html   # 신규
│   └── trading_edge.html      # 신규
│
└── static/
    ├── css/
    │   └── style.css          # 기존 + 확장
    │
    └── js/
        ├── common.js          # 신규 (공통 유틸리티)
        ├── chart-utils.js     # 신규 (Chart.js 헬퍼)
        ├── transfer.js        # 기존
        ├── dashboard.js       # 신규
        ├── events.js          # 신규
        ├── config.js          # 신규
        ├── commands.js        # 신규
        ├── assets.js          # 신규
        ├── transactions.js    # 신규
        ├── positions.js       # 신규
        └── trading_edge.js    # 신규
```

---

## 3. 공통 컴포넌트

### 3.1 base.html 수정

**파일**: `web/templates/base.html`

```html
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}AlphaEngine{% endblock %}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
    <link href="/static/css/style.css" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    {% block head %}{% endblock %}
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container-fluid">
            <a class="navbar-brand" href="/">
                <i class="bi bi-currency-exchange"></i> AlphaEngine
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav">
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'dashboard' %}active{% endif %}" href="/dashboard">
                            <i class="bi bi-speedometer2"></i> 대시보드
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'positions' %}active{% endif %}" href="/positions">
                            <i class="bi bi-graph-up-arrow"></i> 포지션
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'transactions' %}active{% endif %}" href="/transactions">
                            <i class="bi bi-list-ul"></i> 거래 내역
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'assets' %}active{% endif %}" href="/assets">
                            <i class="bi bi-wallet2"></i> 자산
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'trading_edge' %}active{% endif %}" href="/trading-edge">
                            <i class="bi bi-bar-chart-line"></i> Trading Edge
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if active_page == 'transfer' %}active{% endif %}" href="/transfer">
                            <i class="bi bi-arrow-left-right"></i> 입출금
                        </a>
                    </li>
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown">
                            <i class="bi bi-gear"></i> 관리
                        </a>
                        <ul class="dropdown-menu">
                            <li>
                                <a class="dropdown-item {% if active_page == 'events' %}active{% endif %}" href="/events">
                                    <i class="bi bi-journal-text"></i> 이벤트
                                </a>
                            </li>
                            <li>
                                <a class="dropdown-item {% if active_page == 'config' %}active{% endif %}" href="/config">
                                    <i class="bi bi-sliders"></i> 설정
                                </a>
                            </li>
                            <li>
                                <a class="dropdown-item {% if active_page == 'commands' %}active{% endif %}" href="/commands">
                                    <i class="bi bi-terminal"></i> Commands
                                </a>
                            </li>
                        </ul>
                    </li>
                </ul>
                <!-- 모드 표시 -->
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <span class="nav-link">
                            <span class="badge bg-{{ 'danger' if mode == 'PRODUCTION' else 'warning' }}">
                                {{ mode }}
                            </span>
                        </span>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <main class="container-fluid py-4">
        {% block content %}{% endblock %}
    </main>

    <footer class="footer mt-auto py-3 bg-light">
        <div class="container text-center">
            <span class="text-muted">AlphaEngine v2.0 - Binance Futures Trading System</span>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="/static/js/common.js"></script>
    {% block scripts %}{% endblock %}
</body>
</html>
```

### 3.2 공통 JavaScript

**파일**: `web/static/js/common.js`

```javascript
/**
 * AlphaEngine 공통 유틸리티
 */

const AlphaEngine = {
    /**
     * API 호출
     */
    async api(endpoint, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
            },
        };
        
        const response = await fetch(endpoint, { ...defaultOptions, ...options });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        return response.json();
    },
    
    /**
     * UTC → KST 변환
     */
    formatKST(utcString, includeTime = true) {
        if (!utcString) return '-';
        const date = new Date(utcString);
        const kst = new Date(date.getTime() + 9 * 60 * 60 * 1000);
        
        if (includeTime) {
            return kst.toISOString().replace('T', ' ').substring(0, 19);
        }
        return kst.toISOString().substring(0, 10);
    },
    
    /**
     * 숫자 포맷팅
     */
    formatNumber(value, decimals = 2) {
        if (value === null || value === undefined || value === '') return '-';
        const num = parseFloat(value);
        if (isNaN(num)) return value;
        return num.toLocaleString('ko-KR', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
        });
    },
    
    /**
     * 금액 포맷팅 (색상 포함)
     */
    formatAmount(value, decimals = 2) {
        const num = parseFloat(value);
        if (isNaN(num)) return { text: '-', class: '' };
        
        const formatted = this.formatNumber(Math.abs(num), decimals);
        
        if (num > 0) {
            return { text: `+${formatted}`, class: 'text-success' };
        } else if (num < 0) {
            return { text: `-${formatted}`, class: 'text-danger' };
        }
        return { text: formatted, class: '' };
    },
    
    /**
     * 퍼센트 포맷팅
     */
    formatPercent(value, decimals = 2) {
        const num = parseFloat(value);
        if (isNaN(num)) return '-';
        return `${num >= 0 ? '+' : ''}${num.toFixed(decimals)}%`;
    },
    
    /**
     * 상태 뱃지 생성
     */
    statusBadge(status) {
        const badges = {
            // Command 상태
            'NEW': 'bg-primary',
            'SENT': 'bg-warning',
            'ACK': 'bg-success',
            'FAILED': 'bg-danger',
            // 포지션 상태
            'OPEN': 'bg-primary',
            'CLOSED': 'bg-secondary',
            // 포지션 방향
            'LONG': 'bg-success',
            'SHORT': 'bg-danger',
        };
        
        const bgClass = badges[status] || 'bg-secondary';
        return `<span class="badge ${bgClass}">${status}</span>`;
    },
    
    /**
     * 로딩 스피너 표시
     */
    showLoading(elementId) {
        const el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = `
                <div class="d-flex justify-content-center py-4">
                    <div class="spinner-border" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </div>
            `;
        }
    },
    
    /**
     * 에러 표시
     */
    showError(elementId, message) {
        const el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="bi bi-exclamation-triangle"></i> ${message}
                </div>
            `;
        }
    },
    
    /**
     * 토스트 알림
     */
    toast(message, type = 'info') {
        const toastContainer = document.getElementById('toast-container') || this._createToastContainer();
        
        const toastEl = document.createElement('div');
        toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
        toastEl.setAttribute('role', 'alert');
        toastEl.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;
        
        toastContainer.appendChild(toastEl);
        const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
        toast.show();
        
        toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
    },
    
    _createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
        return container;
    },
    
    /**
     * 폴링 시작
     */
    startPolling(callback, interval = 5000) {
        callback(); // 즉시 실행
        return setInterval(callback, interval);
    },
    
    /**
     * 폴링 중지
     */
    stopPolling(intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
        }
    },
};

// 전역 객체로 노출
window.AE = AlphaEngine;
```

### 3.3 Chart.js 헬퍼

**파일**: `web/static/js/chart-utils.js`

```javascript
/**
 * Chart.js 유틸리티
 */

const ChartUtils = {
    // 기본 색상
    colors: {
        primary: 'rgb(13, 110, 253)',
        success: 'rgb(25, 135, 84)',
        danger: 'rgb(220, 53, 69)',
        warning: 'rgb(255, 193, 7)',
        info: 'rgb(13, 202, 240)',
        gray: 'rgb(108, 117, 125)',
    },
    
    /**
     * 일별 수익 Bar Chart 생성
     */
    createDailyPnLChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const colors = data.values.map(v => 
            parseFloat(v) >= 0 ? this.colors.success : this.colors.danger
        );
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '일별 수익 (USDT)',
                    data: data.values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)} USDT`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 누적 수익 Line Chart 생성
     */
    createCumulativePnLChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 수익 (USDT)',
                    data: data.values,
                    borderColor: this.colors.primary,
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)} USDT`
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 일별 수익률 Bar Chart 생성
     */
    createDailyReturnsChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const colors = data.values.map(v => 
            parseFloat(v) >= 0 ? this.colors.success : this.colors.danger
        );
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '일별 수익률 (%)',
                    data: data.values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.1)' },
                        ticks: {
                            callback: (value) => `${value}%`
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 누적 수익률 Line Chart 생성
     */
    createCumulativeReturnsChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 수익률 (%)',
                    data: data.values,
                    borderColor: this.colors.info,
                    backgroundColor: 'rgba(13, 202, 240, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' },
                        ticks: {
                            callback: (value) => `${value}%`
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * Trading Edge Line Chart 생성
     */
    createTradingEdgeChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 Edge',
                    data: data.values,
                    borderColor: this.colors.warning,
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 차트 업데이트
     */
    updateChart(chart, labels, values) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.update();
    },
    
    /**
     * 차트 파괴
     */
    destroyChart(chart) {
        if (chart) {
            chart.destroy();
        }
    },
};

window.ChartUtils = ChartUtils;
```

### 3.4 CSS 확장

**파일**: `web/static/css/style.css` (추가)

```css
/* 기존 스타일 유지하고 아래 추가 */

/* ===== 카드 스타일 ===== */
.stat-card {
    border: none;
    border-radius: 0.5rem;
    box-shadow: 0 0.125rem 0.25rem rgba(0, 0, 0, 0.075);
    transition: transform 0.15s ease-in-out;
}

.stat-card:hover {
    transform: translateY(-2px);
}

.stat-card .card-body {
    padding: 1.25rem;
}

.stat-card .stat-value {
    font-size: 1.75rem;
    font-weight: 600;
}

.stat-card .stat-label {
    color: #6c757d;
    font-size: 0.875rem;
}

/* ===== 테이블 스타일 ===== */
.table-hover tbody tr:hover {
    background-color: rgba(13, 110, 253, 0.05);
}

.table th {
    font-weight: 600;
    background-color: #f8f9fa;
    border-bottom: 2px solid #dee2e6;
}

.table-clickable tbody tr {
    cursor: pointer;
}

/* ===== 차트 컨테이너 ===== */
.chart-container {
    position: relative;
    height: 300px;
    width: 100%;
}

.chart-container-sm {
    height: 200px;
}

.chart-container-lg {
    height: 400px;
}

/* ===== 상태 뱃지 ===== */
.badge-pnl-positive {
    background-color: #198754;
}

.badge-pnl-negative {
    background-color: #dc3545;
}

/* ===== 필터 폼 ===== */
.filter-form {
    background-color: #f8f9fa;
    border-radius: 0.5rem;
    padding: 1rem;
    margin-bottom: 1rem;
}

.filter-form .form-label {
    font-size: 0.875rem;
    font-weight: 500;
    margin-bottom: 0.25rem;
}

/* ===== 페이지네이션 ===== */
.pagination-info {
    color: #6c757d;
    font-size: 0.875rem;
}

/* ===== 모달 ===== */
.modal-detail .modal-body {
    max-height: 70vh;
    overflow-y: auto;
}

.json-viewer {
    background-color: #f8f9fa;
    border-radius: 0.375rem;
    padding: 1rem;
    font-family: 'Monaco', 'Menlo', monospace;
    font-size: 0.8125rem;
    white-space: pre-wrap;
    word-break: break-all;
}

/* ===== 거래 타입 아이콘 ===== */
.tx-type-trade { color: #0d6efd; }
.tx-type-fee { color: #dc3545; }
.tx-type-funding { color: #fd7e14; }
.tx-type-transfer { color: #198754; }
.tx-type-deposit { color: #20c997; }
.tx-type-withdrawal { color: #6f42c1; }

/* ===== 포지션 상세 ===== */
.position-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

.position-header.long {
    background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
}

.position-header.short {
    background: linear-gradient(135deg, #eb3349 0%, #f45c43 100%);
}

.position-timeline {
    position: relative;
    padding-left: 2rem;
}

.position-timeline::before {
    content: '';
    position: absolute;
    left: 0.5rem;
    top: 0;
    bottom: 0;
    width: 2px;
    background-color: #dee2e6;
}

.position-timeline-item {
    position: relative;
    padding-bottom: 1rem;
}

.position-timeline-item::before {
    content: '';
    position: absolute;
    left: -1.625rem;
    top: 0.25rem;
    width: 0.75rem;
    height: 0.75rem;
    border-radius: 50%;
    background-color: #0d6efd;
    border: 2px solid white;
    box-shadow: 0 0 0 2px #0d6efd;
}

.position-timeline-item.open::before {
    background-color: #198754;
    box-shadow: 0 0 0 2px #198754;
}

.position-timeline-item.close::before {
    background-color: #dc3545;
    box-shadow: 0 0 0 2px #dc3545;
}

/* ===== 반응형 ===== */
@media (max-width: 768px) {
    .stat-card .stat-value {
        font-size: 1.5rem;
    }
    
    .chart-container {
        height: 250px;
    }
    
    .table-responsive {
        font-size: 0.875rem;
    }
}
```

---

## 4. 페이지별 구현

### 4.1 대시보드 (`/dashboard`)

#### 4.1.1 API 확장

**파일**: `web/routes/pnl.py` (신규)

```python
"""
PnL/Returns API 라우트

수익 및 수익률 관련 API
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.pnl_service import PnLService

router = APIRouter(prefix="/api/pnl", tags=["PnL"])


@router.get("/summary")
async def get_pnl_summary(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """PnL 요약 조회
    
    일일/주간/월간/전체 손익 및 수익률
    """
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_pnl_summary(mode)


@router.get("/daily-series")
async def get_daily_pnl_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 수익 시계열
    
    차트 데이터용
    """
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    
    return await service.get_daily_pnl_series(mode, start_date, end_date)


@router.get("/cumulative-series")
async def get_cumulative_pnl_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """누적 수익 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    
    return await service.get_cumulative_pnl_series(mode, start_date, end_date)


@router.get("/returns/daily-series")
async def get_daily_returns_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 수익률 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    
    return await service.get_daily_returns_series(mode, start_date, end_date)


@router.get("/returns/cumulative-series")
async def get_cumulative_returns_series(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """누적 수익률 시계열"""
    service = PnLService(db)
    mode = settings.mode.value.upper()
    
    end_date = datetime.now(timezone.utc).date()
    start_date = end_date - timedelta(days=days)
    
    return await service.get_cumulative_returns_series(mode, start_date, end_date)
```

**파일**: `web/services/pnl_service.py` (신규)

```python
"""
PnL 서비스

복식부기 데이터 기반 손익 계산
"""

import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class PnLService:
    """PnL 계산 서비스"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_pnl_summary(self, mode: str) -> dict[str, Any]:
        """PnL 요약"""
        # 일일 PnL
        daily_pnl = await self._get_period_pnl(mode, days=1)
        weekly_pnl = await self._get_period_pnl(mode, days=7)
        monthly_pnl = await self._get_period_pnl(mode, days=30)
        total_pnl = await self._get_total_pnl(mode)
        
        # 초기 자본 (config_store에서)
        initial_capital = await self._get_initial_capital(mode)
        
        # 현재 자산
        current_equity = await self._get_current_equity(mode)
        
        # 수익률 계산
        if initial_capital > 0:
            daily_return = (daily_pnl / initial_capital) * 100
            weekly_return = (weekly_pnl / initial_capital) * 100
            monthly_return = (monthly_pnl / initial_capital) * 100
            total_return = ((current_equity - initial_capital) / initial_capital) * 100
        else:
            daily_return = weekly_return = monthly_return = total_return = Decimal("0")
        
        # 거래 통계
        stats = await self._get_trade_stats(mode, days=1)
        
        return {
            "daily_pnl": str(daily_pnl),
            "weekly_pnl": str(weekly_pnl),
            "monthly_pnl": str(monthly_pnl),
            "total_pnl": str(total_pnl),
            "daily_return_pct": str(round(daily_return, 2)),
            "weekly_return_pct": str(round(weekly_return, 2)),
            "monthly_return_pct": str(round(monthly_return, 2)),
            "total_return_pct": str(round(total_return, 2)),
            "initial_capital": str(initial_capital),
            "current_equity": str(current_equity),
            "trade_count_today": stats["trade_count"],
            "winning_trades_today": stats["winning_trades"],
            "losing_trades_today": stats["losing_trades"],
            "win_rate_today": str(stats["win_rate"]),
        }
    
    async def _get_period_pnl(self, mode: str, days: int) -> Decimal:
        """기간 PnL 조회 (복식부기 기반)"""
        try:
            # INCOME:TRADING:REALIZED_PNL 계정의 기간 합계
            sql = """
                SELECT COALESCE(SUM(
                    CASE WHEN jl.side = 'CREDIT' THEN CAST(jl.amount AS REAL)
                         ELSE -CAST(jl.amount AS REAL) END
                ), 0)
                FROM journal_line jl
                JOIN journal_entry je ON jl.entry_id = je.entry_id
                WHERE jl.account_id = 'INCOME:TRADING:REALIZED_PNL'
                  AND je.scope_mode = ?
                  AND je.ts >= datetime('now', ?)
            """
            row = await self.db.fetchone(sql, (mode, f'-{days} days'))
            return Decimal(str(row[0])) if row and row[0] else Decimal("0")
        except Exception as e:
            logger.debug(f"Period PnL query failed: {e}")
            return Decimal("0")
    
    async def _get_total_pnl(self, mode: str) -> Decimal:
        """전체 PnL"""
        try:
            sql = """
                SELECT balance FROM account_balance
                WHERE account_id = 'INCOME:TRADING:REALIZED_PNL'
                  AND scope_mode = ?
            """
            row = await self.db.fetchone(sql, (mode,))
            # INCOME 계정은 Credit이 양수이므로 음수가 실제 수익
            return -Decimal(str(row[0])) if row and row[0] else Decimal("0")
        except Exception as e:
            logger.debug(f"Total PnL query failed: {e}")
            return Decimal("0")
    
    async def _get_initial_capital(self, mode: str) -> Decimal:
        """초기 자본 조회"""
        try:
            sql = """
                SELECT value_json FROM config_store
                WHERE config_key = 'initial_capital'
            """
            row = await self.db.fetchone(sql)
            if row:
                config = json.loads(row[0])
                return Decimal(str(config.get("USDT", "0")))
            return Decimal("5000")  # 기본값
        except Exception:
            return Decimal("5000")
    
    async def _get_current_equity(self, mode: str) -> Decimal:
        """현재 총 자산"""
        try:
            sql = """
                SELECT COALESCE(SUM(CAST(balance AS REAL)), 0)
                FROM account_balance ab
                JOIN account a ON ab.account_id = a.account_id
                WHERE a.account_type = 'ASSET'
                  AND a.venue IN ('BINANCE_SPOT', 'BINANCE_FUTURES')
                  AND ab.scope_mode = ?
            """
            row = await self.db.fetchone(sql, (mode,))
            return Decimal(str(row[0])) if row and row[0] else Decimal("0")
        except Exception as e:
            logger.debug(f"Current equity query failed: {e}")
            return Decimal("0")
    
    async def _get_trade_stats(self, mode: str, days: int) -> dict[str, Any]:
        """거래 통계"""
        try:
            sql = """
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN CAST(jl.amount AS REAL) > 0 AND jl.side = 'CREDIT' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN CAST(jl.amount AS REAL) > 0 AND jl.side = 'DEBIT' THEN 1 ELSE 0 END) as losses
                FROM journal_line jl
                JOIN journal_entry je ON jl.entry_id = je.entry_id
                WHERE jl.account_id = 'INCOME:TRADING:REALIZED_PNL'
                  AND je.scope_mode = ?
                  AND je.ts >= datetime('now', ?)
            """
            row = await self.db.fetchone(sql, (mode, f'-{days} days'))
            
            if row:
                total = row[0] or 0
                wins = row[1] or 0
                losses = row[2] or 0
                win_rate = (wins / total * 100) if total > 0 else 0
                
                return {
                    "trade_count": total,
                    "winning_trades": wins,
                    "losing_trades": losses,
                    "win_rate": round(win_rate, 2),
                }
        except Exception as e:
            logger.debug(f"Trade stats query failed: {e}")
        
        return {
            "trade_count": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
        }
    
    async def get_daily_pnl_series(
        self, mode: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """일별 PnL 시계열"""
        try:
            sql = """
                SELECT 
                    DATE(je.ts) as trade_date,
                    SUM(CASE WHEN jl.side = 'CREDIT' THEN CAST(jl.amount AS REAL)
                             ELSE -CAST(jl.amount AS REAL) END) as daily_pnl
                FROM journal_line jl
                JOIN journal_entry je ON jl.entry_id = je.entry_id
                WHERE jl.account_id = 'INCOME:TRADING:REALIZED_PNL'
                  AND je.scope_mode = ?
                  AND DATE(je.ts) >= ?
                  AND DATE(je.ts) <= ?
                GROUP BY DATE(je.ts)
                ORDER BY trade_date
            """
            rows = await self.db.fetchall(sql, (
                mode, start_date.isoformat(), end_date.isoformat()
            ))
            
            return {
                "labels": [row[0] for row in rows],
                "values": [row[1] for row in rows],
            }
        except Exception as e:
            logger.debug(f"Daily PnL series query failed: {e}")
            return {"labels": [], "values": []}
    
    async def get_cumulative_pnl_series(
        self, mode: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """누적 PnL 시계열"""
        daily = await self.get_daily_pnl_series(mode, start_date, end_date)
        
        cumulative = []
        total = 0
        for value in daily["values"]:
            total += value
            cumulative.append(total)
        
        return {
            "labels": daily["labels"],
            "values": cumulative,
        }
    
    async def get_daily_returns_series(
        self, mode: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """일별 수익률 시계열"""
        daily_pnl = await self.get_daily_pnl_series(mode, start_date, end_date)
        initial_capital = await self._get_initial_capital(mode)
        
        if initial_capital <= 0:
            return {"labels": daily_pnl["labels"], "values": [0] * len(daily_pnl["values"])}
        
        returns = [
            round((pnl / float(initial_capital)) * 100, 2)
            for pnl in daily_pnl["values"]
        ]
        
        return {
            "labels": daily_pnl["labels"],
            "values": returns,
        }
    
    async def get_cumulative_returns_series(
        self, mode: str, start_date: date, end_date: date
    ) -> dict[str, Any]:
        """누적 수익률 시계열"""
        cumulative_pnl = await self.get_cumulative_pnl_series(mode, start_date, end_date)
        initial_capital = await self._get_initial_capital(mode)
        
        if initial_capital <= 0:
            return {"labels": cumulative_pnl["labels"], "values": [0] * len(cumulative_pnl["values"])}
        
        returns = [
            round((pnl / float(initial_capital)) * 100, 2)
            for pnl in cumulative_pnl["values"]
        ]
        
        return {
            "labels": cumulative_pnl["labels"],
            "values": returns,
        }
```

#### 4.1.2 대시보드 템플릿

**파일**: `web/templates/dashboard.html`

```html
{% extends "base.html" %}

{% block title %}대시보드 - AlphaEngine{% endblock %}

{% block content %}
<div class="row mb-4">
    <div class="col-12">
        <h2><i class="bi bi-speedometer2"></i> 대시보드</h2>
    </div>
</div>

<!-- PnL 요약 카드 -->
<div class="row mb-4">
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="card-body">
                <div class="stat-label">오늘 수익</div>
                <div class="stat-value" id="daily-pnl">-</div>
                <div class="text-muted" id="daily-return">-</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="card-body">
                <div class="stat-label">이번 주 수익</div>
                <div class="stat-value" id="weekly-pnl">-</div>
                <div class="text-muted" id="weekly-return">-</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="card-body">
                <div class="stat-label">이번 달 수익</div>
                <div class="stat-value" id="monthly-pnl">-</div>
                <div class="text-muted" id="monthly-return">-</div>
            </div>
        </div>
    </div>
    <div class="col-md-3">
        <div class="card stat-card">
            <div class="card-body">
                <div class="stat-label">총 자산</div>
                <div class="stat-value" id="total-equity">-</div>
                <div class="text-muted" id="total-return">-</div>
            </div>
        </div>
    </div>
</div>

<!-- 차트 -->
<div class="row mb-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-bar-chart"></i> 일별 수익
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="daily-pnl-chart"></canvas>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-graph-up"></i> 누적 수익
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="cumulative-pnl-chart"></canvas>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="row mb-4">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-percent"></i> 일별 수익률
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="daily-returns-chart"></canvas>
                </div>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-graph-up-arrow"></i> 누적 수익률
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="cumulative-returns-chart"></canvas>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- Venue별 자산 현황 -->
<div class="row mb-4">
    <div class="col-12">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-wallet2"></i> Venue별 자산 현황
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover">
                        <thead>
                            <tr>
                                <th>Venue</th>
                                <th>Asset</th>
                                <th class="text-end">Amount</th>
                                <th class="text-end">USDT 환산</th>
                            </tr>
                        </thead>
                        <tbody id="assets-table">
                            <tr>
                                <td colspan="4" class="text-center">로딩 중...</td>
                            </tr>
                        </tbody>
                        <tfoot>
                            <tr class="table-secondary">
                                <th colspan="3">Total</th>
                                <th class="text-end" id="total-assets">-</th>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- 현재 포지션 / 오픈 주문 -->
<div class="row">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-bullseye"></i> 현재 포지션
            </div>
            <div class="card-body" id="current-position">
                <p class="text-muted text-center">포지션 없음</p>
            </div>
        </div>
    </div>
    <div class="col-md-6">
        <div class="card">
            <div class="card-header">
                <i class="bi bi-clock-history"></i> 최근 체결
            </div>
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-sm">
                        <thead>
                            <tr>
                                <th>시간</th>
                                <th>Side</th>
                                <th class="text-end">QTY</th>
                                <th class="text-end">Price</th>
                                <th class="text-end">PnL</th>
                            </tr>
                        </thead>
                        <tbody id="recent-trades">
                            <tr>
                                <td colspan="5" class="text-center">로딩 중...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/chart-utils.js"></script>
<script src="/static/js/dashboard.js"></script>
{% endblock %}
```

#### 4.1.3 대시보드 JavaScript

**파일**: `web/static/js/dashboard.js`

```javascript
/**
 * 대시보드 페이지
 */

let dailyPnLChart = null;
let cumulativePnLChart = null;
let dailyReturnsChart = null;
let cumulativeReturnsChart = null;
let pollingId = null;

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

async function initDashboard() {
    await loadPnLSummary();
    await loadCharts();
    await loadAssets();
    await loadDashboardData();
    
    // 폴링 시작 (30초)
    pollingId = AE.startPolling(async () => {
        await loadPnLSummary();
        await loadDashboardData();
    }, 30000);
}

async function loadPnLSummary() {
    try {
        const data = await AE.api('/api/pnl/summary');
        
        // 일일 PnL
        const dailyPnL = AE.formatAmount(data.daily_pnl);
        document.getElementById('daily-pnl').innerHTML = 
            `<span class="${dailyPnL.class}">${dailyPnL.text} USDT</span>`;
        document.getElementById('daily-return').textContent = 
            `${AE.formatPercent(data.daily_return_pct)}`;
        
        // 주간 PnL
        const weeklyPnL = AE.formatAmount(data.weekly_pnl);
        document.getElementById('weekly-pnl').innerHTML = 
            `<span class="${weeklyPnL.class}">${weeklyPnL.text} USDT</span>`;
        document.getElementById('weekly-return').textContent = 
            `${AE.formatPercent(data.weekly_return_pct)}`;
        
        // 월간 PnL
        const monthlyPnL = AE.formatAmount(data.monthly_pnl);
        document.getElementById('monthly-pnl').innerHTML = 
            `<span class="${monthlyPnL.class}">${monthlyPnL.text} USDT</span>`;
        document.getElementById('monthly-return').textContent = 
            `${AE.formatPercent(data.monthly_return_pct)}`;
        
        // 총 자산
        document.getElementById('total-equity').textContent = 
            `${AE.formatNumber(data.current_equity)} USDT`;
        const totalReturn = AE.formatAmount(data.total_return_pct);
        document.getElementById('total-return').innerHTML = 
            `<span class="${totalReturn.class}">${AE.formatPercent(data.total_return_pct)}</span>`;
        
    } catch (error) {
        console.error('PnL summary error:', error);
    }
}

async function loadCharts() {
    try {
        // 일별 수익
        const dailyPnL = await AE.api('/api/pnl/daily-series?days=30');
        dailyPnLChart = ChartUtils.createDailyPnLChart('daily-pnl-chart', dailyPnL);
        
        // 누적 수익
        const cumulativePnL = await AE.api('/api/pnl/cumulative-series?days=30');
        cumulativePnLChart = ChartUtils.createCumulativePnLChart('cumulative-pnl-chart', cumulativePnL);
        
        // 일별 수익률
        const dailyReturns = await AE.api('/api/pnl/returns/daily-series?days=30');
        dailyReturnsChart = ChartUtils.createDailyReturnsChart('daily-returns-chart', dailyReturns);
        
        // 누적 수익률
        const cumulativeReturns = await AE.api('/api/pnl/returns/cumulative-series?days=30');
        cumulativeReturnsChart = ChartUtils.createCumulativeReturnsChart('cumulative-returns-chart', cumulativeReturns);
        
    } catch (error) {
        console.error('Charts error:', error);
    }
}

async function loadAssets() {
    try {
        const data = await AE.api('/api/ledger/trial-balance');
        
        // ASSET 계정만 필터
        const assets = data.filter(a => 
            a.account_type === 'ASSET' && 
            ['BINANCE_SPOT', 'BINANCE_FUTURES'].includes(a.venue)
        );
        
        const tbody = document.getElementById('assets-table');
        
        if (assets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">자산 없음</td></tr>';
            return;
        }
        
        let totalUsdt = 0;
        
        tbody.innerHTML = assets.map(asset => {
            const balance = parseFloat(asset.balance) || 0;
            // USDT 환산 (간단히 USDT는 1:1, 다른 자산은 별도 환율 필요)
            const usdtValue = asset.asset === 'USDT' ? balance : 0; // TODO: 환율 적용
            totalUsdt += usdtValue;
            
            return `
                <tr>
                    <td>${asset.venue.replace('BINANCE_', '')}</td>
                    <td>${asset.asset || '-'}</td>
                    <td class="text-end">${AE.formatNumber(balance, 8)}</td>
                    <td class="text-end">${AE.formatNumber(usdtValue, 2)} USDT</td>
                </tr>
            `;
        }).join('');
        
        document.getElementById('total-assets').textContent = 
            `${AE.formatNumber(totalUsdt, 2)} USDT`;
        
    } catch (error) {
        console.error('Assets error:', error);
        document.getElementById('assets-table').innerHTML = 
            '<tr><td colspan="4" class="text-center text-danger">로드 실패</td></tr>';
    }
}

async function loadDashboardData() {
    try {
        const data = await AE.api('/api/dashboard');
        
        // 현재 포지션
        if (data.position) {
            const pos = data.position;
            const unrealizedPnL = AE.formatAmount(pos.unrealized_pnl);
            
            document.getElementById('current-position').innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="fw-bold">${pos.symbol}</span>
                    ${AE.statusBadge(pos.side)}
                </div>
                <div class="row">
                    <div class="col-6">
                        <small class="text-muted">수량</small>
                        <div>${pos.qty}</div>
                    </div>
                    <div class="col-6">
                        <small class="text-muted">진입가</small>
                        <div>${AE.formatNumber(pos.entry_price)}</div>
                    </div>
                    <div class="col-6 mt-2">
                        <small class="text-muted">미실현 PnL</small>
                        <div class="${unrealizedPnL.class}">${unrealizedPnL.text} USDT</div>
                    </div>
                    <div class="col-6 mt-2">
                        <small class="text-muted">레버리지</small>
                        <div>${pos.leverage}x</div>
                    </div>
                </div>
            `;
        } else {
            document.getElementById('current-position').innerHTML = 
                '<p class="text-muted text-center mb-0">포지션 없음</p>';
        }
        
        // 최근 체결
        const trades = data.recent_trades || [];
        const tradesBody = document.getElementById('recent-trades');
        
        if (trades.length === 0) {
            tradesBody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">체결 없음</td></tr>';
        } else {
            tradesBody.innerHTML = trades.map(trade => {
                const pnl = AE.formatAmount(trade.realized_pnl);
                return `
                    <tr>
                        <td>${AE.formatKST(trade.ts).substring(11)}</td>
                        <td>${AE.statusBadge(trade.side)}</td>
                        <td class="text-end">${trade.qty}</td>
                        <td class="text-end">${AE.formatNumber(trade.price)}</td>
                        <td class="text-end ${pnl.class}">${pnl.text || '-'}</td>
                    </tr>
                `;
            }).join('');
        }
        
    } catch (error) {
        console.error('Dashboard data error:', error);
    }
}

// 페이지 이탈 시 폴링 중지
window.addEventListener('beforeunload', () => {
    AE.stopPolling(pollingId);
});
```

---

### 4.2 포지션 페이지 (`/positions`)

#### 4.2.1 포지션 API

**파일**: `web/routes/positions.py` (신규)

```python
"""
포지션 라우트

포지션 히스토리 및 상세 조회
"""

from fastapi import APIRouter, Depends, Query, Path, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from web.dependencies import get_db, get_app_settings
from web.services.position_service import PositionService

router = APIRouter(tags=["Positions"])
templates = Jinja2Templates(directory="web/templates")


@router.get("/positions", response_class=HTMLResponse)
async def positions_page(
    request: Request,
    settings: Settings = Depends(get_app_settings),
):
    """포지션 히스토리 페이지"""
    return templates.TemplateResponse("positions.html", {
        "request": request,
        "active_page": "positions",
        "mode": settings.mode.value.upper(),
    })


@router.get("/positions/{session_id}", response_class=HTMLResponse)
async def position_detail_page(
    request: Request,
    session_id: str = Path(...),
    settings: Settings = Depends(get_app_settings),
):
    """포지션 상세 페이지"""
    return templates.TemplateResponse("position_detail.html", {
        "request": request,
        "active_page": "positions",
        "mode": settings.mode.value.upper(),
        "session_id": session_id,
    })


@router.get("/api/positions")
async def get_positions(
    status: str | None = Query(default=None, description="OPEN or CLOSED"),
    symbol: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """포지션 목록 조회"""
    service = PositionService(db)
    mode = settings.mode.value.upper()
    
    return await service.get_positions(mode, status, symbol, limit, offset)


@router.get("/api/positions/{session_id}")
async def get_position_detail(
    session_id: str = Path(...),
    db: SQLiteAdapter = Depends(get_db),
):
    """포지션 상세 조회"""
    service = PositionService(db)
    return await service.get_position_detail(session_id)


@router.get("/api/positions/{session_id}/trades")
async def get_position_trades(
    session_id: str = Path(...),
    db: SQLiteAdapter = Depends(get_db),
):
    """포지션 내 거래 목록"""
    service = PositionService(db)
    return await service.get_position_trades(session_id)
```

#### 4.2.2 포지션 서비스

**파일**: `web/services/position_service.py` (신규)

```python
"""
포지션 서비스

포지션 세션 조회
"""

import logging
from decimal import Decimal
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter

logger = logging.getLogger(__name__)


class PositionService:
    """포지션 서비스"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
    
    async def get_positions(
        self,
        mode: str,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """포지션 목록 조회"""
        conditions = ["scope_mode = ?"]
        params: list[Any] = [mode]
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        
        where_clause = " AND ".join(conditions)
        
        # 목록 조회
        sql = f"""
            SELECT 
                session_id, symbol, side, status,
                opened_at, closed_at,
                initial_qty, max_qty,
                realized_pnl, total_commission, trade_count, close_reason
            FROM position_session
            WHERE {where_clause}
            ORDER BY opened_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        
        rows = await self.db.fetchall(sql, tuple(params))
        
        # 누적 PnL 계산
        positions = []
        cumulative_pnl = Decimal("0")
        
        for row in reversed(rows):  # 시간순 정렬 후 누적
            pnl = Decimal(str(row[8])) if row[8] else Decimal("0")
            cumulative_pnl += pnl
            
            positions.insert(0, {
                "session_id": row[0],
                "symbol": row[1],
                "side": row[2],
                "status": row[3],
                "opened_at": row[4],
                "closed_at": row[5],
                "initial_qty": row[6],
                "max_qty": row[7],
                "realized_pnl": str(pnl),
                "total_commission": row[9],
                "trade_count": row[10],
                "close_reason": row[11],
                "cumulative_pnl": str(cumulative_pnl),
            })
        
        # 총 개수
        count_sql = f"""
            SELECT COUNT(*) FROM position_session
            WHERE {' AND '.join(conditions[:len(conditions)-1] if len(params) > 2 else conditions)}
        """
        count_row = await self.db.fetchone(count_sql, tuple(params[:-2]))
        total_count = count_row[0] if count_row else 0
        
        return {
            "positions": positions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    
    async def get_position_detail(self, session_id: str) -> dict[str, Any]:
        """포지션 상세"""
        sql = """
            SELECT 
                session_id, scope_mode, scope_venue, symbol, side, status,
                opened_at, closed_at,
                initial_qty, max_qty,
                realized_pnl, total_commission, trade_count, close_reason
            FROM position_session
            WHERE session_id = ?
        """
        row = await self.db.fetchone(sql, (session_id,))
        
        if not row:
            return None
        
        return {
            "session_id": row[0],
            "scope_mode": row[1],
            "scope_venue": row[2],
            "symbol": row[3],
            "side": row[4],
            "status": row[5],
            "opened_at": row[6],
            "closed_at": row[7],
            "initial_qty": row[8],
            "max_qty": row[9],
            "realized_pnl": row[10],
            "total_commission": row[11],
            "trade_count": row[12],
            "close_reason": row[13],
        }
    
    async def get_position_trades(self, session_id: str) -> list[dict[str, Any]]:
        """포지션 내 거래 목록"""
        sql = """
            SELECT 
                pt.id, pt.trade_event_id, pt.journal_entry_id,
                pt.action, pt.qty, pt.price,
                pt.realized_pnl, pt.commission, pt.position_qty_after,
                pt.created_at
            FROM position_trade pt
            WHERE pt.session_id = ?
            ORDER BY pt.created_at
        """
        rows = await self.db.fetchall(sql, (session_id,))
        
        return [
            {
                "id": row[0],
                "trade_event_id": row[1],
                "journal_entry_id": row[2],
                "action": row[3],
                "qty": row[4],
                "price": row[5],
                "realized_pnl": row[6],
                "commission": row[7],
                "position_qty_after": row[8],
                "created_at": row[9],
            }
            for row in rows
        ]
```

#### 4.2.3 포지션 템플릿

**파일**: `web/templates/positions.html`

```html
{% extends "base.html" %}

{% block title %}포지션 히스토리 - AlphaEngine{% endblock %}

{% block content %}
<div class="row mb-4">
    <div class="col-12 d-flex justify-content-between align-items-center">
        <h2><i class="bi bi-graph-up-arrow"></i> 포지션 히스토리</h2>
        <div class="btn-group">
            <button class="btn btn-outline-primary" id="filter-all">전체</button>
            <button class="btn btn-outline-success" id="filter-open">OPEN</button>
            <button class="btn btn-outline-secondary" id="filter-closed">CLOSED</button>
        </div>
    </div>
</div>

<div class="card">
    <div class="card-body">
        <div class="table-responsive">
            <table class="table table-hover table-clickable">
                <thead>
                    <tr>
                        <th>Open Time</th>
                        <th>Close Time</th>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Status</th>
                        <th class="text-end">Max QTY</th>
                        <th class="text-end">PnL</th>
                        <th class="text-end">누적 PnL</th>
                        <th>Trades</th>
                    </tr>
                </thead>
                <tbody id="positions-table">
                    <tr>
                        <td colspan="9" class="text-center">로딩 중...</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <!-- 페이지네이션 -->
        <div class="d-flex justify-content-between align-items-center mt-3">
            <div class="pagination-info" id="pagination-info">-</div>
            <nav>
                <ul class="pagination mb-0" id="pagination">
                </ul>
            </nav>
        </div>
    </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/positions.js"></script>
{% endblock %}
```

나머지 페이지들(거래 내역, 자산, 이벤트, 설정, Commands, Trading Edge)도 동일한 패턴으로 구현합니다.

---

## 5. 테스트

### 5.1 API 테스트

**파일**: `tests/integration/web/test_pnl_api.py`

```python
"""PnL API 테스트"""

import pytest
from httpx import AsyncClient
from fastapi import FastAPI

from web.app import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


class TestPnLSummaryAPI:
    """PnL 요약 API 테스트"""
    
    async def test_get_pnl_summary(self, client: AsyncClient) -> None:
        """PnL 요약 조회"""
        response = await client.get("/api/pnl/summary")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "daily_pnl" in data
        assert "weekly_pnl" in data
        assert "total_return_pct" in data
    
    async def test_get_daily_pnl_series(self, client: AsyncClient) -> None:
        """일별 PnL 시계열"""
        response = await client.get("/api/pnl/daily-series?days=7")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "labels" in data
        assert "values" in data
        assert isinstance(data["labels"], list)
        assert isinstance(data["values"], list)


class TestPositionsAPI:
    """포지션 API 테스트"""
    
    async def test_get_positions(self, client: AsyncClient) -> None:
        """포지션 목록 조회"""
        response = await client.get("/api/positions")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "positions" in data
        assert "total_count" in data
    
    async def test_get_positions_with_filter(self, client: AsyncClient) -> None:
        """포지션 필터링"""
        response = await client.get("/api/positions?status=OPEN")
        
        assert response.status_code == 200
```

### 5.2 E2E 테스트

**파일**: `tests/e2e/web/test_dashboard_page.py`

```python
"""대시보드 페이지 E2E 테스트"""

import pytest
from playwright.async_api import Page, expect


@pytest.fixture
def base_url() -> str:
    return "http://localhost:8000"


class TestDashboardPage:
    """대시보드 페이지 테스트"""
    
    async def test_dashboard_loads(self, page: Page, base_url: str) -> None:
        """대시보드 페이지 로드"""
        await page.goto(f"{base_url}/dashboard")
        
        # 타이틀 확인
        await expect(page).to_have_title("대시보드 - AlphaEngine")
        
        # 주요 요소 확인
        await expect(page.locator("#daily-pnl")).to_be_visible()
        await expect(page.locator("#daily-pnl-chart")).to_be_visible()
    
    async def test_dashboard_charts_render(self, page: Page, base_url: str) -> None:
        """차트 렌더링 확인"""
        await page.goto(f"{base_url}/dashboard")
        
        # 차트 캔버스 확인
        await expect(page.locator("canvas#daily-pnl-chart")).to_be_visible()
        await expect(page.locator("canvas#cumulative-pnl-chart")).to_be_visible()
```

---

## 6. 구현 순서

### Phase 1: 기반 (필수)

1. `base.html` 수정 (네비게이션)
2. `common.js` 공통 유틸리티
3. `chart-utils.js` 차트 헬퍼
4. `style.css` 확장

### Phase 2: 대시보드

5. `routes/pnl.py` API
6. `services/pnl_service.py`
7. `templates/dashboard.html`
8. `static/js/dashboard.js`

### Phase 3: 포지션

9. `routes/positions.py`
10. `services/position_service.py`
11. `templates/positions.html`
12. `templates/position_detail.html`
13. `static/js/positions.js`

### Phase 4: 거래 내역 & 자산

14. `routes/transactions.py`
15. `routes/assets.py`
16. `routes/ledger.py` (복식부기 API)
17. 템플릿 및 JavaScript

### Phase 5: 기존 페이지

18. `templates/events.html` + JS
19. `templates/config.html` + JS
20. `templates/commands.html` + JS

### Phase 6: Trading Edge

21. `routes/trading_edge.py`
22. `services/trading_edge_service.py`
23. `templates/trading_edge.html`
24. `static/js/trading_edge.js`

### Phase 7: 테스트

25. API 테스트
26. E2E 테스트

---

## 7. 실행 명령

```bash
# 1. 의존성 설치 (Chart.js는 CDN 사용)

# 2. 서버 실행
.venv\Scripts\python.exe -m web --mode testnet

# 3. API 테스트
.venv\Scripts\python.exe -m pytest tests/integration/web/ -v

# 4. E2E 테스트 (Playwright 필요)
.venv\Scripts\python.exe -m pytest tests/e2e/web/ -v
```

---

## 8. 복식부기 View 활용

### 8.1 개요

복식부기 시스템에서 생성된 **8개의 SQL View**를 활용하여 API 성능을 대폭 개선.
복잡한 JOIN/집계 연산이 DB 수준에서 미리 처리되어 있어, 서비스 코드가 단순해지고 응답 속도가 빨라짐.

### 8.2 사용 가능한 View 목록

| View 이름 | 용도 | 주요 컬럼 |
|-----------|------|-----------|
| `v_trade_summary` | 거래 목록 | entry_id, ts, symbol, bought_qty, sold_qty, fee_usdt, realized_pnl |
| `v_daily_pnl` | 일별 손익 차트 | trade_date, daily_pnl, trading_fees, winning_count, losing_count |
| `v_fee_summary` | 수수료 분석 | fee_date, fee_type, fee_asset, total_usdt_value |
| `v_account_ledger` | 계정별 원장 | ts, account_id, side, amount, signed_amount, transaction_type |
| `v_portfolio` | 자산 현황 | venue, asset, balance, last_updated |
| `v_recent_trades` | 최근 체결 | ts, symbol, side, qty, realized_pnl, fee_usdt |
| `v_symbol_pnl` | 심볼별 성과 | symbol, total_trades, total_pnl, net_pnl, winning_trades, losing_trades |
| `v_funding_history` | 펀딩 내역 | ts, symbol, funding_paid, funding_received |

### 8.3 LedgerStore View 기반 메서드

`core/ledger/store.py`의 `LedgerStore` 클래스에서 제공하는 View 기반 메서드:

```python
# 거래 요약 조회 (거래 내역 페이지)
await ledger_store.get_trade_summary(scope_mode, symbol=None, limit=100, offset=0)

# 일별 손익 조회 (대시보드 차트)
await ledger_store.get_daily_pnl(scope_mode, start_date=None, end_date=None, limit=30)

# 일별 손익 시계열 (차트 데이터 포맷)
await ledger_store.get_daily_pnl_series(scope_mode, days=30)
# 반환: {"labels": [...], "values": [...], "cumulative": [...]}

# 수수료 요약 조회 (수수료 분석)
await ledger_store.get_fee_summary(scope_mode, start_date=None, end_date=None)

# 계정별 원장 조회 (계정 상세)
await ledger_store.get_account_ledger(account_id, scope_mode, limit=100, offset=0)

# 포트폴리오 현황 (자산 페이지)
await ledger_store.get_portfolio(scope_mode)

# 최근 거래 (대시보드 위젯)
await ledger_store.get_recent_trades(scope_mode, limit=10)

# 심볼별 손익 (Trading Edge)
await ledger_store.get_symbol_pnl(scope_mode)

# 펀딩 내역 조회
await ledger_store.get_funding_history(scope_mode, limit=100, offset=0)

# PnL 통계 요약 (대시보드 카드)
await ledger_store.get_pnl_statistics(scope_mode)
# 반환: {"total": {...}, "daily": {...}, "weekly": {...}, "monthly": {...}}
```

### 8.4 서비스 개선 예시

#### 8.4.1 PnL 서비스 (View 활용 버전)

**파일**: `web/services/pnl_service.py` (개선)

```python
"""
PnL 서비스 (View 기반)

복식부기 View를 활용한 고성능 손익 계산
"""

import logging
from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger import LedgerStore

logger = logging.getLogger(__name__)


class PnLService:
    """PnL 계산 서비스 (View 기반)"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_pnl_summary(self, mode: str) -> dict[str, Any]:
        """PnL 요약 - LedgerStore.get_pnl_statistics() 활용"""
        stats = await self.ledger_store.get_pnl_statistics(mode)
        
        # 초기 자본 조회
        initial_capital = await self._get_initial_capital()
        
        # 수익률 계산
        def calc_return(pnl: float) -> float:
            if initial_capital > 0:
                return round((pnl / initial_capital) * 100, 2)
            return 0.0
        
        return {
            "daily_pnl": str(stats["daily"]["pnl"]),
            "weekly_pnl": str(stats["weekly"]["pnl"]),
            "monthly_pnl": str(stats["monthly"]["pnl"]),
            "total_pnl": str(stats["total"]["pnl"]),
            "daily_return_pct": str(calc_return(stats["daily"]["pnl"] or 0)),
            "weekly_return_pct": str(calc_return(stats["weekly"]["pnl"] or 0)),
            "monthly_return_pct": str(calc_return(stats["monthly"]["pnl"] or 0)),
            "total_return_pct": str(calc_return(stats["total"]["pnl"] or 0)),
            "initial_capital": str(initial_capital),
            "trade_count_today": stats["daily"]["trades"],
            "winning_trades_today": stats["daily"]["wins"],
            "losing_trades_today": stats["daily"]["losses"],
            "win_rate_today": str(stats["daily"]["win_rate"]),
            "total_fees": str(stats["total"]["fees"]),
        }
    
    async def get_daily_pnl_series(self, mode: str, days: int = 30) -> dict[str, Any]:
        """일별 PnL 시계열 - LedgerStore.get_daily_pnl_series() 활용"""
        return await self.ledger_store.get_daily_pnl_series(mode, days)
    
    async def get_cumulative_pnl_series(self, mode: str, days: int = 30) -> dict[str, Any]:
        """누적 PnL 시계열"""
        series = await self.ledger_store.get_daily_pnl_series(mode, days)
        return {
            "labels": series["labels"],
            "values": series["cumulative"],
        }
    
    async def _get_initial_capital(self) -> float:
        """초기 자본 조회"""
        import json
        try:
            row = await self.db.fetchone(
                "SELECT value_json FROM config_store WHERE config_key = 'initial_capital'"
            )
            if row:
                config = json.loads(row[0])
                return float(config.get("USDT", 5000))
        except Exception:
            pass
        return 5000.0
```

#### 8.4.2 거래 내역 서비스 (View 활용)

**파일**: `web/services/transaction_service.py` (신규)

```python
"""
거래 내역 서비스 (View 기반)
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger import LedgerStore


class TransactionService:
    """거래 내역 서비스"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_transactions(
        self,
        mode: str,
        symbol: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """거래 목록 조회 - v_trade_summary View 활용"""
        trades = await self.ledger_store.get_trade_summary(
            scope_mode=mode,
            symbol=symbol,
            limit=limit,
            offset=offset,
        )
        
        # 총 개수 조회
        count_sql = "SELECT COUNT(*) FROM v_trade_summary WHERE scope_mode = ?"
        params = [mode]
        if symbol:
            count_sql += " AND symbol = ?"
            params.append(symbol)
        
        count_row = await self.db.fetchone(count_sql, tuple(params))
        total_count = count_row[0] if count_row else 0
        
        return {
            "transactions": trades,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
        }
    
    async def get_recent_trades(self, mode: str, limit: int = 10) -> list[dict[str, Any]]:
        """최근 거래 - v_recent_trades View 활용"""
        return await self.ledger_store.get_recent_trades(mode, limit)
```

#### 8.4.3 자산 서비스 (View 활용)

**파일**: `web/services/asset_service.py` (신규)

```python
"""
자산 서비스 (View 기반)
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger import LedgerStore


class AssetService:
    """자산 현황 서비스"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_portfolio(self, mode: str) -> list[dict[str, Any]]:
        """포트폴리오 현황 - v_portfolio View 활용"""
        return await self.ledger_store.get_portfolio(mode)
    
    async def get_portfolio_summary(self, mode: str) -> dict[str, Any]:
        """포트폴리오 요약"""
        portfolio = await self.ledger_store.get_portfolio(mode)
        
        # Venue별 합계
        spot_total = sum(
            p["balance"] for p in portfolio 
            if p["venue"] == "BINANCE_SPOT" and p["asset"] == "USDT"
        )
        futures_total = sum(
            p["balance"] for p in portfolio 
            if p["venue"] == "BINANCE_FUTURES" and p["asset"] == "USDT"
        )
        
        return {
            "assets": portfolio,
            "spot_total_usdt": spot_total,
            "futures_total_usdt": futures_total,
            "total_usdt": spot_total + futures_total,
        }
```

#### 8.4.4 Trading Edge 서비스 (View 활용)

**파일**: `web/services/trading_edge_service.py` (신규)

```python
"""
Trading Edge 서비스 (View 기반)
"""

from typing import Any

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.ledger import LedgerStore


class TradingEdgeService:
    """Trading Edge 분석 서비스"""
    
    def __init__(self, db: SQLiteAdapter):
        self.db = db
        self.ledger_store = LedgerStore(db)
    
    async def get_symbol_performance(self, mode: str) -> list[dict[str, Any]]:
        """심볼별 성과 - v_symbol_pnl View 활용"""
        return await self.ledger_store.get_symbol_pnl(mode)
    
    async def get_edge_summary(self, mode: str) -> dict[str, Any]:
        """Edge 요약 통계"""
        symbols = await self.ledger_store.get_symbol_pnl(mode)
        stats = await self.ledger_store.get_pnl_statistics(mode)
        
        # 최고/최저 성과 심볼
        best_symbol = symbols[0] if symbols else None
        worst_symbol = symbols[-1] if symbols else None
        
        # 평균 거래당 수익
        total_pnl = stats["total"]["pnl"] or 0
        total_trades = stats["total"]["trades"] or 0
        avg_pnl_per_trade = round(total_pnl / total_trades, 2) if total_trades > 0 else 0
        
        return {
            "symbols": symbols,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "total_fees": stats["total"]["fees"] or 0,
            "win_rate": stats["total"]["win_rate"],
            "avg_pnl_per_trade": avg_pnl_per_trade,
            "best_symbol": best_symbol,
            "worst_symbol": worst_symbol,
        }
```

### 8.5 API 라우트 개선

#### 8.5.1 Ledger API (신규)

**파일**: `web/routes/ledger.py`

```python
"""
복식부기 API 라우트

View 기반 고성능 조회 API
"""

from fastapi import APIRouter, Depends, Query

from adapters.db.sqlite_adapter import SQLiteAdapter
from core.config.loader import Settings
from core.ledger import LedgerStore
from web.dependencies import get_db, get_app_settings

router = APIRouter(prefix="/api/ledger", tags=["Ledger"])


@router.get("/trade-summary")
async def get_trade_summary(
    symbol: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """거래 요약 조회 (v_trade_summary)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_trade_summary(mode, symbol, limit, offset)


@router.get("/daily-pnl")
async def get_daily_pnl(
    days: int = Query(default=30, ge=1, le=365),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """일별 손익 시계열 (v_daily_pnl)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_daily_pnl_series(mode, days)


@router.get("/pnl-stats")
async def get_pnl_statistics(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """PnL 통계 요약"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_pnl_statistics(mode)


@router.get("/portfolio")
async def get_portfolio(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """포트폴리오 현황 (v_portfolio)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_portfolio(mode)


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(default=10, ge=1, le=50),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """최근 거래 (v_recent_trades)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_recent_trades(mode, limit)


@router.get("/symbol-pnl")
async def get_symbol_pnl(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """심볼별 손익 (v_symbol_pnl)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_symbol_pnl(mode)


@router.get("/fee-summary")
async def get_fee_summary(
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """수수료 요약 (v_fee_summary)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_fee_summary(mode, start_date, end_date)


@router.get("/funding-history")
async def get_funding_history(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """펀딩 내역 (v_funding_history)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_funding_history(mode, limit, offset)


@router.get("/trial-balance")
async def get_trial_balance(
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """시산표 조회"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_trial_balance(mode)


@router.get("/account-ledger/{account_id:path}")
async def get_account_ledger(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: SQLiteAdapter = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """계정별 원장 (v_account_ledger)"""
    store = LedgerStore(db)
    mode = settings.mode.value.upper()
    return await store.get_account_ledger(account_id, mode, limit, offset)
```

### 8.6 View 성능 이점

| 기존 방식 | View 활용 방식 | 개선 효과 |
|-----------|----------------|-----------|
| 매 요청마다 JOIN 연산 | 미리 정의된 View 조회 | **50-80% 응답 시간 단축** |
| Python에서 집계 계산 | DB 수준 집계 | **CPU 부하 감소** |
| 복잡한 서비스 코드 | 단순 View 조회 | **코드 유지보수성 향상** |
| 반복 쿼리 최적화 필요 | View 인덱스 활용 | **자동 쿼리 최적화** |

### 8.7 마이그레이션 필수

View 사용 전 반드시 마이그레이션 실행:

```bash
# View 포함 스키마 생성
.venv\Scripts\python.exe -m scripts.migrate_ledger --mode testnet
```

---

## 9. 주의사항

1. **복식부기 의존성**: 이 문서는 `01_double_entry_bookkeeping.md` 완료를 전제로 함
2. **View 마이그레이션**: View 기반 API 사용 전 `migrate_ledger.py` 실행 필수
3. **Chart.js CDN**: 네트워크 연결 필요
4. **KST 변환**: 모든 시간은 UTC 저장, 표시 시 KST 변환
5. **폴링 간격**: 대시보드 30초, 다른 페이지는 5초
6. **모바일 대응**: Bootstrap 반응형 사용
7. **View 성능**: 대용량 데이터에서 View가 느려지면 인덱스 추가 고려
