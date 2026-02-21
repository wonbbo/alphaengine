/**
 * Commands 페이지
 */

let commandsData = [];
let createModal = null;
let detailModal = null;
let pollingId = null;

document.addEventListener('DOMContentLoaded', () => {
    createModal = new bootstrap.Modal(document.getElementById('createCommandModal'));
    detailModal = new bootstrap.Modal(document.getElementById('commandDetailModal'));
    
    initCommands();
});

async function initCommands() {
    // Command 타입 로드
    await loadCommandTypes();
    
    // 초기 로드
    await loadCommands();
    
    // 폴링 시작 (5초)
    pollingId = AE.startPolling(loadCommands, 5000);
}

async function loadCommandTypes() {
    try {
        const types = await AE.api('/api/commands/types/all');
        const select = document.getElementById('command-type');
        
        if (select && types) {
            types.forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = type;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Load command types error:', error);
    }
}

async function loadCommands() {
    const tbody = document.getElementById('commands-table');
    if (!tbody) return;
    
    try {
        const status = document.getElementById('filter-status')?.value || '';
        const includeCompleted = document.getElementById('filter-include-completed')?.checked ?? true;
        
        const params = {
            limit: 50,
            include_completed: includeCompleted,
        };
        if (status) params.status = status;
        
        const queryString = AE.buildQueryString(params);
        const data = await AE.api(`/api/commands${queryString}`);
        
        commandsData = data.commands || [];
        
        if (commandsData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Command 없음</td></tr>';
            document.getElementById('pagination-info').textContent = '0 건';
            return;
        }
        
        tbody.innerHTML = commandsData.map((cmd, index) => {
            const timeStr = AE.formatKST(cmd.ts);
            const symbol = cmd.scope?.symbol || '-';
            const actor = cmd.actor ? `${cmd.actor.kind}:${cmd.actor.id}` : '-';
            
            return `
                <tr>
                    <td>${timeStr}</td>
                    <td><strong>${cmd.command_type}</strong></td>
                    <td>${symbol}</td>
                    <td>${AE.statusBadge(cmd.status)}</td>
                    <td><small class="text-muted">${actor}</small></td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="showCommandDetail(${index})">
                            <i class="bi bi-eye"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
        
        document.getElementById('pagination-info').textContent = `총 ${data.total_count} 건`;
        
    } catch (error) {
        console.error('Load commands error:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-danger">로드 실패</td></tr>';
    }
}

function showCreateModal() {
    document.getElementById('command-type').value = '';
    document.getElementById('scope-venue').value = 'FUTURES';
    document.getElementById('scope-symbol').value = '';
    document.getElementById('command-priority').value = '5';
    document.getElementById('command-payload').value = '{}';
    
    createModal.show();
}

async function createCommand() {
    const commandType = document.getElementById('command-type').value;
    const venue = document.getElementById('scope-venue').value;
    const symbol = document.getElementById('scope-symbol').value;
    const priority = parseInt(document.getElementById('command-priority').value);
    const payloadStr = document.getElementById('command-payload').value;
    
    if (!commandType) {
        AE.toast('Command 타입을 선택해주세요.', 'warning');
        return;
    }
    
    let payload;
    try {
        payload = JSON.parse(payloadStr);
    } catch (error) {
        AE.toast('유효하지 않은 JSON 형식입니다.', 'danger');
        return;
    }
    
    try {
        const result = await AE.api('/api/commands', {
            method: 'POST',
            body: JSON.stringify({
                command_type: commandType,
                scope: {
                    exchange: 'BINANCE',
                    venue: venue,
                    account_id: 'main',
                    symbol: symbol || null,
                },
                payload: payload,
                priority: priority,
            }),
        });
        
        AE.toast(`Command 발행됨: ${result.command_id.substring(0, 8)}...`, 'success');
        createModal.hide();
        loadCommands();
        
    } catch (error) {
        AE.toast(`발행 실패: ${error.message}`, 'danger');
    }
}

function showCommandDetail(index) {
    const cmd = commandsData[index];
    if (!cmd) return;
    
    document.getElementById('detail-command-id').textContent = cmd.command_id;
    document.getElementById('detail-command-type').textContent = cmd.command_type;
    document.getElementById('detail-ts').textContent = AE.formatKST(cmd.ts);
    document.getElementById('detail-status').innerHTML = AE.statusBadge(cmd.status);
    document.getElementById('detail-actor').textContent = cmd.actor 
        ? `${cmd.actor.kind}:${cmd.actor.id}` 
        : '-';
    document.getElementById('detail-scope').textContent = cmd.scope 
        ? `${cmd.scope.exchange}:${cmd.scope.venue}:${cmd.scope.symbol || '*'}` 
        : '-';
    document.getElementById('detail-payload').textContent = JSON.stringify(cmd.payload, null, 2);
    
    // Result
    const resultSection = document.getElementById('detail-result-section');
    if (cmd.result) {
        document.getElementById('detail-result').textContent = JSON.stringify(cmd.result, null, 2);
        resultSection.style.display = 'block';
    } else {
        resultSection.style.display = 'none';
    }
    
    // Error
    const errorSection = document.getElementById('detail-error-section');
    if (cmd.last_error) {
        document.getElementById('detail-error').textContent = cmd.last_error;
        errorSection.style.display = 'block';
    } else {
        errorSection.style.display = 'none';
    }
    
    detailModal.show();
}

// 페이지 이탈 시 폴링 중지
window.addEventListener('beforeunload', () => {
    AE.stopPolling(pollingId);
});
