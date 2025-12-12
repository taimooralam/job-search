/**
 * Job Detail Page Scripts
 *
 * This module provides functionality for the job detail page including:
 * - Toast notifications
 * - Inline field editing
 * - Pipeline processing and monitoring
 * - CV and Cover Letter management
 * - Contact management
 *
 * Updated 2025-12-06 - Extracted from job_detail.html template
 */

// Job ID is set by the template before this script loads
// Expected: window.JOB_DETAIL_CONFIG = { jobId: '...' }
const getJobId = () => window.JOB_DETAIL_CONFIG?.jobId || '';

// ============================================================================
// Sticky Header Component (Alpine.js)
// ============================================================================

/**
 * Alpine.js component for the compact sticky header behavior.
 * When user scrolls past a threshold, the full header fades out and
 * a compact bar appears with job title, company, and score.
 *
 * Usage in template:
 * <div class="job-detail-header-wrapper" x-data="stickyHeader()" x-init="init()">
 */
function stickyHeader() {
    return {
        scrolled: false,
        threshold: 150, // pixels before switching to compact

        init() {
            this.checkScroll();
            window.addEventListener('scroll', () => this.checkScroll(), { passive: true });
        },

        checkScroll() {
            const shouldBeScrolled = window.scrollY > this.threshold;
            if (shouldBeScrolled !== this.scrolled) {
                this.scrolled = shouldBeScrolled;
                this.$el.classList.toggle('scrolled', this.scrolled);
            }
        }
    };
}

// Expose stickyHeader globally for Alpine.js
window.stickyHeader = stickyHeader;

// Track highest layer reached (monotonic progress)
let highestLayerReached = 0;
const layerOrder = ['intake', 'pain_points', 'company_research', 'role_research', 'fit_scoring', 'people_mapping', 'cv_outreach_generation'];

// ============================================================================
// Toast Notifications
// ============================================================================

function showToast(message, type = 'success', duration = 4000) {
    const toast = document.createElement('div');

    // Map type to toast class
    const typeClass = type === 'error' ? 'toast-error' : type === 'info' ? 'toast-info' : 'toast-success';
    toast.className = `toast ${typeClass}`;

    // Icon based on type
    const icons = {
        success: `<svg class="w-5 h-5 text-green-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>`,
        error: `<svg class="w-5 h-5 text-red-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>`,
        info: `<svg class="w-5 h-5 text-blue-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>`
    };

    // Support multi-line messages by converting newlines to <br>
    const formattedMessage = message.replace(/\n/g, '<br>');

    toast.innerHTML = `
        ${icons[type] || icons.success}
        <span class="text-sm font-medium text-gray-900" style="white-space: pre-line;">${formattedMessage}</span>
        <button onclick="this.parentElement.remove()" class="ml-auto text-gray-400 hover:text-gray-600 transition-colors">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
        </button>
    `;

    document.body.appendChild(toast);

    // Auto-dismiss after specified duration
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(2rem)';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/**
 * Show detailed pipeline log panel with layer status
 * @param {string} action - Action name (e.g., 'full-extraction')
 * @param {Object} layerStatus - Per-layer status from backend
 * @param {Object} data - Full response data
 * @param {boolean} isPending - If true, show as "in progress" with spinning icons
 */
// Global state for simulated progress
let pipelineProgressInterval = null;
let currentProgressIndex = 0;

// Define layer info based on action (keys match backend layer_status)
const LAYER_CONFIGS = {
    'full-extraction': [
        { key: 'jd_processor', label: 'JD Processor', desc: 'Parse into sections', duration: 2000 },
        { key: 'jd_extractor', label: 'JD Extractor', desc: 'Extract role info', duration: 3000 },
        { key: 'layer_2', label: 'Pain Points', desc: 'Mine pain points', duration: 4000 },
        { key: 'layer_4', label: 'Fit Scoring', desc: 'Calculate fit score', duration: 2000 }
    ],
    'structure-jd': [
        { key: 'fetch_job', label: 'Fetch Job', desc: 'Load job from database', duration: 500 },
        { key: 'extract_text', label: 'Extract Text', desc: 'Extract JD text', duration: 1000 },
        { key: 'jd_processor', label: 'JD Processor', desc: 'Parse into sections', duration: 3000 },
        { key: 'persist', label: 'Save Results', desc: 'Persist to database', duration: 500 }
    ],
    'research-company': [
        { key: 'fetch_job', label: 'Fetch Job', desc: 'Load job from database', duration: 500 },
        { key: 'cache_check', label: 'Cache Check', desc: 'Check for cached research', duration: 1000 },
        { key: 'company_research', label: 'Company Research', desc: 'Research company signals', duration: 8000 },
        { key: 'role_research', label: 'Role Research', desc: 'Research role context', duration: 6000 },
        { key: 'persist', label: 'Save Results', desc: 'Persist to database', duration: 500 }
    ],
    'generate-cv': [
        { key: 'fetch_job', label: 'Fetch Job', desc: 'Load job from database', duration: 500 },
        { key: 'validate', label: 'Validate', desc: 'Validate job data', duration: 1000 },
        { key: 'build_state', label: 'Build State', desc: 'Prepare CV generation state', duration: 2000 },
        { key: 'cv_generator', label: 'Generate CV', desc: 'Generate tailored CV', duration: 15000 },
        { key: 'persist', label: 'Save Results', desc: 'Persist to database', duration: 500 }
    ]
};

/**
 * Start simulated progress animation for the pipeline log panel.
 * This gives visual feedback while the actual API call is running.
 */
function startSimulatedProgress(action) {
    const layers = LAYER_CONFIGS[action] || [];
    if (layers.length === 0) return;

    currentProgressIndex = 0;

    // Clear any existing interval
    if (pipelineProgressInterval) {
        clearInterval(pipelineProgressInterval);
    }

    // Update the panel to show first layer in progress
    updatePanelProgress(action, currentProgressIndex);

    // Schedule progress through layers based on estimated durations
    let totalDelay = 0;
    layers.forEach((layer, index) => {
        if (index === 0) return; // First layer already shown

        totalDelay += layers[index - 1].duration;

        setTimeout(() => {
            // Only update if the panel is still in pending state
            const panel = document.getElementById('pipeline-log-panel');
            const statusFooter = panel?.querySelector('.bg-gray-50');
            if (panel && statusFooter?.textContent.includes('Processing')) {
                currentProgressIndex = index;
                updatePanelProgress(action, index);
            }
        }, totalDelay);
    });
}

/**
 * Update the panel to show progress at a specific layer index.
 */
function updatePanelProgress(action, progressIndex) {
    const layers = LAYER_CONFIGS[action] || [];
    const panel = document.getElementById('pipeline-log-panel');
    if (!panel) return;

    const layerContainer = panel.querySelector('.space-y-1');
    if (!layerContainer) return;

    const spinnerSvg = '<svg class="w-4 h-4 animate-spin text-indigo-600" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';

    const layerStatusHtml = layers.map((layer, index) => {
        let statusIcon = '⏳';
        let message = layer.desc;

        if (index < progressIndex) {
            // Completed layers
            statusIcon = '✅';
            message = 'Complete';
        } else if (index === progressIndex) {
            // Current layer (in progress)
            statusIcon = spinnerSvg;
            message = 'Processing...';
        }
        // Future layers stay as pending (⏳)

        return `
            <div class="flex items-start gap-2 py-1" data-layer-key="${layer.key}">
                <span class="text-base flex items-center">${statusIcon}</span>
                <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-700">${layer.label}</div>
                    <div class="text-xs text-gray-500 truncate">${message}</div>
                </div>
            </div>
        `;
    }).join('');

    layerContainer.innerHTML = layerStatusHtml;
}

/**
 * Stop the simulated progress (called when real results arrive).
 */
function stopSimulatedProgress() {
    if (pipelineProgressInterval) {
        clearInterval(pipelineProgressInterval);
        pipelineProgressInterval = null;
    }
    currentProgressIndex = 0;
}

function showPipelineLogPanel(action, layerStatus, data, isPending = false) {
    const existingPanel = document.getElementById('pipeline-log-panel');
    const layers = LAYER_CONFIGS[action] || [];

    // Build layer status HTML
    const layerStatusHtml = layers.map((layer, index) => {
        const status = layerStatus?.[layer.key];
        const statusType = status?.status;
        let statusIcon = '⏳'; // pending/not started

        if (isPending) {
            // Show first layer as "in progress" with spinning animation, rest as pending
            if (index === 0) {
                // Use inline SVG spinner for better animation
                statusIcon = '<svg class="w-4 h-4 animate-spin text-indigo-600" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>';
            } else {
                statusIcon = '⏳';
            }
        } else {
            if (statusType === 'success') statusIcon = '✅';
            else if (statusType === 'failed') statusIcon = '❌';
            else if (statusType === 'warning') statusIcon = '⚠️';
            else if (statusType === 'skipped') statusIcon = '⏭️';
            else if (status) statusIcon = '❌'; // fallback for unknown status
        }
        const message = isPending && index === 0 ? 'Processing...' : (status?.message || layer.desc);

        return `
            <div class="flex items-start gap-2 py-1" data-layer-key="${layer.key}">
                <span class="text-base flex items-center">${statusIcon}</span>
                <div class="flex-1 min-w-0">
                    <div class="text-sm font-medium text-gray-700">${layer.label}</div>
                    <div class="text-xs text-gray-500 truncate">${message}</div>
                </div>
            </div>
        `;
    }).join('');

    // Build summary stats based on action type (skip if pending)
    let summaryHtml = '';
    if (data && !isPending) {
        const stats = [];

        // Full extraction stats
        if (data.section_count) stats.push(`📄 ${data.section_count} sections`);
        if (data.pain_points_count) stats.push(`🎯 ${data.pain_points_count} pain points`);
        if (data.fit_score !== undefined) stats.push(`📊 Fit: ${data.fit_score}%`);
        if (data.annotation_score !== undefined && data.annotation_score !== null) {
            stats.push(`👤 Match: ${data.annotation_score}%`);
        }

        // Research stats
        if (data.signals_count) stats.push(`📡 ${data.signals_count} signals`);
        if (data.company_type) stats.push(`🏢 ${data.company_type}`);
        if (data.business_impact_count) stats.push(`💼 ${data.business_impact_count} impacts`);
        if (data.from_cache) stats.push(`⚡ From cache`);

        // CV generation stats
        if (data.word_count) stats.push(`📝 ${data.word_count} words`);
        if (layerStatus?.cv_generator?.has_reasoning) stats.push(`💡 With reasoning`);
        if (layerStatus?.build_state?.has_annotations) stats.push(`🏷️ With annotations`);

        if (stats.length > 0) {
            summaryHtml = `
                <div id="pipeline-summary-stats" class="mt-3 pt-3 border-t border-gray-200">
                    <div class="text-xs font-medium text-gray-500 uppercase mb-2">Results</div>
                    <div class="flex flex-wrap gap-2">
                        ${stats.map(s => `<span class="text-xs bg-gray-100 px-2 py-1 rounded">${s}</span>`).join('')}
                    </div>
                </div>
            `;
        }
    }

    // If panel already exists, update only the layer status + summary sections (preserve logs!)
    if (existingPanel) {
        const layerContainer = existingPanel.querySelector('.space-y-1');
        if (layerContainer) {
            layerContainer.innerHTML = layerStatusHtml;
        }
        // Update or insert summary stats (after the layer container)
        const existingSummary = existingPanel.querySelector('#pipeline-summary-stats');
        if (summaryHtml) {
            if (existingSummary) {
                existingSummary.outerHTML = summaryHtml;
            } else {
                // Insert after layer container
                const contentArea = existingPanel.querySelector('.p-4.max-h-80');
                if (contentArea) {
                    contentArea.insertAdjacentHTML('beforeend', summaryHtml);
                }
            }
        }
        // Update the footer status message
        const footer = existingPanel.querySelector('.bg-gray-50');
        if (footer) {
            footer.innerHTML = isPending ? 'Processing... please wait' : 'Refreshing page in a moment...';
        }
        return; // Don't recreate the panel
    }

    // Stop any existing simulated progress (only when creating new panel)
    stopSimulatedProgress();

    // Create panel
    const panel = document.createElement('div');
    panel.id = 'pipeline-log-panel';
    panel.className = 'fixed bottom-4 right-4 w-96 bg-white rounded-lg shadow-xl border border-gray-200 z-50 overflow-hidden';
    panel.innerHTML = `
        <div class="bg-gradient-to-r from-purple-600 to-blue-600 px-4 py-2 flex items-center justify-between">
            <span class="text-white font-medium text-sm">Pipeline Log</span>
            <button onclick="this.closest('#pipeline-log-panel').remove()" class="text-white/80 hover:text-white">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>
        <div class="p-4 max-h-80 overflow-y-auto">
            <div class="space-y-1">
                ${layerStatusHtml || '<div class="text-sm text-gray-500">No layer data available</div>'}
            </div>
            ${summaryHtml}
        </div>
        <!-- Collapsible Log Terminal Section -->
        <div class="border-t border-gray-200">
            <button id="pipeline-log-terminal-toggle"
                    onclick="togglePipelineLogTerminal()"
                    class="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-600 hover:bg-gray-50 transition-colors">
                <span class="flex items-center gap-2">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>
                    </svg>
                    <span id="pipeline-log-terminal-label">Show Logs</span>
                </span>
                <svg id="pipeline-log-terminal-chevron" class="w-4 h-4 transform transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                </svg>
            </button>
            <div id="pipeline-log-terminal" class="hidden bg-gray-900 max-h-48 overflow-y-auto">
                <div id="pipeline-log-terminal-content" class="p-3 font-mono text-xs text-green-400 space-y-0.5">
                    <!-- Log lines will be appended here -->
                </div>
            </div>
        </div>
        <div class="bg-gray-50 px-4 py-2 text-xs text-gray-500 text-center">
            ${isPending ? 'Processing... please wait' : 'Refreshing page in a moment...'}
        </div>
    `;

    document.body.appendChild(panel);

    // NOTE: Simulated progress removed - now using real SSE/polling data only
    // The panel starts with first layer showing as "Processing..." via isPending logic

    // Auto-remove after 5 seconds (only if not pending)
    if (!isPending) {
        setTimeout(() => {
            if (panel.parentElement) {
                panel.style.opacity = '0';
                panel.style.transform = 'translateY(1rem)';
                panel.style.transition = 'all 0.3s ease';
                setTimeout(() => panel.remove(), 300);
            }
        }, 5000);
    }
}

/**
 * Toggle the visibility of the log terminal in the pipeline log panel.
 */
function togglePipelineLogTerminal() {
    const terminal = document.getElementById('pipeline-log-terminal');
    const label = document.getElementById('pipeline-log-terminal-label');
    const chevron = document.getElementById('pipeline-log-terminal-chevron');

    if (!terminal) return;

    const isHidden = terminal.classList.contains('hidden');

    if (isHidden) {
        terminal.classList.remove('hidden');
        if (label) label.textContent = 'Hide Logs';
        if (chevron) chevron.classList.add('rotate-180');
    } else {
        terminal.classList.add('hidden');
        if (label) label.textContent = 'Show Logs';
        if (chevron) chevron.classList.remove('rotate-180');
    }
}

/**
 * Append a log line to the pipeline log panel's terminal section.
 * Creates the panel if it doesn't exist.
 * @param {string} logText - The log text to append
 */
function appendLogToPipelinePanel(logText) {
    const panel = document.getElementById('pipeline-log-panel');

    // If panel doesn't exist, we can't append logs
    if (!panel) {
        console.log('[Pipeline Log] Panel not found, log:', logText);
        return;
    }

    // Find or create the log terminal content container
    let terminalContent = document.getElementById('pipeline-log-terminal-content');

    if (!terminalContent) {
        console.log('[Pipeline Log] Terminal content not found, log:', logText);
        return;
    }

    // Create a new log line element
    const logLine = document.createElement('div');
    logLine.className = 'text-green-400 whitespace-pre-wrap break-all leading-tight';

    // Format the log text - highlight different log levels
    let formattedText = logText;

    // Apply styling based on log content
    if (/\[ERROR\]|error|failed|exception/i.test(logText)) {
        logLine.className = 'text-red-400 whitespace-pre-wrap break-all leading-tight';
    } else if (/\[WARN\]|warning/i.test(logText)) {
        logLine.className = 'text-yellow-400 whitespace-pre-wrap break-all leading-tight';
    } else if (/\[INFO\]|Starting|Complete|Success/i.test(logText)) {
        logLine.className = 'text-green-400 whitespace-pre-wrap break-all leading-tight';
    } else if (/\[DEBUG\]/i.test(logText)) {
        logLine.className = 'text-gray-500 whitespace-pre-wrap break-all leading-tight';
    }

    logLine.textContent = formattedText;
    terminalContent.appendChild(logLine);

    // Auto-expand terminal on first log (so logs are visible immediately)
    const terminal = document.getElementById('pipeline-log-terminal');
    if (terminal && terminal.classList.contains('hidden')) {
        terminal.classList.remove('hidden');
        const chevron = document.getElementById('pipeline-log-terminal-chevron');
        if (chevron) chevron.classList.add('rotate-180');
    }

    // Auto-scroll to bottom
    if (terminal) {
        terminal.scrollTop = terminal.scrollHeight;
    }

    // Update log count in the toggle button label
    const logCount = terminalContent.children.length;
    const label = document.getElementById('pipeline-log-terminal-label');
    if (label) {
        label.textContent = `Hide Logs (${logCount})`;
    }
}

// Expose globally
window.showPipelineLogPanel = showPipelineLogPanel;
window.startSimulatedProgress = startSimulatedProgress;
window.stopSimulatedProgress = stopSimulatedProgress;
window.togglePipelineLogTerminal = togglePipelineLogTerminal;
window.appendLogToPipelinePanel = appendLogToPipelinePanel;

// ============================================================================
// Field Updates
// ============================================================================

async function updateJobField(field, value) {
    const jobId = getJobId();
    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: value })
        });

        const result = await response.json();

        if (result.success) {
            showToast(`${field} updated successfully`);
        } else {
            showToast(result.error || 'Update failed', 'error');
        }
    } catch (err) {
        showToast('Update failed: ' + err.message, 'error');
    }
}

