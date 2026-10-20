// =============================================================================
// AI Data Insight Builder - Frontend Application Logic (app.js)
// =============================================================================

// 애플리케이션 상태 변수
let selectedFile = null;
let currentDiagnostics = null;
let currentChart = null;
let activeSuggestions = [];

// DOM 요소 참조
const serverStatusBadge = document.getElementById('serverStatusBadge');
const serverStatusText = document.getElementById('serverStatusText');
const alertBanner = document.getElementById('alertBanner');
const alertMessage = document.getElementById('alertMessage');
const alertCloseBtn = document.getElementById('alertCloseBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingText = document.getElementById('loadingText');

const dropZone = document.getElementById('dropZone');
const csvFileInput = document.getElementById('csvFileInput');
const selectedFileInfo = document.getElementById('selectedFileInfo');
const selectedFileName = document.getElementById('selectedFileName');
const selectedFileSize = document.getElementById('selectedFileSize');
const inspectBtn = document.getElementById('inspectBtn');

const diagnosticsSection = document.getElementById('diagnosticsSection');
const statEncoding = document.getElementById('statEncoding');
const statSkiprows = document.getElementById('statSkiprows');
const statDimensions = document.getElementById('statDimensions');
const statRecYear = document.getElementById('statRecYear');
const statAggregates = document.getElementById('statAggregates');
const statDuplicates = document.getElementById('statDuplicates');
const warningsContainer = document.getElementById('warningsContainer');
const warningsList = document.getElementById('warningsList');
const previewThead = document.getElementById('previewThead');
const previewTbody = document.getElementById('previewTbody');
const suggestBtn = document.getElementById('suggestBtn');

const suggestionsSection = document.getElementById('suggestionsSection');
const suggestionsList = document.getElementById('suggestionsList');
const manualToolSelect = document.getElementById('manualToolSelect');
const manualRefPeriod = document.getElementById('manualRefPeriod');
const manualRunBtn = document.getElementById('manualRunBtn');

const resultSection = document.getElementById('resultSection');
const metaToolName = document.getElementById('metaToolName');
const metaRefPeriod = document.getElementById('metaRefPeriod');
const metaRowsUsed = document.getElementById('metaRowsUsed');
const metaRowsExcluded = document.getElementById('metaRowsExcluded');
const metaExclusionReason = document.getElementById('metaExclusionReason');
const resultSummaryBox = document.getElementById('resultSummaryBox');
const chartContainer = document.getElementById('chartContainer');
const resultChart = document.getElementById('resultChart');
const resultThead = document.getElementById('resultThead');
const resultTbody = document.getElementById('resultTbody');
const explainBtn = document.getElementById('explainBtn');

const reportSection = document.getElementById('reportSection');
const reportModeBadge = document.getElementById('reportModeBadge');
const reportContent = document.getElementById('reportContent');

const qaSection = document.getElementById('qaSection');
const qaInput = document.getElementById('qaInput');
const qaSubmitBtn = document.getElementById('qaSubmitBtn');
const qaChatContainer = document.getElementById('qaChatContainer');
const qaMessagesList = document.getElementById('qaMessagesList');
const qaChipBtns = document.querySelectorAll('.qa-chip-btn');

// =============================================================================
// 유틸리티 함수: 알림, 로딩, 서식 변환
// =============================================================================

function showLoading(msg = '처리 중입니다...') {
    loadingText.textContent = msg;
    loadingOverlay.classList.remove('hidden');
}

function hideLoading() {
    loadingOverlay.classList.add('hidden');
}

function showAlert(message) {
    alertMessage.textContent = message;
    alertBanner.classList.remove('hidden');
    console.error(`[ERROR] ${message}`);
}

function hideAlert() {
    alertBanner.classList.add('hidden');
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    if (typeof text !== 'string') return text === null || text === undefined ? '' : String(text);
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function formatInline(str) {
    let s = escapeHtml(str);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    return s;
}

function parseMarkdownToHtml(md) {
    if (!md) return '';
    const lines = md.split('\n');
    const output = [];
    let inList = false;
    let listType = 'ul';
    let inTable = false;

    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();

        if (inList && !line.startsWith('- ') && !line.startsWith('* ') && !/^\d+\.\s/.test(line)) {
            output.push(`</${listType}>`);
            inList = false;
        }

        if (inTable && !line.startsWith('|')) {
            output.push('</tbody></table></div>');
            inTable = false;
        }

        if (line === '') continue;

        if (line.startsWith('### ')) {
            output.push(`<h3>${escapeHtml(line.slice(4))}</h3>`);
            continue;
        }
        if (line.startsWith('## ')) {
            output.push(`<h2>${escapeHtml(line.slice(3))}</h2>`);
            continue;
        }
        if (line.startsWith('# ')) {
            output.push(`<h1>${escapeHtml(line.slice(2))}</h1>`);
            continue;
        }

        if (line.startsWith('> ')) {
            output.push(`<blockquote>${formatInline(line.slice(2))}</blockquote>`);
            continue;
        }

        if (line.startsWith('|') && line.endsWith('|')) {
            const cells = line.split('|').slice(1, -1).map(c => c.trim());
            if (cells.every(c => /^[-:]+$/.test(c))) {
                continue;
            }
            if (!inTable) {
                inTable = true;
                output.push('<div class="table-responsive"><table class="data-table"><thead><tr>');
                cells.forEach(c => output.push(`<th>${formatInline(c)}</th>`));
                output.push('</tr></thead><tbody>');
            } else {
                output.push('<tr>');
                cells.forEach(c => output.push(`<td>${formatInline(c)}</td>`));
                output.push('</tr>');
            }
            continue;
        }

        if (line.startsWith('- ') || line.startsWith('* ')) {
            if (!inList) {
                inList = true;
                listType = 'ul';
                output.push('<ul>');
            }
            output.push(`<li>${formatInline(line.slice(2))}</li>`);
            continue;
        }

        if (/^\d+\.\s/.test(line)) {
            const content = line.replace(/^\d+\.\s+/, '');
            if (!inList) {
                inList = true;
                listType = 'ol';
                output.push('<ol>');
            }
            output.push(`<li>${formatInline(content)}</li>`);
            continue;
        }

        output.push(`<p>${formatInline(line)}</p>`);
    }

    if (inList) output.push(`</${listType}>`);
    if (inTable) output.push('</tbody></table></div>');

    return output.join('\n');
}

// =============================================================================
// 1. 서버 헬스체크 (/health)
// =============================================================================

async function checkHealth() {
    console.log('[PAGE] 서버 헬스체크 시작...');
    try {
        const res = await fetch('/health');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        
        if (data.status === 'ok') {
            serverStatusBadge.className = 'status-badge online';
            const keyInfo = data.api_key_configured ? 'API 키 활성' : 'API 키 미설정';
            serverStatusText.textContent = `정상 연결 (${data.model} / ${keyInfo})`;
            console.log(`[PAGE] 서버 헬스체크 완료: status=ok, model=${data.model}, api_key_configured=${data.api_key_configured}`);
        } else {
            throw new Error('상태값 불일치');
        }
    } catch (err) {
        serverStatusBadge.className = 'status-badge offline';
        serverStatusText.textContent = '서버 연결 끊김';
        console.error('[ERROR] 서버 헬스체크 실패:', err.message);
    }
}

// =============================================================================
// 2. 파일 선택 및 드래그 앤 드롭
// =============================================================================

function handleFileSelect(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.csv')) {
        showAlert('CSV(.csv) 파일만 업로드할 수 있습니다.');
        return;
    }

    selectedFile = file;
    selectedFileName.textContent = file.name;
    selectedFileSize.textContent = `(${formatBytes(file.size)})`;
    selectedFileInfo.classList.remove('hidden');
    inspectBtn.disabled = false;
    hideAlert();
    console.log(`[UPLOAD] 파일 선택됨: name=${file.name}, size=${file.size} bytes`);
}

csvFileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        handleFileSelect(e.dataTransfer.files[0]);
    }
});

alertCloseBtn.addEventListener('click', hideAlert);

// =============================================================================
// 3. Step 1 -> 2: 데이터 진단 (/inspect)
// =============================================================================

inspectBtn.addEventListener('click', async () => {
    if (!selectedFile) {
        showAlert('진단할 CSV 파일을 먼저 선택해 주세요.');
        return;
    }

    showLoading('CSV 인코딩 자동 분석 및 데이터 품질 종합 진단 중...');
    console.log(`[INSPECT] 진단 시작: file=${selectedFile.name}`);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
        const res = await fetch('/inspect', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (!res.ok || data.status !== 'success') {
            throw new Error(data.message || '데이터 진단에 실패했습니다.');
        }

        currentDiagnostics = data.diagnostics;
        console.log('[INSPECT] 진단 성공 완료:', currentDiagnostics);
        renderDiagnostics(currentDiagnostics);
        hideAlert();
    } catch (err) {
        console.error('[ERROR] 진단 실패:', err.message);
        showAlert(err.message || '데이터 진단 중 오류가 발생했습니다.');
    } finally {
        hideLoading();
    }
});

function renderDiagnostics(diag) {
    statEncoding.textContent = diag.file_info.encoding || '-';
    statSkiprows.textContent = `${diag.file_info.skiprows || 0}줄`;
    statDimensions.textContent = `${diag.dimensions.row_count}행 × ${diag.dimensions.col_count}열`;
    statRecYear.textContent = diag.recommended_reference_year || '-';
    statAggregates.textContent = `${diag.aggregate_candidates.length}개`;
    statDuplicates.textContent = `${diag.duplicate_rows}건`;

    if (diag.recommended_reference_year) {
        manualRefPeriod.value = diag.recommended_reference_year;
    }

    if (diag.warnings && diag.warnings.length > 0) {
        warningsList.innerHTML = diag.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('');
        warningsContainer.classList.remove('hidden');
    } else {
        warningsContainer.classList.add('hidden');
    }

    previewThead.innerHTML = '';
    previewTbody.innerHTML = '';

    if (diag.preview && diag.preview.length > 0) {
        const columns = diag.dimensions.columns || Object.keys(diag.preview[0]);
        const trHead = document.createElement('tr');
        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            trHead.appendChild(th);
        });
        previewThead.appendChild(trHead);

        diag.preview.forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                const val = row[col];
                td.textContent = (val !== null && val !== undefined) ? val : '';
                tr.appendChild(td);
            });
            previewTbody.appendChild(tr);
        });
    }

    diagnosticsSection.classList.remove('hidden');
    qaSection.classList.remove('hidden');
    diagnosticsSection.scrollIntoView({ behavior: 'smooth' });
}

