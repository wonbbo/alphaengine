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
     * 가격 포맷팅 (소수점 4자리)
     */
    formatPrice(value) {
        if (value === null || value === undefined || value === '') return '-';
        const num = parseFloat(value);
        if (isNaN(num)) return value;
        return num.toLocaleString('ko-KR', {
            minimumFractionDigits: 4,
            maximumFractionDigits: 4,
        });
    },
    
    /**
     * 수수료 포맷팅 (소수점 6자리 + USDT 단위)
     */
    formatCommission(value) {
        if (value === null || value === undefined || value === '') return '-';
        const num = parseFloat(value);
        if (isNaN(num)) return value;
        const formatted = num.toLocaleString('ko-KR', {
            minimumFractionDigits: 6,
            maximumFractionDigits: 6,
        });
        return `${formatted}`;
    },
    
    /**
     * 금액 포맷팅 (색상 포함, PnL용 소수점 4자리)
     */
    formatAmount(value, decimals = 4) {
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
     * 계정 타입 배지 (색상 + 한글명)
     */
    formatAccountType(type) {
        const types = {
            'ASSET': { label: '자산', color: 'bg-primary', icon: 'bi-wallet2' },
            'EXPENSE': { label: '비용', color: 'bg-danger', icon: 'bi-dash-circle' },
            'INCOME': { label: '수익', color: 'bg-success', icon: 'bi-plus-circle' },
            'EQUITY': { label: '자본', color: 'bg-info', icon: 'bi-bank' },
        };
        const config = types[type] || { label: type, color: 'bg-secondary', icon: 'bi-question-circle' };
        return `<span class="badge ${config.color}"><i class="bi ${config.icon}"></i> ${config.label}</span>`;
    },
    
    /**
     * Venue(계좌) 배지 (색상 + 한글명)
     */
    formatVenue(venue) {
        const venues = {
            'BINANCE_SPOT': { label: '현물', color: 'bg-warning text-dark', icon: 'bi-coin' },
            'BINANCE_FUTURES': { label: '선물', color: 'bg-primary', icon: 'bi-graph-up-arrow' },
            'EXTERNAL': { label: '외부', color: 'bg-external', icon: 'bi-box-arrow-up-right' },
            'SYSTEM': { label: '시스템', color: 'bg-system', icon: 'bi-gear' },
        };
        const config = venues[venue] || { label: venue || '-', color: 'bg-secondary', icon: 'bi-question-circle' };
        return `<span class="badge ${config.color}"><i class="bi ${config.icon}"></i> ${config.label}</span>`;
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
            // 거래 방향
            'BUY': 'bg-success',
            'SELL': 'bg-danger',
            // Transfer 상태
            'PENDING': 'bg-warning',
            'COMPLETED': 'bg-success',
            'CANCELLED': 'bg-secondary',
        };
        
        const bgClass = badges[status] || 'bg-secondary';
        return `<span class="badge ${bgClass}">${status}</span>`;
    },
    
    /**
     * 이벤트/커맨드 타입 카테고리 및 한글 매핑
     * 카테고리별 색상:
     *   - engine: 보라색 (엔진/제어)
     *   - websocket: 회색 (웹소켓)
     *   - order: 파란색 (주문/체결)
     *   - position: 청록색 (포지션/잔고/수수료)
     *   - transfer: 주황색 (내부이체)
     *   - deposit: 초록색 (입금)
     *   - withdraw: 빨간색 (출금)
     *   - reconcile: 노란색 (정합성/감사)
     *   - strategy: 남색 (전략)
     *   - bnb: 황금색 (BNB 수수료)
     */
    _typeConfig: {
        // 카테고리별 색상 정의
        categories: {
            engine: { color: 'bg-purple', textColor: 'text-white' },
            websocket: { color: 'bg-secondary', textColor: 'text-white' },
            order: { color: 'bg-primary', textColor: 'text-white' },
            position: { color: 'bg-info', textColor: 'text-dark' },
            transfer: { color: 'bg-orange', textColor: 'text-white' },
            deposit: { color: 'bg-success', textColor: 'text-white' },
            withdraw: { color: 'bg-danger', textColor: 'text-white' },
            reconcile: { color: 'bg-warning', textColor: 'text-dark' },
            strategy: { color: 'bg-indigo', textColor: 'text-white' },
            bnb: { color: 'bg-gold', textColor: 'text-dark' },
            unknown: { color: 'bg-secondary', textColor: 'text-white' },
        },
        
        // 이벤트 타입 매핑 (타입명 -> { ko: 한글명, category: 카테고리 })
        events: {
            // 엔진 / 제어
            "EngineStarted": { ko: "엔진 시작", category: "engine" },
            "EngineStopped": { ko: "엔진 중지", category: "engine" },
            "EnginePaused": { ko: "엔진 일시정지", category: "engine" },
            "EngineResumed": { ko: "엔진 재개", category: "engine" },
            "EngineModeChanged": { ko: "엔진 모드 변경", category: "engine" },
            "ManualOverrideExecuted": { ko: "수동 오버라이드", category: "engine" },
            "RiskGuardRejected": { ko: "리스크 가드 거부", category: "engine" },
            "ConfigChanged": { ko: "설정 변경", category: "engine" },
            
            // 웹소켓 연결
            "WebSocketConnected": { ko: "웹소켓 연결", category: "websocket" },
            "WebSocketDisconnected": { ko: "웹소켓 끊김", category: "websocket" },
            "WebSocketReconnected": { ko: "웹소켓 재연결", category: "websocket" },
            
            // 주문 / 체결
            "OrderPlaced": { ko: "주문 생성", category: "order" },
            "OrderRejected": { ko: "주문 거부", category: "order" },
            "OrderCancelled": { ko: "주문 취소", category: "order" },
            "OrderUpdated": { ko: "주문 업데이트", category: "order" },
            "TradeExecuted": { ko: "체결", category: "order" },
            
            // 포지션 / 잔고 / 수수료
            "PositionChanged": { ko: "포지션 변경", category: "position" },
            "BalanceChanged": { ko: "잔고 변경", category: "position" },
            "FeeCharged": { ko: "수수료 부과", category: "position" },
            "FundingApplied": { ko: "펀딩비 적용", category: "position" },
            
            // 내부 이체
            "InternalTransferRequested": { ko: "내부이체 요청", category: "transfer" },
            "InternalTransferCompleted": { ko: "내부이체 완료", category: "transfer" },
            "InternalTransferFailed": { ko: "내부이체 실패", category: "transfer" },
            
            // 입금
            "DepositDetected": { ko: "입금 감지", category: "deposit" },
            "DepositInitiated": { ko: "입금 시작", category: "deposit" },
            "DepositTrxPurchased": { ko: "TRX 매수 (입금)", category: "deposit" },
            "DepositTrxSent": { ko: "TRX 전송 (입금)", category: "deposit" },
            "DepositTrxReceived": { ko: "TRX 수신 (입금)", category: "deposit" },
            "DepositUsdtConverted": { ko: "USDT 환전 (입금)", category: "deposit" },
            "DepositSpotTransferred": { ko: "현물→선물 이체", category: "deposit" },
            "DepositCompleted": { ko: "입금 완료", category: "deposit" },
            
            // 출금
            "WithdrawRequested": { ko: "출금 요청", category: "withdraw" },
            "WithdrawFailed": { ko: "출금 실패", category: "withdraw" },
            "WithdrawInitiated": { ko: "출금 시작", category: "withdraw" },
            "WithdrawFuturesTransferred": { ko: "선물→현물 이체", category: "withdraw" },
            "WithdrawUsdtConverted": { ko: "TRX 환전 (출금)", category: "withdraw" },
            "WithdrawTrxSent": { ko: "TRX 전송 (출금)", category: "withdraw" },
            "WithdrawTrxReceived": { ko: "TRX 수신 (출금)", category: "withdraw" },
            "WithdrawKrwConverted": { ko: "KRW 환전 (출금)", category: "withdraw" },
            "WithdrawCompleted": { ko: "출금 완료", category: "withdraw" },
            
            // 정합성 / 감사
            "DriftDetected": { ko: "드리프트 감지", category: "reconcile" },
            "ReconciliationPerformed": { ko: "정합성 검증", category: "reconcile" },
            "QuarantineStarted": { ko: "격리 시작", category: "reconcile" },
            "QuarantineCompleted": { ko: "격리 완료", category: "reconcile" },
            
            // 전략
            "StrategyLoaded": { ko: "전략 로드", category: "strategy" },
            "StrategyStarted": { ko: "전략 시작", category: "strategy" },
            "StrategyStopped": { ko: "전략 중지", category: "strategy" },
            "StrategyError": { ko: "전략 오류", category: "strategy" },
            
            // BNB 수수료 관리
            "BnbBalanceLow": { ko: "BNB 잔고 부족", category: "bnb" },
            "BnbReplenishStarted": { ko: "BNB 충전 시작", category: "bnb" },
            "BnbReplenishCompleted": { ko: "BNB 충전 완료", category: "bnb" },
            "BnbReplenishFailed": { ko: "BNB 충전 실패", category: "bnb" },
        },
        
        // 커맨드 타입 매핑 (타입명 -> { ko: 한글명, category: 카테고리 })
        commands: {
            // 엔진 / 제어
            "PauseEngine": { ko: "엔진 일시정지", category: "engine" },
            "ResumeEngine": { ko: "엔진 재개", category: "engine" },
            "SetEngineMode": { ko: "엔진 모드 설정", category: "engine" },
            "CancelAll": { ko: "전체 주문 취소", category: "engine" },
            "RunReconcile": { ko: "정합성 검증", category: "reconcile" },
            "RebuildProjection": { ko: "프로젝션 재구축", category: "engine" },
            "UpdateConfig": { ko: "설정 업데이트", category: "engine" },
            
            // 거래
            "PlaceOrder": { ko: "주문 생성", category: "order" },
            "CancelOrder": { ko: "주문 취소", category: "order" },
            "ClosePosition": { ko: "포지션 청산", category: "order" },
            "SetLeverage": { ko: "레버리지 설정", category: "order" },
            
            // 이체
            "InternalTransfer": { ko: "내부 이체", category: "transfer" },
            "Withdraw": { ko: "출금", category: "withdraw" },
            "Deposit": { ko: "입금", category: "deposit" },
            "CancelTransfer": { ko: "이체 취소", category: "transfer" },
        },
    },
    
    /**
     * 이벤트 타입 한글명 반환
     */
    getEventTypeKo(eventType) {
        const config = this._typeConfig.events[eventType];
        return config ? config.ko : eventType;
    },
    
    /**
     * 커맨드 타입 한글명 반환
     */
    getCommandTypeKo(commandType) {
        const config = this._typeConfig.commands[commandType];
        return config ? config.ko : commandType;
    },
    
    /**
     * 이벤트 타입 배지 생성 (한글 + 카테고리 색상)
     */
    eventTypeBadge(eventType) {
        const config = this._typeConfig.events[eventType];
        const ko = config ? config.ko : eventType;
        const category = config ? config.category : 'unknown';
        const catConfig = this._typeConfig.categories[category];
        
        return `<span class="badge ${catConfig.color} ${catConfig.textColor}" title="${eventType}">${ko}</span>`;
    },
    
    /**
     * 커맨드 타입 배지 생성 (한글 + 카테고리 색상)
     */
    commandTypeBadge(commandType) {
        const config = this._typeConfig.commands[commandType];
        const ko = config ? config.ko : commandType;
        const category = config ? config.category : 'unknown';
        const catConfig = this._typeConfig.categories[category];
        
        return `<span class="badge ${catConfig.color} ${catConfig.textColor}" title="${commandType}">${ko}</span>`;
    },
    
    /**
     * 타입 셀렉트 옵션 텍스트 생성 (한글명 + 영문명)
     */
    getEventTypeOptionText(eventType) {
        const ko = this.getEventTypeKo(eventType);
        return ko !== eventType ? `${ko} (${eventType})` : eventType;
    },
    
    /**
     * 타입 셀렉트 옵션 텍스트 생성 (한글명 + 영문명)
     */
    getCommandTypeOptionText(commandType) {
        const ko = this.getCommandTypeKo(commandType);
        return ko !== commandType ? `${ko} (${commandType})` : commandType;
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
     * 빈 상태 표시
     */
    showEmpty(elementId, message = '데이터가 없습니다.') {
        const el = document.getElementById(elementId);
        if (el) {
            el.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-inbox" style="font-size: 2rem;"></i>
                    <p class="mt-2">${message}</p>
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
        callback();
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
    
    /**
     * URL 쿼리 파라미터 생성
     */
    buildQueryString(params) {
        const query = Object.entries(params)
            .filter(([_, v]) => v !== null && v !== undefined && v !== '')
            .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
            .join('&');
        return query ? `?${query}` : '';
    },
    
    /**
     * 페이지네이션 생성
     */
    createPagination(totalCount, limit, offset, onPageClick) {
        const currentPage = Math.floor(offset / limit) + 1;
        const totalPages = Math.ceil(totalCount / limit);
        
        let html = '';
        
        // 이전 버튼
        html += `
            <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage - 1}">이전</a>
            </li>
        `;
        
        // 페이지 번호
        const startPage = Math.max(1, currentPage - 2);
        const endPage = Math.min(totalPages, currentPage + 2);
        
        for (let i = startPage; i <= endPage; i++) {
            html += `
                <li class="page-item ${i === currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        // 다음 버튼
        html += `
            <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage + 1}">다음</a>
            </li>
        `;
        
        return html;
    },
    
    /**
     * 확인 다이얼로그
     */
    async confirm(message) {
        return window.confirm(message);
    },
    
    /**
     * 디바운스
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
};

// 전역 객체로 노출
window.AE = AlphaEngine;
