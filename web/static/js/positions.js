/**
 * 포지션 페이지
 */

let currentFilter = null;
let currentLimit = 50;
let currentOffset = 0;

document.addEventListener('DOMContentLoaded', () => {
    // 상세 페이지인 경우
    if (typeof SESSION_ID !== 'undefined' && SESSION_ID) {
        loadPositionDetail(SESSION_ID);
        loadPositionTrades(SESSION_ID);
    } else {
        // 목록 페이지
        initPositionsList();
    }
});

// =========================================================================
// 포지션 목록
// =========================================================================

function initPositionsList() {
    // 필터 버튼 이벤트
    document.getElementById('filter-all')?.addEventListener('click', () => setFilter(null));
    document.getElementById('filter-open')?.addEventListener('click', () => setFilter('OPEN'));
    document.getElementById('filter-closed')?.addEventListener('click', () => setFilter('CLOSED'));
    
    // 초기 로드
    loadPositions();
}

function setFilter(status) {
    currentFilter = status;
    currentOffset = 0;
    
    // 버튼 활성화 상태 업데이트
    document.querySelectorAll('.btn-group .btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    if (status === null) {
        document.getElementById('filter-all')?.classList.add('active');
    } else if (status === 'OPEN') {
        document.getElementById('filter-open')?.classList.add('active');
    } else if (status === 'CLOSED') {
        document.getElementById('filter-closed')?.classList.add('active');
    }
    
    loadPositions();
}

