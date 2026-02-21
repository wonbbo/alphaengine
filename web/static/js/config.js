/**
 * 설정 페이지
 */

let configsData = [];
let configModal = null;
let addConfigModal = null;

document.addEventListener('DOMContentLoaded', () => {
    configModal = new bootstrap.Modal(document.getElementById('configModal'));
    addConfigModal = new bootstrap.Modal(document.getElementById('addConfigModal'));
    
    loadConfigs();
});

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
            
            return `
                <div class="col-md-6 col-lg-4 mb-3">
                    <div class="card config-card h-100" onclick="editConfig(${index})" style="cursor: pointer;">
                        <div class="card-body">
                            <h5 class="card-title">
                                <i class="bi bi-gear"></i> ${config.key}
                            </h5>
                            <p class="config-key text-muted mb-2">v${config.version}</p>
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

function editConfig(index) {
    const config = configsData[index];
    if (!config) return;
    
    document.getElementById('configModalTitle').textContent = `설정 편집: ${config.key}`;
    document.getElementById('config-key').value = config.key;
    document.getElementById('config-value').value = JSON.stringify(config.value, null, 2);
    document.getElementById('config-version').value = config.version;
    document.getElementById('delete-btn').style.display = 'block';
    
    configModal.show();
}

async function saveConfig() {
    const key = document.getElementById('config-key').value;
    const valueStr = document.getElementById('config-value').value;
    const version = parseInt(document.getElementById('config-version').value);
    
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
