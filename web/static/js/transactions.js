/**
 * 거래 내역 페이지
 */

let currentSymbol = null;
let currentLimit = 50;
let currentOffset = 0;
let displaySymbol = null;

document.addEventListener('DOMContentLoaded', () => {
    initTransactions();
});

function initTransactions() {
    // 초기 로드
    loadTransactions();
}

async function loadTransactions() {
    const tbody = document.getElementById('transactions-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="5" class="text-center"><div class="spinner-border spinner-border-sm"></div> 로딩 중...</td></tr>';
    
    try {
        const params = {
            limit: currentLimit,
            offset: currentOffset,
        };
        if (currentSymbol) {
            params.symbol = currentSymbol;
        }
        
        const queryString = AE.buildQueryString(params);
        const data = await AE.api(`/api/transactions${queryString}`);
        
        if (!data.transactions || data.transactions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">거래 내역 없음</td></tr>';
            updatePaginationInfo(0, currentLimit, currentOffset);
            return;
        }
        
        // 첫 번째 거래의 심볼을 타이틀에 표시
        if (data.transactions.length > 0 && data.transactions[0].symbol) {
            displaySymbol = data.transactions[0].symbol;
            updateSymbolTitle();
        }
        
        tbody.innerHTML = data.transactions.map(tx => {
            const pnl = AE.formatAmount(tx.realized_pnl || 0);
            const timeStr = AE.formatKST(tx.ts);
            
            return `
                <tr>
                    <td>${timeStr}</td>
                    <td class="text-end">${tx.bought_qty || '-'}</td>
                    <td class="text-end">${tx.sold_qty || '-'}</td>
                    <td class="text-end d-none d-sm-table-cell">${AE.formatCommission(tx.fee_usdt || 0)}</td>
                    <td class="text-end ${pnl.class}">${pnl.text}</td>
                </tr>
            `;
        }).join('');
        
        updatePaginationInfo(data.total_count, data.limit, data.offset);
        updatePagination(data.total_count, data.limit, data.offset);
        
    } catch (error) {
        console.error('Load transactions error:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">로드 실패</td></tr>';
    }
}

function updateSymbolTitle() {
    const symbolTitle = document.getElementById('symbol-title');
    if (!symbolTitle) return;
    
    if (displaySymbol) {
        symbolTitle.textContent = `(${displaySymbol})`;
    } else {
        symbolTitle.textContent = '';
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
