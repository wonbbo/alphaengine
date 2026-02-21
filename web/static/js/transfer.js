// AlphaEngine Transfer UI JavaScript

const API_BASE = '/api/transfer';
let currentTransferId = null;
let pollingInterval = null;
let maxDepositAmount = 0;
let maxWithdrawAmount = 0;

// 출금 예상 금액 계산용 시세 정보
let withdrawPriceInfo = {
    trxUsdtPrice: 0,
    trxKrwPrice: 0,
    networkFeeTrx: 1,
    binanceTradeRate: 0.001,
    upbitTradeRate: 0.0005,
};

// =========================================================================
// 입금 상태
// =========================================================================

async function loadDepositStatus() {
    const statusDiv = document.getElementById('deposit-status');
    const form = document.getElementById('deposit-form');
    const unavailable = document.getElementById('deposit-unavailable');
    
    try {
        const response = await fetch(`${API_BASE}/deposit/status`);
        
        // 입출금 기능 비활성화 체크 (503)
        if (response.status === 503) {
            const errorData = await response.json();
            const reason = errorData.detail?.reason || '입출금 기능이 비활성화되어 있습니다.';
            statusDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-info-circle"></i> ${reason}
                </div>
            `;
            form.classList.add('d-none');
            unavailable.classList.add('d-none');
            return;
        }
        
        const data = await response.json();
        
        if (data.can_deposit && !data.pending_deposit) {
            // 입금 가능
            statusDiv.innerHTML = `
                <div class="balance-info">
                    <div class="row">
                        <div class="col-6">
                            <div class="balance-label">KRW 잔고</div>
                            <div class="balance-value">${formatNumber(data.krw_balance)}원</div>
                        </div>
                        <div class="col-6">
                            <div class="balance-label">TRX 잔고</div>
                            <div class="balance-value">${formatNumber(data.trx_balance)} TRX</div>
                        </div>
                    </div>
                    <div class="row mt-2">
                        <div class="col-6">
                            <div class="balance-label">TRX 가격</div>
                            <div class="balance-value">${formatNumber(data.trx_price_krw)}원</div>
                        </div>
                        <div class="col-6">
                            <div class="balance-label">예상 수수료</div>
                            <div class="balance-value">~${formatNumber(data.fee_krw)}원</div>
                        </div>
                    </div>
                </div>
            `;
            form.classList.remove('d-none');
            unavailable.classList.add('d-none');
            
            // 최대 입금 가능 금액 설정
            maxDepositAmount = Math.floor(parseFloat(data.krw_balance) - parseFloat(data.fee_krw));
            document.getElementById('deposit-amount').max = maxDepositAmount;
            
        } else if (data.pending_deposit) {
            // 입금 진행 중
            statusDiv.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-hourglass-split"></i> 입금이 진행 중입니다.
                </div>
            `;
            form.classList.add('d-none');
            unavailable.classList.add('d-none');
            currentTransferId = data.pending_transfer_id;
            loadTransferProgress(data.pending_transfer_id);
            
        } else {
            // 입금 불가 - 현재 잔고 정보 함께 표시
            const krwBalance = parseFloat(data.krw_balance || 0);
            const trxBalance = parseFloat(data.trx_balance || 0);
            
            statusDiv.innerHTML = `
                <div class="balance-info mb-3">
                    <div class="row">
                        <div class="col-6">
                            <div class="balance-label">KRW 잔고</div>
                            <div class="balance-value text-warning">${formatNumber(krwBalance)}원</div>
                        </div>
                        <div class="col-6">
                            <div class="balance-label">TRX 잔고</div>
                            <div class="balance-value">${formatNumber(trxBalance)} TRX</div>
                        </div>
                    </div>
                </div>
            `;
            form.classList.add('d-none');
            unavailable.classList.remove('d-none');
            document.getElementById('deposit-unavailable-msg').textContent = 
                `KRW 잔고가 부족합니다. (최소 5,000원 필요, 현재: ${formatNumber(krwBalance)}원)`;
        }
        
    } catch (error) {
        console.error('Failed to load deposit status:', error);
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> 상태 조회 실패
            </div>
        `;
    }
}

// =========================================================================
// 출금 상태
// =========================================================================

async function loadWithdrawStatus() {
    const statusDiv = document.getElementById('withdraw-status');
    const form = document.getElementById('withdraw-form');
    const unavailable = document.getElementById('withdraw-unavailable');
    const positionWarning = document.getElementById('position-warning');
    
    try {
        const response = await fetch(`${API_BASE}/withdraw/status`);
        
        // 입출금 기능 비활성화 체크 (503)
        if (response.status === 503) {
            const errorData = await response.json();
            const reason = errorData.detail?.reason || '입출금 기능이 비활성화되어 있습니다.';
            statusDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="bi bi-info-circle"></i> ${reason}
                </div>
            `;
            form.classList.add('d-none');
            unavailable.classList.add('d-none');
            if (positionWarning) positionWarning.classList.add('d-none');
            return;
        }
        
        const data = await response.json();
        
        if (data.can_withdraw && !data.pending_withdraw) {
            // 시세 정보 저장
            withdrawPriceInfo = {
                trxUsdtPrice: parseFloat(data.trx_usdt_price || 0),
                trxKrwPrice: parseFloat(data.trx_krw_price || 0),
                networkFeeTrx: parseFloat(data.network_fee_trx || 1),
                binanceTradeRate: parseFloat(data.binance_trade_fee_rate || 0.001),
                upbitTradeRate: parseFloat(data.upbit_trade_fee_rate || 0.0005),
            };
            
            // 출금 가능
            statusDiv.innerHTML = `
                <div class="balance-info">
                    <div class="row">
                        <div class="col-6">
                            <div class="balance-label">USDT 잔고</div>
                            <div class="balance-value">${formatNumber(data.usdt_balance)} USDT</div>
                        </div>
                        <div class="col-6">
                            <div class="balance-label">최소 출금</div>
                            <div class="balance-value">${formatNumber(data.min_withdraw_usdt)} USDT</div>
                        </div>
                    </div>
                    <div class="row mt-2">
                        <div class="col-6">
                            <div class="balance-label">TRX/USDT</div>
                            <div class="balance-value">${formatNumber(withdrawPriceInfo.trxUsdtPrice)} USDT</div>
                        </div>
                        <div class="col-6">
                            <div class="balance-label">TRX/KRW</div>
                            <div class="balance-value">${formatNumber(withdrawPriceInfo.trxKrwPrice)}원</div>
                        </div>
                    </div>
                </div>
            `;
            form.classList.remove('d-none');
            unavailable.classList.add('d-none');
            
            // 포지션 경고
            if (data.has_position) {
                positionWarning.classList.remove('d-none');
                document.getElementById('position-warning-msg').textContent = 
                    `${data.position_count}개의 포지션이 있습니다. 출금 시 주의하세요.`;
            } else {
                positionWarning.classList.add('d-none');
            }
            
            // 최대 출금 가능 금액 설정
            maxWithdrawAmount = parseFloat(data.usdt_balance);
            document.getElementById('withdraw-amount').max = maxWithdrawAmount;
            
            // 예상 금액 계산 이벤트 바인딩
            const amountInput = document.getElementById('withdraw-amount');
            amountInput.removeEventListener('input', updateWithdrawEstimate);
            amountInput.addEventListener('input', updateWithdrawEstimate);
            
        } else if (data.pending_withdraw) {
            // 출금 진행 중
            statusDiv.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-hourglass-split"></i> 출금이 진행 중입니다.
                </div>
            `;
            form.classList.add('d-none');
            unavailable.classList.add('d-none');
            currentTransferId = data.pending_transfer_id;
            loadTransferProgress(data.pending_transfer_id);
            
        } else {
            // 출금 불가
            statusDiv.innerHTML = '';
            form.classList.add('d-none');
            unavailable.classList.remove('d-none');
            document.getElementById('withdraw-unavailable-msg').textContent = 
                'USDT 잔고가 부족합니다. (최소 10 USDT 필요)';
        }
        
    } catch (error) {
        console.error('Failed to load withdraw status:', error);
        statusDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle"></i> 상태 조회 실패
            </div>
        `;
    }
}

