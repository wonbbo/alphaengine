/**
 * 거래 내역 페이지
 */

let currentSymbol = null;
let currentLimit = 50;
let currentOffset = 0;
let allSymbols = new Set();

document.addEventListener('DOMContentLoaded', () => {
    initTransactions();
});

function initTransactions() {
    // 심볼 필터 이벤트
    document.getElementById('symbol-filter')?.addEventListener('change', (e) => {
        currentSymbol = e.target.value || null;
        currentOffset = 0;
        loadTransactions();
    });
    
    // 초기 로드
    loadTransactions();
}

async function loadTransactions() {
    const tbody = document.getElementById('transactions-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="6" class="text-center"><div class="spinner-border spinner-border-sm"></div> 로딩 중...</td></tr>';
    
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
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">거래 내역 없음</td></tr>';
            updatePaginationInfo(0, currentLimit, currentOffset);
            return;
        }
        
        // 심볼 목록 수집
        data.transactions.forEach(tx => {
            if (tx.symbol) {
                allSymbols.add(tx.symbol);
            }
        });
        updateSymbolFilter();
        
        tbody.innerHTML = data.transactions.map(tx => {
            const pnl = AE.formatAmount(tx.realized_pnl || 0);
            const timeStr = AE.formatKST(tx.ts);
            
            return `
                <tr>
                    <td>${timeStr}</td>
                    <td><strong>${tx.symbol || '-'}</strong></td>
                    <td class="text-end">${tx.bought_qty || '-'}</td>
                    <td class="text-end">${tx.sold_qty || '-'}</td>
                    <td class="text-end">${AE.formatNumber(tx.fee_usdt || 0)}</td>
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

function updateSymbolFilter() {
    const select = document.getElementById('symbol-filter');
    if (!select) return;
    
    // 현재 선택값 유지
    const currentValue = select.value;
    
    // 기존 옵션 유지하면서 새 심볼 추가
    const existingOptions = new Set();
    for (const option of select.options) {
        existingOptions.add(option.value);
    }
    
    allSymbols.forEach(symbol => {
        if (!existingOptions.has(symbol)) {
            const option = document.createElement('option');
            option.value = symbol;
            option.textContent = symbol;
            select.appendChild(option);
        }
    });
    
    // 선택값 복원
    select.value = currentValue;
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