async function saveRemarks() {
    const jobId = getJobId();
    const remarks = document.getElementById('remarks-textarea').value;
    const notes = document.getElementById('notes-textarea').value;

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ remarks, notes })
        });

        const result = await response.json();

        if (result.success) {
            showToast('Notes saved successfully');
        } else {
            showToast(result.error || 'Save failed', 'error');
        }
    } catch (err) {
        showToast('Save failed: ' + err.message, 'error');
    }
}

async function deleteJob() {
    const jobId = getJobId();
    if (!confirm('Are you sure you want to delete this job? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch('/api/jobs/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_ids: [jobId] })
        });

        const result = await response.json();

        if (result.success) {
            showToast('Job deleted successfully');
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            showToast(result.error || 'Delete failed', 'error');
        }
    } catch (err) {
        showToast('Delete failed: ' + err.message, 'error');
    }
}

// ============================================================================
// Toggle Functions
// ============================================================================

function toggleRawData() {
    const container = document.getElementById('raw-data-container');
    const chevron = document.getElementById('raw-data-chevron');

    container.classList.toggle('hidden');
    chevron.classList.toggle('rotate-90');
}

function toggleJobDescription() {
    const preview = document.getElementById('job-description-preview');
    const full = document.getElementById('job-description-full');
    const chevron = document.getElementById('job-description-chevron');

    if (preview.classList.contains('hidden')) {
        preview.classList.remove('hidden');
        full.classList.add('hidden');
        chevron.classList.remove('rotate-90');
    } else {
        preview.classList.add('hidden');
        full.classList.remove('hidden');
        chevron.classList.add('rotate-90');
    }
}

function toggleJobViewer() {
    const container = document.getElementById('job-viewer-container');
    const icon = document.getElementById('job-viewer-icon');
    const button = document.querySelector('[aria-controls="job-viewer-container"]');

    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        icon.classList.add('rotate-90');
        button.setAttribute('aria-expanded', 'true');

        const iframe = document.getElementById('job-iframe');
        if (!iframe.dataset.initialized) {
            iframe.dataset.initialized = 'true';
            setupIframeHandlers();
        }
    } else {
        container.classList.add('hidden');
        icon.classList.remove('rotate-90');
        button.setAttribute('aria-expanded', 'false');
    }
}

// ============================================================================
// Export Functions
// ============================================================================

