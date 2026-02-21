/**
 * 이벤트 페이지
 * 
 * 이벤트/커맨드 타입 한글화 및 색상은 common.js의 AE._typeConfig 사용
 */

let currentLimit = 50;
let currentOffset = 0;
let filters = {
    event_type: null,
    symbol: null,
    from_ts: null,
    to_ts: null,
};
let eventsData = [];

document.addEventListener('DOMContentLoaded', () => {
    initEvents();
});

async function initEvents() {
    // 이벤트 타입 목록 로드
    await loadEventTypes();
    
    // 필터 이벤트
    document.getElementById('filter-symbol')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') applyFilter();
    });
    
    // 초기 로드
    loadEvents();
}

async function loadEventTypes() {
    try {
        const types = await AE.api('/api/events/types');
        const select = document.getElementById('filter-event-type');
        
        if (select && types) {
            types.forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = AE.getEventTypeOptionText(type);
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Load event types error:', error);
    }
}

function applyFilter() {
    filters.event_type = document.getElementById('filter-event-type')?.value || null;
    filters.symbol = document.getElementById('filter-symbol')?.value || null;
    
    const fromDate = document.getElementById('filter-from-date')?.value;
    const toDate = document.getElementById('filter-to-date')?.value;
    
    filters.from_ts = fromDate ? `${fromDate}T00:00:00Z` : null;
    filters.to_ts = toDate ? `${toDate}T23:59:59Z` : null;
    
    currentOffset = 0;
    loadEvents();
}

async function loadEvents() {
    const tbody = document.getElementById('events-table');
    if (!tbody) return;
    
    tbody.innerHTML = '<tr><td colspan="5" class="text-center"><div class="spinner-border spinner-border-sm"></div> 로딩 중...</td></tr>';
    
    try {
        const params = {
            limit: currentLimit,
            offset: currentOffset,
        };
        
        if (filters.event_type) params.event_type = filters.event_type;
        if (filters.symbol) params.symbol = filters.symbol;
        if (filters.from_ts) params.from_ts = filters.from_ts;
        if (filters.to_ts) params.to_ts = filters.to_ts;
        
        const queryString = AE.buildQueryString(params);
        const data = await AE.api(`/api/events${queryString}`);
        
        eventsData = data.events || [];
        
        if (eventsData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">이벤트 없음</td></tr>';
            updatePaginationInfo(0, currentLimit, currentOffset);
            return;
        }
        
        tbody.innerHTML = eventsData.map((event, index) => {
            const timeStr = AE.formatKST(event.ts);
            const symbol = event.scope?.symbol || '-';
            const entity = event.entity_kind ? `${event.entity_kind}:${event.entity_id || ''}` : '-';
            
            return `
                <tr onclick="showEventDetail(${index})" style="cursor: pointer;">
                    <td>${timeStr}</td>
                    <td>${AE.eventTypeBadge(event.event_type)}</td>
                    <td><strong>${symbol}</strong></td>
                    <td><code>${entity}</code></td>
                    <td>${event.source || '-'}</td>
                </tr>
            `;
        }).join('');
        
        updatePaginationInfo(data.total_count, data.limit, data.offset);
        updatePagination(data.total_count, data.limit, data.offset);
        
    } catch (error) {
        console.error('Load events error:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">로드 실패</td></tr>';
    }
}

function showEventDetail(index) {
    const event = eventsData[index];
    if (!event) return;
    
    document.getElementById('modal-event-id').textContent = event.event_id;
    document.getElementById('modal-event-type').innerHTML = `${AE.eventTypeBadge(event.event_type)} <small class="text-muted">(${event.event_type})</small>`;
    document.getElementById('modal-ts').textContent = AE.formatKST(event.ts);
    document.getElementById('modal-symbol').textContent = event.scope?.symbol || '-';
    document.getElementById('modal-entity').textContent = event.entity_kind 
        ? `${event.entity_kind}:${event.entity_id || ''}` 
        : '-';
    document.getElementById('modal-source').textContent = event.source || '-';
    document.getElementById('modal-payload').textContent = JSON.stringify(event.payload, null, 2);
    
    const modal = new bootstrap.Modal(document.getElementById('eventModal'));
    modal.show();
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
    
    html += `
        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${currentPage - 1}); return false;">이전</a>
        </li>
    `;
    
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);
    
    for (let i = startPage; i <= endPage; i++) {
        html += `
            <li class="page-item ${i === currentPage ? 'active' : ''}">
                <a class="page-link" href="#" onclick="goToPage(${i}); return false;">${i}</a>
            </li>
        `;
    }
    
    html += `
        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
            <a class="page-link" href="#" onclick="goToPage(${currentPage + 1}); return false;">다음</a>
        </li>
    `;
    
    pagination.innerHTML = html;
}

function goToPage(page) {
    currentOffset = (page - 1) * currentLimit;
    loadEvents();
}
