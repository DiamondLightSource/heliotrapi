const REFRESH_INTERVAL_MS = 5000; // Configurable refresh interval

class AnalysisAPI {
    constructor(baseURL = '') {
        this.baseURL = baseURL || window.location.origin;
    }

    // New: fetch all jobs if allowed by backend
    async getAllResults() {
        const response = await fetch(`${this.baseURL}/results/all`);
        if (!response.ok) throw new Error('Not allowed or failed to fetch all results');
        return response.json();
    }

    async getAnalyses() {
        const response = await fetch(`${this.baseURL}/get_analyses`);
        if (!response.ok) throw new Error('Failed to fetch analyses');
        return response.json();
    }

    async submitAnalysis(analysisName, inputs) {
        const response = await fetch(`${this.baseURL}/analyse`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                analysis_name: analysisName,
                inputs: inputs
            })
        });

        if (!response.ok) throw new Error('Failed to submit analysis');
        return response.json();
    }

    async getResult(requestId) {
        const response = await fetch(`${this.baseURL}/results/id/${requestId}`);

        if (!response.ok) throw new Error('Result not found');
        return response.json();
    }

    async getLatestResult() {
        const response = await fetch(`${this.baseURL}/results/latest`);

        if (!response.ok) throw new Error('No results available');
        return response.json();
    }

    async getHealth() {
        const response = await fetch(`${this.baseURL}/healthz`);

        if (!response.ok) throw new Error('API not available');
        return response.json();
    }
}

class AnalysisUI {
    constructor() {
        this.api = new AnalysisAPI();
        this.analyses = [];
        this.filteredAnalyses = [];
        this.selectedAnalysis = null;
        this.requestHistory = [];
        this.pollIntervals = new Map();

        this.init();
    }

    async init() {
        // Check API health
        try {
            await this.api.getHealth();
        } catch (error) {
            this.showError('API is not available. Make sure the server is running.');
            return;
        }

        // Load analyses
        await this.loadAnalyses();
        this.setupTooltip();

        // Try to load all jobs from backend if allowed
        let loadedFromBackend = false;

        try {
            const allResults = await this.api.getAllResults();

            console.log('Loaded jobs from backend:', allResults);

            if (Array.isArray(allResults) && allResults.length > 0) {
                // Convert backend results to requestHistory format
                this.requestHistory = allResults.map(r => ({
                    requestId: r.request_id || r.id || '',
                    analysisName: r.analysis_name || r.name || 'Unknown',
                    inputs: r.inputs || {},
                    status: r.status || 'unknown',
                    result: typeof r.result !== 'undefined' ? r.result : null,
                    createdAt: r.created_at || r.createdAt || '',
                    finishedAt: r.finished_at || r.finishedAt || ''
                }));

                this.renderResults();
                loadedFromBackend = true;
            }
        } catch (e) {
            console.error('Error loading jobs from backend:', e);

            // Fallback to local storage if not allowed
        }

        if (!loadedFromBackend) {
            this.loadHistoryFromStorage();
        }

        this.setupEventListeners();

        // Immediately refresh on page load so history/results appear without waiting
        await this.pollForUpdates();
    }

    async loadAnalyses() {
        try {
            this.analyses = await this.api.getAnalyses();

            // Sort analyses alphabetically by name
            this.analyses.sort((a, b) =>
                (a.name || '').localeCompare(b.name || '')
            );

            // Seed filtered list and render
            this.filteredAnalyses = this.analyses.slice();
            this.renderAnalysesList();

        } catch (error) {

            this.showError(
                'Failed to load analyses: ' + error.message
            );
        }
    }

    setupTooltip() {
        const tooltip = document.getElementById('tooltip');

        document.addEventListener('mouseover', (e) => {
            const icon = e.target.closest('.info-icon');
            if (!icon) return;

            const text = decodeURIComponent(icon.dataset.doc || '');

            tooltip.textContent = text || 'No description available';
            tooltip.style.display = 'block';
        });

        document.addEventListener('mousemove', (e) => {
            const icon = e.target.closest('.info-icon');

            if (!icon) {
                tooltip.style.display = 'none';
                return;
            }

            tooltip.style.left = e.pageX + 12 + 'px';
            tooltip.style.top = e.pageY + 12 + 'px';
        });

        document.addEventListener('mouseout', (e) => {
            if (e.target.closest('.info-icon')) {
                tooltip.style.display = 'none';
            }
        });
    }

