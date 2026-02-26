/**
 * 거래 내역 페이지
 * 선물/현물/모두 필터, 기본은 선물만 표시
 */

let currentSymbol = null;
let currentVenue = 'FUTURES';  // FUTURES(선물) / SPOT(현물) / ALL(모두), 기본 선물
let currentLimit = 50;
let currentOffset = 0;

document.addEventListener('DOMContentLoaded', () => {
    initTransactions();
});

function initTransactions() {
    // venue 필터 버튼
    document.querySelectorAll('[id^="filter-venue-"]').forEach(btn => {
        btn.addEventListener('click', () => {
            const venue = btn.getAttribute('data-venue');
            if (!venue) return;
            currentVenue = venue;
            currentOffset = 0;
            document.querySelectorAll('[id^="filter-venue-"]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadTransactions();
        });
    });
    loadTransactions();
}

async function loadTransactions() {
    const tbody = document.getElementById('transactions-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="6" class="text-center"><div class="spinner-border spinner-border-sm"></div> 로딩 중...</td></tr>';
    
    try {
        const params = {
            venue: currentVenue,
            limit: currentLimit,
            offset: currentOffset,
        };
        if (currentSymbol) {
            params.symbol = currentSymbol;
        }
        
        const queryString = AE.buildQueryString(params);
        const data = await AE.api(`/api/transactions${queryString}`);
        
        if (!data.transactions || data.transactions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">거래 내역 없음</td></tr>';
            updatePaginationInfo(0, currentLimit, currentOffset);
            return;
        }
        
        tbody.innerHTML = data.transactions.map(tx => {
            const pnl = AE.formatAmount(tx.realized_pnl || 0);
            const timeStr = AE.formatKST(tx.ts);
            const venueBadge = tx.scope_venue === 'FUTURES'
                ? '<span class="badge bg-primary">선물</span>'
                : (tx.scope_venue === 'SPOT' ? '<span class="badge bg-info">현물</span>' : '<span class="badge bg-light text-dark">-</span>');
            // 거래: 매수=양수(초록), 매도=음수(빨강), 아이콘+텍스트로 접근성 확보
            const bought = parseFloat(tx.bought_qty) || 0;
            const sold = parseFloat(tx.sold_qty) || 0;
            const isBuy = bought > 0;
            const qtyStr = isBuy ? AE.formatQuantity(tx.bought_qty) : AE.formatQuantity(tx.sold_qty);
            const signedQty = isBuy ? `+${qtyStr}` : `-${qtyStr}`;
            const tradeCell = isBuy
                ? `<span class="text-success" title="매수"><i class="bi bi-arrow-up"></i> ${signedQty} <small class="text-muted">매수</small></span>`
                : `<span class="text-danger" title="매도"><i class="bi bi-arrow-down"></i> ${signedQty} <small class="text-muted">매도</small></span>`;
            
            return `
                <tr>
                    <td><code>${tx.symbol || '-'}</code></td>
                    <td>${venueBadge}</td>
                    <td>${timeStr}</td>
                    <td class="text-end">${tradeCell}</td>
                    <td class="text-end d-none d-sm-table-cell">${AE.formatCommission(tx.fee_usdt || 0)}</td>
                    <td class="text-end ${pnl.class}">${pnl.text}</td>
                </tr>
            `;
        }).join('');
        
        updatePaginationInfo(data.total_count, data.limit, data.offset);
        updatePagination(data.total_count, data.limit, data.offset);
        
    } catch (error) {
        console.error('Load transactions error:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">로드 실패</td></tr>';
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
    loadTransactions();
}