async function loadPositions() {
    const tbody = document.getElementById('positions-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="9" class="text-center"><div class="spinner-border spinner-border-sm"></div> 로딩 중...</td></tr>';
    
    try {
        const params = {
            limit: currentLimit,
            offset: currentOffset,
        };
        if (currentFilter) {
            params.status = currentFilter;
        }
        
        const queryString = AE.buildQueryString(params);
        const data = await AE.api(`/api/positions${queryString}`);
        
        if (!data.positions || data.positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted">포지션 없음</td></tr>';
            updatePaginationInfo(0, currentLimit, currentOffset);
            return;
        }
        
        tbody.innerHTML = data.positions.map(pos => {
            const pnl = AE.formatAmount(pos.realized_pnl);
            const cumPnl = AE.formatAmount(pos.cumulative_pnl);
            const openedAt = AE.formatKST(pos.opened_at);
            const closedAt = pos.closed_at ? AE.formatKST(pos.closed_at) : '-';
            
            return `
                <tr onclick="window.location.href='/positions/${pos.session_id}'" style="cursor: pointer;">
                    <td>${openedAt}</td>
                    <td>${closedAt}</td>
                    <td><strong>${pos.symbol}</strong></td>
                    <td>${AE.statusBadge(pos.side)}</td>
                    <td>${AE.statusBadge(pos.status)}</td>
                    <td class="text-end">${pos.max_qty || '-'}</td>
                    <td class="text-end ${pnl.class}">${pnl.text}</td>
                    <td class="text-end ${cumPnl.class}">${cumPnl.text}</td>
                    <td class="text-center">${pos.trade_count || 0}</td>
                </tr>
            `;
        }).join('');
        
        updatePaginationInfo(data.total_count, data.limit, data.offset);
        updatePagination(data.total_count, data.limit, data.offset);
        
    } catch (error) {
        console.error('Load positions error:', error);
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-danger">로드 실패</td></tr>';
    }
}

function updatePaginationInfo(total, limit, offset) {
    const info = document.getElementById('pagination-info');
    if (!info) return;
    
    if (total === 0) {
        info.textContent = '0 건';
    } else {
        const start = offset + 1;
        const end = Math.min(offset + limit, total);
        info.textContent = `${start}-${end} / 총 ${total} 건`;
    }
}

function updatePagination(total, limit, offset) {
    const pagination = document.getElementById('pagination');
    if (!pagination) return;
    
    const totalPages = Math.ceil(total / limit);
    const currentPage = Math.floor(offset / limit) + 1;
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let html = '';
    
    // 이전 버튼
    html += `
        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${currentPage - 1}); return false;">이전</a>
        </li>
    `;
    
    // 페이지 번호
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="goToPage(${i}); return false;">${i}</a>
            </li>
        `;
    }
    
    // 다음 버튼
    html += `
        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${currentPage + 1}); return false;">다음</a>
        </li>
    `;
    
    pagination.innerHTML = html;
}

function goToPage(page) {
    currentOffset = (page - 1) * currentLimit;
    loadPositions();
}

// =========================================================================
// 포지션 상세
// =========================================================================

async function loadPositionDetail(sessionId) {
    try {
        const data = await AE.api(`/api/positions/${sessionId}`);
        
        if (!data) {
            AE.showError('position-header', '포지션을 찾을 수 없습니다.');
            return;
        }
        
        // 헤더 업데이트
        document.getElementById('position-symbol').textContent = data.symbol || '-';
        document.getElementById('position-side').innerHTML = AE.statusBadge(data.side);
        
        const statusEl = document.getElementById('position-status');
        statusEl.textContent = data.status;
        statusEl.className = `badge ${data.status === 'OPEN' ? 'bg-primary' : 'bg-secondary'}`;
        
        const pnl = AE.formatAmount(data.realized_pnl);
        document.getElementById('position-pnl').innerHTML = `<span class="${pnl.class}">${pnl.text} USDT</span>`;
        
        // 헤더 색상
        const header = document.getElementById('position-header');
        header.classList.remove('long', 'short');
        if (data.side === 'LONG') {
            header.classList.add('long');
        } else if (data.side === 'SHORT') {
            header.classList.add('short');
        }
        
        // 상세 정보
        document.getElementById('detail-opened-at').textContent = AE.formatKST(data.opened_at);
        document.getElementById('detail-closed-at').textContent = data.closed_at ? AE.formatKST(data.closed_at) : '-';
        document.getElementById('detail-initial-qty').textContent = data.initial_qty || '-';
        document.getElementById('detail-max-qty').textContent = data.max_qty || '-';
        document.getElementById('detail-trade-count').textContent = data.trade_count || 0;
        document.getElementById('detail-commission').textContent = `${AE.formatNumber(data.total_commission)} USDT`;
        document.getElementById('detail-close-reason').textContent = data.close_reason || '-';
        
    } catch (error) {
        console.error('Load position detail error:', error);
        AE.showError('position-header', '포지션 정보를 불러올 수 없습니다.');
    }
}

async function loadPositionTrades(sessionId) {
    const tbody = document.getElementById('trades-table');
    const timeline = document.getElementById('timeline');
    
    try {
        const trades = await AE.api(`/api/positions/${sessionId}/trades`);
        
        if (!trades || trades.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">거래 내역 없음</td></tr>';
            timeline.innerHTML = '<div class="text-center text-muted">거래 내역 없음</div>';
            return;
        }
        
        // 거래 테이블
        tbody.innerHTML = trades.map(trade => {
            const pnl = AE.formatAmount(trade.realized_pnl || 0);
            const timeStr = AE.formatKST(trade.created_at);
            
            return `
                <tr>
                    <td>${timeStr}</td>
                    <td>${AE.statusBadge(trade.action)}</td>
                    <td class="text-end">${trade.qty || '-'}</td>
                    <td class="text-end">${AE.formatNumber(trade.price)}</td>
                    <td class="text-end ${pnl.class}">${pnl.text}</td>
                    <td class="text-end">${AE.formatNumber(trade.commission)}</td>
                    <td class="text-end">${trade.position_qty_after || '0'}</td>
                </tr>
            `;
        }).join('');
        
        // 타임라인
        timeline.innerHTML = trades.map((trade, index) => {
            const timeStr = AE.formatKST(trade.created_at);
            const isFirst = index === 0;
            const isLast = index === trades.length - 1 && trade.position_qty_after === '0';
            
            let itemClass = '';
            if (isFirst) itemClass = 'open';
            if (isLast) itemClass = 'close';
            
            return `
                <div class="position-timeline-item ${itemClass}">
                    <div class="d-flex justify-content-between">
                        <div>
                            <strong>${trade.action}</strong>
                            <span class="text-muted ms-2">${trade.qty} @ ${AE.formatNumber(trade.price)}</span>
                        </div>
                        <small class="text-muted">${timeStr}</small>
                    </div>
                    ${trade.realized_pnl ? `<small class="${parseFloat(trade.realized_pnl) >= 0 ? 'text-success' : 'text-danger'}">PnL: ${AE.formatNumber(trade.realized_pnl)} USDT</small>` : ''}
                </div>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Load position trades error:', error);
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-danger">로드 실패</td></tr>';
        timeline.innerHTML = '<div class="text-center text-danger">로드 실패</div>';
    }
}