async function exportPagePDF(jobId, url) {
    const btn = document.getElementById('export-page-pdf-btn');
    const textEl = document.getElementById('export-page-pdf-text');
    const originalText = textEl.textContent;

    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    textEl.textContent = 'Generating...';

    try {
        const response = await fetch(`/api/jobs/${jobId}/export-page-pdf`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const errorMsg = errorData.error || `PDF generation failed (${response.status})`;
            throw new Error(errorMsg);
        }

        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;

        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'job_posting.pdf';
        if (contentDisposition && contentDisposition.includes('filename=')) {
            const match = contentDisposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
        }
        a.download = filename;

        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(downloadUrl);

        textEl.textContent = 'Downloaded!';
        setTimeout(() => { textEl.textContent = originalText; }, 2000);

    } catch (error) {
        console.error('Export PDF failed:', error);
        showToast(error.message || 'Failed to export PDF. Try opening in new tab instead.', 'error');
        textEl.textContent = originalText;
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

async function exportDossierPDF(jobId) {
    const btn = document.getElementById('export-dossier-btn');
    const textEl = document.getElementById('export-dossier-text');
    const originalText = textEl.textContent;

    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    textEl.textContent = 'Generating...';

    try {
        const response = await fetch(`/api/jobs/${jobId}/export-dossier-pdf`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Export failed: ${response.status}`);
        }

        const blob = await response.blob();

        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'dossier.pdf';
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
        }

        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(downloadUrl);

        textEl.textContent = 'Downloaded!';
        showToast('Dossier PDF exported successfully', 'success');
        setTimeout(() => { textEl.textContent = originalText; }, 2000);

    } catch (error) {
        console.error('Export dossier PDF failed:', error);
        showToast(error.message || 'Failed to export dossier PDF', 'error');
        textEl.textContent = originalText;
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

async function copyMetaPrompt(jobId) {
    const btn = document.getElementById('copy-meta-prompt-btn');
    const textEl = document.getElementById('copy-meta-prompt-text');
    const originalText = textEl.textContent;

    btn.disabled = true;
    btn.classList.add('opacity-50', 'cursor-not-allowed');
    textEl.textContent = 'Generating...';

    try {
        const response = await fetch(`/api/jobs/${jobId}/meta-prompt`);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `Failed to generate meta prompt: ${response.status}`);
        }

        const data = await response.json();
        const metaPrompt = data.prompt;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(metaPrompt);
            textEl.textContent = 'Copied!';
            showToast('Meta prompt copied to clipboard! Paste into Claude Code.', 'success');
        } else {
            const textarea = document.createElement('textarea');
            textarea.value = metaPrompt;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            document.body.removeChild(textarea);
            textEl.textContent = 'Copied!';
            showToast('Meta prompt copied to clipboard! Paste into Claude Code.', 'success');
        }

        setTimeout(() => { textEl.textContent = originalText; }, 2000);

    } catch (error) {
        console.error('Copy meta prompt failed:', error);
        showToast(error.message || 'Failed to copy meta prompt', 'error');
        textEl.textContent = originalText;
    } finally {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

// ============================================================================
// Iframe Handlers
// ============================================================================

function setupIframeHandlers() {
    const iframe = document.getElementById('job-iframe');
    const loading = document.getElementById('iframe-loading');
    const error = document.getElementById('iframe-error');

    const loadTimeout = setTimeout(() => {
        if (!loading.classList.contains('hidden')) {
            loading.classList.add('hidden');
            error.classList.remove('hidden');
        }
    }, 10000);

    iframe.addEventListener('load', function() {
        clearTimeout(loadTimeout);
        loading.classList.add('hidden');

        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            if (iframeDoc) {
                iframe.classList.remove('hidden');
            } else {
                error.classList.remove('hidden');
            }
        } catch (e) {
            error.classList.remove('hidden');
        }
    });

    iframe.addEventListener('error', function() {
        clearTimeout(loadTimeout);
        loading.classList.add('hidden');
        error.classList.remove('hidden');
    });
}

// ============================================================================
// Inline Editing (GAP-055)
// ============================================================================

const originalFieldValues = new Map();

function enableEdit(fieldElement) {
    const valueEl = fieldElement.querySelector('.field-value');
    const inputEl = fieldElement.querySelector('.field-input');
    const editBtn = fieldElement.querySelector('.edit-btn');
    const field = fieldElement.dataset.field;

    originalFieldValues.set(field, inputEl.value);

    valueEl.classList.add('hidden');
    inputEl.classList.remove('hidden');
    editBtn.classList.add('hidden');

    inputEl.focus();
    inputEl.select();

    inputEl.addEventListener('blur', () => saveFieldEdit(fieldElement), { once: true });

    inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            inputEl.blur();
        }
        if (e.key === 'Escape') {
            cancelFieldEdit(fieldElement);
        }
    });
}

function showFieldSaveIndicator(fieldElement, status) {
    let indicator = fieldElement.querySelector('.save-indicator');
    if (!indicator) {
        indicator = document.createElement('span');
        indicator.className = 'save-indicator text-xs ml-2 transition-opacity duration-300';
        const label = fieldElement.querySelector('.text-xs.text-gray-500');
        if (label) {
            label.appendChild(indicator);
        }
    }

    if (status === 'saving') {
        indicator.className = 'save-indicator text-xs ml-2 text-amber-600 animate-pulse';
        indicator.textContent = 'Saving...';
        indicator.style.opacity = '1';
    } else if (status === 'saved') {
        indicator.className = 'save-indicator text-xs ml-2 text-green-600';
        indicator.textContent = '✓ Saved';
        indicator.style.opacity = '1';
        setTimeout(() => {
            indicator.style.opacity = '0';
            setTimeout(() => indicator.remove(), 300);
        }, 2000);
    } else if (status === 'error') {
        indicator.className = 'save-indicator text-xs ml-2 text-red-600';
        indicator.textContent = '✗ Error';
        indicator.style.opacity = '1';
        setTimeout(() => {
            indicator.style.opacity = '0';
            setTimeout(() => indicator.remove(), 300);
        }, 3000);
    }
}

async function saveFieldEdit(fieldElement) {
    const jobId = getJobId();
    const field = fieldElement.dataset.field;
    const valueEl = fieldElement.querySelector('.field-value');
    const inputEl = fieldElement.querySelector('.field-input');
    const editBtn = fieldElement.querySelector('.edit-btn');

    let newValue = inputEl.value.trim();
    const originalValue = originalFieldValues.get(field) || '';

    if (newValue === originalValue) {
        valueEl.classList.remove('hidden');
        inputEl.classList.add('hidden');
        editBtn.classList.remove('hidden');
        return;
    }

    if (field === 'score' && newValue !== '') {
        newValue = parseInt(newValue, 10);
        if (isNaN(newValue)) newValue = null;
    }

    showFieldSaveIndicator(fieldElement, 'saving');

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [field]: newValue || null })
        });

        const result = await response.json();

        if (result.success) {
            if (field === 'url' && newValue) {
                valueEl.innerHTML = `<a href="${escapeHtml(newValue)}" target="_blank" class="text-indigo-600 hover:underline break-all">${escapeHtml(newValue)}</a>`;
            } else if (field === 'application_url' && newValue) {
                valueEl.innerHTML = `<a href="${escapeHtml(newValue)}" target="_blank" class="text-indigo-600 hover:underline break-all text-xs">${escapeHtml(newValue.length > 40 ? newValue.substring(0, 40) + '...' : newValue)}</a>`;
                // Update config and trigger visibility update
                window.JOB_DETAIL_CONFIG.applicationUrl = newValue;
                updateScrapeGenerateVisibility();
            } else if (field === 'application_url' && !newValue) {
                valueEl.innerHTML = '<span class="text-gray-400 text-xs">Not set</span>';
                // Clear config and trigger visibility update
                window.JOB_DETAIL_CONFIG.applicationUrl = '';
                updateScrapeGenerateVisibility();
            } else {
                valueEl.textContent = newValue || '-';
            }
            originalFieldValues.set(field, typeof newValue === 'string' ? newValue : String(newValue || ''));
            showFieldSaveIndicator(fieldElement, 'saved');
        } else {
            showFieldSaveIndicator(fieldElement, 'error');
            showToast(result.error || 'Update failed', 'error');
        }
    } catch (err) {
        showFieldSaveIndicator(fieldElement, 'error');
        showToast('Update failed: ' + err.message, 'error');
    }

    valueEl.classList.remove('hidden');
    inputEl.classList.add('hidden');
    editBtn.classList.remove('hidden');
}

function cancelFieldEdit(fieldElement) {
    const valueEl = fieldElement.querySelector('.field-value');
    const inputEl = fieldElement.querySelector('.field-input');
    const editBtn = fieldElement.querySelector('.edit-btn');

    inputEl.value = valueEl.textContent === '-' ? '' : valueEl.textContent;

    valueEl.classList.remove('hidden');
    inputEl.classList.add('hidden');
    editBtn.classList.remove('hidden');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Pipeline Processing
// ============================================================================

let statusPollingInterval = null;
let eventSource = null;

// Outreach generation state (for SSE streaming)
let outreachEventSource = null;
let isOutreachGenerating = false;

// GAP-067: Editable Score Field (Detail Page)
function enableScoreEditDetail(displayEl, jobId, currentScore) {
    const container = displayEl.closest('.editable-score-container');
    const input = container.querySelector('.score-input');

    displayEl.classList.add('hidden');
    input.classList.remove('hidden');
    input.value = currentScore !== null ? currentScore : '';
    input.focus();
    input.select();
}

function handleScoreKeydownDetail(event, input, jobId) {
    if (event.key === 'Enter') {
        event.preventDefault();
        input.blur();
    } else if (event.key === 'Escape') {
        cancelScoreEditDetail(input);
    }
}

function cancelScoreEditDetail(input) {
    const container = input.closest('.editable-score-container');
    const display = container.querySelector('.score-display');
    input.classList.add('hidden');
    display.classList.remove('hidden');
}

async function saveScoreDetail(input, jobId) {
    const container = input.closest('.editable-score-container');
    const display = container.querySelector('.score-display');
    const newScore = input.value.trim();

    let scoreValue = null;
    if (newScore !== '') {
        scoreValue = parseInt(newScore, 10);
        if (isNaN(scoreValue) || scoreValue < 0 || scoreValue > 100) {
            showToast('Score must be between 0 and 100', 'error');
            cancelScoreEditDetail(input);
            return;
        }
    }

    try {
        const response = await fetch('/api/jobs/score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId, score: scoreValue })
        });

        const result = await response.json();

        if (result.success) {
            updateScoreBadgeDetail(display, scoreValue);
            showToast('Score updated', 'success');
        } else {
            showToast(result.error || 'Failed to update score', 'error');
        }
    } catch (error) {
        console.error('Error updating score:', error);
        showToast('Failed to update score', 'error');
    }

    input.classList.add('hidden');
    display.classList.remove('hidden');
}

function updateScoreBadgeDetail(display, score) {
    let badgeClass = 'theme-bg-hover theme-text-secondary';
    let displayText = 'Score: —';

    if (score !== null) {
        displayText = `Score: ${score}`;
        if (score >= 80) badgeClass = 'bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-400';
        else if (score >= 60) badgeClass = 'bg-yellow-100 dark:bg-yellow-900/40 text-yellow-800 dark:text-yellow-400';
    }

    display.innerHTML = `<span class="px-2 py-0.5 rounded-full text-xs font-medium ${badgeClass}">${displayText}</span>`;
}

// GAP-045: Tier selection
let selectedTier = 'auto';
const tierLabels = {
    'auto': 'Auto',
    'A': 'Gold (A)',
    'B': 'Silver (B)',
    'C': 'Bronze (C)',
    'D': 'Skip (D)'
};

function setProcessingTier(tier) {
    selectedTier = tier;
    document.getElementById('selected-tier').value = tier;
    document.getElementById('process-btn-label').textContent = `Process (${tierLabels[tier]})`;

    document.querySelectorAll('.tier-option').forEach(btn => {
        const checkIcon = btn.querySelector('[id^="tier-check-"]');
        if (checkIcon) checkIcon.classList.add('hidden');
    });
    const selectedCheck = document.getElementById(`tier-check-${tier}`);
    if (selectedCheck) selectedCheck.classList.remove('hidden');
}

async function processJobDetail(jobId, jobTitle) {
    const tier = document.getElementById('selected-tier')?.value || 'auto';
    const tierDisplay = tierLabels[tier] || 'Auto';

    const confirmed = confirm(
        `Process job through pipeline?\n\n` +
        `Job: ${jobTitle}\n` +
        `Tier: ${tierDisplay}\n\n` +
        `This will trigger the processing pipeline on the VPS runner.`
    );

    if (!confirmed) return;

    try {
        showToast(`Starting pipeline (${tierDisplay})...`, 'info');

        const response = await fetch('/api/runner/jobs/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_id: jobId,
                level: 2,
                processing_tier: tier
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            let errorMessage;
            try {
                const errorData = JSON.parse(errorText);
                errorMessage = errorData.error || errorData.detail || `Server error: ${response.status}`;
            } catch {
                errorMessage = `Server error: ${response.status} - ${errorText}`;
            }
            showToast(errorMessage, 'error');
            return;
        }

        const result = await response.json();

        if (result.run_id) {
            showToast(`Pipeline started! Run ID: ${result.run_id}`);
            monitorPipeline(result.run_id);
        } else {
            showToast(result.error || 'Failed to start pipeline', 'error');
        }
    } catch (err) {
        console.error('Pipeline execution error:', err);
        showToast(`Pipeline failed: ${err.message}`, 'error');
    }
}

function monitorPipeline(runId) {
    const container = document.getElementById('pipeline-progress-container');
    container.classList.remove('hidden');

    document.getElementById('pipeline-run-id').textContent = `Run: ${runId}`;

    // Show stop button for cancellation (calls global function from base.html)
    if (typeof showPipelineStopButton === 'function') {
        showPipelineStopButton(runId);
    }

    resetPipelineSteps();
    startLogStreaming(runId);

    statusPollingInterval = setInterval(() => pollPipelineStatus(runId), 2000);
    pollPipelineStatus(runId);
}

function resetPipelineSteps() {
    // Reset monotonic progress tracker
    highestLayerReached = 0;

    // Reset horizontal steps
    const stepsH = document.querySelectorAll('.pipeline-step-h');
    stepsH.forEach(step => {
        step.classList.remove('executing', 'success', 'failed');
        step.classList.add('pending');

        const icon = step.querySelector('.step-icon-h');
        icon.classList.remove('bg-indigo-600', 'bg-green-500', 'bg-red-500', 'text-white');
        icon.classList.add('bg-gray-200', 'dark:bg-gray-700', 'text-gray-500', 'dark:text-gray-400');

        // Reset icon display
        step.querySelector('.step-number').classList.remove('hidden');
        step.querySelector('.step-check').classList.add('hidden');
        step.querySelector('.step-spinner').classList.add('hidden');
        step.querySelector('.step-error').classList.add('hidden');

        // Reset label color
        const label = step.querySelector('.step-label-h');
        label.classList.remove('text-indigo-600', 'dark:text-indigo-400', 'text-green-600', 'dark:text-green-400', 'text-red-600', 'dark:text-red-400');
        label.classList.add('text-gray-500', 'dark:text-gray-400');

        // Hide duration
        const duration = step.querySelector('.step-duration-h');
        if (duration) {
            duration.classList.add('hidden');
            duration.textContent = '--';
        }
    });

    // Reset progress bar and line
    document.getElementById('pipeline-overall-percent').textContent = '0%';
    document.getElementById('pipeline-overall-progress-bar').style.width = '0%';

    const progressLine = document.getElementById('pipeline-progress-line');
    if (progressLine) progressLine.style.width = '0%';

    // Hide error display
    const errorDisplay = document.getElementById('pipeline-error-display');
    if (errorDisplay) errorDisplay.classList.add('hidden');

    // Hide current step details
    const stepDetails = document.getElementById('current-step-details');
    if (stepDetails) stepDetails.classList.add('hidden');
}

function connectPipelineSSE(runId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/api/runner/jobs/${runId}/progress`);

    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handlePipelineProgressUpdate(data);
        } catch (err) {
            console.error('Failed to parse SSE data:', err);
        }
    };

    eventSource.onerror = (err) => {
        console.error('SSE connection error:', err);
        eventSource.close();
        if (!statusPollingInterval) {
            statusPollingInterval = setInterval(() => pollPipelineStatus(runId), 2000);
        }
    };
}

function handlePipelineProgressUpdate(data) {
    if (!data) return;

    if (data.layer && data.status) {
        updatePipelineStep(data.layer, data.status, data.error, data.duration);
    }

    if (data.progress !== undefined) {
        updateOverallProgress(data.progress);
    }

    if (data.status === 'complete' || data.status === 'completed') {
        handlePipelineComplete();
    }

    if (data.status === 'failed') {
        handlePipelineFailed(data.error);
    }
}

// Step titles for current step display
const stepTitles = {
    'intake': { title: 'Intake', description: 'Parsing job posting and candidate profile...' },
    'pain_points': { title: 'Pain Point Mining', description: 'Extracting company and role pain points...' },
    'company_research': { title: 'Company Research', description: 'Researching company via FireCrawl...' },
    'role_research': { title: 'Role Research', description: 'Analyzing specific role requirements...' },
    'fit_scoring': { title: 'Fit Scoring', description: 'Calculating candidate fit score (0-100)...' },
    'people_mapping': { title: 'People Mapping', description: 'Finding LinkedIn contacts and recruiters...' },
    'cv_outreach_generation': { title: 'CV & Outreach', description: 'Generating personalized CV and outreach messages...' }
};

function updatePipelineStep(layerName, status, errorMessage, duration) {
    const step = document.querySelector(`.pipeline-step-h[data-layer="${layerName}"]`);
    if (!step) {
        console.warn(`Layer not found: ${layerName}`);
        return;
    }

    const icon = step.querySelector('.step-icon-h');
    const numberEl = step.querySelector('.step-number');
    const checkEl = step.querySelector('.step-check');
    const spinnerEl = step.querySelector('.step-spinner');
    const errorEl = step.querySelector('.step-error');
    const labelEl = step.querySelector('.step-label-h');
    const durationEl = step.querySelector('.step-duration-h');

    // Remove all state classes
    step.classList.remove('pending', 'executing', 'success', 'failed', 'skipped');
    step.classList.add(status);

    // Reset icon classes
    icon.classList.remove('bg-gray-200', 'dark:bg-gray-700', 'bg-indigo-600', 'bg-green-500', 'bg-red-500', 'text-gray-500', 'dark:text-gray-400', 'text-white', 'ring-4', 'ring-indigo-200', 'dark:ring-indigo-900');
    labelEl.classList.remove('text-gray-500', 'dark:text-gray-400', 'text-indigo-600', 'dark:text-indigo-400', 'text-green-600', 'dark:text-green-400', 'text-red-600', 'dark:text-red-400');

    // Hide all icon variants first
    numberEl.classList.add('hidden');
    checkEl.classList.add('hidden');
    spinnerEl.classList.add('hidden');
    errorEl.classList.add('hidden');

    switch (status) {
        case 'executing':
            icon.classList.add('bg-indigo-600', 'text-white', 'ring-4', 'ring-indigo-200', 'dark:ring-indigo-900');
            labelEl.classList.add('text-indigo-600', 'dark:text-indigo-400');
            spinnerEl.classList.remove('hidden');
            // Show current step details
            showCurrentStepDetails(layerName);
            break;
        case 'success':
            icon.classList.add('bg-green-500', 'text-white');
            labelEl.classList.add('text-green-600', 'dark:text-green-400');
            checkEl.classList.remove('hidden');
            // Update progress line
            updateProgressLine(layerName);
            break;
        case 'failed':
            icon.classList.add('bg-red-500', 'text-white');
            labelEl.classList.add('text-red-600', 'dark:text-red-400');
            errorEl.classList.remove('hidden');
            if (errorMessage) {
                showPipelineError(errorMessage);
            }
            break;
        default: // pending, skipped
            icon.classList.add('bg-gray-200', 'dark:bg-gray-700', 'text-gray-500', 'dark:text-gray-400');
            labelEl.classList.add('text-gray-500', 'dark:text-gray-400');
            numberEl.classList.remove('hidden');
    }

    // Show duration if provided
    if (duration && durationEl) {
        durationEl.textContent = formatDuration(duration);
        durationEl.classList.remove('hidden');
    }
}

function showCurrentStepDetails(layerName) {
    const details = document.getElementById('current-step-details');
    const titleEl = document.getElementById('current-step-title');
    const descEl = document.getElementById('current-step-description');

    if (!details || !titleEl || !descEl) return;

    const stepInfo = stepTitles[layerName] || { title: 'Processing...', description: 'Working on pipeline step...' };
    titleEl.textContent = stepInfo.title;
    descEl.textContent = stepInfo.description;
    details.classList.remove('hidden');
}

function showPipelineError(message) {
    const errorDisplay = document.getElementById('pipeline-error-display');
    const errorMessage = document.getElementById('pipeline-error-message');

    if (!errorDisplay || !errorMessage) return;

    errorMessage.textContent = message;
    errorDisplay.classList.remove('hidden');

    // Hide current step details
    const stepDetails = document.getElementById('current-step-details');
    if (stepDetails) stepDetails.classList.add('hidden');
}

function updateProgressLine(layerName) {
    const progressLine = document.getElementById('pipeline-progress-line');
    if (!progressLine) return;

    // Find completed step number
    const step = document.querySelector(`.pipeline-step-h[data-layer="${layerName}"]`);
    if (!step) return;

    const stepNum = parseInt(step.dataset.step, 10);
    const totalSteps = 7;

    // Calculate width as percentage (each step is ~14.3% of total width)
    // Account for the spacing - the line goes from step 1 to step 7
    const widthPercent = ((stepNum - 1) / (totalSteps - 1)) * 100;
    progressLine.style.width = `${widthPercent}%`;
}

function updateOverallProgress(percent) {
    const percentEl = document.getElementById('pipeline-overall-percent');
    const progressBar = document.getElementById('pipeline-overall-progress-bar');

    percentEl.textContent = `${Math.round(percent)}%`;
    progressBar.style.width = `${percent}%`;
}

function calculateOverallProgress() {
    const steps = document.querySelectorAll('.pipeline-step-h');
    const totalSteps = steps.length;
    let completedSteps = 0;

    steps.forEach(step => {
        if (step.classList.contains('success')) {
            completedSteps++;
        } else if (step.classList.contains('executing')) {
            completedSteps += 0.5;
        }
    });

    const progress = (completedSteps / totalSteps) * 100;
    updateOverallProgress(progress);
}

function handlePipelineComplete() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
    }

    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    updateOverallProgress(100);
    showToast('Pipeline completed successfully!', 'success');

    setTimeout(() => {
        window.location.reload();
    }, 3000);
}

