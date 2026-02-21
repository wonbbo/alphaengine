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
        if (dailyPnL.labels.length > 0) {
            dailyPnLChart = ChartUtils.createDailyPnLChart('daily-pnl-chart', dailyPnL);
        }
        
        // 누적 수익
        const cumulativePnL = await AE.api('/api/pnl/cumulative-series?days=30');
        if (cumulativePnL.labels.length > 0) {
            cumulativePnLChart = ChartUtils.createCumulativePnLChart('cumulative-pnl-chart', cumulativePnL);
        }
        
        // 일별 수익률
        const dailyReturns = await AE.api('/api/pnl/returns/daily-series?days=30');
        if (dailyReturns.labels.length > 0) {
            dailyReturnsChart = ChartUtils.createDailyReturnsChart('daily-returns-chart', dailyReturns);
        }
        
        // 누적 수익률
        const cumulativeReturns = await AE.api('/api/pnl/returns/cumulative-series?days=30');
        if (cumulativeReturns.labels.length > 0) {
            cumulativeReturnsChart = ChartUtils.createCumulativeReturnsChart('cumulative-returns-chart', cumulativeReturns);
        }
        
    } catch (error) {
        console.error('Charts error:', error);
    }
}

async function loadAssets() {
    try {
        const data = await AE.api('/api/ledger/portfolio');
        
        const tbody = document.getElementById('assets-table');
        
        if (!data || data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">자산 없음</td></tr>';
            document.getElementById('total-assets').textContent = '0.00 USDT';
            return;
        }
        
        let totalUsdt = 0;
        
        tbody.innerHTML = data.map(asset => {
            const balance = parseFloat(asset.balance) || 0;
            
            // USDT 환산
            if (asset.asset === 'USDT') {
                totalUsdt += balance;
            }
            
            return `
                <tr>
                    <td>${AE.formatVenue(asset.venue)}</td>
                    <td>${asset.asset || '-'}</td>
                    <td class="text-end">${AE.formatNumber(balance, 4)}</td>
                </tr>
            `;
        }).join('');
        
        document.getElementById('total-assets').textContent = 
            `${AE.formatNumber(totalUsdt, 2)} USDT`;
        
    } catch (error) {
        console.error('Assets error:', error);
        document.getElementById('assets-table').innerHTML = 
            '<tr><td colspan="3" class="text-center text-danger">로드 실패</td></tr>';
    }
}

async function loadDashboardData() {
    try {
        const data = await AE.api('/api/dashboard');
        
        // 현재 포지션
        if (data.position && data.position.qty && parseFloat(data.position.qty) !== 0) {
            const pos = data.position;
            const unrealizedPnL = AE.formatAmount(pos.unrealized_pnl || 0);
            const side = parseFloat(pos.qty) > 0 ? 'LONG' : 'SHORT';
            
            document.getElementById('current-position').innerHTML = `
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <span class="fw-bold">${pos.symbol || '-'}</span>
                    ${AE.statusBadge(side)}
                </div>
                <div class="row">
                    <div class="col-6">
                        <small class="text-muted">수량</small>
                        <div>${Math.abs(parseFloat(pos.qty) || 0)}</div>
                    </div>
                    <div class="col-6">
                        <small class="text-muted">진입가</small>
                        <div>${AE.formatPrice(pos.entry_price)}</div>
                    </div>
                    <div class="col-6 mt-2">
                        <small class="text-muted">미실현 PnL</small>
                        <div class="${unrealizedPnL.class}">${unrealizedPnL.text} USDT</div>
                    </div>
                    <div class="col-6 mt-2">
                        <small class="text-muted">레버리지</small>
                        <div>${pos.leverage || 1}x</div>
                    </div>
                </div>
            `;
        } else {
            document.getElementById('current-position').innerHTML = 
                '<p class="text-muted text-center mb-0">포지션 없음</p>';
        }
        
    } catch (error) {
        console.error('Dashboard data error:', error);
    }
    
    // 최근 체결
    await loadRecentTrades();
}

async function loadRecentTrades() {
    try {
        const trades = await AE.api('/api/ledger/recent-trades?limit=5');
        const tradesBody = document.getElementById('recent-trades');
        
        if (!trades || trades.length === 0) {
            tradesBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">체결 없음</td></tr>';
            return;
        }
        
        tradesBody.innerHTML = trades.map(trade => {
            const pnl = AE.formatAmount(trade.realized_pnl || 0);
            const timeStr = trade.ts ? AE.formatKST(trade.ts).substring(11, 19) : '-';
            const qty = trade.qty || trade.bought_qty || trade.sold_qty || '-';
            const side = trade.side || '-';
            const sideDisplay = side === 'BUY' ? 'LONG' : (side === 'SELL' ? 'SHORT' : side);
            
            return `
                <tr>
                    <td>${timeStr}</td>
                    <td>${AE.statusBadge(sideDisplay)}</td>
                    <td class="text-end">${qty}</td>
                    <td class="text-end ${pnl.class}">${pnl.text}</td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Recent trades error:', error);
        document.getElementById('recent-trades').innerHTML = 
            '<tr><td colspan="4" class="text-center text-danger">로드 실패</td></tr>';
    }
}

// 페이지 이탈 시 폴링 중지
window.addEventListener('beforeunload', () => {
    AE.stopPolling(pollingId);
});
