/**
 * 설정 페이지
 * 
 * Key-Value 편집 모달과 JSON 모드 토글 지원
 */

let configsData = [];
let configModal = null;
let addConfigModal = null;

// 현재 편집 중인 설정
let currentConfig = null;
let originalValues = {};  // 원본 값 (변경 감지용)
let isJsonMode = false;

// 기본값 정의 (힌트 표시용)
const DEFAULT_CONFIGS = {
    "engine": {
        "mode": { default: "RUNNING", desc: "엔진 모드 (RUNNING, PAUSED, SAFE)" },
        "poll_interval_sec": { default: 30, desc: "폴링 주기 (초)" },
    },
    "risk": {
        "max_position_size": { default: "0", desc: "최대 포지션 크기 (0=무제한)" },
        "daily_loss_limit": { default: "0", desc: "일일 손실 한도 (0=무제한)" },
        "max_open_orders": { default: 0, desc: "최대 미체결 주문 수 (0=무제한)" },
        "min_balance": { default: "0", desc: "최소 잔고 (0=무제한)" },
        "risk_per_trade": { default: "0.02", desc: "거래당 리스크 비율 (2%)" },
        "reward_ratio": { default: "1.5", desc: "R:R 비율 (1:1.5)" },
        "partial_tp_ratio": { default: "0.5", desc: "부분 익절 비율 (50%)" },
        "equity_reset_trades": { default: 50, desc: "자산 재평가 주기 (거래 수)" },
    },
    "strategy": {
        "name": { default: null, desc: "전략 이름 (필수)" },
        "module": { default: null, desc: "전략 모듈 경로 (필수)" },
        "class": { default: null, desc: "전략 클래스명 (필수)" },
        "params": { default: {}, desc: "전략 파라미터 (JSON)" },
        "auto_start": { default: false, desc: "봇 시작 시 자동 시작" },
    },
    "strategy_state": {
        "account_equity": { default: "0", desc: "기준 자산 (읽기 전용)" },
        "trade_count_since_reset": { default: 0, desc: "재평가 이후 거래 수 (읽기 전용)" },
        "total_trade_count": { default: 0, desc: "총 거래 수 (읽기 전용)" },
    },
    "transfer": {
        "min_deposit_krw": { default: 5000, desc: "최소 입금 금액 (KRW)" },
        "min_withdraw_usdt": { default: 10, desc: "최소 출금 금액 (USDT)" },
        "trx_fee": { default: 1, desc: "TRX 출금 수수료" },
        "daily_withdraw_limit_usdt": { default: 0, desc: "일일 출금 한도 (0=무제한)" },
        "krw_deposit_hold_hours": { default: 24, desc: "KRW 입금 후 대기 시간 (시간)" },
    },
    "bnb_fee": {
        "enabled": { default: true, desc: "BNB 자동 충전 활성화" },
        "min_bnb_ratio": { default: "0.01", desc: "최소 BNB 비율 (1%)" },
        "target_bnb_ratio": { default: "0.02", desc: "충전 목표 비율 (2%)" },
        "min_trigger_usdt": { default: "10", desc: "최소 트리거 금액 (USDT)" },
        "check_interval_sec": { default: 3600, desc: "체크 주기 (초)" },
    },
};

// 읽기 전용 설정 키
const READONLY_CONFIG_KEYS = ["strategy_state"];