// =============================================================================
// 4. Step 2 -> 3: AI 분석 제안 (/suggest)
// =============================================================================

suggestBtn.addEventListener('click', async () => {
    showLoading('Gemini가 데이터 특성을 파악하여 최적의 분석 3~5개를 선별 중...');
    console.log('[SUGGEST] Gemini 분석 추천 요청 (/suggest)');

    try {
        const res = await fetch('/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();

        if (!res.ok || data.status !== 'success') {
            throw new Error(data.message || '분석 제안 생성에 실패했습니다.');
        }

        activeSuggestions = data.suggestions || [];
        console.log(`[SUGGEST] 제안 수신 완료: ${activeSuggestions.length}개 제안`, activeSuggestions);
        renderSuggestions(activeSuggestions);
        hideAlert();
    } catch (err) {
        console.error('[ERROR] 분석 추천 실패:', err.message);
        showAlert(err.message || 'Gemini 분석 제안을 가져오지 못했습니다.');
    } finally {
        hideLoading();
    }
});

function renderSuggestions(suggestions) {
    suggestionsList.innerHTML = '';

    if (!suggestions || suggestions.length === 0) {
        suggestionsList.innerHTML = '<p style="color:var(--slate-500);">추천된 분석이 없습니다. 아래 수동 실행 기능을 이용해 보세요.</p>';
    } else {
        suggestions.forEach((s, idx) => {
            const card = document.createElement('div');
            card.className = 'suggestion-card';
            card.innerHTML = `
                <div>
                    <div class="suggestion-header">
                        <span class="suggestion-tool">${escapeHtml(s.tool)}</span>
                        <span class="ref-badge">${escapeHtml(s.reference_period || s.params?.reference_period || '기준시점')}</span>
                    </div>
                    <div class="suggestion-why">${escapeHtml(s.why || '데이터 특성에 적합한 분석입니다.')}</div>
                    ${s.caution ? `<div class="suggestion-caution">⚠️ ${escapeHtml(s.caution)}</div>` : ''}
                </div>
                <button class="btn btn-primary run-suggest-btn" data-index="${idx}" style="margin-top:14px; width:100%;">
                    이 분석 실행하기
                </button>
            `;
            suggestionsList.appendChild(card);
        });

        document.querySelectorAll('.run-suggest-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.currentTarget.getAttribute('data-index'), 10);
                const item = activeSuggestions[idx];
                if (item) {
                    runTool(item.tool, item.params || {});
                }
            });
        });
    }

    suggestionsSection.classList.remove('hidden');
    suggestionsSection.scrollIntoView({ behavior: 'smooth' });
}

// 수동 도구 실행 핸들러
manualRunBtn.addEventListener('click', () => {
    const selectedTool = manualToolSelect.value;
    if (!selectedTool) {
        showAlert('실행할 분석 도구를 선택해 주세요.');
        return;
    }
    const refPeriod = manualRefPeriod.value.trim();
    const params = {};
    if (refPeriod) {
        params.reference_period = refPeriod;
    }
    runTool(selectedTool, params);
});