function handlePipelineFailed(errorMessage) {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
    }

    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    showToast(errorMessage || 'Pipeline failed', 'error');
}

function handlePipelineCancelled() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
    }

    if (eventSource) {
        eventSource.close();
        eventSource = null;
    }

    // Update progress bar to show cancelled state
    const progressBar = document.getElementById('pipeline-overall-progress-bar');
    if (progressBar) {
        progressBar.classList.remove('from-indigo-500', 'to-indigo-600');
        progressBar.classList.add('from-gray-400', 'to-gray-500');
    }

    // Update percentage text
    const percentText = document.getElementById('pipeline-overall-percent');
    if (percentText) {
        percentText.textContent = 'Cancelled';
        percentText.classList.remove('text-indigo-700', 'dark:text-indigo-400');
        percentText.classList.add('text-gray-600', 'dark:text-gray-400');
    }

    showToast('Pipeline cancelled - all changes discarded', 'info');
}

function formatDuration(seconds) {
    if (seconds < 1) return '<1s';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
}

async function pollPipelineStatus(runId) {
    try {
        const response = await fetch(`/api/runner/jobs/${runId}/status`);
        const data = await response.json();

        if (response.ok) {
            handlePipelineProgressUpdate(data);

            if (data.layers && Array.isArray(data.layers)) {
                data.layers.forEach(layer => {
                    updatePipelineStep(layer.name, layer.status, layer.error, layer.duration);
                });
                calculateOverallProgress();
            } else {
                const progressValue = data.progress ? Math.round(data.progress * 100) : 0;
                updateOverallProgress(progressValue);
            }

            if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
                // Hide stop button when pipeline ends
                if (typeof hidePipelineStopButton === 'function') {
                    hidePipelineStopButton();
                }

                if (data.status === 'completed') {
                    handlePipelineComplete();
                } else if (data.status === 'cancelled') {
                    handlePipelineCancelled();
                } else {
                    handlePipelineFailed(data.error);
                }
            }
        }
    } catch (err) {
        console.error('Status poll failed:', err);
    }
}

function startLogStreaming(runId) {
    const logsContent = document.getElementById('logs-content');
    const logsContainer = document.getElementById('logs-container');
    logsContent.textContent = '';

    // Show logs container automatically when streaming starts
    logsContainer.classList.remove('hidden');
    document.getElementById('logs-toggle-text').textContent = 'Hide';

    // Mark first step as executing immediately
    updatePipelineStep('intake', 'executing');

    eventSource = new EventSource(`/api/runner/jobs/${runId}/logs`);

    eventSource.onmessage = (event) => {
        const logLine = document.createElement('div');
        logLine.textContent = event.data;
        logsContent.appendChild(logLine);

        parseLogAndUpdateSteps(event.data);

        const logsContainer = document.getElementById('logs-container');
        logsContainer.scrollTop = logsContainer.scrollHeight;
    };

    eventSource.addEventListener('end', (event) => {
        const endLine = document.createElement('div');
        endLine.className = 'text-yellow-400';
        endLine.textContent = `Pipeline ${event.data}`;
        logsContent.appendChild(endLine);

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        // Hide stop button when pipeline ends (calls global function from base.html)
        if (typeof hidePipelineStopButton === 'function') {
            hidePipelineStopButton();
        }

        // Check if pipeline completed, failed, or cancelled based on the event data
        const eventData = event.data ? event.data.toLowerCase() : '';
        if (eventData.includes('completed') || eventData.includes('success')) {
            handlePipelineComplete();
        } else if (eventData.includes('cancelled')) {
            handlePipelineCancelled();
        } else if (eventData.includes('failed') || eventData.includes('error')) {
            handlePipelineFailed(event.data);
        } else {
            // Default to completed if we get an 'end' event without explicit status
            // This handles cases where the pipeline finishes but status isn't explicit
            handlePipelineComplete();
        }
    });

    eventSource.addEventListener('error', (event) => {
        console.error('Log stream error:', event);
        const errorLine = document.createElement('div');
        errorLine.className = 'text-red-400';
        errorLine.textContent = 'Log streaming ended or encountered an error';
        logsContent.appendChild(errorLine);

        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    });
}