// =========================================================================
// 입금 요청
// =========================================================================

document.getElementById('deposit-form')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const amount = document.getElementById('deposit-amount').value;
    if (!amount || parseFloat(amount) < 5000) {
        alert('최소 입금 금액은 5,000원입니다.');
        return;
    }
    
    const btn = document.getElementById('deposit-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 처리 중...';
    
    try {
        const response = await fetch(`${API_BASE}/deposit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount_krw: amount })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '입금 요청 실패');
        }
        
        const data = await response.json();
        currentTransferId = data.transfer_id;
        
        // 상태 갱신
        loadDepositStatus();
        loadTransferProgress(data.transfer_id);
        startPolling();
        
    } catch (error) {
        alert('입금 요청 실패: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-circle"></i> 입금 시작';
    }
});

// =========================================================================
// 출금 요청
// =========================================================================

document.getElementById('withdraw-form')?.addEventListener('submit', async function(e) {
    e.preventDefault();
    
    const amount = document.getElementById('withdraw-amount').value;
    if (!amount || parseFloat(amount) < 10) {
        alert('최소 출금 금액은 10 USDT입니다.');
        return;
    }
    
    const btn = document.getElementById('withdraw-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 처리 중...';
    
    try {
        const response = await fetch(`${API_BASE}/withdraw`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount_usdt: amount })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '출금 요청 실패');
        }
        
        const data = await response.json();
        currentTransferId = data.transfer_id;
        
        // 상태 갱신
        loadWithdrawStatus();
        loadTransferProgress(data.transfer_id);
        startPolling();
        
    } catch (error) {
        alert('출금 요청 실패: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-check-circle"></i> 출금 시작';
    }
});

// =========================================================================
// 진행 상태 표시
// =========================================================================

async function loadTransferProgress(transferId) {
    const section = document.getElementById('progress-section');
    
    try {
        const response = await fetch(`${API_BASE}/${transferId}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        // 진행 상태 표시
        section.style.display = 'block';
        
        const progress = (data.current_step / data.total_steps) * 100;
        document.getElementById('progress-bar').style.width = `${progress}%`;
        document.getElementById('progress-bar').textContent = `${Math.round(progress)}%`;
        
        document.getElementById('progress-type').textContent = 
            data.transfer_type === 'DEPOSIT' ? '입금' : '출금';
        document.getElementById('progress-type').className = 
            'badge ' + (data.transfer_type === 'DEPOSIT' ? 'bg-success' : 'bg-danger');
        
        document.getElementById('progress-status').textContent = getStatusText(data.status);
        document.getElementById('progress-status').className = 
            'badge status-' + data.status.toLowerCase();
        
        document.getElementById('progress-amount').textContent = 
            formatNumber(data.requested_amount) + 
            (data.transfer_type === 'DEPOSIT' ? '원' : ' USDT');
        
        document.getElementById('progress-step').textContent = 
            `${data.current_step} / ${data.total_steps}`;
        
        document.getElementById('progress-id').textContent = data.transfer_id;
        
        // 취소 버튼 표시 여부
        const cancelBtn = document.getElementById('cancel-btn');
        const cancellable = ['PENDING', 'PURCHASING'].includes(data.status);
        cancelBtn.style.display = cancellable ? 'inline-block' : 'none';
        
        // 완료/실패 시 폴링 중지 및 알림 표시
        if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(data.status)) {
            stopPolling();
            loadDepositStatus();
            loadWithdrawStatus();
            loadHistory();
            
            // Toast 알림 표시
            const typeText = data.transfer_type === 'DEPOSIT' ? '입금' : '출금';
            if (data.status === 'COMPLETED') {
                const actualAmount = data.actual_amount 
                    ? formatNumber(data.actual_amount) + (data.transfer_type === 'DEPOSIT' ? ' USDT' : '원')
                    : '';
                showToast(`${typeText} 완료! ${actualAmount}`, 'success');
            } else if (data.status === 'FAILED') {
                showToast(`${typeText} 실패: ${data.error_message || '알 수 없는 오류'}`, 'danger');
            } else if (data.status === 'CANCELLED') {
                showToast(`${typeText}이 취소되었습니다.`, 'warning');
            }
            
            // 진행 상태 섹션 3초 후 숨김
            setTimeout(() => {
                section.style.display = 'none';
            }, 3000);
        }
        
    } catch (error) {
        console.error('Failed to load transfer progress:', error);
    }
}