document.addEventListener('DOMContentLoaded', () => {
    configModal = new bootstrap.Modal(document.getElementById('configModal'));
    addConfigModal = new bootstrap.Modal(document.getElementById('addConfigModal'));
    
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
    const container = document.getElementById('configs-container');
    
    try {
        configsData = await AE.api('/api/config');
        
        if (!configsData || configsData.length === 0) {
            container.innerHTML = `
                <div class="col-12 text-center py-4">
                    <i class="bi bi-inbox" style="font-size: 3rem; color: #ccc;"></i>
                    <p class="mt-2 text-muted">설정이 없습니다.</p>
                    <button class="btn btn-primary" onclick="showAddModal()">
                        <i class="bi bi-plus-lg"></i> 설정 추가
                    </button>
                </div>
            `;
            return;
        }
        
        container.innerHTML = configsData.map((config, index) => {
            const valuePreview = formatValuePreview(config.value);
            const updatedAt = AE.formatKST(config.updated_at);
            const isReadonly = READONLY_CONFIG_KEYS.includes(config.key);
            const fieldCount = typeof config.value === 'object' ? Object.keys(config.value).length : 1;
            
            return `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card config-card h-100 ${isReadonly ? 'border-secondary' : ''}" onclick="editConfig(${index})" style="cursor: pointer;">
                        <div class="card-body">
                            <h5 class="card-title d-flex align-items-center">
                                <i class="bi bi-gear me-2"></i> 
                                ${config.key}
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
        }).join('');
        
    } catch (error) {
        console.error('Load configs error:', error);
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i> 설정을 불러올 수 없습니다.
                </div>
            </div>
        `;
    }
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
    
    // 모달 헤더 설정
    document.getElementById('configModalTitle').textContent = `설정 편집: ${config.key}`;
    document.getElementById('config-key').value = config.key;
    document.getElementById('config-version').value = config.version;
    
    // 읽기 전용 체크
    const isReadonly = READONLY_CONFIG_KEYS.includes(config.key);
    
    // 삭제 버튼 표시/숨김
    document.getElementById('delete-btn').style.display = isReadonly ? 'none' : 'block';
    
    // JSON 모드 토글 초기화
    document.getElementById('json-mode-toggle').checked = false;
    document.getElementById('kv-edit-mode').style.display = 'block';
    document.getElementById('json-edit-mode').style.display = 'none';
    
    // 변경 표시 초기화
    document.getElementById('changes-indicator').style.display = 'none';
    
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
        const isChanged = JSON.stringify(value) !== JSON.stringify(originalValues[key]);
        
        return createFieldHtml(key, value, fieldType, defaultValue, description, isReadonly, isChanged);
    }).join('');
    
    // 이벤트 리스너 연결
    attachFieldEventListeners();
}

/**
 * 필드 HTML 생성
 */
function createFieldHtml(key, value, fieldType, defaultValue, description, isReadonly, isChanged) {
    const typeIcon = getTypeIcon(fieldType);
    const typeBadge = getTypeBadgeClass(fieldType);
    const changedClass = isChanged ? 'border-warning' : '';
    const changedBadge = isChanged ? '<span class="badge bg-warning text-dark ms-1">변경됨</span>' : '';
    
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
            inputHtml = `
                <input type="text" class="form-control form-control-sm field-input ${changedClass}"
                       id="field-${key}" data-field="${key}" data-type="${fieldType}"
                       value="${escapeHtml(String(value))}" ${isReadonly ? 'readonly' : ''}>
            `;
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
        const eventType = input.type === 'checkbox' ? 'change' : 'input';
        
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
// 새 설정 추가
// =============================================================================

function showAddModal() {
    document.getElementById('new-config-key').value = '';
    document.getElementById('new-config-value').value = '{}';
    addConfigModal.show();
}

async function addConfig() {
    const key = document.getElementById('new-config-key').value.trim();
    const valueStr = document.getElementById('new-config-value').value;
    
    if (!key) {
        AE.toast('Key를 입력해주세요.', 'warning');
        return;
    }
    
    let value;
    try {
        value = JSON.parse(valueStr);
    } catch (error) {
        AE.toast('유효하지 않은 JSON 형식입니다.', 'danger');
        return;
    }
    
    try {
        await AE.api(`/api/config/${key}`, {
            method: 'PUT',
            body: JSON.stringify({
                value: value,
            }),
        });
        
        AE.toast('설정이 추가되었습니다.', 'success');
        addConfigModal.hide();
        loadConfigs();
        
    } catch (error) {
        AE.toast(`추가 실패: ${error.message}`, 'danger');
    }
}

// =============================================================================
// 유틸리티
// =============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
