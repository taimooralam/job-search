/**
 * CLI Panel - Global Pipeline Console
 *
 * A persistent, AWS/GCP-style console bar at the bottom of every page.
 * Manages pipeline run logs, layer status, and multi-run tabs.
 *
 * Architecture:
 * - Alpine.js store for reactive state
 * - Custom events for loose coupling with pipeline-actions.js
 * - sessionStorage for persistence across navigation
 */

/* ============================================================================
   Constants
   ============================================================================ */

const CLI_STORAGE_KEY = 'cli_state';
const MAX_RUNS = 10;
const MAX_LOGS_PER_RUN = 500;
const SAVE_DEBOUNCE_MS = 2000;

/* ============================================================================
   Alpine Store
   ============================================================================ */

document.addEventListener('alpine:init', () => {
    Alpine.store('cli', {
        // State
        expanded: false,
        activeRunId: null,
        runs: {},
        runOrder: [], // Newest first

        // Context menu state
        contextMenu: {
            visible: false,
            x: 0,
            y: 0,
            targetRunId: null
        },

        // Internal
        _saveTimeout: null,
        _initialized: false,

        /**
         * Initialize the CLI store - restore from sessionStorage
         */
        init() {
            if (this._initialized) return;
            this._initialized = true;

            // Restore state from sessionStorage
            try {
                const saved = sessionStorage.getItem(CLI_STORAGE_KEY);
                if (saved) {
                    const state = JSON.parse(saved);
                    this.expanded = state.expanded || false;
                    this.activeRunId = state.activeRunId || null;
                    this.runs = state.runs || {};
                    this.runOrder = state.runOrder || [];

                    // Validate activeRunId still exists
                    if (this.activeRunId && !this.runs[this.activeRunId]) {
                        this.activeRunId = this.runOrder[0] || null;
                    }

                    console.log('[CLI] Restored state:', {
                        runs: this.runOrder.length,
                        activeRunId: this.activeRunId
                    });
                }
            } catch (e) {
                console.error('[CLI] Failed to restore state:', e);
            }

            // Set up event listeners
            this._setupEventListeners();

            // Keyboard shortcut: Ctrl+` to toggle
            document.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === '`') {
                    e.preventDefault();
                    this.toggle();
                }
            });

            console.log('[CLI] Initialized');
        },

        /**
         * Set up custom event listeners for pipeline communication
         */
        _setupEventListeners() {
            // Start a new pipeline run
            window.addEventListener('cli:start-run', (e) => {
                this.startRun(e.detail);
            });

            // Append a log line
            window.addEventListener('cli:log', (e) => {
                this.appendLog(e.detail);
            });

            // Update layer status
            window.addEventListener('cli:layer-status', (e) => {
                this.updateLayerStatus(e.detail);
            });

            // Pipeline completed
            window.addEventListener('cli:complete', (e) => {
                this.completeRun(e.detail);
            });

            // Queue events for integration with WebSocket queue
            window.addEventListener('queue:job-started', (e) => {
                this._handleQueueJobStarted(e.detail);
            });

            window.addEventListener('queue:job-completed', (e) => {
                this._handleQueueJobCompleted(e.detail);
            });

            window.addEventListener('queue:job-failed', (e) => {
                this._handleQueueJobFailed(e.detail);
            });
        },

        /**
         * Handle queue job started event - transition from queued to running
         */
        _handleQueueJobStarted(detail) {
            const { jobId, runId } = detail;

            // Check if we have a queued tab for this job
            const queuedRunId = `queued_${jobId}`;
            if (this.runs[queuedRunId]) {
                // Remove the queued tab
                delete this.runs[queuedRunId];
                const idx = this.runOrder.indexOf(queuedRunId);
                if (idx > -1) {
                    this.runOrder.splice(idx, 1);
                }

                // If it was active, we'll switch to the new run
                if (this.activeRunId === queuedRunId) {
                    this.activeRunId = null;
                }
            }

            // The actual run tab will be created by the SSE/pipeline system
            // We just need to make sure the panel is open
            if (runId) {
                this.expanded = true;
            }
        },

        /**
         * Handle queue job completed event
         */
        _handleQueueJobCompleted(detail) {
            const { jobId } = detail;

            // Check if we have a queued tab for this job
            const queuedRunId = `queued_${jobId}`;
            if (this.runs[queuedRunId]) {
                // Update status
                this.runs[queuedRunId].status = 'success';
                this.runs[queuedRunId].completedAt = Date.now();
                this._saveStateImmediate();
            }
        },

        /**
         * Handle queue job failed event
         */
        _handleQueueJobFailed(detail) {
            const { jobId, error } = detail;

            // Check if we have a queued tab for this job
            const queuedRunId = `queued_${jobId}`;
            if (this.runs[queuedRunId]) {
                // Update status
                this.runs[queuedRunId].status = 'error';
                this.runs[queuedRunId].error = error;
                this.runs[queuedRunId].completedAt = Date.now();
                this._saveStateImmediate();
            }
        },

        /**
         * Toggle panel expanded/collapsed
         */
        toggle() {
            this.expanded = !this.expanded;
            this._saveState();
        },

        /**
         * Show the panel (expand it)
         */
        showPanel() {
            this.expanded = true;
            this._saveState();
        },

        /**
         * Add or switch to a tab for a job
         * Used by live status badges and queue page
         * @param {string} jobId - The job ID
         * @param {string} runId - Optional run ID if the job is running
         */
        addTab(jobId, runId = null) {
            // If we have a run ID, check if that tab exists
            if (runId && this.runs[runId]) {
                this.activeRunId = runId;
                this.expanded = true;
                this._saveState();
                return;
            }

            // Check for queued tab
            const queuedRunId = `queued_${jobId}`;
            if (this.runs[queuedRunId]) {
                this.activeRunId = queuedRunId;
                this.expanded = true;
                this._saveState();
                return;
            }

            // Get queue info from store
            let jobTitle = 'Unknown Job';
            let position = null;
            let status = 'queued';

            if (window.Alpine && Alpine.store('queue')) {
                const queueItem = Alpine.store('queue').getItemByJobId(jobId);
                if (queueItem) {
                    jobTitle = queueItem.job_title || jobTitle;
                    position = Alpine.store('queue').getPosition(jobId);

                    if (queueItem.queueStatus === 'running') {
                        status = 'running';
                    } else if (queueItem.queueStatus === 'failed') {
                        status = 'error';
                    }
                }
            }

            // Create a queued tab
            this.runs[queuedRunId] = {
                jobId,
                jobTitle: this._truncateTitle(jobTitle),
                action: 'queued',
                status,
                logs: [{
                    ts: Date.now(),
                    type: 'info',
                    text: position
                        ? `Waiting in queue (position #${position})...`
                        : `Waiting for pipeline to start...`
                }],
                layerStatus: {},
                startedAt: Date.now(),
                completedAt: null,
                queuePosition: position
            };

            // Add to front of run order
            this.runOrder.unshift(queuedRunId);

            // Switch to new tab
            this.activeRunId = queuedRunId;
            this.expanded = true;

            // Cleanup old runs
            this._cleanup();

            // Save immediately
            this._saveStateImmediate();
        },

        /**
         * Start a new pipeline run
         * @param {Object} detail - { runId, jobId, jobTitle, action }
         */
        startRun(detail) {
            const { runId, jobId, jobTitle, action } = detail;

            console.log('[CLI] Starting run:', { runId, jobId, jobTitle, action });

            // Create run entry
            this.runs[runId] = {
                jobId,
                jobTitle: this._truncateTitle(jobTitle),
                action,
                status: 'running',
                logs: [],
                layerStatus: {},
                startedAt: Date.now(),
                completedAt: null
            };

            // Add to front of run order
            this.runOrder.unshift(runId);

            // Switch to new run
            this.activeRunId = runId;

            // Expand panel to show logs
            this.expanded = true;

            // Cleanup old runs
            this._cleanup();

            // Save immediately
            this._saveStateImmediate();
        },

        /**
         * Append a log line to a run
         * @param {Object} detail - { runId, text, logType }
         */
        appendLog(detail) {
            const { runId, text, logType = 'info' } = detail;

            if (!this.runs[runId]) {
                console.warn('[CLI] Unknown runId:', runId);
                return;
            }

            // Add log entry
            this.runs[runId].logs.push({
                ts: Date.now(),
                type: logType,
                text
            });

            // Trim if too many logs
            if (this.runs[runId].logs.length > MAX_LOGS_PER_RUN) {
                this.runs[runId].logs = this.runs[runId].logs.slice(-MAX_LOGS_PER_RUN);
            }

            // Debounced save
            this._saveState();

            // Auto-scroll if at bottom
            this._autoScroll();
        },

        /**
         * Update layer status for a run
         * @param {Object} detail - { runId, layerStatus }
         */
        updateLayerStatus(detail) {
            const { runId, layerStatus } = detail;

            if (!this.runs[runId]) {
                console.warn('[CLI] Unknown runId for layer status:', runId);
                return;
            }

            // Merge layer status
            this.runs[runId].layerStatus = {
                ...this.runs[runId].layerStatus,
                ...layerStatus
            };

            // Debounced save
            this._saveState();
        },

        /**
         * Mark a run as complete
         * @param {Object} detail - { runId, status, result, error }
         */
        completeRun(detail) {
            const { runId, status, result, error } = detail;

            if (!this.runs[runId]) {
                console.warn('[CLI] Unknown runId for completion:', runId);
                return;
            }

            this.runs[runId].status = status; // 'success' or 'error'
            this.runs[runId].completedAt = Date.now();

            if (error) {
                this.runs[runId].error = error;
            }

            console.log('[CLI] Run completed:', { runId, status });

            // Show toast if panel is collapsed
            if (!this.expanded && typeof showToast === 'function') {
                const jobTitle = this.runs[runId].jobTitle;
                if (status === 'success') {
                    showToast(`Pipeline completed: ${jobTitle}`, 'success');
                } else {
                    showToast(`Pipeline failed: ${jobTitle}`, 'error');
                }
            }

            // Save immediately
            this._saveStateImmediate();
        },

        /**
         * Switch to a different run tab
         */
        switchToRun(runId) {
            if (this.runs[runId]) {
                this.activeRunId = runId;
                this._saveState();
            }
        },

        /**
         * Close a run tab
         */
        closeRun(runId) {
            // Remove from runs
            delete this.runs[runId];

            // Remove from order
            const idx = this.runOrder.indexOf(runId);
            if (idx > -1) {
                this.runOrder.splice(idx, 1);
            }

            // If we closed the active run, switch to another
            if (this.activeRunId === runId) {
                this.activeRunId = this.runOrder[0] || null;
            }

            this._saveStateImmediate();
        },

        /**
         * Show context menu for a tab
         * @param {MouseEvent} event - The contextmenu event
         * @param {string} runId - The run ID for the tab
         */
        showTabContextMenu(event, runId) {
            // Position menu at click location, but ensure it stays on screen
            const menuWidth = 180;
            const menuHeight = 160;
            let x = event.clientX;
            let y = event.clientY;

            // Adjust if would go off right edge
            if (x + menuWidth > window.innerWidth) {
                x = window.innerWidth - menuWidth - 10;
            }

            // Adjust if would go off bottom (since panel is at bottom)
            if (y + menuHeight > window.innerHeight) {
                y = y - menuHeight;
            }

            this.contextMenu = {
                visible: true,
                x,
                y,
                targetRunId: runId
            };
        },

        /**
         * Hide the context menu
         */
        hideContextMenu() {
            this.contextMenu.visible = false;
            this.contextMenu.targetRunId = null;
        },

        /**
         * Close the tab that was right-clicked
         */
        closeContextMenuTab() {
            if (this.contextMenu.targetRunId) {
                this.closeRun(this.contextMenu.targetRunId);
            }
            this.hideContextMenu();
        },

        /**
         * Close all tabs except the one that was right-clicked
         */
        closeOtherTabs() {
            const keepRunId = this.contextMenu.targetRunId;
            if (!keepRunId) {
                this.hideContextMenu();
                return;
            }

            // Get all run IDs except the target
            const toClose = this.runOrder.filter(id => id !== keepRunId);

            // Close each one
            for (const runId of toClose) {
                delete this.runs[runId];
            }

            // Update order to only contain the kept run
            this.runOrder = [keepRunId];
            this.activeRunId = keepRunId;

            this._saveStateImmediate();
            this.hideContextMenu();
        },

        /**
         * Close all tabs that have completed (success or error)
         */
        closeCompletedTabs() {
            const toClose = this.runOrder.filter(id =>
                this.runs[id]?.status === 'success' || this.runs[id]?.status === 'error'
            );

            for (const runId of toClose) {
                delete this.runs[runId];
                const idx = this.runOrder.indexOf(runId);
                if (idx > -1) {
                    this.runOrder.splice(idx, 1);
                }
            }

            // If active run was closed, switch to another
            if (!this.runs[this.activeRunId]) {
                this.activeRunId = this.runOrder[0] || null;
            }

            this._saveStateImmediate();
            this.hideContextMenu();

            if (typeof showToast === 'function' && toClose.length > 0) {
                showToast(`Closed ${toClose.length} completed tab${toClose.length > 1 ? 's' : ''}`, 'success');
            }
        },

        /**
         * Close all tabs
         */
        closeAllTabs() {
            const count = this.runOrder.length;

            this.runs = {};
            this.runOrder = [];
            this.activeRunId = null;

            this._saveStateImmediate();
            this.hideContextMenu();

            if (typeof showToast === 'function' && count > 0) {
                showToast(`Closed ${count} tab${count > 1 ? 's' : ''}`, 'success');
            }
        },

        /**
         * Clear logs for current run
         */
        clearCurrentLogs() {
            if (this.activeRunId && this.runs[this.activeRunId]) {
                this.runs[this.activeRunId].logs = [];
                this._saveStateImmediate();
            }
        },

        /**
         * Copy logs to clipboard
         */
        async copyLogs() {
            if (!this.activeRunId || !this.runs[this.activeRunId]) return;

            const logs = this.runs[this.activeRunId].logs
                .map(log => `[${log.type.toUpperCase()}] ${log.text}`)
                .join('\n');

            try {
                await navigator.clipboard.writeText(logs);
                if (typeof showToast === 'function') {
                    showToast('Logs copied to clipboard', 'success');
                }
            } catch (e) {
                console.error('[CLI] Failed to copy logs:', e);
                if (typeof showToast === 'function') {
                    showToast('Failed to copy logs', 'error');
                }
            }
        },

        /**
         * Check if any run is currently in progress
         */
        hasRunningPipeline() {
            return Object.values(this.runs).some(run => run.status === 'running');
        },

        /**
         * Get the title of the active or running run
         */
        getActiveRunTitle() {
            const runningRun = Object.values(this.runs).find(run => run.status === 'running');
            if (runningRun) return runningRun.jobTitle;
            if (this.activeRunId && this.runs[this.activeRunId]) {
                return this.runs[this.activeRunId].jobTitle;
            }
            return '';
        },

        /**
         * Get layer status for active run
         */
        getActiveLayerStatus() {
            if (this.activeRunId && this.runs[this.activeRunId]) {
                return this.runs[this.activeRunId].layerStatus || {};
            }
            return {};
        },

        /**
         * Truncate job title for tab display
         */
        _truncateTitle(title, maxLen = 25) {
            if (!title) return 'Unknown';
            if (title.length <= maxLen) return title;
            return title.substring(0, maxLen - 3) + '...';
        },

        /**
         * Auto-scroll logs to bottom if user is at bottom
         */
        _autoScroll() {
            // Use requestAnimationFrame to ensure DOM is updated
            requestAnimationFrame(() => {
                const logsContainer = document.querySelector('.cli-logs');
                if (logsContainer) {
                    const isAtBottom = logsContainer.scrollHeight - logsContainer.scrollTop <= logsContainer.clientHeight + 50;
                    if (isAtBottom) {
                        logsContainer.scrollTop = logsContainer.scrollHeight;
                    }
                }
            });
        },

        /**
         * Cleanup old runs to stay within limits
         */
        _cleanup() {
            // Remove excess runs (keep MAX_RUNS)
            while (this.runOrder.length > MAX_RUNS) {
                const oldestRunId = this.runOrder.pop();
                delete this.runs[oldestRunId];
            }
        },

        /**
         * Save state to sessionStorage (debounced)
         */
        _saveState() {
            if (this._saveTimeout) {
                clearTimeout(this._saveTimeout);
            }

            this._saveTimeout = setTimeout(() => {
                this._saveStateImmediate();
            }, SAVE_DEBOUNCE_MS);
        },

        /**
         * Save state to sessionStorage immediately
         */
        _saveStateImmediate() {
            try {
                const state = {
                    expanded: this.expanded,
                    activeRunId: this.activeRunId,
                    runs: this.runs,
                    runOrder: this.runOrder
                };

                sessionStorage.setItem(CLI_STORAGE_KEY, JSON.stringify(state));
            } catch (e) {
                console.error('[CLI] Failed to save state:', e);

                // If quota exceeded, try to clear old runs
                if (e.name === 'QuotaExceededError') {
                    this._cleanup();
                    // Trim logs more aggressively
                    for (const runId of this.runOrder) {
                        if (this.runs[runId]?.logs.length > 100) {
                            this.runs[runId].logs = this.runs[runId].logs.slice(-100);
                        }
                    }
                }
            }
        }
    });
});

/* ============================================================================
   Global Helper Functions
   ============================================================================ */

/**
 * Dispatch a CLI event (for use by pipeline-actions.js)
 */
window.cliDispatch = function(eventName, detail) {
    window.dispatchEvent(new CustomEvent(eventName, { detail }));
};

/**
 * Determine log type from log text
 */
window.cliDetectLogType = function(text) {
    if (/\[ERROR\]|error|failed|exception/i.test(text)) return 'error';
    if (/\[WARN\]|warning/i.test(text)) return 'warning';
    if (/\[SUCCESS\]|success|complete|done/i.test(text)) return 'success';
    if (/\[DEBUG\]/i.test(text)) return 'debug';
    return 'info';
};

console.log('[CLI Panel] Module loaded');