// =========================================================================
// 진행 중인 이체 확인
// =========================================================================

async function checkPendingTransfers() {
    try {
        const response = await fetch(`${API_BASE}/pending/list`);
        const data = await response.json();
        
        const alert = document.getElementById('pending-alert');
        
        if (data.transfers.length > 0) {
            const transfer = data.transfers[0];
            currentTransferId = transfer.transfer_id;
            
            alert.classList.remove('d-none');
            document.getElementById('pending-message').textContent = 
                `${transfer.transfer_type === 'DEPOSIT' ? '입금' : '출금'}이 진행 중입니다... ` +
                `(${transfer.current_step}/${transfer.total_steps})`;
            
            loadTransferProgress(transfer.transfer_id);
            
            if (!pollingInterval) {
                startPolling();
            }
        } else {
            alert.classList.add('d-none');
            document.getElementById('progress-section').style.display = 'none';
            stopPolling();
        }
        
    } catch (error) {
        console.error('Failed to check pending transfers:', error);
    }
}

// =========================================================================
// 이체 내역
// =========================================================================

async function loadHistory() {
    const tbody = document.getElementById('history-table');
    
    try {
        const response = await fetch(`${API_BASE}/?limit=20`);
        const data = await response.json();
        
        if (data.transfers.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-muted">이체 내역이 없습니다.</td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = data.transfers.map(t => `
            <tr onclick="showTransferDetail('${t.transfer_id}')">
                <td><code>${t.transfer_id}</code></td>
                <td>
                    <span class="badge ${t.transfer_type === 'DEPOSIT' ? 'bg-success' : 'bg-danger'}">
                        ${t.transfer_type === 'DEPOSIT' ? '입금' : '출금'}
                    </span>
                </td>
                <td>${formatNumber(t.requested_amount)}${t.transfer_type === 'DEPOSIT' ? '원' : ' USDT'}</td>
                <td>${t.actual_amount ? formatNumber(t.actual_amount) + (t.transfer_type === 'DEPOSIT' ? ' USDT' : '원') : '-'}</td>
                <td><span class="badge status-${t.status.toLowerCase()}">${getStatusText(t.status)}</span></td>
                <td>${formatDateTime(t.requested_at)}</td>
                <td>${t.completed_at ? formatDateTime(t.completed_at) : '-'}</td>
            </tr>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load history:', error);
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="text-center text-danger">로딩 실패</td>
            </tr>
        `;
    }
}

// =========================================================================
// 상세 보기
// =========================================================================

async function showTransferDetail(transferId) {
    try {
        const response = await fetch(`${API_BASE}/${transferId}`);
        const data = await response.json();
        
        const content = document.getElementById('detail-content');
        content.innerHTML = `
            <dl class="row">
                <dt class="col-sm-4">이체 ID</dt>
                <dd class="col-sm-8"><code>${data.transfer_id}</code></dd>
                
                <dt class="col-sm-4">유형</dt>
                <dd class="col-sm-8">
                    <span class="badge ${data.transfer_type === 'DEPOSIT' ? 'bg-success' : 'bg-danger'}">
                        ${data.transfer_type === 'DEPOSIT' ? '입금' : '출금'}
                    </span>
                </dd>
                
                <dt class="col-sm-4">상태</dt>
                <dd class="col-sm-8">
                    <span class="badge status-${data.status.toLowerCase()}">${getStatusText(data.status)}</span>
                </dd>
                
                <dt class="col-sm-4">요청 금액</dt>
                <dd class="col-sm-8">${formatNumber(data.requested_amount)}${data.transfer_type === 'DEPOSIT' ? '원' : ' USDT'}</dd>
                
                <dt class="col-sm-4">실제 금액</dt>
                <dd class="col-sm-8">${data.actual_amount ? formatNumber(data.actual_amount) + (data.transfer_type === 'DEPOSIT' ? ' USDT' : '원') : '-'}</dd>
                
                <dt class="col-sm-4">진행 단계</dt>
                <dd class="col-sm-8">${data.current_step} / ${data.total_steps}</dd>
                
                <dt class="col-sm-4">요청 시각</dt>
                <dd class="col-sm-8">${formatDateTime(data.requested_at)}</dd>
                
                <dt class="col-sm-4">완료 시각</dt>
                <dd class="col-sm-8">${data.completed_at ? formatDateTime(data.completed_at) : '-'}</dd>
                
                ${data.error_message ? `
                <dt class="col-sm-4">에러</dt>
                <dd class="col-sm-8 text-danger">${data.error_message}</dd>
                ` : ''}
            </dl>
        `;
        
        // 재시도 버튼 표시
        const retryBtn = document.getElementById('retry-btn');
        if (data.status === 'FAILED') {
            retryBtn.classList.remove('d-none');
            retryBtn.dataset.transferId = data.transfer_id;
        } else {
            retryBtn.classList.add('d-none');
        }
        
        const modal = new bootstrap.Modal(document.getElementById('detailModal'));
        modal.show();
        
    } catch (error) {
        console.error('Failed to load transfer detail:', error);
        alert('상세 정보 로딩 실패');
    }
}

function viewTransferDetail() {
    if (currentTransferId) {
        showTransferDetail(currentTransferId);
    }
}

// =========================================================================
// 취소 / 재시도
// =========================================================================

async function cancelTransfer() {
    if (!currentTransferId) return;
    
    if (!confirm('이체를 취소하시겠습니까?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/${currentTransferId}/cancel`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '취소 실패');
        }
        
        alert('이체가 취소되었습니다.');
        stopPolling();
        loadDepositStatus();
        loadWithdrawStatus();
        loadHistory();
        document.getElementById('progress-section').style.display = 'none';
        
    } catch (error) {
        alert('취소 실패: ' + error.message);
    }
}

