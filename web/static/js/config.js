/**
 * 설정 페이지
 * 
 * Key-Value 편집 모달과 JSON 모드 토글 지원
 */

let configsData = [];
let configModal = null;

// 현재 편집 중인 설정
let currentConfig = null;
let originalValues = {};  // 원본 값 (변경 감지용)
let isJsonMode = false;

// 설정별 전체 설명 및 사용처
const CONFIG_DESCRIPTIONS = {
    "engine": {
        desc: "엔진 동작 모드 및 폴링 주기",
        usage: "RiskGuard(엔진 모드 검사), ConfigStore.get_engine_mode()",
    },
    "risk": {
        desc: "리스크 관리 규칙. Command 발행 전 RiskGuard가 검증",
        usage: "RiskGuard(주문 전 검증), 전략 ctx.risk_per_trade 등",
    },
    "strategy": {
        desc: "실행할 전략. Bot 시작 시 로드",
        usage: "BotEngine._load_and_start_strategy()",
    },
    "strategy_state": {
        desc: "전략 상태 (Bot이 거래 시 자동 저장)",
        usage: "StrategyRunner(재시작 시 복원)",
    },
    "transfer": {
        desc: "입출금 관리 제한. Upbit↔Binance 이체 시 적용",
        usage: "TransferManager, Web 입출금 페이지",
    },
    "bnb_fee": {
        desc: "BNB 수수료 할인을 위한 자동 충전",
        usage: "BnbFeeManager(production 모드)",
    },
    "bot_status": {
        desc: "Bot 프로세스 상태 (heartbeat 등)",
        usage: "BotEngine, Web 대시보드",
    },
    "price_cache": {
        desc: "가격 캐시. Bot이 60초마다 Binance API로 갱신",
        usage: "AssetService(자산 USDT 환산)",
    },
    "initial_capital": {
        desc: "최초 실행 시 초기 자산 기록",
        usage: "InitialCapitalRecorder, PnLService(수익률 계산)",
    },
    "poller_income_last_poll": {
        desc: "수익(펀딩비 등) 폴러 마지막 폴링 시각",
        usage: "BotEngine IncomePoller",
    },
    "poller_transfer_last_poll": {
        desc: "이체 폴러 마지막 폴링 시각",
        usage: "BotEngine TransferPoller",
    },
    "poller_convert_last_poll": {
        desc: "환전 폴러 마지막 폴링 시각",
        usage: "BotEngine ConvertPoller",
    },
    "poller_deposit_withdraw_last_poll": {
        desc: "입출금 폴러 마지막 폴링 시각",
        usage: "BotEngine DepositWithdrawPoller",
    },
    "poller_reconciliation_last_poll": {
        desc: "정합 폴러 마지막 폴링 시각",
        usage: "BotEngine ReconciliationPoller",
    },
    "poller_reconciliation_last_reconciliation": {
        desc: "마지막 정합 결과",
        usage: "BotEngine ReconciliationPoller",
    },
};

