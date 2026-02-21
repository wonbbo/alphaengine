/**
 * Trading Edge 페이지
 */

let cumulativeEdgeChart = null;
let symbolPnLChart = null;

document.addEventListener('DOMContentLoaded', () => {
    loadEdgeSummary();
    loadEdgeChart();
});

async function loadEdgeSummary() {
    // 먼저 로딩 상태 해제 (API 실패 시에도 "데이터 없음" 표시)
    renderDayCard('best-day', null, true);
    renderDayCard('worst-day', null, false);
    
    try {
        const data = await AE.api('/api/trading-edge/summary');
        
        // 요약 카드
        const totalPnl = AE.formatAmount(data.total_pnl || 0);
        document.getElementById('total-pnl').innerHTML = 
            `<span class="${totalPnl.class}">${totalPnl.text}</span>`;
        
        document.getElementById('total-trades').textContent = data.total_trades || 0;
        document.getElementById('win-rate').textContent = `${data.win_rate || 0}%`;
        
        const avgPnl = AE.formatAmount(data.avg_pnl_per_trade || 0);
        document.getElementById('avg-pnl').innerHTML = 
            `<span class="${avgPnl.class}">${avgPnl.text}</span>`;
        
        const pf = data.profit_factor;
        const pfClass = pf >= 1.5 ? 'edge-positive' : (pf < 1 ? 'edge-negative' : '');
        document.getElementById('profit-factor').innerHTML = 
            `<span class="${pfClass}">${pf === Infinity ? '∞' : pf}</span>`;
        
        document.getElementById('total-fees').textContent = 
            AE.formatNumber(data.total_fees || 0);
        
        // 심볼별 테이블
        const symbols = data.symbols || [];
        const tbody = document.getElementById('symbols-table');
        
        if (symbols.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">데이터 없음</td></tr>';
        } else {
            tbody.innerHTML = symbols.map(s => {
                const pnl = AE.formatAmount(s.net_pnl || 0);
                const winRate = s.total_trades > 0 
                    ? Math.round((s.winning_trades || 0) / s.total_trades * 100) 
                    : 0;
                
                return `
                    <tr>
                        <td><strong>${s.symbol}</strong></td>
                        <td class="text-end">${s.total_trades || 0}</td>
                        <td class="text-end">${winRate}%</td>
                        <td class="text-end ${pnl.class}">${pnl.text}</td>
                    </tr>
                `;
            }).join('');
            
            // 심볼별 차트
            const chartData = {
                labels: symbols.map(s => s.symbol),
                values: symbols.map(s => s.net_pnl || 0),
            };
            
            if (symbolPnLChart) {
                ChartUtils.destroyChart(symbolPnLChart);
            }
            symbolPnLChart = ChartUtils.createSymbolPnLChart('symbol-pnl-chart', chartData);
        }
        
        // 최고/최저 수익일
        renderDayCard('best-day', data.best_day, true);
        renderDayCard('worst-day', data.worst_day, false);
        
    } catch (error) {
        console.error('Load edge summary error:', error);
        // 초기에 이미 "데이터 없음"으로 설정됨
    }
}

function renderDayCard(elementId, dayData, isBest) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    if (!dayData) {
        el.innerHTML = '<p class="text-muted text-center mb-0">데이터 없음</p>';
        return;
    }
    
    const pnl = AE.formatAmount(dayData.pnl || 0);
    const dateStr = dayData.date || '-';
    
    el.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-2">
            <h4 class="mb-0">${dateStr}</h4>
            <span class="fs-4 ${pnl.class}">${pnl.text} USDT</span>
        </div>
        <div class="row text-center">
            <div class="col-6">
                <div class="text-muted small">거래 수</div>
                <div class="fw-bold">${dayData.trade_count || 0}</div>
            </div>
            <div class="col-6">
                <div class="text-muted small">일 수익</div>
                <div class="fw-bold ${pnl.class}">${pnl.text}</div>
            </div>
        </div>
    `;
}

async function loadEdgeChart() {
    try {
        const data = await AE.api('/api/trading-edge/daily-series?days=60');
        
        if (data.labels && data.labels.length > 0) {
            const chartData = {
                labels: data.labels,
                values: data.cumulative,
            };
            
            cumulativeEdgeChart = ChartUtils.createTradingEdgeChart('cumulative-edge-chart', chartData);
        }
        
    } catch (error) {
        console.error('Load edge chart error:', error);
    }
}