/**
 * Start SSE log streaming for outreach generation (InMail/Connection).
 * Similar to startLogStreaming but specific to outreach operations.
 * @param {string} runId - The operation run ID
 * @param {string} messageType - Either 'inmail' or 'connection'
 */
function startOutreachLogStreaming(runId, messageType) {
    // Close any existing connection
    if (outreachEventSource) {
        outreachEventSource.close();
        outreachEventSource = null;
    }

    const logsContent = document.getElementById('logs-content');
    const logsContainer = document.getElementById('logs-container');

    // Clear and show logs
    if (logsContent) logsContent.innerHTML = '';
    if (logsContainer) {
        logsContainer.classList.remove('hidden');
        const toggleText = document.getElementById('logs-toggle-text');
        if (toggleText) toggleText.textContent = 'Hide';
    }

    // Connect to the runner service operation logs SSE endpoint
    outreachEventSource = new EventSource(`/api/runner/operations/${runId}/logs`);

    outreachEventSource.onmessage = (event) => {
        // Use the existing appendLogToPipelinePanel function
        appendLogToPipelinePanel(event.data);
    };

    outreachEventSource.addEventListener('result', (event) => {
        try {
            const result = JSON.parse(event.data);
            if (result.success) {
                const label = messageType === 'connection' ? 'Connection message' : 'InMail';
                showToast(`${label} generated successfully!`, 'success');
            }
        } catch (e) {
            console.error('Failed to parse result:', e);
        }
    });

    outreachEventSource.addEventListener('end', (event) => {
        if (outreachEventSource) {
            outreachEventSource.close();
            outreachEventSource = null;
        }
        isOutreachGenerating = false;
        enableOutreachButtons();

        if (event.data === 'completed') {
            window.location.reload();
        } else {
            showToast('Generation failed', 'error');
        }
    });

    outreachEventSource.addEventListener('error', (event) => {
        console.error('Outreach SSE error:', event);
        if (outreachEventSource) {
            outreachEventSource.close();
            outreachEventSource = null;
        }
        isOutreachGenerating = false;
        enableOutreachButtons();
    });
}

/**
 * Disable all outreach generation buttons during generation.
 */
function disableOutreachButtons() {
    document.querySelectorAll('button[onclick^="generateOutreach"]').forEach(btn => {
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed');
    });
}

/**
 * Re-enable all outreach generation buttons after generation completes/fails.
 */
function enableOutreachButtons() {
    document.querySelectorAll('button[onclick^="generateOutreach"]').forEach(btn => {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed');
    });
}

function parseLogAndUpdateSteps(logText) {
    // Layer detection patterns - match both module names and log messages
    // Logs look like: "2025-12-08 21:22:00 [INFO] src.layer3.company_researcher: Searching..."
    // Or: "LAYER 2: Pain-Point Miner"
    // NOTE: Patterns are more specific to avoid false positives (e.g., pain_point in company_research)
    const layerPatterns = {
        'intake': /(?:layer1[^0-9]|layer_1|LAYER 1:|src\.layer1\.|intake_processor|jd_extractor)/i,
        'pain_points': /(?:layer2[^0-9]|layer_2|LAYER 2:|src\.layer2\.|pain_point_miner)/i,
        'company_research': /(?:layer3[^0-9]|layer_3|LAYER 3:|src\.layer3\.|company_research(?:er)?(?:\.|:))/i,
        'role_research': /(?:layer4[^0-9]|layer_4|LAYER 4:|src\.layer4\.|role_research(?:er)?(?:\.|:))/i,
        'fit_scoring': /(?:layer5[^0-9]|layer_5|LAYER 5:|src\.layer5\.|fit_scor(?:ing|er)?(?:\.|:)|fit_analysis)/i,
        'people_mapping': /(?:people_mapper(?:\.|:)|contact.*discovery|linkedin.*search)/i,
        'cv_outreach_generation': /(?:layer6[^0-9]|layer_6|LAYER 6:|layer7[^0-9]|layer_7|LAYER 7:|src\.layer6\.|src\.layer7\.|cv_gen(?:erator)?(?:\.|:)|outreach_gen(?:\.|:)|header_generator|markdown_cv|layer6_v2)/i
    };

    // Track which layer we detected
    let detectedLayer = null;

    for (const [layerName, pattern] of Object.entries(layerPatterns)) {
        if (pattern.test(logText)) {
            detectedLayer = layerName;
            console.log(`[Pipeline] Detected layer: ${layerName} from log: ${logText.substring(0, 80)}...`);
            break;
        }
    }

    if (detectedLayer) {
        const detectedIndex = layerOrder.indexOf(detectedLayer);

        // MONOTONIC ENFORCEMENT: Only update if moving forward
        if (detectedIndex >= 0 && detectedIndex < highestLayerReached) {
            console.log(`[Pipeline] Ignoring regression: ${detectedLayer} (${detectedIndex}) < highest (${highestLayerReached})`);
            return;
        }

        // Check for start indicators - be more aggressive about detecting "executing" state
        const isStarting = /LAYER \d:|Starting|Begin|Searching|Scraping|Processing|Analyzing|Generating|Mining|Researching|Running|Extracting/i.test(logText);
        // Check for completion indicators
        const isComplete = /complete|finished|done\b|✓|✔|success|Extracted \d+|Generated|Found \d+|Persisted|published/i.test(logText);
        // Check for error indicators
        const isError = /failed|error|exception|❌/i.test(logText);

        if (isError) {
            console.log(`[Pipeline] ${detectedLayer} -> FAILED`);
            updatePipelineStep(detectedLayer, 'failed', logText);
            calculateOverallProgress();
        } else if (isComplete) {
            console.log(`[Pipeline] ${detectedLayer} -> SUCCESS`);
            updatePipelineStep(detectedLayer, 'success');
            // Update monotonic tracker on success
            highestLayerReached = Math.max(highestLayerReached, detectedIndex + 1);
            calculateOverallProgress();
        } else if (isStarting) {
            console.log(`[Pipeline] ${detectedLayer} -> EXECUTING`);
            updatePipelineStep(detectedLayer, 'executing');
            calculateOverallProgress();
        }
    }

    // Also check for explicit layer completion markers
    const completionMatch = logText.match(/[✓✔]\s*(Layer\s*)?(\d+)/i);
    if (completionMatch) {
        const layerMap = {
            '1': 'intake',
            '2': 'pain_points',
            '3': 'company_research',
            '4': 'role_research',
            '5': 'fit_scoring',
            '6': 'people_mapping',
            '7': 'cv_outreach_generation'
        };
        const layerName = layerMap[completionMatch[2]];
        if (layerName) {
            updatePipelineStep(layerName, 'success');
            calculateOverallProgress();
        }
    }

    // Check for "Pipeline completed" message
    if (/pipeline.*completed|all layers.*complete|run.*complete|Pipeline complete|Persisted to MongoDB/i.test(logText)) {
        console.log('[Pipeline] Completion message detected in logs');
        // Mark all steps as complete
        ['intake', 'pain_points', 'company_research', 'role_research', 'fit_scoring', 'people_mapping', 'cv_outreach_generation'].forEach(layer => {
            const step = document.querySelector(`.pipeline-step-h[data-layer="${layer}"]`);
            if (step && !step.classList.contains('success') && !step.classList.contains('failed')) {
                updatePipelineStep(layer, 'success');
            }
        });
        calculateOverallProgress();
        // Trigger the completion handler after a brief delay to let final logs appear
        setTimeout(() => handlePipelineComplete(), 1000);
    }

    // Check for pipeline failure message
    if (/pipeline.*failed|fatal error|critical error/i.test(logText)) {
        console.log('[Pipeline] Failure message detected in logs');
        handlePipelineFailed(logText);
    }
}

function displayArtifacts(runId, artifacts) {
    const container = document.getElementById('artifacts-container');
    const list = document.getElementById('artifacts-list');

    if (!artifacts || artifacts.length === 0) return;

    container.classList.remove('hidden');
    list.innerHTML = '';

    artifacts.forEach(artifact => {
        const button = document.createElement('a');
        button.href = `/api/runner/jobs/${runId}/artifacts/${artifact}`;
        button.download = artifact;
        button.className = 'inline-flex items-center px-3 py-2 border border-indigo-300 rounded-md text-sm font-medium text-indigo-700 bg-white hover:bg-indigo-50 transition';
        button.innerHTML = `
            <svg class="h-4 w-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3 3m0 0l3-3m-3 3V10"/>
            </svg>
            ${artifact}
        `;
        list.appendChild(button);
    });
}

function toggleLogsFull() {
    const logsContainer = document.getElementById('logs-container');
    const toggleText = document.getElementById('logs-toggle-text');

    if (logsContainer.classList.contains('hidden')) {
        logsContainer.classList.remove('hidden');
        toggleText.textContent = 'Hide';
    } else {
        logsContainer.classList.add('hidden');
        toggleText.textContent = 'Show';
    }
}

async function copyLogsToClipboard() {
    const logsContent = document.getElementById('logs-content');

    if (!logsContent) {
        showToast('Logs not found', 'error');
        return;
    }

    const logsText = logsContent.innerText || logsContent.textContent;

    if (!logsText || logsText.trim() === '' || logsText.includes('Waiting for logs')) {
        showToast('No logs to copy', 'info');
        return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
        try {
            await navigator.clipboard.writeText(logsText);
            showToast('Logs copied to clipboard!', 'success');
        } catch (err) {
            console.error('Clipboard API failed:', err);
            fallbackCopyTextToClipboard(logsText);
        }
    } else {
        fallbackCopyTextToClipboard(logsText);
    }
}

function fallbackCopyTextToClipboard(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;

    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    textArea.style.opacity = '0';

    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showToast('Logs copied to clipboard!', 'success');
        } else {
            showToast('Failed to copy logs', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('Copy not supported in this browser', 'error');
    }

    document.body.removeChild(textArea);
}

// ============================================================================
// CV Editor Functions
// ============================================================================