// 기본값 정의 (힌트 표시용) - desc: 설명, usage: 사용처
const DEFAULT_CONFIGS = {
    "engine": {
        "mode": {
            default: "RUNNING",
            desc: "엔진 모드",
            usage: "RiskGuard: PAUSED/SAFE 시 신규 거래 거부",
            options: [
                { value: "RUNNING", label: "정상 (RUNNING)" },
                { value: "PAUSED", label: "거래중지 (PAUSED)" },
                { value: "SAFE", label: "청산만 (SAFE)" },
            ],
        },
        "poll_interval_sec": { default: 30, desc: "폴링 주기 (초)", usage: "ConfigStore 참조용" },
    },
    "risk": {
        "max_position_size": { default: "0", desc: "최대 포지션 크기 (0=무제한)", usage: "RiskGuard MaxPositionSizeRule" },
        "daily_loss_limit": { default: "0", desc: "일일 손실 한도 USDT (0=무제한)", usage: "RiskGuard DailyLossLimitRule" },
        "max_open_orders": { default: 0, desc: "최대 미체결 주문 수 (0=무제한)", usage: "RiskGuard MaxOpenOrdersRule" },
        "min_balance": { default: "0", desc: "최소 잔고 USDT (0=무제한)", usage: "RiskGuard MinBalanceRule" },
        "risk_per_trade": { default: "0.02", desc: "거래당 리스크 비율 (2%)", usage: "전략 ctx.risk_per_trade, 수량 계산" },
        "reward_ratio": { default: "1.5", desc: "R:R 비율 (1:1.5)", usage: "전략 ctx.reward_ratio, 익절가 계산" },
        "partial_tp_ratio": { default: "0.5", desc: "부분 익절 비율 (50%)", usage: "전략 ctx.partial_tp_ratio" },
        "equity_reset_trades": { default: 50, desc: "자산 재평가 주기 (거래 수)", usage: "전략 ctx.equity_reset_trades" },
    },
    "strategy": {
        "name": { default: null, desc: "전략 표시 이름", usage: "Web UI 표시" },
        "module": { default: null, desc: "전략 모듈 경로 (예: strategies.examples.sma_cross)", usage: "BotEngine 전략 로드" },
        "class": { default: null, desc: "전략 클래스명 (예: SmaCrossStrategy)", usage: "BotEngine 전략 로드" },
        "params": { default: {}, desc: "전략 파라미터 (JSON)", usage: "전략 on_init()에 전달" },
        "auto_start": { default: false, desc: "Bot 시작 시 자동 시작", usage: "BotEngine._load_and_start_strategy()" },
    },
    "strategy_state": {
        "account_equity": { default: "0", desc: "기준 자산 (50거래 재평가용)", usage: "전략 수량 계산" },
        "trade_count_since_reset": { default: 0, desc: "재평가 이후 거래 수", usage: "전략 equity_reset" },
        "total_trade_count": { default: 0, desc: "총 거래 수", usage: "전략 상태 저장" },
    },
    "transfer": {
        "min_deposit_krw": { default: 5000, desc: "최소 입금 금액 (KRW)", usage: "Upbit 입금 가능 여부" },
        "min_withdraw_usdt": { default: 10, desc: "최소 출금 금액 (USDT)", usage: "Web 출금, WithdrawHandler" },
        "trx_fee": { default: 1, desc: "TRX 출금 수수료", usage: "TRX 출금 시 차감" },
        "daily_withdraw_limit_usdt": { default: 0, desc: "일일 출금 한도 (0=무제한)", usage: "출금 제한" },
        "krw_deposit_hold_hours": { default: 24, desc: "KRW 입금 후 대기 시간 (시간)", usage: "입금 후 이체 대기" },
    },
    "bnb_fee": {
        "enabled": { default: true, desc: "BNB 자동 충전 활성화", usage: "BnbFeeManager" },
        "min_bnb_ratio": { default: "0.01", desc: "최소 BNB 비율 (1%)", usage: "충전 트리거" },
        "target_bnb_ratio": { default: "0.02", desc: "충전 목표 비율 (2%)", usage: "충전 목표" },
        "min_trigger_usdt": { default: "10", desc: "최소 트리거 금액 (USDT)", usage: "소액 시 충전 생략" },
        "check_interval_sec": { default: 3600, desc: "체크 주기 (초)", usage: "1시간마다 BNB 비율 확인" },
    },
    "price_cache": {
        "prices": { default: {}, desc: "심볼별 가격 (BNBUSDT 등)", usage: "AssetService USDT 환산" },
        "updated_at": { default: null, desc: "마지막 업데이트 시간", usage: "캐시 유효성" },
    },
    "initial_capital": {
        "initialized": { default: false, desc: "초기 자산 기록 완료 여부", usage: "최초 실행 판단" },
        "epoch_date": { default: null, desc: "기준일", usage: "백필 시작일" },
        "USDT": { default: "0", desc: "초기 USDT 잔고", usage: "PnL 수익률 계산" },
    },
};

