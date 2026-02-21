/**
 * Chart.js 유틸리티
 */

const ChartUtils = {
    // 기본 색상
    colors: {
        primary: 'rgb(13, 110, 253)',
        success: 'rgb(25, 135, 84)',
        danger: 'rgb(220, 53, 69)',
        warning: 'rgb(255, 193, 7)',
        info: 'rgb(13, 202, 240)',
        gray: 'rgb(108, 117, 125)',
    },
    
    /**
     * 일별 수익 Bar Chart 생성
     */
    createDailyPnLChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const colors = data.values.map(v => 
            parseFloat(v) >= 0 ? this.colors.success : this.colors.danger
        );
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '일별 수익 (USDT)',
                    data: data.values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)} USDT`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 누적 수익 Line Chart 생성
     */
    createCumulativePnLChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 수익 (USDT)',
                    data: data.values,
                    borderColor: this.colors.primary,
                    backgroundColor: 'rgba(13, 110, 253, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)} USDT`
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 일별 수익률 Bar Chart 생성
     */
    createDailyReturnsChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const colors = data.values.map(v => 
            parseFloat(v) >= 0 ? this.colors.success : this.colors.danger
        );
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '일별 수익률 (%)',
                    data: data.values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(0,0,0,0.1)' },
                        ticks: {
                            callback: (value) => `${value}%`
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 누적 수익률 Line Chart 생성
     */
    createCumulativeReturnsChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 수익률 (%)',
                    data: data.values,
                    borderColor: this.colors.info,
                    backgroundColor: 'rgba(13, 202, 240, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(2)}%`
                        }
                    }
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' },
                        ticks: {
                            callback: (value) => `${value}%`
                        }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * Trading Edge Line Chart 생성
     */
    createTradingEdgeChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '누적 Edge',
                    data: data.values,
                    borderColor: this.colors.warning,
                    backgroundColor: 'rgba(255, 193, 7, 0.1)',
                    fill: true,
                    tension: 0.1,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 심볼별 수익 Horizontal Bar Chart 생성
     */
    createSymbolPnLChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        const colors = data.values.map(v => 
            parseFloat(v) >= 0 ? this.colors.success : this.colors.danger
        );
        
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: data.labels,
                datasets: [{
                    label: '수익 (USDT)',
                    data: data.values,
                    backgroundColor: colors,
                    borderWidth: 0,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => `${ctx.parsed.x >= 0 ? '+' : ''}${ctx.parsed.x.toFixed(2)} USDT`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    y: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 거래별 Trading Edge Line Chart 생성
     */
    createPerTradeEdgeChart(canvasId, data) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        return new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [
                    {
                        label: 'Trading Edge',
                        data: data.edges,
                        borderColor: this.colors.primary,
                        backgroundColor: 'rgba(13, 110, 253, 0.1)',
                        fill: true,
                        tension: 0.2,
                        yAxisID: 'y',
                    },
                    {
                        label: 'PnL',
                        data: data.pnls,
                        type: 'bar',
                        backgroundColor: data.pnls.map(v => 
                            parseFloat(v) >= 0 ? 'rgba(25, 135, 84, 0.6)' : 'rgba(220, 53, 69, 0.6)'
                        ),
                        yAxisID: 'y1',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                plugins: {
                    legend: { 
                        display: true,
                        position: 'top',
                    },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.dataset.label === 'Trading Edge') {
                                    return `Edge: ${ctx.parsed.y.toFixed(4)}`;
                                } else {
                                    return `PnL: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(4)} USDT`;
                                }
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Edge'
                        },
                        grid: { color: 'rgba(0,0,0,0.1)' }
                    },
                    y1: {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {
                            display: true,
                            text: 'PnL (USDT)'
                        },
                        grid: {
                            drawOnChartArea: false,
                        },
                    },
                    x: {
                        grid: { display: false }
                    }
                }
            }
        });
    },
    
    /**
     * 차트 업데이트
     */
    updateChart(chart, labels, values) {
        chart.data.labels = labels;
        chart.data.datasets[0].data = values;
        chart.update();
    },
    
    /**
     * 차트 파괴
     */
    destroyChart(chart) {
        if (chart) {
            chart.destroy();
        }
    },
};

window.ChartUtils = ChartUtils;