async function exportCVFromDetailPage() {
    const jobId = getJobId();
    try {
        showToast('Generating PDF...', 'info');
        console.log('Requesting PDF generation for job:', jobId);

        const response = await fetch(`/api/jobs/${jobId}/cv-editor/pdf`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        });

        console.log('PDF generation response status:', response.status);

        if (!response.ok) {
            let errorMessage = 'PDF generation failed';
            try {
                const errorData = await response.json();
                errorMessage = errorData.error || errorData.detail || errorMessage;
                console.error('PDF generation error:', errorData);
            } catch (parseErr) {
                const errorText = await response.text();
                console.error('PDF generation error (non-JSON):', errorText);
                errorMessage = errorText || errorMessage;
            }
            throw new Error(errorMessage);
        }

        const blob = await response.blob();
        console.log('PDF blob size:', blob.size, 'bytes');

        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'CV.pdf';
        if (contentDisposition) {
            const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
            if (matches != null && matches[1]) {
                filename = matches[1].replace(/['"]/g, '');
            }
        }
        console.log('Downloading PDF as:', filename);

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        showToast('PDF downloaded successfully');
    } catch (err) {
        console.error('Export PDF error:', err);
        showToast('PDF generation failed: ' + err.message, 'error');
    }
}

// ============================================================================
// Cover Letter Editing
// ============================================================================

let clEditMode = false;

function toggleCoverLetterEdit() {
    clEditMode = !clEditMode;

    const editBtn = document.getElementById('edit-cl-btn');
    const editText = document.getElementById('edit-cl-text');
    const saveBtn = document.getElementById('save-cl-btn');
    const displayDiv = document.getElementById('cl-display');
    const textArea = document.getElementById('cl-textarea');
    const warningsDiv = document.getElementById('cl-warnings');

    if (clEditMode) {
        editText.textContent = 'Cancel';
        editBtn.classList.remove('text-purple-700', 'bg-purple-50', 'border-purple-200');
        editBtn.classList.add('text-red-700', 'bg-red-50', 'border-red-200');
        saveBtn.classList.remove('hidden');
        displayDiv.classList.add('hidden');
        textArea.classList.remove('hidden');
        warningsDiv.classList.add('hidden');
        textArea.focus();
    } else {
        editText.textContent = 'Edit';
        editBtn.classList.remove('text-red-700', 'bg-red-50', 'border-red-200');
        editBtn.classList.add('text-purple-700', 'bg-purple-50', 'border-purple-200');
        saveBtn.classList.add('hidden');
        displayDiv.classList.remove('hidden');
        textArea.classList.add('hidden');
        textArea.value = document.getElementById('cl-text').textContent;
    }
}

async function saveCoverLetterChanges() {
    const jobId = getJobId();
    const textArea = document.getElementById('cl-textarea');
    const newText = textArea.value.trim();

    if (!newText) {
        showToast('Cover letter cannot be empty', 'error');
        return;
    }

    showToast('Saving cover letter...', 'info');

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cover_letter: newText })
        });

        const result = await response.json();

        if (result.success) {
            document.getElementById('cl-text').textContent = newText;
            showToast('Cover letter saved');
            validateCoverLetter(newText);
            toggleCoverLetterEdit();
        } else {
            showToast(result.error || 'Failed to save', 'error');
        }
    } catch (err) {
        showToast('Save failed: ' + err.message, 'error');
    }
}

function validateCoverLetter(text) {
    const warnings = [];
    const words = text.split(/\s+/).length;

    if (words < 180) warnings.push('Cover letter is short (' + words + ' words, recommended: 180-420)');
    if (words > 420) warnings.push('Cover letter is long (' + words + ' words, recommended: 180-420)');

    if (!/\d+%|\d+x|\$\d+|\d+\s*(years?|months?|days?|hours?)/i.test(text)) {
        warnings.push('No quantified metrics found (add percentages, multipliers, or dollar amounts)');
    }

    if (!text.includes('calendly.com/taimooralam')) {
        warnings.push('Missing Calendly link (required for call-to-action)');
    }

    const boilerplate = ['excited to apply', 'dream job', 'perfect fit', 'passionate about', 'eager to'];
    const found = boilerplate.filter(phrase => text.toLowerCase().includes(phrase));
    if (found.length > 2) {
        warnings.push('Contains generic phrases: ' + found.join(', '));
    }

    const warningsDiv = document.getElementById('cl-warnings');
    if (warnings.length > 0) {
        warningsDiv.innerHTML = '<strong>Validation Warnings:</strong><ul class="list-disc ml-4 mt-1">' +
            warnings.map(w => '<li>' + w + '</li>').join('') + '</ul>';
        warningsDiv.classList.remove('hidden');
    } else {
        warningsDiv.classList.add('hidden');
    }
}

async function generateCoverLetterPDF() {
    const jobId = getJobId();
    try {
        showToast('Generating cover letter PDF...', 'info');

        const response = await fetch(`/api/jobs/${jobId}/cover-letter/pdf`, {
            method: 'POST'
        });

        const result = await response.json();

        if (result.success) {
            showToast('PDF generated successfully');
            setTimeout(() => {
                window.location.href = `/api/jobs/${jobId}/cover-letter/download`;
            }, 500);
        } else {
            showToast(result.error || 'PDF generation failed', 'error');
        }
    } catch (err) {
        showToast('PDF generation failed: ' + err.message, 'error');
    }
}

// ============================================================================
// Cover Letter Main Section (Copy & Edit for main content area)
// ============================================================================

let clMainEditMode = false;

/**
 * Copy cover letter text to clipboard.
 * Uses the main content area cover letter text.
 *
 * @param {HTMLElement} buttonElement - The button that triggered the copy (for visual feedback)
 */
async function copyCoverLetter(buttonElement = null) {
    const clText = document.getElementById('cl-main-text')?.innerText;

    if (!clText || clText.trim() === '') {
        showToast('No cover letter to copy', 'error');
        return;
    }

    await copyToClipboard(clText, 'Cover letter', buttonElement);
}

/**
 * Toggle edit mode for cover letter in main content area.
 */
function toggleCoverLetterEditMain() {
    clMainEditMode = !clMainEditMode;

    const editBtn = document.getElementById('edit-cl-main-btn');
    const editText = document.getElementById('edit-cl-main-text');
    const saveBtn = document.getElementById('save-cl-main-btn');
    const displayDiv = document.getElementById('cl-main-display');
    const textArea = document.getElementById('cl-main-textarea');
    const warningsDiv = document.getElementById('cl-main-warnings');

    if (clMainEditMode) {
        editText.textContent = 'Cancel';
        editBtn.classList.remove('btn-secondary');
        editBtn.classList.add('btn-danger');
        saveBtn.classList.remove('hidden');
        displayDiv.classList.add('hidden');
        textArea.classList.remove('hidden');
        warningsDiv.classList.add('hidden');
        textArea.focus();
    } else {
        editText.textContent = 'Edit';
        editBtn.classList.remove('btn-danger');
        editBtn.classList.add('btn-secondary');
        saveBtn.classList.add('hidden');
        displayDiv.classList.remove('hidden');
        textArea.classList.add('hidden');
        textArea.value = document.getElementById('cl-main-text').textContent;
    }
}

/**
 * Save cover letter changes from main content area.
 * Also syncs to the sidebar cover letter display.
 */
async function saveCoverLetterChangesMain() {
    const jobId = getJobId();
    const textArea = document.getElementById('cl-main-textarea');
    const newText = textArea.value.trim();

    if (!newText) {
        showToast('Cover letter cannot be empty', 'error');
        return;
    }

    showToast('Saving cover letter...', 'info');

    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cover_letter: newText })
        });

        const result = await response.json();

        if (result.success) {
            // Update main content area
            document.getElementById('cl-main-text').textContent = newText;

            // Also update sidebar cover letter if it exists
            const sidebarClText = document.getElementById('cl-text');
            if (sidebarClText) {
                // Sidebar shows truncated version (500 chars)
                sidebarClText.textContent = newText.length > 500
                    ? newText.substring(0, 500) + '...'
                    : newText;
            }

            // Update sidebar textarea too
            const sidebarTextarea = document.getElementById('cl-textarea');
            if (sidebarTextarea) {
                sidebarTextarea.value = newText;
            }

            // Update word count
            const wordCount = newText.split(/\s+/).filter(w => w.length > 0).length;
            const wordCountEl = document.getElementById('cl-word-count');
            if (wordCountEl) {
                wordCountEl.textContent = `${wordCount} words`;
            }

            showToast('Cover letter saved');
            validateCoverLetterMain(newText);
            toggleCoverLetterEditMain();
        } else {
            showToast(result.error || 'Failed to save', 'error');
        }
    } catch (err) {
        showToast('Save failed: ' + err.message, 'error');
    }
}

/**
 * Validate cover letter and show warnings in main content area.
 *
 * @param {string} text - The cover letter text to validate
 */
function validateCoverLetterMain(text) {
    const warnings = [];
    const words = text.split(/\s+/).filter(w => w.length > 0).length;

    if (words < 180) warnings.push(`Cover letter is short (${words} words, recommended: 180-420)`);
    if (words > 420) warnings.push(`Cover letter is long (${words} words, recommended: 180-420)`);

    if (!/\d+%|\d+x|\$\d+|\d+\s*(years?|months?|days?|hours?)/i.test(text)) {
        warnings.push('No quantified metrics found (add percentages, multipliers, or dollar amounts)');
    }

    if (!text.includes('calendly.com/taimooralam')) {
        warnings.push('Missing Calendly link (required for call-to-action)');
    }

    const boilerplate = ['excited to apply', 'dream job', 'perfect fit', 'passionate about', 'eager to'];
    const found = boilerplate.filter(phrase => text.toLowerCase().includes(phrase));
    if (found.length > 2) {
        warnings.push('Contains generic phrases: ' + found.join(', '));
    }

    const warningsDiv = document.getElementById('cl-main-warnings');
    if (warnings.length > 0) {
        warningsDiv.innerHTML = '<strong>Validation Warnings:</strong><ul class="list-disc ml-4 mt-1">' +
            warnings.map(w => `<li>${w}</li>`).join('') + '</ul>';
        warningsDiv.classList.remove('hidden');
    } else {
        warningsDiv.classList.add('hidden');
    }
}

// ============================================================================
// Contact Management Functions
// ============================================================================

let validatedContacts = [];

async function deleteContact(contactType, contactIndex, contactName) {
    const jobId = getJobId();
    const confirmed = confirm(`Remove ${contactName}?`);
    if (!confirmed) return;

    try {
        const response = await fetch(
            `/api/jobs/${jobId}/contacts/${contactType}/${contactIndex}`,
            { method: 'DELETE' }
        );

        const result = await response.json();

        if (result.success) {
            const card = document.querySelector(
                `.contact-card[data-contact-type="${contactType}"][data-contact-index="${contactIndex}"]`
            );
            if (card) {
                card.style.transition = 'opacity 0.3s, transform 0.3s';
                card.style.opacity = '0';
                card.style.transform = 'scale(0.95)';
                setTimeout(() => {
                    card.remove();
                    updateContactIndices(contactType);
                }, 300);
            }
            showToast(result.message || 'Contact removed');
        } else {
            showToast(result.error || 'Failed to delete contact', 'error');
        }
    } catch (err) {
        showToast('Failed to delete contact: ' + err.message, 'error');
    }
}

function updateContactIndices(contactType) {
    const cards = document.querySelectorAll(
        `.contact-card[data-contact-type="${contactType}"]`
    );
    cards.forEach((card, index) => {
        card.setAttribute('data-contact-index', index);
        const deleteBtn = card.querySelector('button[onclick*="deleteContact"]');
        if (deleteBtn) {
            const contactName = deleteBtn.getAttribute('onclick').match(/'([^']+)'\)$/)?.[1] || 'contact';
            deleteBtn.setAttribute('onclick', `deleteContact('${contactType}', ${index}, '${contactName}')`);
        }
    });
}

/**
 * Generate outreach message for a specific contact.
 *
 * @param {string} contactType - 'primary' or 'secondary'
 * @param {number} contactIndex - Index of the contact in the array
 * @param {string} messageType - 'connection' or 'inmail'
 * @param {HTMLButtonElement} buttonElement - The button that triggered the action
 */
async function generateOutreach(contactType, contactIndex, messageType, buttonElement) {
    // Prevent concurrent generations
    if (isOutreachGenerating) {
        showToast('Generation already in progress', 'info');
        return;
    }

    const jobId = getJobId();

    // Get the selected processing tier from the dropdown (if available)
    let tier = document.getElementById('selected-tier')?.value || 'auto';
    // Map "auto" to "balanced" for outreach generation (backend only accepts fast/balanced/quality)
    if (tier === 'auto') {
        tier = 'balanced';
    }

    isOutreachGenerating = true;
    disableOutreachButtons();

    // Show button spinner
    if (buttonElement) {
        buttonElement.dataset.originalContent = buttonElement.innerHTML;
        buttonElement.innerHTML = `
            <svg class="btn-spinner w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Generating...</span>
        `;
    }

    try {
        // POST to streaming endpoint (note: /api/runner/ prefix for runner service)
        const response = await fetch(
            `/api/runner/contacts/${jobId}/${contactType}/${contactIndex}/generate-outreach/stream`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tier: tier,
                    message_type: messageType
                })
            }
        );

        const kickoff = await response.json();

        if (kickoff.run_id) {
            // Start SSE streaming to show real-time logs
            startOutreachLogStreaming(kickoff.run_id, messageType);
        } else {
            throw new Error(kickoff.error || kickoff.detail || 'Failed to start generation');
        }
    } catch (error) {
        showToast(`Failed to generate: ${error.message}`, 'error');
        isOutreachGenerating = false;
        enableOutreachButtons();

        // Restore button
        if (buttonElement && buttonElement.dataset.originalContent) {
            buttonElement.innerHTML = buttonElement.dataset.originalContent;
        }
    }
}