// 읽기 전용 설정 키 (시스템에서만 변경 가능, config_service.py와 동기화)
const READONLY_CONFIG_KEYS = [
    "bot_status",
    "strategy_state",
    "price_cache",
    "initial_capital",
    "poller_income_last_poll",
    "poller_transfer_last_poll",
    "poller_convert_last_poll",
    "poller_deposit_withdraw_last_poll",
    "poller_reconciliation_last_poll",
    "poller_reconciliation_last_reconciliation",
];

document.addEventListener('DOMContentLoaded', () => {
    configModal = new bootstrap.Modal(document.getElementById('configModal'));
    
    // JSON 모드 토글 이벤트
    document.getElementById('json-mode-toggle').addEventListener('change', toggleJsonMode);
    
    loadConfigs();
});

// =============================================================================
// 타입 추론 및 유틸리티
// =============================================================================

/**
 * 값의 타입 추론
 * @param {any} value - 원본 값
 * @returns {string} 타입 ('boolean', 'integer', 'number', 'decimal', 'string', 'object', 'null')
 */
function inferFieldType(value) {
    if (value === null) return 'null';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') {
        return Number.isInteger(value) ? 'integer' : 'number';
    }
    if (typeof value === 'string') {
        // 빈 문자열
        if (value === '') return 'string';
        // Decimal 문자열 판별 (숫자로 파싱 가능하면)
        if (/^-?\d+(\.\d+)?$/.test(value)) return 'decimal';
        return 'string';
    }
    if (typeof value === 'object') return 'object';
    return 'unknown';
}

/**
 * 타입별 아이콘 반환
 */
function getTypeIcon(type) {
    const icons = {
        'boolean': 'bi-toggle-on',
        'integer': 'bi-123',
        'number': 'bi-123',
        'decimal': 'bi-currency-dollar',
        'string': 'bi-fonts',
        'object': 'bi-braces',
        'null': 'bi-dash-circle',
        'unknown': 'bi-question-circle',
    };
    return icons[type] || 'bi-question-circle';
}

/**
 * 타입별 배지 색상 반환
 */
function getTypeBadgeClass(type) {
    const classes = {
        'boolean': 'bg-success',
        'integer': 'bg-primary',
        'number': 'bg-primary',
        'decimal': 'bg-info',
        'string': 'bg-secondary',
        'object': 'bg-warning text-dark',
        'null': 'bg-dark',
    };
    return classes[type] || 'bg-secondary';
}

/**
 * 입력값을 원래 타입으로 변환
 */
function convertToOriginalType(inputValue, originalType, originalValue) {
    switch (originalType) {
        case 'boolean':
            return inputValue === true || inputValue === 'true';
        case 'integer':
            const intVal = parseInt(inputValue, 10);
            return isNaN(intVal) ? originalValue : intVal;
        case 'number':
            const numVal = parseFloat(inputValue);
            return isNaN(numVal) ? originalValue : numVal;
        case 'decimal':
            // Decimal은 문자열로 유지
            if (inputValue === '' || inputValue === null) return originalValue;
            return String(inputValue);
        case 'string':
            return String(inputValue);
        case 'object':
            try {
                return JSON.parse(inputValue);
            } catch {
                return originalValue;
            }
        case 'null':
            if (inputValue === '' || inputValue === 'null') return null;
            return inputValue;
        default:
            return inputValue;
    }
}

// =============================================================================
// 설정 로드 및 표시
// =============================================================================

