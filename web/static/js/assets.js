/**
 * 자산 현황 페이지
 */

let trialBalanceLoaded = false;

document.addEventListener('DOMContentLoaded', () => {
    loadAssets();
});

async function loadAssets() {
    try {
        const data = await AE.api('/api/assets');
        
        // 요약 카드
        document.getElementById('spot-total').textContent = AE.formatNumber(data.spot_total_usdt || 0);
        document.getElementById('futures-total').textContent = AE.formatNumber(data.futures_total_usdt || 0);
        document.getElementById('total-assets').textContent = AE.formatNumber(data.total_usdt || 0);
        
        // 자산 테이블
        const tbody = document.getElementById('assets-table');
        
        if (!data.assets || data.assets.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">자산 없음</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.assets.map(asset => {
            const balance = parseFloat(asset.balance) || 0;
            const lastUpdated = asset.last_updated ? AE.formatKST(asset.last_updated) : '-';
            
            return `
                <tr>
                    <td>${asset.venue || '-'}</td>
                    <td><strong>${asset.asset || '-'}</strong></td>
                    <td class="text-end">${AE.formatNumber(balance, 4)}</td>
                    <td>${lastUpdated}</td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Load assets error:', error);
        document.getElementById('assets-table').innerHTML = 
            '<tr><td colspan="4" class="text-center text-danger">로드 실패</td></tr>';
    }
}

function toggleTrialBalance() {
    const section = document.getElementById('trial-balance-section');
    const icon = document.getElementById('trial-balance-icon');
    
    if (section.classList.contains('show')) {
        section.classList.remove('show');
        icon.classList.remove('bi-chevron-up');
        icon.classList.add('bi-chevron-down');
    } else {
        section.classList.add('show');
        icon.classList.remove('bi-chevron-down');
        icon.classList.add('bi-chevron-up');
        
        if (!trialBalanceLoaded) {
            loadTrialBalance();
        }
    }
}

async function loadTrialBalance() {
    const tbody = document.getElementById('trial-balance-table');
    
    try {
        const data = await AE.api('/api/assets/trial-balance');
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">데이터 없음</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(item => {
            const balance = parseFloat(item.balance) || 0;
            const balanceClass = balance > 0 ? 'text-success' : (balance < 0 ? 'text-danger' : '');
            
            return `
                <tr>
                    <td><code>${item.account_id}</code></td>
                    <td>${item.account_type || '-'}</td>
                    <td>${item.venue || '-'}</td>
                    <td>${item.asset || '-'}</td>
                    <td class="text-end ${balanceClass}">${AE.formatNumber(balance, 4)}</td>
                </tr>
            `;
        }).join('');
        
        trialBalanceLoaded = true;
        
    } catch (error) {
        console.error('Load trial balance error:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">로드 실패</td></tr>';
    }
}