// =============================================================================
// 5. Step 3 -> 4: 도구 실행 (/run) & Chart.js 시각화
// =============================================================================

async function runTool(toolName, params) {
    showLoading(`Pandas가 '${toolName}' 도구를 엄밀하게 연산 중...`);
    console.log(`[RUN] 도구 실행 요청: tool=${toolName}, params=`, params);

    try {
        const res = await fetch('/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool: toolName, params: params })
        });
        const data = await res.json();

        if (!res.ok || data.status !== 'success') {
            throw new Error(data.message || '도구 실행 중 오류가 발생했습니다.');
        }

        const result = data.result;
        console.log(`[RUN] 도구 연산 완료: tool=${result.tool}, rows_used=${result.rows_used}, rows_excluded=${result.rows_excluded}`);
        renderRunResult(result);
        hideAlert();
    } catch (err) {
        console.error('[ERROR] 도구 실행 실패:', err.message);
        showAlert(err.message || '도구 실행에 실패했습니다.');
    } finally {
        hideLoading();
    }
}

function renderRunResult(result) {
    metaToolName.textContent = result.tool;
    metaRefPeriod.textContent = result.reference_period || '-';
    metaRowsUsed.textContent = `${result.rows_used}개 행`;
    metaRowsExcluded.textContent = `${result.rows_excluded}개 행`;
    metaExclusionReason.textContent = result.exclusion_reason || '없음';

    resultSummaryBox.innerHTML = `
        <div>${escapeHtml(result.summary || '')}</div>
        ${result.caution ? `<div style="font-size:0.85rem; color:#b45309; margin-top:8px; font-weight:normal;">💡 ${escapeHtml(result.caution)}</div>` : ''}
    `;

    const chartSpec = result.chart_data || result.chart_spec;
    if (chartSpec) {
        chartContainer.classList.remove('hidden');
        renderChart(chartSpec);
    } else {
        if (currentChart) {
            currentChart.destroy();
            currentChart = null;
        }
        chartContainer.classList.add('hidden');
    }

    renderResultTable(result);

    resultSection.classList.remove('hidden');
    resultSection.scrollIntoView({ behavior: 'smooth' });
}

function renderChart(spec) {
    if (currentChart) {
        currentChart.destroy();
        currentChart = null;
    }

    const ctx = resultChart.getContext('2d');
    const chartType = spec.type || spec.chart_type || 'bar';

    const options = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: spec.datasets && spec.datasets.length > 1,
                position: 'top'
            },
            tooltip: {}
        }
    };

    if (spec.indexAxis) {
        options.indexAxis = spec.indexAxis;
    }

    if (chartType === 'scatter') {
        options.plugins.tooltip.callbacks = {
            label: function(context) {
                const pt = context.raw;
                return `${pt.label || ''} (X: ${pt.x}, Y: ${pt.y})`;
            }
        };
        options.scales = {
            x: { title: { display: true, text: 'X 변수' } },
            y: { title: { display: true, text: 'Y 변수' } }
        };
    }

    const chartConfig = {
        type: chartType,
        data: {
            labels: spec.labels || [],
            datasets: spec.datasets || []
        },
        options: options
    };

    try {
        currentChart = new Chart(ctx, chartConfig);
        console.log(`[CHART] 차트 렌더링 완료: type=${chartType}, datasets=${spec.datasets?.length || 0}`);
    } catch (err) {
        console.error('[ERROR] Chart.js 렌더링 실패:', err);
    }
}

function renderResultTable(result) {
    resultThead.innerHTML = '';
    resultTbody.innerHTML = '';

    const data = result.data;
    if (!data) return;

    let rows = [];
    let headers = [];

    if (data.top_n && data.bottom_n) {
        const top = data.top_n.map(r => ({ '구분': '상위', ...r }));
        const bottom = data.bottom_n.map(r => ({ '구분': '하위', ...r }));
        rows = [...top, ...bottom];
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.groups)) {
        rows = data.groups;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.top_growth)) {
        rows = data.top_growth;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.distribution)) {
        rows = data.distribution;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.coverage_table)) {
        rows = data.coverage_table;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.sample_records)) {
        rows = data.sample_records;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.aggregate_candidates)) {
        rows = data.aggregate_candidates;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data.sample_points)) {
        rows = data.sample_points;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (Array.isArray(data)) {
        rows = data;
        if (rows.length > 0) headers = Object.keys(rows[0]);
    } else if (typeof data === 'object') {
        headers = ['항목', '값'];
        rows = Object.entries(data)
            .filter(([k, v]) => typeof v !== 'object')
            .map(([k, v]) => ({ '항목': k, '값': v }));
    }

    if (rows.length > 0 && headers.length > 0) {
        const headerRow = document.createElement('tr');
        headers.forEach(h => {
            const th = document.createElement('th');
            th.textContent = h;
            headerRow.appendChild(th);
        });
        resultThead.appendChild(headerRow);

        rows.forEach(r => {
            const tr = document.createElement('tr');
            headers.forEach(h => {
                const td = document.createElement('td');
                const val = r[h];
                td.textContent = (val !== null && val !== undefined) ? val : '-';
                tr.appendChild(td);
            });
            resultTbody.appendChild(tr);
        });
    }
}