async function loadConfigs() {
    const loadingEl = document.getElementById('configs-loading');
    const accordionWrapper = document.getElementById('configs-accordion-wrapper');
    
    try {
        configsData = await AE.api('/api/config');
        
        if (!configsData || configsData.length === 0) {
            loadingEl.style.display = 'none';
            accordionWrapper.style.display = 'block';
            document.getElementById('editable-count').textContent = '0';
            document.getElementById('readonly-count').textContent = '0';
            document.getElementById('editable-configs-grid').innerHTML = `
                <div class="col-12 text-center py-4">
                    <i class="bi bi-inbox" style="font-size: 3rem; color: #ccc;"></i>
                    <p class="mt-2 text-muted">설정이 없습니다. Bot을 시작하면 기본 설정이 생성됩니다.</p>
                </div>
            `;
            document.getElementById('readonly-configs-grid').innerHTML = '';
            return;
        }
        
        // 편집 가능 / 편집 불가 분리
        const editableConfigs = configsData.filter(c => !READONLY_CONFIG_KEYS.includes(c.key));
        const readonlyConfigs = configsData.filter(c => READONLY_CONFIG_KEYS.includes(c.key));
        
        // 알파벳순 정렬
        editableConfigs.sort((a, b) => a.key.localeCompare(b.key));
        readonlyConfigs.sort((a, b) => a.key.localeCompare(b.key));
        
        loadingEl.style.display = 'none';
        accordionWrapper.style.display = 'block';
        
        // 개수 표시
        document.getElementById('editable-count').textContent = editableConfigs.length;
        document.getElementById('readonly-count').textContent = readonlyConfigs.length;
        
        // 편집 가능한 설정 카드 렌더링
        const editableGrid = document.getElementById('editable-configs-grid');
        editableGrid.innerHTML = editableConfigs.length > 0
            ? editableConfigs.map((config) => renderConfigCard(config, false)).join('')
            : '<div class="col-12 text-center py-3 text-muted">편집 가능한 설정이 없습니다.</div>';
        
        // 편집 불가 설정 카드 렌더링
        const readonlyGrid = document.getElementById('readonly-configs-grid');
        readonlyGrid.innerHTML = readonlyConfigs.length > 0
            ? readonlyConfigs.map((config) => renderConfigCard(config, true)).join('')
            : '<div class="col-12 text-center py-3 text-muted">편집 불가 설정이 없습니다.</div>';
        
        // 카드 툴팁 초기화
        initTooltips(accordionWrapper);
        
    } catch (error) {
        console.error('Load configs error:', error);
        loadingEl.style.display = 'none';
        accordionWrapper.style.display = 'block';
        const existingError = document.getElementById('configs-load-error');
        if (existingError) existingError.remove();
        const errorDiv = document.createElement('div');
        errorDiv.id = 'configs-load-error';
        errorDiv.className = 'alert alert-danger mb-3';
        errorDiv.innerHTML = '<i class="bi bi-exclamation-triangle"></i> 설정을 불러올 수 없습니다.';
        accordionWrapper.insertBefore(errorDiv, accordionWrapper.firstChild);
    }
}

/**
 * 설정 카드 HTML 생성
 */
function renderConfigCard(config, isReadonly) {
    const index = configsData.findIndex(c => c.key === config.key);
    const valuePreview = formatValuePreview(config.value);
    const updatedAt = AE.formatKST(config.updated_at);
    const fieldCount = typeof config.value === 'object' ? Object.keys(config.value).length : 1;
    const meta = CONFIG_DESCRIPTIONS[config.key];
    const tooltipText = meta
        ? `${meta.desc} · 사용처: ${meta.usage}`
        : '';
    const tooltipAttr = tooltipText
        ? ` data-bs-toggle="tooltip" data-bs-placement="top" data-bs-title="${escapeAttr(tooltipText)}"`
        : '';
    
    return `
        <div class="col-md-6 col-lg-4 mb-3">
            <div class="card config-card h-100 ${isReadonly ? 'border-secondary' : ''}" onclick="editConfig(${index})" style="cursor: pointer;">
                <div class="card-body">
                    <h5 class="card-title d-flex align-items-center">
                        <i class="bi bi-gear me-2"></i> 
                        ${config.key}
                        ${tooltipAttr ? `<i class="bi bi-info-circle text-muted ms-1"${tooltipAttr} style="cursor: help;"></i>` : ''}
                        ${isReadonly ? '<span class="badge bg-secondary ms-2 small">읽기전용</span>' : ''}
                    </h5>
                    <p class="config-key text-muted mb-2">
                        v${config.version} · ${fieldCount}개 필드
                    </p>
                    <pre class="json-viewer small" style="max-height: 100px; overflow: hidden;">${valuePreview}</pre>
                </div>
                <div class="card-footer text-muted small">
                    ${updatedAt} by ${config.updated_by || '-'}
                </div>
            </div>
        </div>
    `;
}