async function retryTransfer() {
    const transferId = document.getElementById('retry-btn').dataset.transferId;
    if (!transferId) return;
    
    try {
        const response = await fetch(`${API_BASE}/${transferId}/retry`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '재시도 실패');
        }
        
        bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();
        
        currentTransferId = transferId;
        loadTransferProgress(transferId);
        startPolling();
        loadHistory();
        
    } catch (error) {
        alert('재시도 실패: ' + error.message);
    }
}

// =========================================================================
// 폴링
// =========================================================================

function startPolling() {
    if (pollingInterval) return;
    
    pollingInterval = setInterval(() => {
        if (currentTransferId) {
            loadTransferProgress(currentTransferId);
        }
    }, 5000); // 5초마다
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
    currentTransferId = null;
}

// =========================================================================
// 유틸리티
// =========================================================================

function formatNumber(value) {
    const num = parseFloat(value);
    if (isNaN(num)) return value;
    return num.toLocaleString('ko-KR', { maximumFractionDigits: 2 });
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('ko-KR');
}

function getStatusText(status) {
    const statusMap = {
        'PENDING': '대기중',
        'PURCHASING': '매수중',
        'SENDING': '전송중',
        'CONFIRMING': '확인중',
        'CONVERTING': '환전중',
        'TRANSFERRING': '이체중',
        'COMPLETED': '완료',
        'FAILED': '실패',
        'CANCELLED': '취소됨'
    };
    return statusMap[status] || status;
}

