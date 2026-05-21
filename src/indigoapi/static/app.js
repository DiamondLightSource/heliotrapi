class AnalysisAPI {
    constructor(baseURL = '') {
        this.baseURL = baseURL || window.location.origin;
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
        const response = await fetch(`${this.baseURL}/result/id/${requestId}`);
        if (!response.ok) throw new Error('Result not found');
        return response.json();
    }

    async getLatestResult() {
        const response = await fetch(`${this.baseURL}/result/latest`);
        if (!response.ok) throw new Error('No results available');
        return response.json();
    }

    async getHealth() {
        const response = await fetch(`${this.baseURL}/health`);
        if (!response.ok) throw new Error('API not available');
        return response.json();
    }
}

class AnalysisUI {
    constructor() {
        this.api = new AnalysisAPI();
        this.analyses = [];
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
        this.setupEventListeners();
        this.loadHistoryFromStorage();
    }

    async loadAnalyses() {
        try {
            this.analyses = await this.api.getAnalyses();
            this.renderAnalysesList();
        } catch (error) {
            this.showError('Failed to load analyses: ' + error.message);
        }
    }

    renderAnalysesList() {
        const list = document.getElementById('analyses-list');
        list.innerHTML = '';

        if (this.analyses.length === 0) {
            list.innerHTML = '<div class="no-results">No analyses available</div>';
            return;
        }

        this.analyses.forEach((analysis, index) => {
            const item = document.createElement('div');
            item.className = 'analysis-item';
            if (this.selectedAnalysis?.name === analysis.name) {
                item.classList.add('selected');
            }

            const paramsText = analysis.parameters
                .map(p => `${p.name}: ${p.annotation}`)
                .join(', ');

            item.innerHTML = `
        <div class="analysis-item-name">${analysis.name}</div>
        <div class="analysis-item-params">${paramsText || 'No parameters'}</div>
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
            form.innerHTML = '<div class="info-message">Select an analysis to view its parameters</div>';
            return;
        }

        const params = this.selectedAnalysis.parameters;
        if (params.length === 0) {
            form.innerHTML = '<div class="info-message">This analysis has no parameters</div>';
            return;
        }

        params.forEach(param => {
            const group = document.createElement('div');
            group.className = 'form-group';

            const label = document.createElement('label');
            label.textContent = param.name;

            const inputType = this.getUIInputType(param.annotation);
            let input;

            if (inputType === 'textarea') {
                // Multi-value input (array/list)
                input = document.createElement('textarea');
                input.placeholder = `Enter values (comma-separated or JSON array):\ne.g., [1.0, 2.5, 3.7, 4.2]`;
                input.className = 'array-input';
                input.rows = 4;
            } else if (inputType === 'checkbox') {
                input = document.createElement('input');
                input.type = 'checkbox';
                input.className = 'checkbox-input';
            } else if (inputType === 'json') {
                // JSON input for complex types
                input = document.createElement('textarea');
                input.placeholder = `Enter JSON value:\ne.g., {"key": "value"}`;
                input.className = 'json-input';
                input.rows = 3;
            } else {
                input = document.createElement('input');
                input.type = inputType;
                input.placeholder = param.default ? `Default: ${param.default}` : `Enter ${param.name}`;
            }

            input.id = `param-${param.name}`;
            input.dataset.type = param.annotation;

            const typeHint = document.createElement('div');
            typeHint.className = 'parameter-type';
            typeHint.textContent = `Type: ${param.annotation}`;

            group.appendChild(label);
            group.appendChild(input);
            group.appendChild(typeHint);
            form.appendChild(group);
        });
    }

    getUIInputType(annotation) {
        const ann = annotation.toLowerCase();

        // Check for list/array types
        if (ann.includes('list') || ann.includes('sequence') || ann.includes('ndarray') || ann.includes('array')) {
            return 'textarea';
        }

        // Check for primitive types
        if (ann.includes('int')) return 'number';
        if (ann.includes('float')) return 'number';
        if (ann.includes('bool')) return 'checkbox';
        if (ann.includes('str')) return 'text';

        // For complex types (Any, dict, object, etc.) use JSON
        if (ann.includes('dict') || ann.includes('any') || ann.includes('object')) {
            return 'json';
        }

        return 'text';
    }

    setupEventListeners() {
        document.getElementById('submit-btn').addEventListener('click', () => this.submitAnalysis());
        document.getElementById('clear-btn').addEventListener('click', () => this.clearHistory());

        // Poll for results every 2 seconds
        setInterval(() => this.pollForUpdates(), 2000);
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
            const result = await this.api.submitAnalysis(this.selectedAnalysis.name, inputs);
            this.showSuccess(`Analysis submitted! Request ID: ${result.request_id}`);

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
            this.showError('Failed to submit analysis: ' + error.message);
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
            const ann = param.annotation.toLowerCase();

            // Handle checkbox specially
            if (input.type === 'checkbox') {
                value = input.checked;
            } else {
                value = input.value;
            }

            if (!value && value !== false && value !== 0) {
                this.showError(`Please fill in ${param.name}`);
                return null;
            }

            // Convert to appropriate type
            if (ann.includes('list') || ann.includes('sequence') || ann.includes('ndarray') || ann.includes('array')) {
                // Parse array/list inputs
                value = this.parseArrayInput(value, ann);
                if (value === null) {
                    this.showError(`Invalid array format for ${param.name}. Use comma-separated values or JSON format.`);
                    return null;
                }
            } else if (ann.includes('int')) {
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
            } else if (ann.includes('dict') || ann.includes('object') || (ann.includes('any') && input.classList.contains('json-input'))) {
                // Parse JSON input
                try {
                    value = JSON.parse(value);
                } catch (e) {
                    this.showError(`${param.name} must be valid JSON: ${e.message}`);
                    return null;
                }
            }
            // String and bool are already in correct format

            inputs[param.name] = value;
        }

        return inputs;
    }

    parseArrayInput(value, annotation) {
        // Try to parse as JSON first
        try {
            const parsed = JSON.parse(value);
            if (Array.isArray(parsed)) {
                return this.convertArrayElements(parsed, annotation);
            }
        } catch (e) {
            // Not JSON, try comma-separated
        }

        // Parse as comma-separated values
        const values = value.split(',').map(v => v.trim()).filter(v => v.length > 0);
        if (values.length === 0) return null;

        return this.convertArrayElements(values, annotation);
    }

    convertArrayElements(arr, annotation) {
        const ann = annotation.toLowerCase();

        // Determine element type from annotation
        let elementType = 'string';
        if (ann.includes('int')) elementType = 'int';
        else if (ann.includes('float')) elementType = 'float';

        return arr.map(v => {
            if (elementType === 'int') return parseInt(v, 10);
            if (elementType === 'float') return parseFloat(v);
            return String(v);
        });
    }

    startPollingForResult(requestId) {
        if (this.pollIntervals.has(requestId)) return;

        const interval = setInterval(async () => {
            try {
                const result = await this.api.getResult(requestId);
                const entry = this.requestHistory.find(r => r.requestId === requestId);
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
                // Still waiting for result
            }
        }, 2000);

        this.pollIntervals.set(requestId, interval);
    }

    pollForUpdates() {
        this.requestHistory.forEach(entry => {
            if (entry.status === 'running') {
                this.startPollingForResult(entry.requestId);
            }
        });
    }

    renderResults() {
        const container = document.getElementById('results-container');

        if (this.requestHistory.length === 0) {
            container.innerHTML = '<div class="no-results">No analysis results yet</div>';
            return;
        }

        container.innerHTML = this.requestHistory.map((entry, index) => `
      <div class="result-item">
        <div class="result-header">
          <div>
            <strong>${entry.analysisName}</strong>
            <span class="status-badge status-${entry.status}">${entry.status}</span>
            ${entry.status === 'running' ? '<span class="loading-spinner"></span>' : ''}
          </div>
          <button class="btn-danger" onclick="ui.deleteResult(${index})">Delete</button>
        </div>
        <div class="result-id">Request ID: ${entry.requestId}</div>
        ${entry.inputs ? `<div class="result-content"><strong>Inputs:</strong> ${JSON.stringify(entry.inputs)}</div>` : ''}
        ${entry.result !== null ? `<div class="result-content"><strong>Result:</strong> ${this.formatResult(entry.result)}</div>` : ''}
        <div class="result-time">
          ${entry.createdAt ? `Submitted: ${new Date(entry.createdAt).toLocaleString()}` : ''}
          ${entry.finishedAt ? ` | Finished: ${new Date(entry.finishedAt).toLocaleString()}` : ''}
        </div>
      </div>
    `).join('');
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
        localStorage.setItem('analysisHistory', JSON.stringify(this.requestHistory));
    }

    loadHistoryFromStorage() {
        const stored = localStorage.getItem('analysisHistory');
        if (stored) {
            try {
                this.requestHistory = JSON.parse(stored).slice(0, 50); // Keep last 50
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