async function copyFirecrawlPrompt() {
    const jobId = getJobId();
    try {
        const response = await fetch(`/api/jobs/${jobId}/contacts/prompt`);
        const result = await response.json();

        if (result.success) {
            await copyToClipboard(result.prompt, 'FireCrawl prompt');
        } else {
            showToast(result.error || 'Failed to generate prompt', 'error');
        }
    } catch (err) {
        showToast('Failed to copy prompt: ' + err.message, 'error');
    }
}

/**
 * Copy text to clipboard and show a toast notification.
 * Used for copying existing outreach messages.
 *
 * @param {string} text - The text to copy
 * @param {string} label - Label for the toast message (e.g., "Connection request")
 */
async function copyToClipboard(text, label = 'Text', buttonElement = null) {
    // Defensive null/undefined handling
    if (text === null || text === undefined || text === '') {
        showToast(`No ${label} content to copy`, 'error');
        return;
    }

    // Ensure text is a string
    const textStr = String(text);

    try {
        // Primary method: Clipboard API (requires secure context - HTTPS or localhost)
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(textStr);
        } else {
            // Fallback: execCommand for non-secure contexts (HTTP on non-localhost)
            // This is deprecated but still works in all browsers
            const textArea = document.createElement('textarea');
            textArea.value = textStr;
            // Prevent scrolling to bottom of page
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            const success = document.execCommand('copy');
            document.body.removeChild(textArea);
            if (!success) {
                throw new Error('Copy command failed');
            }
        }
        showToast(`${label} copied to clipboard!`, 'success');

        // Provide visual feedback on the button if available
        if (buttonElement) {
            const originalHTML = buttonElement.innerHTML;
            buttonElement.innerHTML = '<svg class="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>Copied!';
            buttonElement.classList.add('text-green-600');
            setTimeout(() => {
                buttonElement.innerHTML = originalHTML;
                buttonElement.classList.remove('text-green-600');
            }, 2000);
        }
    } catch (err) {
        console.error('Clipboard copy failed:', err);
        showToast(`Failed to copy ${label}: ${err.message}`, 'error');
    }
}

/**
 * Generate a contact message (InMail or Connection Request) for a specific contact.
 * This is called from the inline buttons on contact cards.
 *
 * @param {string} jobId - The job ID
 * @param {string} contactName - Name of the contact
 * @param {string} contactRole - Role/title of the contact
 * @param {string} messageType - 'inmail' or 'connection'
 */
async function generateContactMessage(jobId, contactName, contactRole, messageType) {
    const messageLabel = messageType === 'connection' ? 'Connection request' : 'InMail';

    showToast(`Generating ${messageLabel} for ${contactName}...`, 'info');

    try {
        const response = await fetch(`/api/jobs/${jobId}/contacts/generate-message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contact_name: contactName,
                contact_role: contactRole,
                message_type: messageType
            })
        });

        const result = await response.json();

        if (result.success && result.message) {
            // Copy to clipboard
            await navigator.clipboard.writeText(result.message);
            showToast(`${messageLabel} copied to clipboard!`, 'success');
        } else {
            showToast(result.error || `Failed to generate ${messageLabel}`, 'error');
        }
    } catch (err) {
        showToast(`Failed to generate ${messageLabel}: ${err.message}`, 'error');
    }
}

function openAddContactsModal() {
    const modal = document.getElementById('add-contacts-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.getElementById('contacts-json-input').value = '';
        document.getElementById('json-input-step').classList.remove('hidden');
        document.getElementById('preview-step').classList.add('hidden');
    }
}

function closeAddContactsModal() {
    const modal = document.getElementById('add-contacts-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

function backToJsonInput() {
    document.getElementById('json-input-step').classList.remove('hidden');
    document.getElementById('preview-step').classList.add('hidden');
}

function validateContactSchema(contact) {
    const required = ['name', 'role', 'linkedin_url'];
    const missing = required.filter(field => !contact[field] && !contact[`contact_${field}`]);
    return missing.length === 0;
}

function validateAndPreviewContacts() {
    const input = document.getElementById('contacts-json-input').value.trim();
    let contacts;

    try {
        contacts = JSON.parse(input);
        if (!Array.isArray(contacts)) {
            contacts = [contacts];
        }
    } catch (e) {
        showToast('Invalid JSON format', 'error');
        return;
    }

    validatedContacts = contacts.filter(c => validateContactSchema(c));

    if (validatedContacts.length === 0) {
        showToast('No valid contacts found. Required: name, role, linkedin_url', 'error');
        return;
    }

    displayPreview(validatedContacts);
    document.getElementById('json-input-step').classList.add('hidden');
    document.getElementById('preview-step').classList.remove('hidden');
}

function displayPreview(contacts) {
    const previewList = document.getElementById('contacts-preview-list');
    previewList.innerHTML = contacts.map((c, i) => `
        <div class="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg">
            <div class="font-medium">${escapeHtml(c.name || c.contact_name)}</div>
            <div class="text-sm text-gray-600 dark:text-gray-400">${escapeHtml(c.role || c.contact_role)}</div>
            <a href="${escapeHtml(c.linkedin_url)}" target="_blank" class="text-indigo-600 dark:text-indigo-400 hover:underline truncate block max-w-[200px]">
                ${escapeHtml(c.linkedin_url)}
            </a>
        </div>
    `).join('');

    document.getElementById('contacts-preview-count').textContent = `${contacts.length} contact(s) ready to import`;
}

async function importContacts() {
    const jobId = getJobId();
    if (validatedContacts.length === 0) {
        showToast('No contacts to import', 'error');
        return;
    }

    const contactType = document.getElementById('contact-type-select').value;
    const importBtn = document.getElementById('import-btn');
    importBtn.disabled = true;
    importBtn.textContent = 'Importing...';

    try {
        const response = await fetch(`/api/jobs/${jobId}/contacts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                contacts: validatedContacts,
                contact_type: contactType
            })
        });

        const result = await response.json();

        if (result.success) {
            showToast(`Imported ${result.importedCount} contacts`, 'success');
            closeAddContactsModal();
            setTimeout(() => location.reload(), 500);
        } else {
            showToast(result.error || 'Import failed', 'error');
        }
    } catch (err) {
        showToast('Import failed: ' + err.message, 'error');
    } finally {
        importBtn.disabled = false;
        importBtn.textContent = 'Import Contacts';
    }
}

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const runId = urlParams.get('run_id');
    if (runId) {
        monitorPipeline(runId);
    }

    // Initialize Planned Answers
    initPlannedAnswers();
});

// ============================================================================
// UI Refresh Event Handler (for CLI Panel integration)
// ============================================================================

/**
 * Handle UI refresh events dispatched by the CLI panel after pipeline completion.
 * This replaces the old page reload behavior with targeted section refresh.
 *
 * For now, this triggers a full page reload as a fallback until proper
 * partial endpoints are implemented in Phase 4.
 *
 * Event detail: { jobId: string, sections: string[] }
 * Expected sections: 'jd-structured', 'jd-viewer', 'pain-points', 'fit-score',
 *                    'action-buttons', 'company-research', 'role-research',
 *                    'cv-preview', 'outcome-tracker'
 */
window.addEventListener('ui:refresh-job', (event) => {
    const { jobId, sections } = event.detail;
    const currentJobId = getJobId();

    console.log('[UI Refresh] Received refresh event:', { jobId, sections, currentJobId });

    // Only refresh if we're on the same job page
    if (jobId !== currentJobId) {
        console.log('[UI Refresh] Job ID mismatch, skipping refresh');
        return;
    }

    // Note: We use full page reload instead of HTMX partial swap because:
    // 1. The page contains inline scripts with global const/let declarations
    // 2. HTMX innerHTML swap re-executes scripts, causing redeclaration errors
    // 3. CLI panel state is preserved via sessionStorage across reload
    //
    // The 2-second delay allows users to see the completion status in CLI panel

    showToast('Pipeline completed! Refreshing page...', 'success');

    setTimeout(() => {
        window.location.reload();
    }, 2000);
});

// ============================================================================
// Planned Answers Management
// ============================================================================

let plannedAnswersData = [];
let currentEditIndex = -1;

/**
 * Initialize Planned Answers from JOB_DETAIL_CONFIG.
 * Called on DOMContentLoaded.
 */
function initPlannedAnswers() {
    plannedAnswersData = window.JOB_DETAIL_CONFIG?.plannedAnswers || [];
    renderPlannedAnswers();
    updateScrapeGenerateVisibility();
}

/**
 * Update visibility of Scrape & Generate button based on application_url.
 */
function updateScrapeGenerateVisibility() {
    const applicationUrl = window.JOB_DETAIL_CONFIG?.applicationUrl || '';
    const scrapeContainer = document.getElementById('scrape-generate-container');
    const noUrlMessage = document.getElementById('no-app-url-message');

    if (applicationUrl && applicationUrl.trim() !== '') {
        // Application URL is set - show scrape button
        if (scrapeContainer) scrapeContainer.classList.remove('hidden');
        if (noUrlMessage) noUrlMessage.classList.add('hidden');
    } else {
        // No application URL - show message
        if (scrapeContainer) scrapeContainer.classList.add('hidden');
        if (noUrlMessage) noUrlMessage.classList.remove('hidden');
    }
}

/**
 * Render the list of planned answers in the container.
 */
function renderPlannedAnswers() {
    const container = document.getElementById('planned-answers-container');
    if (!container) return;

    if (plannedAnswersData.length === 0) {
        const hasAppUrl = window.JOB_DETAIL_CONFIG?.applicationUrl;
        const message = hasAppUrl
            ? 'No answers yet. Click "Scrape & Generate" or add manually.'
            : 'No answers yet. Set an Application URL to enable scraping, or add manually.';
        container.innerHTML = `<p class="text-xs text-gray-500 dark:text-gray-400 text-center py-4">${message}</p>`;
        return;
    }

    container.innerHTML = plannedAnswersData.map((qa, i) => `
        <div class="planned-answer-item border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition" data-index="${i}">
            <div class="flex justify-between items-start gap-2 mb-2">
                <span class="text-xs font-medium text-gray-700 dark:text-gray-300 flex-1">${escapeHtml(qa.question || '').substring(0, 80)}${(qa.question || '').length > 80 ? '...' : ''}</span>
                <div class="flex gap-1 flex-shrink-0">
                    <button onclick="copyPlannedAnswer(${i})" class="p-1 text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition" title="Copy answer">
                        <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/>
                        </svg>
                    </button>
                    <button onclick="editPlannedAnswer(${i})" class="p-1 text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition" title="Edit">
                        <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"/>
                        </svg>
                    </button>
                    <button onclick="deletePlannedAnswer(${i})" class="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition" title="Delete">
                        <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                        </svg>
                    </button>
                </div>
            </div>
            <p class="text-xs text-gray-600 dark:text-gray-400 line-clamp-2">${escapeHtml(qa.answer || '')}</p>
            <span class="inline-block mt-2 px-2 py-0.5 text-[10px] bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded">${qa.field_type || 'textarea'}</span>
        </div>
    `).join('');
}

/**
 * Copy a planned answer to clipboard.
 */