// =========================================================================
// 퍼센트 버튼
// =========================================================================

function setDepositPercent(percent) {
    if (maxDepositAmount <= 0) return;
    
    let amount = Math.floor(maxDepositAmount * percent / 100);
    
    // 최소 금액 체크
    if (amount < 5000) {
        amount = Math.min(5000, maxDepositAmount);
    }
    
    // 1000원 단위로 내림
    amount = Math.floor(amount / 1000) * 1000;
    
    document.getElementById('deposit-amount').value = amount;
}

function setWithdrawPercent(percent) {
    if (maxWithdrawAmount <= 0) return;
    
    let amount = maxWithdrawAmount * percent / 100;
    
    // 최소 금액 체크
    if (amount < 10) {
        amount = Math.min(10, maxWithdrawAmount);
    }
    
    // 소수점 2자리까지
    amount = Math.floor(amount * 100) / 100;
    
    document.getElementById('withdraw-amount').value = amount;
    
    // 예상 금액 업데이트
    updateWithdrawEstimate();
}

// =========================================================================
// 예상 출금 금액 계산
// =========================================================================

function updateWithdrawEstimate() {
    const amountInput = document.getElementById('withdraw-amount');
    const estimateDiv = document.getElementById('withdraw-estimate');
    
    if (!estimateDiv) return;
    
    const usdtAmount = parseFloat(amountInput.value) || 0;
    
    if (usdtAmount <= 0 || withdrawPriceInfo.trxUsdtPrice <= 0) {
        estimateDiv.classList.add('d-none');
        return;
    }
    
    // 출금 과정 계산:
    // 1. USDT -> TRX 환전 (Binance 거래 수수료 0.1%)
    const usdtAfterFee = usdtAmount * (1 - withdrawPriceInfo.binanceTradeRate);
    const trxAmount = usdtAfterFee / withdrawPriceInfo.trxUsdtPrice;
    
    // 2. TRX 출금 수수료 (1 TRX)
    const trxAfterNetworkFee = Math.max(0, trxAmount - withdrawPriceInfo.networkFeeTrx);
    
    // 3. TRX -> KRW 환전 (Upbit 거래 수수료 0.05%)
    const krwBeforeFee = trxAfterNetworkFee * withdrawPriceInfo.trxKrwPrice;
    const estimatedKrw = krwBeforeFee * (1 - withdrawPriceInfo.upbitTradeRate);
    
    // 수수료 상세
    const binanceFeeUsdt = usdtAmount * withdrawPriceInfo.binanceTradeRate;
    const networkFeeKrw = withdrawPriceInfo.networkFeeTrx * withdrawPriceInfo.trxKrwPrice;
    const upbitFeeKrw = krwBeforeFee * withdrawPriceInfo.upbitTradeRate;
    const totalFeeKrw = (binanceFeeUsdt * withdrawPriceInfo.trxKrwPrice / withdrawPriceInfo.trxUsdtPrice) 
                        + networkFeeKrw + upbitFeeKrw;
    
    // UI 업데이트
    estimateDiv.classList.remove('d-none');
    estimateDiv.innerHTML = `
        <div class="estimate-info">
            <div class="row mb-2">
                <div class="col-12">
                    <div class="estimate-label text-success fw-bold">예상 수령액</div>
                    <div class="estimate-value fs-5 text-success fw-bold">≈ ${formatNumber(Math.floor(estimatedKrw))}원</div>
                </div>
            </div>
            <hr class="my-2">
            <div class="row small text-muted">
                <div class="col-12 mb-1">
                    <i class="bi bi-info-circle"></i> 수수료 내역
                </div>
                <div class="col-6">Binance 거래 (0.1%)</div>
                <div class="col-6 text-end">≈ ${formatNumber(binanceFeeUsdt.toFixed(4))} USDT</div>
                <div class="col-6">네트워크 수수료</div>
                <div class="col-6 text-end">1 TRX (≈ ${formatNumber(Math.floor(networkFeeKrw))}원)</div>
                <div class="col-6">Upbit 거래 (0.05%)</div>
                <div class="col-6 text-end">≈ ${formatNumber(Math.floor(upbitFeeKrw))}원</div>
                <div class="col-6 fw-bold">총 예상 수수료</div>
                <div class="col-6 text-end fw-bold text-danger">≈ ${formatNumber(Math.floor(totalFeeKrw))}원</div>
            </div>
            <div class="row small text-muted mt-2">
                <div class="col-12">
                    <i class="bi bi-exclamation-triangle"></i> 실제 금액은 환율 변동에 따라 달라질 수 있습니다.
                </div>
            </div>
        </div>
    `;
}

// =========================================================================
// Toast 알림
// =========================================================================

function showToast(message, type = 'info') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }
    
    const toastEl = document.createElement('div');
    toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <i class="bi bi-${type === 'success' ? 'check-circle' : type === 'danger' ? 'x-circle' : 'info-circle'}"></i>
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 5000 });
    toast.show();
    
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}
