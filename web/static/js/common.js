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
            // Transfer 상태
            'PENDING': 'bg-warning',
            'COMPLETED': 'bg-success',
            'CANCELLED': 'bg-secondary',
            // Event 타입
            'TradeExecuted': 'bg-info',
            'OrderPlaced': 'bg-primary',
            'PositionUpdated': 'bg-warning',
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