function formatValuePreview(value) {
    try {
        if (typeof value === 'object') {
            return JSON.stringify(value, null, 2).substring(0, 200);
        }
        return String(value).substring(0, 200);
    } catch {
        return String(value).substring(0, 200);
    }
}

// =============================================================================
// Key-Value 편집 모달
// =============================================================================

function editConfig(index) {
    const config = configsData[index];
    if (!config) return;
    
    currentConfig = config;
    originalValues = JSON.parse(JSON.stringify(config.value));
    isJsonMode = false;
    
    // 읽기 전용 체크
    const isReadonly = READONLY_CONFIG_KEYS.includes(config.key);
    
    // 모달 헤더 설정
    document.getElementById('configModalTitle').textContent = isReadonly
        ? `설정 조회: ${config.key}`
        : `설정 편집: ${config.key}`;
    document.getElementById('config-key').value = config.key;
    document.getElementById('config-version').value = config.version;
    
    // 삭제/저장 버튼 표시/숨김 (읽기 전용은 조회만 가능)
    document.getElementById('delete-btn').style.display = isReadonly ? 'none' : 'block';
    document.getElementById('save-btn').style.display = isReadonly ? 'none' : 'inline-block';
    
    // JSON 모드 토글 초기화
    document.getElementById('json-mode-toggle').checked = false;
    document.getElementById('kv-edit-mode').style.display = 'block';
    document.getElementById('json-edit-mode').style.display = 'none';
    
    // 변경 표시 초기화
    document.getElementById('changes-indicator').style.display = 'none';
    
    // 설정 설명 표시
    const meta = CONFIG_DESCRIPTIONS[config.key];
    const descAlert = document.getElementById('config-desc-alert');
    const descText = document.getElementById('config-desc-text');
    if (meta) {
        descAlert.style.display = 'block';
        descText.innerHTML = `<strong>${escapeHtml(meta.desc)}</strong><br><small class="text-muted">사용처: ${escapeHtml(meta.usage)}</small>`;
    } else {
        descAlert.style.display = 'none';
    }
    
    // Key-Value 필드 생성
    renderKvFields(config.key, config.value, isReadonly);
    
    // JSON 텍스트 영역 설정
    document.getElementById('config-value-json').value = JSON.stringify(config.value, null, 2);
    
    configModal.show();
}

/**
 * Key-Value 필드 렌더링
 */