    // Helper: resolve annotation from a parameter object, with fallbacks
    getAnnotation(param) {
        return param.annotation || param.type || param.type_hint || param.kind || 'Any';
    }

    renderAnalysesList() {
        const list = document.getElementById('analyses-list');

        list.innerHTML = '';

        if (this.filteredAnalyses.length === 0) {
            list.innerHTML = '<div class="no-results">No analyses available</div>';
            return;
        }

        this.filteredAnalyses.forEach((analysis) => {
            const item = document.createElement('div');

            item.className = 'analysis-item';

            if (this.selectedAnalysis?.name === analysis.name) {
                item.classList.add('selected');
            }

            const paramsText = analysis.parameters
                .map(p => `${p.name}: ${this.getAnnotation(p)}`)
                .join(', ');

            item.innerHTML = `
                <div class="analysis-item-name">
                    ${analysis.name}
                    <span class="info-icon"
                        data-doc="${encodeURIComponent(analysis.docstring || '')}">
                        i
                    </span>
                </div>
                <div class="analysis-item-params">
                    ${paramsText || 'No parameters'}
                </div>
            `;

            item.addEventListener('click', () => this.selectAnalysis(analysis));

            list.appendChild(item);
        });
    }

    selectAnalysis(analysis) {
        this.selectedAnalysis = analysis;

        this.renderAnalysesList();
        this.renderInputForm();
    }