// =============================================================================
// 6. Step 4 -> 5: AI 보고서 작성 (/explain)
// =============================================================================

explainBtn.addEventListener('click', async () => {
    const selectedMode = document.querySelector('input[name="explainMode"]:checked')?.value || 'B';
    const modeDesc = selectedMode === 'B' ? '정식 검증 모드 B' : '추측 비교 모드 A';
    
    showLoading(`Gemini가 ${modeDesc}로 심층 데이터 분석 보고서를 작성 중...`);
    console.log(`[EXPLAIN] AI 보고서 작성 요청 (/explain): mode=${selectedMode}`);

    try {
        const res = await fetch('/explain', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: selectedMode })
        });
        const data = await res.json();

        if (!res.ok || data.status !== 'success') {
            throw new Error(data.message || 'AI 보고서 작성에 실패했습니다.');
        }

        console.log(`[EXPLAIN] AI 보고서 수신 완료: mode=${data.mode}, tool=${data.tool_analyzed}`);
        renderReport(data);
        hideAlert();
    } catch (err) {
        console.error('[ERROR] 보고서 생성 실패:', err.message);
        showAlert(err.message || 'AI 보고서 생성 중 오류가 발생했습니다.');
    } finally {
        hideLoading();
    }
});

function renderReport(data) {
    const isModeB = data.mode === 'B';
    reportModeBadge.textContent = isModeB ? '모드 B (정식 검증 보고서)' : '모드 A (비교용 추측 보고서)';
    reportModeBadge.className = `badge ${isModeB ? 'badge-primary' : 'badge-warning'}`;

    reportContent.innerHTML = parseMarkdownToHtml(data.explanation || '');

    reportSection.classList.remove('hidden');
    qaSection.classList.remove('hidden');
    reportSection.scrollIntoView({ behavior: 'smooth' });
}

// =============================================================================
// 7. 데이터 심층 질의응답 (Q&A /ask)
// =============================================================================

async function handleAskQuestion(question) {
    const q = (question || qaInput.value).trim();
    if (!q) {
        showAlert('질문 내용을 입력해 주세요.');
        return;
    }

    showLoading('Gemini가 데이터 근거를 바탕으로 답변을 작성 중입니다...');
    console.log(`[QA] 질문 전송: "${q}"`);

    try {
        const res = await fetch('/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: q })
        });
        const data = await res.json();

        if (!res.ok || data.status !== 'success') {
            throw new Error(data.message || '답변 생성에 실패했습니다.');
        }

        console.log('[QA] 답변 수신 완료:', data);
        renderQaMessage(data.question, data.answer);
        qaInput.value = '';
        hideAlert();
    } catch (err) {
        console.error('[ERROR] Q&A 요청 실패:', err.message);
        showAlert(err.message || '답변 생성 중 오류가 발생했습니다.');
    } finally {
        hideLoading();
    }
}

function renderQaMessage(question, answer) {
    const item = document.createElement('div');
    item.className = 'qa-message-item';
    item.innerHTML = `
        <div class="qa-question-bubble">
            <span>❓ 질문:</span> ${escapeHtml(question)}
        </div>
        <div class="qa-answer-bubble">
            ${parseMarkdownToHtml(answer)}
        </div>
    `;

    qaMessagesList.appendChild(item);
    qaChatContainer.classList.remove('hidden');
    item.scrollIntoView({ behavior: 'smooth' });
}

qaSubmitBtn.addEventListener('click', () => {
    handleAskQuestion();
});

qaInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleAskQuestion();
    }
});

qaChipBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const q = btn.getAttribute('data-question');
        if (q) {
            qaInput.value = q;
            handleAskQuestion(q);
        }
    });
});

// =============================================================================
// 초기화: 페이지 로드 시 실행
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
});