function renderKvFields(configKey, values, isReadonly = false) {
    const container = document.getElementById('kv-fields-container');
    const defaultConfig = DEFAULT_CONFIGS[configKey] || {};
    
    disposeTooltips(container);
    
    if (typeof values !== 'object' || values === null) {
        // 단일 값인 경우
        container.innerHTML = `
            <div class="alert alert-info">
                이 설정은 단순 값입니다. JSON 모드에서 편집하세요.
            </div>
        `;
        document.getElementById('json-mode-toggle').checked = true;
        toggleJsonMode();
        return;
    }
    
    const fields = Object.entries(values);
    
    if (fields.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                설정이 비어 있습니다. JSON 모드에서 필드를 추가하세요.
            </div>
        `;
        return;
    }
    
    container.innerHTML = fields.map(([key, value]) => {
        const fieldType = inferFieldType(value);
        const fieldDefault = defaultConfig[key];
        const defaultValue = fieldDefault?.default;
        const description = fieldDefault?.desc || '';
        const usage = fieldDefault?.usage || '';
        const options = fieldDefault?.options;
        const isChanged = JSON.stringify(value) !== JSON.stringify(originalValues[key]);
        
        return createFieldHtml(key, value, fieldType, defaultValue, description, usage, options, isReadonly, isChanged);
    }).join('');
    
    // 이벤트 리스너 연결
    attachFieldEventListeners();
    
    // 필드 툴팁 초기화
    initTooltips(container);
}

/**
 * 필드 HTML 생성
 */
function createFieldHtml(key, value, fieldType, defaultValue, description, usage, options, isReadonly, isChanged) {
    const typeIcon = getTypeIcon(fieldType);
    const typeBadge = getTypeBadgeClass(fieldType);
    const changedClass = isChanged ? 'border-warning' : '';
    const changedBadge = isChanged ? '<span class="badge bg-warning text-dark ms-1">변경됨</span>' : '';
    const tooltipText = usage ? `${description || key} · 사용처: ${usage}` : (description || '');
    const tooltipAttr = tooltipText
        ? ` data-bs-toggle="tooltip" data-bs-placement="top" data-bs-title="${escapeAttr(tooltipText)}"`
        : '';
    
    let inputHtml = '';
    
    switch (fieldType) {
        case 'boolean':
            inputHtml = `
                <div class="form-check form-switch">
                    <input class="form-check-input field-input" type="checkbox" 
                           id="field-${key}" data-field="${key}" data-type="${fieldType}"
                           ${value ? 'checked' : ''} ${isReadonly ? 'disabled' : ''}>
                    <label class="form-check-label" for="field-${key}">
                        ${value ? '활성화' : '비활성화'}
                    </label>
                </div>
            `;
            break;
            
        case 'integer':
            inputHtml = `
                <input type="number" step="1" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="${value}" ${isReadonly ? 'readonly' : ''}>
            `;
            break;
            
        case 'number':
            inputHtml = `
                <input type="number" step="any" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="${value}" ${isReadonly ? 'readonly' : ''}>
            `;
            break;
            
        case 'decimal':
            inputHtml = `
                <input type="text" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="${value}" pattern="^-?\\d+(\\.\\d+)?$"
                       ${isReadonly ? 'readonly' : ''}>
                <div class="invalid-feedback">숫자 형식이 올바르지 않습니다.</div>
            `;
            break;
            
        case 'string':
            // options가 있으면 select로 렌더링 (고정 선택지)
            if (options && Array.isArray(options) && options.length > 0) {
                const strValue = String(value ?? '');
                const hasValue = options.some(opt => opt.value === strValue);
                let optsHtml = options.map(opt =>
                    `<option value="${escapeAttr(opt.value)}" ${opt.value === strValue ? 'selected' : ''}>${escapeHtml(opt.label)}</option>`
                ).join('');
                // DB에 옵션에 없는 값이 저장된 경우 해당 값도 선택지에 포함
                if (!hasValue && strValue) {
                    optsHtml = `<option value="${escapeAttr(strValue)}" selected>${escapeHtml(strValue)}</option>` + optsHtml;
                }
                inputHtml = `
                    <select class="form-select form-select-sm field-input ${changedClass}"
                            id="field-${key}" data-field="${key}" data-type="${fieldType}"
                            ${isReadonly ? 'disabled' : ''}>
                        ${optsHtml}
                    </select>
                `;
            } else {
                inputHtml = `
                    <input type="text" class="form-control form-control-sm field-input ${changedClass}"
                           id="field-${key}" data-field="${key}" data-type="${fieldType}"
                           value="${escapeHtml(String(value))}" ${isReadonly ? 'readonly' : ''}>
                `;
            }
            break;
            
        case 'object':
            inputHtml = `
                <textarea class="form-control form-control-sm font-monospace field-input ${changedClass}"
                          id="field-${key}" data-field="${key}" data-type="${fieldType}"
                          rows="3" ${isReadonly ? 'readonly' : ''}>${JSON.stringify(value, null, 2)}</textarea>
                <div class="invalid-feedback">유효한 JSON 형식이 아닙니다.</div>
            `;
            break;
            
        case 'null':
            inputHtml = `
                <input type="text" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="null" placeholder="null" ${isReadonly ? 'readonly' : ''}>
            `;
            break;
            
        default:
            inputHtml = `
                <input type="text" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="${escapeHtml(String(value))}" ${isReadonly ? 'readonly' : ''}>
            `;
    }
    
    // 기본값 힌트
    let defaultHint = '';
    if (defaultValue !== undefined && defaultValue !== null) {
        const defaultStr = typeof defaultValue === 'object' ? JSON.stringify(defaultValue) : String(defaultValue);
        defaultHint = `<small class="text-muted">기본값: ${escapeHtml(defaultStr)}</small>`;
    }
    
    return `
        <div class="mb-3 config-field" data-field="${key}">
            <label class="form-label d-flex align-items-center" for="field-${key}">
                <span class="badge ${typeBadge} me-2">
                    <i class="bi ${typeIcon}"></i>
                </span>
                <code>${key}</code>
                ${tooltipAttr ? `<i class="bi bi-info-circle text-muted ms-1"${tooltipAttr} style="cursor: help;"></i>` : ''}
                ${changedBadge}
            </label>
            ${inputHtml}
            <div class="d-flex justify-content-between mt-1">
                <small class="text-muted">${description}</small>
                ${defaultHint}
            </div>
        </div>
    `;
}

/**
 * 필드 이벤트 리스너 연결
 */
function attachFieldEventListeners() {
    const inputs = document.querySelectorAll('.field-input');
    
    inputs.forEach(input => {
        const eventType = (input.type === 'checkbox' || input.tagName === 'SELECT') ? 'change' : 'input';
        
        input.addEventListener(eventType, (e) => {
            validateField(e.target);
            updateChangesIndicator();
            
            // 체크박스 라벨 업데이트
            if (input.type === 'checkbox') {
                const label = input.nextElementSibling;
                if (label) {
                    label.textContent = input.checked ? '활성화' : '비활성화';
                }
            }
        });
    });
}

/**
 * 필드 유효성 검사
 */
function validateField(input) {
    const fieldType = input.dataset.type;
    const value = input.type === 'checkbox' ? input.checked : input.value;
    let isValid = true;
    
    switch (fieldType) {
        case 'decimal':
            isValid = /^-?\d+(\.\d+)?$/.test(value) || value === '';
            break;
        case 'integer':
            isValid = /^-?\d+$/.test(value) || value === '';
            break;
        case 'object':
            try {
                JSON.parse(value);
            } catch {
                isValid = false;
            }
            break;
    }
    
    if (isValid) {
        input.classList.remove('is-invalid');
        input.classList.add('is-valid');
    } else {
        input.classList.remove('is-valid');
        input.classList.add('is-invalid');
    }
    
    return isValid;
}

/**
 * 변경 사항 표시 업데이트
 */
function updateChangesIndicator() {
    const currentValues = collectFieldValues();
    const hasChanges = JSON.stringify(currentValues) !== JSON.stringify(originalValues);
    
    document.getElementById('changes-indicator').style.display = hasChanges ? 'inline' : 'none';
    
    // 각 필드의 변경 상태 업데이트
    document.querySelectorAll('.config-field').forEach(fieldDiv => {
        const fieldName = fieldDiv.dataset.field;
        const input = fieldDiv.querySelector('.field-input');
        const isChanged = JSON.stringify(currentValues[fieldName]) !== JSON.stringify(originalValues[fieldName]);
        
        if (isChanged) {
            input.classList.add('border-warning');
            const existingBadge = fieldDiv.querySelector('.badge.bg-warning.text-dark');
            if (!existingBadge) {
                const label = fieldDiv.querySelector('label');
                const badge = document.createElement('span');
                badge.className = 'badge bg-warning text-dark ms-1';
                badge.textContent = '변경됨';
                label.appendChild(badge);
            }
        } else {
            input.classList.remove('border-warning');
            const badge = fieldDiv.querySelector('.badge.bg-warning.text-dark');
            if (badge) badge.remove();
        }
    });
}

/**
 * 필드 값 수집
 */
function collectFieldValues() {
    const values = {};
    const inputs = document.querySelectorAll('.field-input');
    
    inputs.forEach(input => {
        const fieldName = input.dataset.field;
        const fieldType = input.dataset.type;
        let value;
        
        if (input.type === 'checkbox') {
            value = input.checked;
        } else {
            value = input.value;
        }
        
        values[fieldName] = convertToOriginalType(value, fieldType, originalValues[fieldName]);
    });
    
    return values;
}

// =============================================================================
// JSON 모드 토글
// =============================================================================

function toggleJsonMode() {
    isJsonMode = document.getElementById('json-mode-toggle').checked;
    
    if (isJsonMode) {
        // KV 모드의 현재 값을 JSON으로 변환
        const currentValues = collectFieldValues();
        document.getElementById('config-value-json').value = JSON.stringify(currentValues, null, 2);
        
        document.getElementById('kv-edit-mode').style.display = 'none';
        document.getElementById('json-edit-mode').style.display = 'block';
    } else {
        // JSON 값을 파싱하여 KV 모드로 전환
        try {
            const jsonValue = JSON.parse(document.getElementById('config-value-json').value);
            const configKey = document.getElementById('config-key').value;
            const isReadonly = READONLY_CONFIG_KEYS.includes(configKey);
            
            renderKvFields(configKey, jsonValue, isReadonly);
            
            document.getElementById('kv-edit-mode').style.display = 'block';
            document.getElementById('json-edit-mode').style.display = 'none';
            document.getElementById('json-error').textContent = '';
            document.getElementById('config-value-json').classList.remove('is-invalid');
        } catch (error) {
            document.getElementById('json-error').textContent = '유효하지 않은 JSON 형식입니다: ' + error.message;
            document.getElementById('config-value-json').classList.add('is-invalid');
            // JSON 모드 유지
            document.getElementById('json-mode-toggle').checked = true;
        }
    }
}

// =============================================================================
// 저장 및 삭제
// =============================================================================

async function saveConfig() {
    const key = document.getElementById('config-key').value;
    const version = parseInt(document.getElementById('config-version').value);
    
    let value;
    
    if (isJsonMode) {
        // JSON 모드에서 값 가져오기
        try {
            value = JSON.parse(document.getElementById('config-value-json').value);
        } catch (error) {
            AE.toast('유효하지 않은 JSON 형식입니다.', 'danger');
            return;
        }
    } else {
        // KV 모드에서 값 수집
        // 모든 필드 유효성 검사
        let allValid = true;
        document.querySelectorAll('.field-input').forEach(input => {
            if (!validateField(input)) {
                allValid = false;
            }
        });
        
        if (!allValid) {
            AE.toast('입력값이 올바르지 않습니다. 오류를 수정해주세요.', 'danger');
            return;
        }
        
        value = collectFieldValues();
    }
    
    try {
        await AE.api(`/api/config/${key}`, {
            method: 'PUT',
            body: JSON.stringify({
                value: value,
                expected_version: version,
            }),
        });
        
        AE.toast('설정이 저장되었습니다.', 'success');
        configModal.hide();
        loadConfigs();
        
    } catch (error) {
        AE.toast(`저장 실패: ${error.message}`, 'danger');
    }
}

async function deleteConfig() {
    const key = document.getElementById('config-key').value;
    
    if (!await AE.confirm(`"${key}" 설정을 삭제하시겠습니까?`)) {
        return;
    }
    
    try {
        await AE.api(`/api/config/${key}`, {
            method: 'DELETE',
        });
        
        AE.toast('설정이 삭제되었습니다.', 'success');
        configModal.hide();
        loadConfigs();
        
    } catch (error) {
        AE.toast(`삭제 실패: ${error.message}`, 'danger');
    }
}

// =============================================================================
// 툴팁 유틸리티
// =============================================================================

/** 컨테이너 내 툴팁 초기화 (동적 생성 요소용) */
function initTooltips(container) {
    if (!container) return;
    container.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
        if (!bootstrap.Tooltip.getInstance(el)) {
            new bootstrap.Tooltip(el);
        }
    });
}

/** 컨테이너 내 툴팁 해제 (재렌더 전 호출) */
function disposeTooltips(container) {
    if (!container) return;
    container.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(el => {
        const t = bootstrap.Tooltip.getInstance(el);
        if (t) t.dispose();
    });
}

// =============================================================================
// 유틸리티
// =============================================================================

/** HTML 속성용 이스케이프 (툴팁 title 등) */
function escapeAttr(text) {
    if (text == null || text === '') return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