    renderInputForm() {
        const form = document.getElementById('dynamic-inputs');

        form.innerHTML = '';

        if (!this.selectedAnalysis) {
            form.innerHTML =
                '<div class="info-message">Select an analysis to view its parameters</div>';
            return;
        }

        const params = this.selectedAnalysis.parameters;

        if (params.length === 0) {
            form.innerHTML =
                '<div class="info-message">This analysis has no parameters</div>';
            return;
        }

        params.forEach(param => {
            const group = document.createElement('div');

            group.className = 'form-group';

            const label = document.createElement('label');
            label.textContent = param.name;

            // FIX: use getAnnotation() so type hints always resolve
            const annotation = this.getAnnotation(param);
            const inputType = this.getUIInputType(annotation);

            let input;

            if (inputType === 'textarea') {
                input = document.createElement('textarea');

                input.placeholder =
                    `Enter values (comma-separated or JSON array):\n` +
                    `e.g., [1.0, 2.5, 3.7, 4.2]`;

                input.className = 'array-input';
                input.rows = 4;

            } else if (inputType === 'checkbox') {

                input = document.createElement('input');

                input.type = 'checkbox';
                input.className = 'checkbox-input';

            } else if (inputType === 'json') {

                input = document.createElement('textarea');

                input.placeholder =
                    `Enter JSON value:\n` +
                    `e.g., {"key": "value"}`;

                input.className = 'json-input';
                input.rows = 3;

            } else {

                input = document.createElement('input');

                input.type = inputType;

                input.placeholder = `Enter ${param.name}`;
            }

            // Pre-populate with default value if present
            if (param.default !== null && param.default !== undefined) {
                if (inputType === 'checkbox') {
                    input.checked = param.default === 'True';
                } else if (param.default !== 'None') {
                    // Backend sends repr() strings, so strip surrounding quotes
                    // e.g. "'kev'" → "kev", "0.5" → "0.5"
                    const raw = String(param.default);
                    const unquoted = /^(['"]).*\1$/.test(raw)
                        ? raw.slice(1, -1)
                        : raw;
                    input.value = unquoted;
                }
                // 'None' default: leave field empty — null is sent if user doesn't fill it in
            }

            input.id = `param-${param.name}`;
            // FIX: store resolved annotation, not raw (possibly undefined) field
            input.dataset.type = annotation;

            const typeHint = document.createElement('div');

            typeHint.className = 'parameter-type';
            // FIX: display the resolved annotation
            typeHint.textContent = `Type: ${annotation}`;

            group.appendChild(label);
            group.appendChild(input);
            group.appendChild(typeHint);

            form.appendChild(group);
        });
    }

    getUIInputType(annotation) {
        const ann = annotation.toLowerCase();

        // Check for list/array types
        if (
            ann.includes('list') ||
            ann.includes('sequence') ||
            ann.includes('ndarray') ||
            ann.includes('array')
        ) {
            return 'textarea';
        }

        // Primitive types
        if (ann.includes('int')) return 'number';
        if (ann.includes('float')) return 'number';
        if (ann.includes('bool')) return 'checkbox';
        if (ann.includes('str')) return 'text';

        // Complex types
        if (
            ann.includes('dict') ||
            ann.includes('any') ||
            ann.includes('object')
        ) {
            return 'json';
        }

        return 'text';
    }

    setupEventListeners() {
        document
            .getElementById('submit-btn')
            .addEventListener('click', () => this.submitAnalysis());

        document
            .getElementById('clear-btn')
            .addEventListener('click', () => this.clearHistory());

        const search = document.getElementById('analysis-search');
        if (search) {
            search.addEventListener('input', (e) => this.filterAnalyses(e.target.value));
        }

        // Refresh every N seconds
        setInterval(() => this.pollForUpdates(), REFRESH_INTERVAL_MS);
    }

    filterAnalyses(query) {
        const q = (query || '').trim().toLowerCase();

        if (!q) {
            this.filteredAnalyses = this.analyses.slice();
            this.renderAnalysesList();
            return;
        }

        this.filteredAnalyses = this.analyses.filter(a => {
            const name = (a.name || '').toLowerCase();
            const doc = (a.docstring || '').toLowerCase();
            const params = (a.parameters || []).map(p => (p.name || '').toLowerCase()).join(' ');

            return name.includes(q) || doc.includes(q) || params.includes(q);
        });

        this.renderAnalysesList();
    }

    async submitAnalysis() {
        if (!this.selectedAnalysis) {
            this.showError('Please select an analysis first');
            return;
        }

        const inputs = this.gatherInputs();

        if (!inputs) return;

        const submitBtn = document.getElementById('submit-btn');

        const originalText = submitBtn.textContent;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        try {
            const result = await this.api.submitAnalysis(
                this.selectedAnalysis.name,
                inputs
            );

            this.showSuccess(
                `Analysis submitted! Request ID: ${result.request_id}`
            );

            const requestEntry = {
                requestId: result.request_id,
                analysisName: this.selectedAnalysis.name,
                inputs: inputs,
                status: 'running',
                result: null,
                createdAt: new Date().toISOString()
            };

            this.requestHistory.unshift(requestEntry);

            this.saveHistoryToStorage();
            this.renderResults();

            this.startPollingForResult(result.request_id);

        } catch (error) {

            this.showError(
                'Failed to submit analysis: ' + error.message
            );

        } finally {

            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    }

    gatherInputs() {
        const inputs = {};
        const params = this.selectedAnalysis.parameters;

        for (const param of params) {
            const input = document.getElementById(`param-${param.name}`);

            if (!input) continue;

            let value;

            // FIX: use getAnnotation() so type-coercion logic always has a valid string
            const ann = this.getAnnotation(param).toLowerCase();

            // A parameter is optional if its annotation includes 'none' (e.g. "ndarray | None",
            // "Optional[float]") or if its default is explicitly 'None'
            const isOptional = ann.includes('none') || param.default === 'None';

            // Checkbox
            if (input.type === 'checkbox') {
                value = input.checked;
            } else {
                value = input.value.trim();
            }

            // If the user explicitly typed "None", or the field is empty and optional → send null
            if (value === 'None' || value === 'none' || (!value && value !== false && value !== 0)) {
                if (isOptional || value === 'None' || value === 'none') {
                    inputs[param.name] = null;
                    continue;
                }
                this.showError(`Please fill in ${param.name}`);
                return null;
            }

            // Convert type
            if (
                ann.includes('list') ||
                ann.includes('sequence') ||
                ann.includes('ndarray') ||
                ann.includes('array')
            ) {

                value = this.parseArrayInput(value, ann);

                if (value === null) {
                    this.showError(
                        `Invalid array format for ${param.name}.`
                    );
                    return null;
                }

            } else if (
                ann.includes('int') &&
                !ann.includes('float')
            ) {

                value = parseInt(value, 10);

                if (isNaN(value)) {
                    this.showError(`${param.name} must be a valid integer`);
                    return null;
                }
            } else if (ann.includes('float')) {

                value = parseFloat(value);

                if (isNaN(value)) {
                    this.showError(`${param.name} must be a valid number`);
                    return null;
                }

            } else if (
                ann.includes('dict') ||
                ann.includes('object') ||
                (
                    ann.includes('any') &&
                    input.classList.contains('json-input')
                )
            ) {

                try {
                    value = JSON.parse(value);
                } catch (e) {
                    this.showError(
                        `${param.name} must be valid JSON: ${e.message}`
                    );
                    return null;
                }
            }

            inputs[param.name] = value;
        }

        return inputs;
    }

    parseArrayInput(value, annotation) {
        // Try JSON first
        try {
            const parsed = JSON.parse(value);

            if (Array.isArray(parsed)) {
                return this.convertArrayElements(parsed, annotation);
            }

        } catch (e) {
            // Ignore
        }

        // Fallback to comma-separated
        const values = value
            .split(',')
            .map(v => v.trim())
            .filter(v => v.length > 0);

        if (values.length === 0) return null;

        return this.convertArrayElements(values, annotation);
    }

    convertArrayElements(arr, annotation) {
        const ann = annotation.toLowerCase();

        // Integer arrays
        if (
            ann.includes('int')
        ) {
            return arr.map(v => {
                const n = parseInt(v, 10);

                if (isNaN(n)) {
                    throw new Error(`Invalid integer value: ${v}`);
                }

                return n;
            });
        }

        // Float-like arrays
        if (
            ann.includes('float') ||
            ann.includes('ndarray') ||
            ann.includes('numpy') ||
            ann.includes('array')
        ) {
            return arr.map(v => {
                const n = parseFloat(v);

                if (isNaN(n)) {
                    throw new Error(`Invalid float value: ${v}`);
                }

                return n;
            });
        }

        // Default: strings
        return arr.map(v => String(v));
    }

    startPollingForResult(requestId) {
        if (this.pollIntervals.has(requestId)) return;

        const interval = setInterval(async () => {
            try {
                const result = await this.api.getResult(requestId);

                const entry = this.requestHistory.find(
                    r => r.requestId === requestId
                );

                if (entry) {
                    entry.status = result.status;
                    entry.result = result.result;
                    entry.finishedAt = result.finished_at;

                    this.saveHistoryToStorage();
                    this.renderResults();

                    if (result.status !== 'running') {
                        clearInterval(interval);
                        this.pollIntervals.delete(requestId);
                    }
                }

            } catch (error) {
                // Still waiting
            }

        }, REFRESH_INTERVAL_MS);

        this.pollIntervals.set(requestId, interval);
    }

    async pollForUpdates() {
        try {
            // Reload all results from backend
            const allResults = await this.api.getAllResults();

            if (Array.isArray(allResults)) {

                // Convert backend results to the same format
                const backendResults = allResults.map(r => ({
                    requestId: r.request_id || r.id || '',
                    analysisName: r.analysis_name || r.name || 'Unknown',
                    inputs: r.inputs || {},
                    status: r.status || 'unknown',
                    result: typeof r.result !== 'undefined' ? r.result : null,
                    createdAt: r.created_at || r.createdAt || '',
                    finishedAt: r.finished_at || r.finishedAt || ''
                }));

                // Completely replace local results
                this.requestHistory = backendResults.sort((a, b) => {
                    const aTime = new Date(a.createdAt || 0).getTime();
                    const bTime = new Date(b.createdAt || 0).getTime();

                    return bTime - aTime;
                });

                this.saveHistoryToStorage();
                this.renderResults();
            }

        } catch (error) {

            console.error('Auto-refresh failed:', error);

            // Fallback:
            // continue polling local running jobs
            this.requestHistory.forEach(entry => {
                if (entry.status === 'running') {
                    this.startPollingForResult(entry.requestId);
                }
            });
        }
    }

    renderResults() {
        const container = document.getElementById('results-container');

        if (
            !Array.isArray(this.requestHistory) ||
            this.requestHistory.length === 0
        ) {
            container.innerHTML =
                '<div class="no-results">No analysis results yet</div>';

            return;
        }

        container.innerHTML = this.requestHistory.map((entry, index) => {

            let statusHtml =
                `<span class="status-badge status-${entry.status}">` +
                `${entry.status}</span>`;

            if (entry.status === 'running') {
                statusHtml += '<span class="loading-spinner"></span>';

            } else if (
                entry.status === 'failed' ||
                entry.status === 'error'
            ) {
                statusHtml +=
                    ' <span class="error-message">Error</span>';
            }

            return `
                <div class="result-item">
                    <div class="result-header">
                        <div>
                            <strong>${entry.analysisName || 'Unknown'}</strong>
                            ${statusHtml}
                        </div>

                        <button
                            class="btn-danger"
                            onclick="ui.deleteResult(${index})"
                        >
                            Delete
                        </button>
                    </div>

                    <div class="result-id">
                        Request ID: ${entry.requestId || ''}
                    </div>

                    ${entry.inputs &&
                    Object.keys(entry.inputs).length > 0
                    ? `
                                <div class="result-content">
                                    <strong>Inputs:</strong>
                                    ${JSON.stringify(entry.inputs)}
                                </div>
                              `
                    : ''
                }

                    ${typeof entry.result !== 'undefined' &&
                    entry.result !== null
                    ? `
                                <div class="result-content">
                                    <strong>Result:</strong>
                                    ${this.formatResult(entry.result)}
                                </div>
                              `
                    : ''
                }

                    <div class="result-time">
                        ${entry.createdAt
                    ? `Submitted: ${new Date(
                        entry.createdAt
                    ).toLocaleString()}`
                    : ''
                }

                        ${entry.finishedAt
                    ? ` | Finished: ${new Date(
                        entry.finishedAt
                    ).toLocaleString()}`
                    : ''
                }
                    </div>
                </div>
            `;
        }).join('');
    }

    formatResult(result) {
        if (typeof result === 'object') {
            return JSON.stringify(result, null, 2);
        }

        return String(result);
    }

    deleteResult(index) {
        const requestId = this.requestHistory[index].requestId;

        if (this.pollIntervals.has(requestId)) {
            clearInterval(this.pollIntervals.get(requestId));
            this.pollIntervals.delete(requestId);
        }

        this.requestHistory.splice(index, 1);

        this.saveHistoryToStorage();
        this.renderResults();
    }

    clearHistory() {
        if (confirm('Are you sure you want to clear all results?')) {

            this.pollIntervals.forEach(interval => clearInterval(interval));

            this.pollIntervals.clear();

            this.requestHistory = [];

            this.saveHistoryToStorage();
            this.renderResults();

            this.showSuccess('History cleared');
        }
    }

    saveHistoryToStorage() {
        localStorage.setItem(
            'analysisHistory',
            JSON.stringify(this.requestHistory)
        );
    }

    loadHistoryFromStorage() {
        const stored = localStorage.getItem('analysisHistory');

        if (stored) {
            try {
                this.requestHistory = JSON.parse(stored).slice(0, 50);

                this.renderResults();

            } catch (error) {

                console.error('Failed to load history:', error);
            }
        }
    }

    showError(message) {
        this.showMessage(message, 'error-message');
    }

    showSuccess(message) {
        this.showMessage(message, 'success-message');
    }

    showMessage(message, className) {
        const container = document.getElementById('messages');

        const msg = document.createElement('div');

        msg.className = className;
        msg.textContent = message;

        container.appendChild(msg);

        setTimeout(() => msg.remove(), 5000);
    }
}

// Initialize UI when DOM is ready
let ui;

document.addEventListener('DOMContentLoaded', () => {
    ui = new AnalysisUI();
});