async function copyPlannedAnswer(index) {
    const qa = plannedAnswersData[index];
    if (!qa || !qa.answer) return;

    try {
        await navigator.clipboard.writeText(qa.answer);
        // Show visual feedback
        const btn = document.querySelector(`[data-index="${index}"] button[onclick*="copyPlannedAnswer"]`);
        if (btn) {
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '<svg class="h-3.5 w-3.5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>';
            setTimeout(() => { btn.innerHTML = originalHTML; }, 1500);
        }
        showToast('Answer copied to clipboard');
    } catch (err) {
        showToast('Failed to copy', 'error');
    }
}

/**
 * Open the modal to edit an existing answer.
 */
function editPlannedAnswer(index) {
    currentEditIndex = index;
    const qa = plannedAnswersData[index];

    document.getElementById('pa-modal-title').textContent = 'Edit Answer';
    document.getElementById('pa-question').value = qa.question || '';
    document.getElementById('pa-field-type').value = qa.field_type || 'textarea';
    document.getElementById('pa-answer').value = qa.answer || '';

    document.getElementById('planned-answer-modal').classList.remove('hidden');
}

/**
 * Open the modal to add a new answer.
 */
function addPlannedAnswer() {
    currentEditIndex = -1;

    document.getElementById('pa-modal-title').textContent = 'Add Answer';
    document.getElementById('pa-question').value = '';
    document.getElementById('pa-field-type').value = 'textarea';
    document.getElementById('pa-answer').value = '';

    document.getElementById('planned-answer-modal').classList.remove('hidden');
}

/**
 * Save the planned answer (add or update).
 */
async function savePlannedAnswer() {
    const question = document.getElementById('pa-question').value.trim();
    const answer = document.getElementById('pa-answer').value.trim();
    const fieldType = document.getElementById('pa-field-type').value;

    if (!question || !answer) {
        showToast('Question and answer are required', 'error');
        return;
    }

    const qa = {
        question: question,
        answer: answer,
        field_type: fieldType,
        source: 'manual'
    };

    if (currentEditIndex >= 0) {
        plannedAnswersData[currentEditIndex] = qa;
    } else {
        plannedAnswersData.push(qa);
    }

    await savePlannedAnswersToServer();
    closePlannedAnswerModal();
    renderPlannedAnswers();
}

/**
 * Delete a planned answer.
 */
async function deletePlannedAnswer(index) {
    if (!confirm('Delete this answer?')) return;

    plannedAnswersData.splice(index, 1);
    await savePlannedAnswersToServer();
    renderPlannedAnswers();
}

/**
 * Persist planned answers to the server.
 */
async function savePlannedAnswersToServer() {
    const jobId = getJobId();
    try {
        const response = await fetch(`/api/jobs/${jobId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ planned_answers: plannedAnswersData })
        });

        const result = await response.json();
        if (!result.success) {
            showToast(result.error || 'Save failed', 'error');
        }
    } catch (err) {
        showToast('Save failed: ' + err.message, 'error');
    }
}

/**
 * Close the planned answer modal.
 */
function closePlannedAnswerModal() {
    document.getElementById('planned-answer-modal').classList.add('hidden');
}

// SSE state for form scraping
let formScrapeEventSource = null;
let isFormScraping = false;

/**
 * Scrape application form and generate planned answers using AI.
 * @param {boolean} forceRefresh - If true, bypasses cached form fields
 */
async function scrapeAndGenerateAnswers(forceRefresh = false) {
    if (isFormScraping) {
        showToast('Form scraping already in progress', 'info');
        return;
    }

    const btn = document.getElementById('scrape-generate-btn');
    const forceBtn = document.getElementById('force-refresh-btn');
    const originalHTML = btn.innerHTML;

    // Update button states
    isFormScraping = true;
    btn.disabled = true;
    forceBtn.disabled = true;
    forceBtn.classList.add('opacity-50', 'cursor-not-allowed');
    btn.innerHTML = `
        <svg class="h-3 w-3 mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25"></circle>
            <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" class="opacity-75"></path>
        </svg>
        Scraping...
    `;

    const jobId = getJobId();

    try {
        // Step 1: POST to start the scraping operation
        const response = await fetch(`/api/runner/jobs/${jobId}/scrape-form-answers/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tier: 'balanced',
                force_refresh: forceRefresh
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }

        const data = await response.json();
        const runId = data.run_id;

        if (!runId) {
            throw new Error('No run_id returned from streaming endpoint');
        }

        console.log(`[scrape-form-answers] Started with run_id: ${runId}`);
        showToast('Scraping application form...', 'info');

        // Step 2: Connect to SSE stream for real-time updates
        await connectToFormScrapeSSE(runId, btn, forceBtn, originalHTML);

    } catch (err) {
        console.error('Form scrape error:', err);
        handleFormScrapeError(err.message);
        resetFormScrapeButtons(btn, forceBtn, originalHTML);
    }
}

/**
 * Connect to SSE stream for form scraping progress.
 */
function connectToFormScrapeSSE(runId, btn, forceBtn, originalBtnHTML) {
    return new Promise((resolve) => {
        const logStreamUrl = `/api/runner/operations/${runId}/logs`;
        console.log(`[scrape-form-answers] Creating EventSource for: ${logStreamUrl}`);

        try {
            formScrapeEventSource = new EventSource(logStreamUrl);
        } catch (e) {
            console.error('[scrape-form-answers] Failed to create EventSource:', e);
            handleFormScrapeError('Failed to connect to streaming endpoint');
            resetFormScrapeButtons(btn, forceBtn, originalBtnHTML);
            resolve({ success: false });
            return;
        }

        formScrapeEventSource.onopen = () => {
            console.log('[scrape-form-answers] SSE connection opened');
        };

        // Handle regular log messages
        formScrapeEventSource.onmessage = (event) => {
            console.log(`[scrape-form-answers] Log: ${event.data}`);
            // Could append to a log panel if desired
        };

        // Handle result event (contains the generated answers)
        formScrapeEventSource.addEventListener('result', (event) => {
            try {
                const result = JSON.parse(event.data);
                console.log('[scrape-form-answers] Result received:', result);

                if (result.success && result.planned_answers) {
                    // Update local data and re-render
                    plannedAnswersData = result.planned_answers;
                    renderPlannedAnswers();
                    showToast(`Generated ${result.planned_answers.length} answers!`, 'success');
                } else if (result.error) {
                    handleFormScrapeError(result.error);
                }
            } catch (e) {
                console.error('[scrape-form-answers] Failed to parse result:', e);
            }
        });

        // Handle end event
        formScrapeEventSource.addEventListener('end', (event) => {
            console.log('[scrape-form-answers] Stream ended:', event.data);
            closeFormScrapeSSE();
            resetFormScrapeButtons(btn, forceBtn, originalBtnHTML);

            if (event.data === 'completed') {
                // Reload to get fresh data from server
                window.location.reload();
            }
            resolve({ success: true });
        });

        // Handle error event from server
        formScrapeEventSource.addEventListener('error', (event) => {
            console.error('[scrape-form-answers] SSE error event:', event);

            // Check if this is a server-sent error with data
            if (event.data) {
                try {
                    const errorData = JSON.parse(event.data);
                    handleFormScrapeError(errorData.error || 'Unknown error');
                } catch {
                    handleFormScrapeError('Connection error');
                }
            }

            closeFormScrapeSSE();
            resetFormScrapeButtons(btn, forceBtn, originalBtnHTML);
            resolve({ success: false });
        });

        // Handle connection errors
        formScrapeEventSource.onerror = (err) => {
            console.error('[scrape-form-answers] SSE connection error:', err);
            // Don't close immediately - the error event listener handles cleanup
        };
    });
}

/**
 * Close SSE connection for form scraping.
 */
function closeFormScrapeSSE() {
    if (formScrapeEventSource) {
        formScrapeEventSource.close();
        formScrapeEventSource = null;
    }
    isFormScraping = false;
}

/**
 * Handle form scrape errors with user-friendly messages.
 */
function handleFormScrapeError(errorMessage) {
    const lowerError = (errorMessage || '').toLowerCase();

    if (lowerError.includes('login') || lowerError.includes('auth') || lowerError.includes('blocked') || lowerError.includes('403')) {
        showToast('Could not access the application form. The page may require login. Please manually add your questions.', 'error');
    } else if (lowerError.includes('no form') || lowerError.includes('no field') || lowerError.includes('not found')) {
        showToast('No form fields found. Please verify the URL points to an application form.', 'error');
    } else if (lowerError.includes('timeout')) {
        showToast('Request timed out. The application form may be loading slowly. Please try again.', 'error');
    } else {
        showToast(`Form scraping failed: ${errorMessage}. You can manually add questions below.`, 'error');
    }
}

/**
 * Reset form scrape buttons to their original state.
 */
function resetFormScrapeButtons(btn, forceBtn, originalHTML) {
    isFormScraping = false;
    if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHTML;
    }
    if (forceBtn) {
        forceBtn.disabled = false;
        forceBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }
}

// ============================================================================
// Global Exports (for inline onclick handlers)
// ============================================================================

window.showToast = showToast;
window.updateJobField = updateJobField;
window.saveRemarks = saveRemarks;
window.deleteJob = deleteJob;
window.toggleRawData = toggleRawData;
window.toggleJobDescription = toggleJobDescription;
window.toggleJobViewer = toggleJobViewer;
window.exportPagePDF = exportPagePDF;
window.exportDossierPDF = exportDossierPDF;
window.copyMetaPrompt = copyMetaPrompt;
window.setupIframeHandlers = setupIframeHandlers;
window.enableEdit = enableEdit;
window.saveFieldEdit = saveFieldEdit;
window.cancelFieldEdit = cancelFieldEdit;
window.enableScoreEditDetail = enableScoreEditDetail;
window.handleScoreKeydownDetail = handleScoreKeydownDetail;
window.cancelScoreEditDetail = cancelScoreEditDetail;
window.saveScoreDetail = saveScoreDetail;
window.setProcessingTier = setProcessingTier;
window.processJobDetail = processJobDetail;
window.monitorPipeline = monitorPipeline;
window.toggleLogsFull = toggleLogsFull;
window.copyLogsToClipboard = copyLogsToClipboard;
window.exportCVFromDetailPage = exportCVFromDetailPage;
window.toggleCoverLetterEdit = toggleCoverLetterEdit;
window.saveCoverLetterChanges = saveCoverLetterChanges;
window.generateCoverLetterPDF = generateCoverLetterPDF;
// Cover Letter Main Section
window.copyCoverLetter = copyCoverLetter;
window.toggleCoverLetterEditMain = toggleCoverLetterEditMain;
window.saveCoverLetterChangesMain = saveCoverLetterChangesMain;
window.deleteContact = deleteContact;
window.generateOutreach = generateOutreach;
window.startOutreachLogStreaming = startOutreachLogStreaming;
window.disableOutreachButtons = disableOutreachButtons;
window.enableOutreachButtons = enableOutreachButtons;
window.generateContactMessage = generateContactMessage;
window.copyToClipboard = copyToClipboard;
window.copyFirecrawlPrompt = copyFirecrawlPrompt;
window.openAddContactsModal = openAddContactsModal;
window.closeAddContactsModal = closeAddContactsModal;
window.backToJsonInput = backToJsonInput;
window.validateAndPreviewContacts = validateAndPreviewContacts;
window.importContacts = importContacts;
// Planned Answers
window.initPlannedAnswers = initPlannedAnswers;
window.updateScrapeGenerateVisibility = updateScrapeGenerateVisibility;
window.copyPlannedAnswer = copyPlannedAnswer;
window.editPlannedAnswer = editPlannedAnswer;
window.addPlannedAnswer = addPlannedAnswer;
window.savePlannedAnswer = savePlannedAnswer;
window.deletePlannedAnswer = deletePlannedAnswer;
window.closePlannedAnswerModal = closePlannedAnswerModal;
window.scrapeAndGenerateAnswers = scrapeAndGenerateAnswers;
