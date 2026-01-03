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
 *
 * Debug Mode:
 * - Enable via: localStorage.setItem('cli_debug', 'true') or ?cli_debug=true
 * - Check state: Alpine.store('cli').debugState()
 * - Clear corrupted state: Alpine.store('cli').clearAll()
 */

/* ============================================================================
   Constants
   ============================================================================ */

const CLI_STORAGE_KEY = 'cli_state';
const MAX_RUNS = 10;
const MAX_LOGS_PER_RUN = 500;
const SAVE_DEBOUNCE_MS = 2000;
const PENDING_LOGS_TIMEOUT_MS = 5000; // How long to wait for run to be created before fetching from API

// Debug mode - enabled via localStorage or URL param
const CLI_DEBUG = localStorage.getItem('cli_debug') === 'true' ||
                  window.location.search.includes('cli_debug=true');

/**
 * Debug logging for CLI panel
 */
function cliDebug(...args) {
    if (CLI_DEBUG) {
        console.log('[CLI DEBUG]', new Date().toISOString(), ...args);
    }
}

/**
 * Validate and sanitize runOrder array
 * Removes undefined/null entries, duplicates, and orphaned entries
 * @param {Array} runOrder - The runOrder array to sanitize
 * @param {Object} runs - The runs object to validate against
 * @returns {Array} - Sanitized runOrder array
 */
function sanitizeRunOrder(runOrder, runs) {
    if (!Array.isArray(runOrder)) {
        cliDebug('runOrder is not an array, returning empty', typeof runOrder);
        return [];
    }

    const seen = new Set();
    const sanitized = [];
    const removed = { undefined: 0, null: 0, duplicates: 0, orphaned: 0 };

    for (const runId of runOrder) {
        // Skip undefined
        if (runId === undefined) {
            removed.undefined++;
            continue;
        }
        // Skip null
        if (runId === null) {
            removed.null++;
            continue;
        }
        // Skip duplicates
        if (seen.has(runId)) {
            removed.duplicates++;
            continue;
        }
        // Skip orphaned entries (in runOrder but not in runs)
        if (runs && !runs[runId]) {
            removed.orphaned++;
            cliDebug('Removing orphaned runId:', runId);
            continue;
        }

        seen.add(runId);
        sanitized.push(runId);
    }

    const totalRemoved = removed.undefined + removed.null + removed.duplicates + removed.orphaned;
    if (totalRemoved > 0) {
        console.warn('[CLI] Sanitized runOrder - removed:', removed);
        cliDebug('Sanitization details', {
            originalLength: runOrder.length,
            sanitizedLength: sanitized.length,
            removed
        });
    }

    return sanitized;
}

/**
 * Validate runs object - ensure all entries are valid
 * @param {Object} runs - The runs object to sanitize
 * @returns {Object} - Sanitized runs object
 */
function sanitizeRuns(runs) {
    if (!runs || typeof runs !== 'object') {
        cliDebug('runs is not an object, returning empty', typeof runs);
        return {};
    }

    const sanitized = {};
    let removed = 0;

    for (const [runId, run] of Object.entries(runs)) {
        // Skip invalid entries
        if (!run || typeof run !== 'object') {
            removed++;
            cliDebug('Removing invalid run entry', runId, run);
            continue;
        }

        // Ensure required fields exist with defaults
        sanitized[runId] = {
            jobId: run.jobId || null,
            jobTitle: run.jobTitle || 'Unknown',
            action: run.action || 'unknown',
            status: run.status || 'unknown',
            logs: Array.isArray(run.logs) ? run.logs : [],
            layerStatus: run.layerStatus || {},
            startedAt: run.startedAt || Date.now(),
            completedAt: run.completedAt || null,
            error: run.error || null,
            // Preserve any extra fields
            ...run
        };
    }

    if (removed > 0) {
        console.warn('[CLI] Removed', removed, 'invalid run entries');
    }

    return sanitized;
}

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
        pollingActive: {}, // Track active polling per runId: { runId: true/false }

        // Panel size state (persisted)
        panelSize: 'medium', // 'small', 'medium', 'large', 'xlarge'
        fontSize: 'medium',  // 'small', 'medium', 'large'

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
        _pendingLogs: {}, // Buffer for logs arriving before run exists: { runId: { logs: [], timer: null } }
        _rxjsAvailable: false, // Set in init()
        _rxjsSubjects: null, // RxJS subjects for reactive streams

        /**
         * Initialize the CLI store - restore from sessionStorage
         */
        init() {
            if (this._initialized) return;
            this._initialized = true;

            cliDebug('Initializing CLI store');

            // Restore state from sessionStorage with validation
            try {
                const saved = sessionStorage.getItem(CLI_STORAGE_KEY);
                cliDebug('Raw sessionStorage data:', saved ? `${saved.length} chars` : 'null');

                if (saved) {
                    let state;
                    try {
                        state = JSON.parse(saved);
                    } catch (parseError) {
                        console.error('[CLI] Failed to parse sessionStorage, clearing corrupted data:', parseError);
                        sessionStorage.removeItem(CLI_STORAGE_KEY);
                        this._setupEventListeners();
                        this._setupKeyboardShortcut();
                        console.log('[CLI] Initialized (cleared corrupted state)');
                        return;
                    }

                    cliDebug('Parsed state:', {
                        expanded: state.expanded,
                        activeRunId: state.activeRunId,
                        runsCount: state.runs ? Object.keys(state.runs).length : 0,
                        runOrderLength: state.runOrder ? state.runOrder.length : 0,
                        runOrderRaw: state.runOrder
                    });

                    this.expanded = state.expanded || false;

                    // Restore panel and font size preferences
                    if (state.panelSize && ['small', 'medium', 'large', 'xlarge'].includes(state.panelSize)) {
                        this.panelSize = state.panelSize;
                    }
                    if (state.fontSize && ['small', 'medium', 'large'].includes(state.fontSize)) {
                        this.fontSize = state.fontSize;
                    }

                    // Sanitize runs first (before runOrder validation)
                    const originalRunsCount = state.runs ? Object.keys(state.runs).length : 0;
                    this.runs = sanitizeRuns(state.runs);

                    // Sanitize runOrder - remove undefined, null, duplicates, orphaned
                    const originalRunOrderLength = state.runOrder ? state.runOrder.length : 0;
                    this.runOrder = sanitizeRunOrder(state.runOrder, this.runs);

                    // Validate activeRunId
                    if (state.activeRunId) {
                        if (this.runs[state.activeRunId]) {
                            this.activeRunId = state.activeRunId;
                        } else {
                            cliDebug('activeRunId not found in runs, selecting first', state.activeRunId);
                            this.activeRunId = this.runOrder[0] || null;
                        }
                    } else {
                        this.activeRunId = this.runOrder[0] || null;
                    }

                    console.log('[CLI] Restored state:', {
                        runs: this.runOrder.length,
                        activeRunId: this.activeRunId
                    });

                    // If we had to sanitize, save the clean state immediately
                    if (originalRunOrderLength !== this.runOrder.length ||
                        originalRunsCount !== Object.keys(this.runs).length) {
                        cliDebug('State was sanitized, saving clean version');
                        this._saveStateImmediate();
                    }
                }
            } catch (e) {
                console.error('[CLI] Failed to restore state:', e);
                // Clear corrupted state
                sessionStorage.removeItem(CLI_STORAGE_KEY);
            }

            // Set up event listeners
            this._setupEventListeners();
            this._setupKeyboardShortcut();

            // Initialize RxJS integration
            this._initRxJS();

            // Re-subscribe running operations that lost their poller on page reload
            // This handles the case where user navigates away and returns while ops are running
            const runStatuses = Object.entries(this.runs).map(([id, run]) => ({
                id: id.slice(-8),
                status: run?.status,
                hasPoller: !!run?._logPoller
            }));
            cliDebug('Run statuses on init:', runStatuses);

            for (const [runId, run] of Object.entries(this.runs)) {
                // Re-subscribe if running OR if status is unknown/queued (might still be in progress)
                const needsResubscribe = (
                    run?.status === 'running' ||
                    run?.status === 'queued' ||
                    run?.status === 'pending'
                ) && !run._logPoller;

                if (needsResubscribe) {
                    cliDebug('Re-subscribing after page reload:', runId, 'status:', run?.status);
                    this.subscribeToLogs(runId);
                }
            }

            console.log('[CLI] Initialized', this._rxjsAvailable ? '(with RxJS)' : '(legacy mode)');
        },

        /**
         * Initialize RxJS subjects for reactive log buffering
         * @private
         */
        _initRxJS() {
            this._rxjsAvailable = typeof window.RxUtils !== 'undefined';

            if (!this._rxjsAvailable) {
                cliDebug('RxUtils not available, using legacy pending logs implementation');
                return;
            }

            const { Subject, BehaviorSubject } = window.RxUtils;

            this._rxjsSubjects = {
                runCreated$: new Subject(),  // Emits when a run is created
                destroy$: new Subject(),     // Cleanup signal
                saveState$: new Subject()    // Debounced save trigger
            };

            // Set up debounced save using RxJS
            this._setupDebouncedSaveRxJS();

            cliDebug('RxJS subjects initialized');
        },

        /**
         * Set up debounced save using RxJS debounceTime operator
         * @private
         */
        _setupDebouncedSaveRxJS() {
            if (!this._rxjsAvailable || !this._rxjsSubjects) return;

            const { debounceTime, tap, takeUntil, catchError, EMPTY } = window.RxUtils;

            this._rxjsSubjects.saveState$.pipe(
                debounceTime(SAVE_DEBOUNCE_MS),
                tap(() => {
                    cliDebug('Debounced save triggered (RxJS)');
                    this._saveStateImmediate();
                }),
                takeUntil(this._rxjsSubjects.destroy$),
                catchError(err => {
                    console.error('[CLI] RxJS save error:', err);
                    return EMPTY;
                })
            ).subscribe();
        },

        /**
         * Set up keyboard shortcut (Ctrl+` to toggle)
         */
        _setupKeyboardShortcut() {
            document.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === '`') {
                    e.preventDefault();
                    this.toggle();
                }
            });
        },

        /**
         * Set up custom event listeners for pipeline communication
         */
        _setupEventListeners() {
            // Start a new pipeline run
            window.addEventListener('cli:start-run', (e) => {
                console.log('[CLI] Received cli:start-run event:', e.detail);
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

            // Fetch logs for an existing run (from pipelines panel click)
            window.addEventListener('cli:fetch-logs', (e) => {
                const { runId, jobId, jobTitle, company, action, status } = e.detail;
                if (runId) {
                    cliDebug('Received cli:fetch-logs event', { runId, jobId, jobTitle, company, action, status });
                    this.fetchRunLogs(runId, jobId, jobTitle, company, status);
                }
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

            // Polling state events for visual indicator
            // Dispatched by LogPoller during fetch cycles
            window.addEventListener('poller:poll-start', (e) => {
                const { runId } = e.detail;
                if (runId) {
                    this.pollingActive = { ...this.pollingActive, [runId]: true };
                }
            });

            window.addEventListener('poller:poll-end', (e) => {
                const { runId } = e.detail;
                if (runId) {
                    this.pollingActive = { ...this.pollingActive, [runId]: false };
                }
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
                // If actual run tab already exists from SSE, just remove queued and switch
                if (runId && this.runs[runId]) {
                    delete this.runs[queuedRunId];
                    const idx = this.runOrder.indexOf(queuedRunId);
                    if (idx > -1) {
                        this.runOrder.splice(idx, 1);
                    }
                    if (this.activeRunId === queuedRunId) {
                        this.activeRunId = runId;  // Switch to actual run
                    }
                    // Ensure log subscription for existing run
                    if (!this.runs[runId]._logPoller && this.runs[runId].status === 'running') {
                        console.log('[CLI] Subscribing to logs for existing run:', runId);
                        this.subscribeToLogs(runId);
                    }
                } else if (runId) {
                    // SSE hasn't created the run tab yet - transition queued tab to running
                    const queuedTab = this.runs[queuedRunId];
                    delete this.runs[queuedRunId];

                    // Create run entry with the actual runId, preserving job info from queued tab
                    this.runs[runId] = {
                        jobId: queuedTab.jobId,
                        jobTitle: queuedTab.jobTitle,  // Preserve title from queued tab
                        action: 'pipeline',
                        status: 'running',
                        startedAt: Date.now(),
                        layerStatus: {},
                        logs: [{
                            ts: Date.now(),
                            type: 'info',
                            text: 'Pipeline started...'
                        }]
                    };

                    // Update runOrder - replace queued ID with real run ID
                    const idx = this.runOrder.indexOf(queuedRunId);
                    if (idx > -1) {
                        this.runOrder[idx] = runId;
                    } else {
                        this.runOrder.unshift(runId);
                    }

                    // Switch active if needed
                    if (this.activeRunId === queuedRunId) {
                        this.activeRunId = runId;
                    }

                    this._saveStateImmediate();

                    // Subscribe to logs immediately (even if panel not expanded)
                    console.log('[CLI] Subscribing to logs for newly started run:', runId);
                    this.subscribeToLogs(runId);
                } else {
                    // No runId provided - just remove queued tab (shouldn't normally happen)
                    delete this.runs[queuedRunId];
                    const idx = this.runOrder.indexOf(queuedRunId);
                    if (idx > -1) {
                        this.runOrder.splice(idx, 1);
                    }
                    if (this.activeRunId === queuedRunId) {
                        this.activeRunId = null;
                    }
                }
            }
            // Note: Don't auto-expand panel - user should open it on demand
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

            // When expanding, ensure ALL running operations are polling
            // This handles cases where polling was missed (e.g., page refresh during batch ops)
            if (this.expanded) {
                for (const [runId, run] of Object.entries(this.runs)) {
                    if (run?.status === 'running' && !run._logPoller) {
                        this.subscribeToLogs(runId);
                    }
                }
            }
        },

        /**
         * Show the panel (expand it)
         */
        showPanel() {
            this.expanded = true;
            this._saveState();

            // When showing panel, ensure ALL running operations are polling
            // This handles cases where polling was missed (e.g., page refresh during batch ops)
            for (const [runId, run] of Object.entries(this.runs)) {
                if (run?.status === 'running' && !run._logPoller) {
                    this.subscribeToLogs(runId);
                }
            }
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
         * Fetch and add run logs from runner API (on-demand)
         * Used when clicking indicator for a run whose logs aren't in memory
         * @param {string} runId - The run ID
         * @param {string} jobId - The job ID
         * @param {string} jobTitle - Optional job title
         * @param {string} company - Optional company name
         * @param {string} opStatus - Optional operation status ('pending', 'running', 'completed', 'failed')
         * @returns {Promise<boolean>} - True if logs were fetched successfully
         */
        async fetchRunLogs(runId, jobId, jobTitle = null, company = null, opStatus = null) {
            // Guard against undefined/null runId
            if (!runId) {
                console.error('[CLI] fetchRunLogs called with undefined/null runId');
                return false;
            }

            // If already in memory with SSE subscription, just switch to it
            if (this.runs[runId]) {
                this.activeRunId = runId;
                this.expanded = true;
                this._saveState();

                // If operation is running but no SSE subscription, start one
                if ((opStatus === 'running' || this.runs[runId].status === 'running') && !this.runs[runId]._logPoller) {
                    this.subscribeToLogs(runId);
                }

                return true;
            }

            try {
                const response = await fetch(`/api/runner/operations/${runId}/status`);

                if (!response.ok) {
                    // Logs no longer available
                    console.warn(`[CLI] Logs not available for run ${runId}: ${response.status}`);
                    this._addUnavailableRunPlaceholder(runId, jobId, jobTitle);
                    return false;
                }

                const data = await response.json();

                // Create run entry from API response
                this.runs[runId] = {
                    jobId,
                    jobTitle: this._truncateTitle(jobTitle || data.job_title || `Job ${jobId?.slice(-6) || 'Unknown'}`),
                    company: company || 'Unknown Company',
                    action: data.operation || 'pipeline',
                    status: data.status === 'completed' ? 'success' : (data.status || 'unknown'),
                    logs: (data.logs || []).map(log => ({
                        ts: Date.now(),
                        type: typeof log === 'string' ? (window.cliDetectLogType?.(log) || 'info') : 'info',
                        text: typeof log === 'string' ? log : log.text || JSON.stringify(log)
                    })),
                    layerStatus: data.layer_status || {},
                    startedAt: data.started_at ? new Date(data.started_at).getTime() : Date.now(),
                    completedAt: data.completed_at ? new Date(data.completed_at).getTime() : null,
                    error: data.error || null,
                    langsmithUrl: data.langsmith_url || null,
                    fromRedis: false,
                    _logPoller: null  // Will be set if we subscribe to log polling
                };

                // Add error log if present
                if (data.error) {
                    this.runs[runId].logs.push({
                        ts: Date.now(),
                        type: 'error',
                        text: `Error: ${data.error}`
                    });
                }

                // Add to front of run order
                this.runOrder.unshift(runId);

                // Switch to the new tab
                this.activeRunId = runId;
                this.expanded = true;

                // Cleanup old runs
                this._cleanup();

                // Save immediately
                this._saveStateImmediate();

                // If operation is running, subscribe to SSE for real-time updates
                if (opStatus === 'running' || data.status === 'running' || data.status === 'queued') {
                    cliDebug(`Operation ${runId} is ${opStatus || data.status}, subscribing to SSE`);
                    this.subscribeToLogs(runId);
                }

                return true;
            } catch (err) {
                console.error('[CLI] Failed to fetch run logs:', err);
                this._addUnavailableRunPlaceholder(runId, jobId, jobTitle);
                return false;
            }
        },

        /**
         * Subscribe to real-time log streaming via HTTP polling (replaces SSE)
         *
         * Uses LogPoller for reliable log fetching that works during long operations.
         * Implements "replay + live tail" pattern: fetches all past logs then polls for new.
         *
         * @param {string} runId - The run ID to subscribe to
         */
        subscribeToLogs(runId) {
            // Guard against undefined/null runId
            if (!runId) {
                console.error('[CLI] subscribeToLogs called with undefined/null runId');
                return;
            }

            // Don't subscribe if run doesn't exist
            if (!this.runs[runId]) {
                console.warn(`[CLI] Cannot subscribe to logs - run ${runId} not found`);
                return;
            }

            // Don't create duplicate subscriptions
            if (this.runs[runId]._logPoller) {
                cliDebug(`Already subscribed to logs for ${runId}`);
                return;
            }

            // Check if LogPoller is available
            if (typeof window.LogPoller === 'undefined') {
                console.error('[CLI] LogPoller not available');
                return;
            }

            cliDebug(`Subscribing to log polling: ${runId}`);
            console.log('[CLI] Creating LogPoller for:', runId);

            try {
                const poller = new window.LogPoller(runId, {
                    pollInterval: 200,  // 200ms for near-instant feel
                    debug: false,
                });
                this.runs[runId]._logPoller = poller;
                console.log('[CLI] LogPoller created for:', runId);

                // Handle each log message
                poller.onLog((log) => {
                    if (!this.runs[runId]) {
                        poller.stop();
                        return;
                    }

                    const text = typeof log.message === 'string'
                        ? log.message
                        : (log.message != null ? JSON.stringify(log.message) : '');
                    const logType = window.cliDetectLogType?.(text) || 'info';

                    // Detect backend from log entry or message text
                    const backend = log.backend || this.detectBackendFromText(text);

                    // Extract tier if present in log
                    const tier = log.tier || null;

                    // Extract cost if present
                    const cost_usd = log.cost_usd || 0;

                    // Build log entry with structured data from backend (if available)
                    const logEntry = {
                        ts: Date.now(),
                        type: logType,
                        text,
                        backend,
                        tier,
                        cost_usd
                    };

                    // Include structured data from backend for CLI panel display
                    // This enables traceback display without re-parsing JSON in frontend
                    if (log.metadata) logEntry.metadata = log.metadata;
                    if (log.traceback) logEntry.traceback = log.traceback;
                    if (log.event) logEntry.event = log.event;
                    if (log.prefix) logEntry.prefix = log.prefix;
                    if (log.source === 'structured_embedded') logEntry.isStructuredFromBackend = true;

                    // Use spread for Alpine.js reactivity
                    this.runs[runId].logs = [...this.runs[runId].logs, logEntry];

                    // Dispatch to execution store for unified tracking
                    if (typeof window.dispatchEvent === 'function') {
                        window.dispatchEvent(new CustomEvent('execution:log', {
                            detail: { runId, log: { message: text, backend, tier, cost_usd, type: logType } }
                        }));
                    }

                    // Trim if too many logs
                    if (this.runs[runId].logs.length > MAX_LOGS_PER_RUN) {
                        this.runs[runId].logs = this.runs[runId].logs.slice(-MAX_LOGS_PER_RUN);
                    }

                    // Auto-scroll if at bottom
                    this._autoScroll();

                    // Debounced save
                    this._saveState();
                });

                // Handle layer status updates
                poller.onLayerStatus((layerStatus) => {
                    if (!this.runs[runId]) {
                        poller.stop();
                        return;
                    }

                    this.runs[runId].layerStatus = {
                        ...this.runs[runId].layerStatus,
                        ...layerStatus
                    };
                    cliDebug(`Layer status update for ${runId}:`, layerStatus);
                });

                // Handle completion
                poller.onComplete((status, error) => {
                    cliDebug(`Log polling ended for ${runId}: ${status}`);

                    if (this.runs[runId]) {
                        // Map backend status to CLI status
                        const cliStatus = status === 'completed' ? 'success' : 'error';
                        this.runs[runId].status = cliStatus;
                        this.runs[runId].completedAt = Date.now();

                        if (error) {
                            this.runs[runId].error = error;
                        }

                        // Clean up poller reference
                        this.runs[runId]._logPoller = null;

                        // Save state
                        this._saveStateImmediate();

                        // Dispatch cli:complete event for pipeline-actions.js to handle
                        // This enables the event-based completion flow where CLI panel
                        // owns the LogPoller and pipeline-actions listens for completion
                        window.dispatchEvent(new CustomEvent('cli:complete', {
                            detail: {
                                runId: runId,
                                status: cliStatus,
                                error: error || null
                            }
                        }));

                        // Show toast if panel is collapsed
                        if (!this.expanded && typeof showToast === 'function') {
                            const jobTitle = this.runs[runId].jobTitle;
                            if (status === 'completed') {
                                showToast(`Pipeline completed: ${jobTitle}`, 'success');
                            } else {
                                showToast(`Pipeline failed: ${jobTitle}`, 'error');
                            }
                        }
                    }
                });

                // Handle errors
                poller.onError((error) => {
                    console.warn(`[CLI] Log polling error for ${runId}:`, error);
                    // Poller will auto-retry, so just log the error
                });

                // Start polling (fire-and-forget with error handling)
                console.log('[CLI] Starting LogPoller for:', runId);
                poller.start().catch(err => console.error('[LogPoller] Polling failed:', err));
                console.log('[CLI] LogPoller started for:', runId);
                cliDebug(`Log polling subscription established for ${runId}`);

            } catch (err) {
                console.error('[CLI] Failed to create LogPoller:', err);
            }
        },

        /**
         * Start polling fallback when SSE fails
         * @param {string} runId - The run ID to poll
         */
        _startPollingFallback(runId) {
            if (!runId || !this.runs[runId]) return;

            // Don't start multiple polling intervals
            if (this.runs[runId]._pollingInterval) return;

            cliDebug(`Starting polling fallback for ${runId}`);

            const pollInterval = setInterval(async () => {
                if (!this.runs[runId] || this.runs[runId].status !== 'running') {
                    clearInterval(pollInterval);
                    if (this.runs[runId]) {
                        this.runs[runId]._pollingInterval = null;
                    }
                    return;
                }

                try {
                    const response = await fetch(`/api/runner/operations/${runId}/status`);
                    if (!response.ok) {
                        console.warn(`[CLI] Polling failed for ${runId}: ${response.status}`);
                        return;
                    }

                    const data = await response.json();

                    // Update logs (only add new ones)
                    const existingCount = this.runs[runId].logs.length;
                    const newLogs = (data.logs || []).slice(existingCount);

                    if (newLogs.length > 0) {
                        for (const log of newLogs) {
                            const text = typeof log === 'string' ? log : log.text || JSON.stringify(log);
                            this.runs[runId].logs = [...this.runs[runId].logs, {
                                ts: Date.now(),
                                type: window.cliDetectLogType?.(text) || 'info',
                                text
                            }];
                        }
                        this._autoScroll();
                    }

                    // Update layer status
                    if (data.layer_status) {
                        this.runs[runId].layerStatus = {
                            ...this.runs[runId].layerStatus,
                            ...data.layer_status
                        };
                    }

                    // Check if completed
                    if (data.status === 'completed' || data.status === 'failed') {
                        const cliStatus = data.status === 'completed' ? 'success' : 'error';
                        this.runs[runId].status = cliStatus;
                        this.runs[runId].completedAt = Date.now();
                        this.runs[runId].error = data.error || null;
                        clearInterval(pollInterval);
                        this.runs[runId]._pollingInterval = null;
                        this._saveStateImmediate();

                        // Dispatch cli:complete event for pipeline-actions.js
                        window.dispatchEvent(new CustomEvent('cli:complete', {
                            detail: {
                                runId: runId,
                                status: cliStatus,
                                error: data.error || null
                            }
                        }));
                    }

                } catch (err) {
                    console.error(`[CLI] Polling error for ${runId}:`, err);
                }
            }, 2000);  // Poll every 2 seconds

            this.runs[runId]._pollingInterval = pollInterval;
        },

        /**
         * Load logs from Redis persistence for completed runs
         * Redis stores logs for 24 hours after completion
         * @param {string} runId - The run ID
         * @param {string} jobId - The job ID
         * @param {string} jobTitle - Optional job title
         * @returns {Promise<boolean>} - True if logs were loaded successfully
         */
        async loadRedisLogs(runId, jobId, jobTitle = null) {
            // Guard against undefined/null runId
            if (!runId) {
                console.error('[CLI] loadRedisLogs called with undefined/null runId');
                return false;
            }

            try {
                // Show loading toast
                if (typeof showToast === 'function') {
                    showToast('Loading logs from Redis...', 'info');
                }

                const response = await fetch(`/api/runner/operations/${runId}/logs/redis`);

                if (!response.ok) {
                    console.warn(`[CLI] Redis logs not available for run ${runId}: ${response.status}`);
                    if (typeof showToast === 'function') {
                        if (response.status === 404) {
                            showToast('Logs expired or unavailable (24h TTL)', 'error');
                        } else {
                            showToast(`Failed to load Redis logs: ${response.status}`, 'error');
                        }
                    }
                    return false;
                }

                const data = await response.json();

                // Update or create run entry with Redis data
                this.runs[runId] = {
                    jobId: jobId || data.job_id,
                    jobTitle: this._truncateTitle(jobTitle || data.job_title || `Job ${(jobId || data.job_id)?.slice(-6) || 'Unknown'}`),
                    action: data.operation || 'pipeline',
                    status: data.status === 'completed' ? 'success' : (data.status || 'unknown'),
                    logs: (data.logs || []).map(log => ({
                        ts: Date.now(),
                        type: 'info',
                        text: typeof log === 'string' ? log : log.text || JSON.stringify(log)
                    })),
                    layerStatus: data.layer_status || {},
                    startedAt: data.started_at ? new Date(data.started_at).getTime() : Date.now(),
                    completedAt: data.completed_at ? new Date(data.completed_at).getTime() : null,
                    error: data.error || null,
                    langsmithUrl: data.langsmith_url || null,
                    fromRedis: true  // Mark as loaded from Redis
                };

                // Add to run order if not present
                if (!this.runOrder.includes(runId)) {
                    this.runOrder.unshift(runId);
                }

                // Switch to the tab
                this.activeRunId = runId;
                this.expanded = true;

                // Save state
                this._saveStateImmediate();

                if (typeof showToast === 'function') {
                    showToast('Logs loaded from Redis cache', 'success');
                }

                cliDebug('Loaded logs from Redis', { runId, logCount: data.logs?.length || 0 });
                return true;

            } catch (err) {
                console.error('[CLI] Failed to load Redis logs:', err);
                if (typeof showToast === 'function') {
                    showToast(`Failed to load Redis logs: ${err.message}`, 'error');
                }
                return false;
            }
        },

        /**
         * Add a placeholder tab when logs are unavailable
         * @private
         */
        _addUnavailableRunPlaceholder(runId, jobId, jobTitle) {
            // Guard against undefined/null runId
            if (!runId) {
                console.error('[CLI] _addUnavailableRunPlaceholder called with undefined/null runId');
                return;
            }

            const now = Date.now();
            this.runs[runId] = {
                jobId,
                jobTitle: this._truncateTitle(jobTitle || `Job ${jobId?.slice(-6) || 'Unknown'}`),
                action: 'pipeline',
                status: 'unknown',
                logs: [{
                    ts: now,
                    type: 'warning',
                    text: '⚠️ Pipeline logs are no longer available'
                }, {
                    ts: now + 1,
                    type: 'info',
                    text: 'This usually happens after a runner service restart or deployment.'
                }, {
                    ts: now + 2,
                    type: 'info',
                    text: 'Logs are kept in memory for ~1 hour. After that, only cached logs in Redis remain (24h TTL).'
                }, {
                    ts: now + 3,
                    type: 'success',
                    text: '✓ Pipeline results are still saved in the database - check the job page for output.'
                }],
                layerStatus: {},
                startedAt: now,
                completedAt: null
            };

            if (runId && !this.runOrder.includes(runId)) {
                this.runOrder.unshift(runId);
            }
            this.activeRunId = runId;
            this.expanded = true;
            this._saveStateImmediate();
        },

        /**
         * Start a new pipeline run
         * @param {Object} detail - { runId, jobId, jobTitle, company, action }
         */
        startRun(detail) {
            const { runId, jobId, jobTitle, company, action } = detail;

            // Guard against undefined runId
            if (!runId) {
                console.error('[CLI] startRun called with undefined/null runId');
                cliDebug('startRun rejected - no runId', detail);
                return;
            }

            cliDebug('Starting run:', { runId, jobId, jobTitle, company, action });
            console.log('[CLI] Starting run:', { runId, jobId, jobTitle, company, action });

            // Check if already exists (prevent duplicates)
            if (this.runs[runId]) {
                cliDebug('Run already exists, updating status instead of creating', runId);
                this.runs[runId].status = 'running';
                this.runs[runId].startedAt = Date.now();
                this.activeRunId = runId;
                this.expanded = true;

                // Subscribe to logs if not already polling (fixes sessionStorage restore case)
                // When a run is restored from storage, _logPoller is null since it's not serialized
                if (!this.runs[runId]._logPoller) {
                    cliDebug('Run exists but no poller, subscribing to logs', runId);
                    this.subscribeToLogs(runId);
                }

                this._saveStateImmediate();
                return;
            }

            // Create run entry
            this.runs[runId] = {
                jobId,
                jobTitle: this._truncateTitle(jobTitle),
                company: company || 'Unknown Company',
                action,
                status: 'running',
                logs: [],
                layerStatus: {},
                startedAt: Date.now(),
                completedAt: null,
                _logPoller: null,
                _pollingInterval: null
            };

            // Add to front of run order using spread for reactivity (prevent duplicates)
            if (!this.runOrder.includes(runId)) {
                this.runOrder = [runId, ...this.runOrder];
            }

            // Switch to new run
            this.activeRunId = runId;

            // Expand panel to show logs
            this.expanded = true;

            // Dispatch to execution store for unified tracking
            if (typeof window.dispatchEvent === 'function') {
                window.dispatchEvent(new CustomEvent('execution:start', {
                    detail: { runId, jobId, jobTitle, action }
                }));
            }

            // Emit to RxJS runCreated$ subject (triggers race() in _queuePendingLog)
            if (this._rxjsAvailable && this._rxjsSubjects?.runCreated$) {
                this._rxjsSubjects.runCreated$.next({ runId, jobId });
            }

            // Replay any pending logs that arrived before this run was created (race condition fix)
            // Note: In RxJS mode, this may be triggered by the race() subscription instead
            this._replayPendingLogs(runId);

            // Always subscribe to log polling when run starts
            // This ensures 200ms polling begins immediately regardless of panel state
            // Logs are buffered in memory and displayed when panel is expanded
            this.subscribeToLogs(runId);

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

            // Queue instead of drop if run doesn't exist yet (race condition fix)
            if (!this.runs[runId]) {
                console.warn('[CLI] Run not found, queuing log for:', runId);
                this._queuePendingLog(runId, { text, logType });
                return;
            }

            // Use spread for Alpine.js reactivity (not .push() which mutates in place)
            this.runs[runId].logs = [...this.runs[runId].logs, {
                ts: Date.now(),
                type: logType,
                text
            }];

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

            // Dispatch to execution store for unified tracking
            if (typeof window.dispatchEvent === 'function') {
                window.dispatchEvent(new CustomEvent('execution:complete', {
                    detail: { runId, status: status === 'success' ? 'completed' : 'failed', error }
                }));
            }

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

                // Start polling if run is still active and not already polling (on-demand)
                if (this.runs[runId].status === 'running' && !this.runs[runId]._logPoller) {
                    this.subscribeToLogs(runId);
                }
            }
        },

        /**
         * Close a run tab
         */
        closeRun(runId) {
            // Guard against undefined runId
            if (!runId) {
                console.error('[CLI] closeRun called with undefined/null runId');
                return;
            }

            cliDebug('Closing run:', runId);

            // Clean up LogPoller if present
            if (this.runs[runId]?._logPoller) {
                try {
                    this.runs[runId]._logPoller.stop();
                } catch (e) {
                    // Ignore close errors
                }
            }

            // Clean up polling interval if present
            if (this.runs[runId]?._pollingInterval) {
                clearInterval(this.runs[runId]._pollingInterval);
            }

            // Remove from runs
            delete this.runs[runId];

            // Remove all instances from order (handles duplicates)
            this.runOrder = this.runOrder.filter(id => id !== runId);

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
         * Check if any log polling is currently active (for visual indicator)
         */
        isPollingActive() {
            return Object.values(this.pollingActive).some(active => active === true);
        },

        /**
         * Get backend usage statistics for a specific run
         * Analyzes logs to count Claude CLI vs LangChain fallback usage
         * @param {string} runId - The run ID to analyze
         * @returns {Object} - { claudeCli, langchain, claudeCliCost, langchainCost }
         */
        getBackendStats(runId) {
            const run = this.runs[runId];
            if (!run || !run.logs) {
                return { claudeCli: 0, langchain: 0, claudeCliCost: 0, langchainCost: 0 };
            }

            let claudeCli = 0, langchain = 0, claudeCliCost = 0, langchainCost = 0;

            run.logs.forEach(log => {
                const text = log.text || '';
                // Use the stored backend field or detect from text
                const backend = log.backend || this.detectBackendFromText(text);

                // Check for Claude CLI backend
                if (backend === 'claude_cli') {
                    claudeCli++;
                    claudeCliCost += log.cost_usd || 0;
                }
                // Check for LangChain fallback
                else if (backend === 'langchain') {
                    langchain++;
                    langchainCost += log.cost_usd || 0;
                }
            });

            return { claudeCli, langchain, claudeCliCost, langchainCost };
        },

        /**
         * Get Claude CLI call count for a run
         * @param {string} runId - The run ID
         * @returns {number} - Number of Claude CLI calls
         */
        getClaudeCliCount(runId) {
            return this.getBackendStats(runId).claudeCli;
        },

        /**
         * Get LangChain fallback call count for a run
         * @param {string} runId - The run ID
         * @returns {number} - Number of LangChain fallback calls
         */
        getLangchainCount(runId) {
            return this.getBackendStats(runId).langchain;
        },

        /**
         * Get Claude CLI cost for a run
         * @param {string} runId - The run ID
         * @returns {number} - Cost in USD
         */
        getClaudeCliCost(runId) {
            return this.getBackendStats(runId).claudeCliCost;
        },

        /**
         * Get LangChain fallback cost for a run
         * @param {string} runId - The run ID
         * @returns {number} - Cost in USD
         */
        getLangchainCost(runId) {
            return this.getBackendStats(runId).langchainCost;
        },

        /**
         * Get total cost for a run (Claude CLI + LangChain)
         * @param {string} runId - The run ID
         * @returns {number} - Total cost in USD
         */
        getTotalCost(runId) {
            const stats = this.getBackendStats(runId);
            return stats.claudeCliCost + stats.langchainCost;
        },

        /**
         * Check if a run has any backend tracking data
         * @param {string} runId - The run ID
         * @returns {boolean} - True if there's backend data to display
         */
        hasBackendData(runId) {
            const stats = this.getBackendStats(runId);
            return stats.claudeCli > 0 || stats.langchain > 0;
        },

        /**
         * Detect backend type from log text
         * @param {string} text - Log message text
         * @returns {string|null} - 'claude_cli', 'langchain', or null
         */
        detectBackendFromText(text) {
            if (!text) return null;
            // Check for explicit tags
            if (text.includes('[Claude CLI]')) return 'claude_cli';
            if (text.includes('[Fallback]') || text.includes('[LangChain]')) return 'langchain';
            // Check for backend= format in log text (e.g., "backend=langchain" or "backend=claude_cli")
            const backendMatch = text.match(/backend=(\w+)/);
            if (backendMatch) {
                const backend = backendMatch[1].toLowerCase();
                if (backend === 'claude_cli' || backend === 'claude-cli' || backend === 'claudecli') return 'claude_cli';
                if (backend === 'langchain' || backend === 'openai') return 'langchain';
            }
            return null;
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
         * Find a run by job ID
         * @param {string} jobId - The job ID to search for
         * @returns {string|null} - The run ID if found, null otherwise
         */
        findRunByJobId(jobId) {
            // First check for queued tab
            const queuedRunId = `queued_${jobId}`;
            if (this.runs[queuedRunId]) {
                return queuedRunId;
            }

            // Search through all runs for matching jobId
            for (const [runId, run] of Object.entries(this.runs)) {
                if (run.jobId === jobId) {
                    return runId;
                }
            }
            return null;
        },

        /**
         * Show logs for a specific job
         * Opens the CLI panel and switches to the job's run tab
         * @param {string} jobId - The job ID
         * @param {string} jobTitle - The job title for display
         */
        showJobLogs(jobId, jobTitle = null) {
            const existingRunId = this.findRunByJobId(jobId);

            if (existingRunId) {
                // Switch to existing tab
                this.activeRunId = existingRunId;
                this.expanded = true;
                this._saveState();
            } else {
                // No run found - create placeholder showing no logs available
                const placeholderRunId = `view_${jobId}`;
                if (!this.runs[placeholderRunId]) {
                    const now = Date.now();
                    this.runs[placeholderRunId] = {
                        jobId,
                        jobTitle: this._truncateTitle(jobTitle || `Job ${jobId?.slice(-6) || 'Unknown'}`),
                        action: 'pipeline',
                        status: 'unknown',
                        logs: [{
                            ts: now,
                            type: 'info',
                            text: 'No pipeline run found in memory for this job.'
                        }, {
                            ts: now + 1,
                            type: 'info',
                            text: 'Start a pipeline run from the job detail page to see logs here.'
                        }],
                        layerStatus: {},
                        startedAt: now,
                        completedAt: null
                    };
                    this.runOrder.unshift(placeholderRunId);
                }
                this.activeRunId = placeholderRunId;
                this.expanded = true;
                this._cleanup();
                this._saveStateImmediate();
            }
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
         * Queue a log for a run that doesn't exist yet (handles race condition)
         *
         * Uses RxJS timer when available for cleaner timeout handling.
         * @private
         */
        _queuePendingLog(runId, logData) {
            if (!this._pendingLogs[runId]) {
                this._pendingLogs[runId] = { logs: [], timer: null, subscription: null };

                // Set timeout to auto-fetch logs from API if run never appears
                if (this._rxjsAvailable && this._rxjsSubjects) {
                    // Use RxJS timer with takeUntil for automatic cleanup
                    const { timer, race, first, tap, takeUntil } = window.RxUtils;

                    this._pendingLogs[runId].subscription = race(
                        // Wait for run to be created
                        this._rxjsSubjects.runCreated$.pipe(
                            first(event => event.runId === runId),
                            tap(() => {
                                cliDebug(`Run ${runId} created, replaying pending logs (RxJS)`);
                                this._replayPendingLogs(runId);
                            })
                        ),
                        // Or timeout after PENDING_LOGS_TIMEOUT_MS
                        timer(PENDING_LOGS_TIMEOUT_MS).pipe(
                            tap(() => {
                                cliDebug(`Pending logs timeout for ${runId} (RxJS)`);
                                this._handlePendingLogsTimeout(runId);
                            })
                        )
                    ).pipe(
                        takeUntil(this._rxjsSubjects.destroy$)
                    ).subscribe();
                } else {
                    // Legacy setTimeout implementation
                    this._pendingLogs[runId].timer = setTimeout(() => {
                        this._handlePendingLogsTimeout(runId);
                    }, PENDING_LOGS_TIMEOUT_MS);
                }
            }
            this._pendingLogs[runId].logs.push({
                ts: Date.now(),
                type: logData.logType || 'info',
                text: logData.text
            });
            cliDebug(`Queued pending log for ${runId}, count: ${this._pendingLogs[runId].logs.length}`);
        },

        /**
         * Replay pending logs when run is created
         *
         * Cleans up both legacy setTimeout and RxJS subscriptions.
         * @private
         */
        _replayPendingLogs(runId) {
            const pending = this._pendingLogs[runId];
            if (!pending || !pending.logs.length) return;

            cliDebug(`Replaying ${pending.logs.length} pending logs for ${runId}`);

            // Clear the legacy timeout
            if (pending.timer) {
                clearTimeout(pending.timer);
            }

            // Unsubscribe RxJS subscription if exists
            if (pending.subscription) {
                pending.subscription.unsubscribe();
            }

            // Use spread for Alpine.js reactivity
            this.runs[runId].logs = [...this.runs[runId].logs, ...pending.logs];

            // Trim if needed
            if (this.runs[runId].logs.length > MAX_LOGS_PER_RUN) {
                this.runs[runId].logs = this.runs[runId].logs.slice(-MAX_LOGS_PER_RUN);
            }

            // Clean up
            delete this._pendingLogs[runId];

            // Save state and scroll
            this._saveState();
            this._autoScroll();
        },

        /**
         * Handle timeout for pending logs - attempt to fetch from API
         * @private
         */
        async _handlePendingLogsTimeout(runId) {
            const pending = this._pendingLogs[runId];
            if (!pending) return;

            console.warn(`[CLI] Pending logs timeout for ${runId}, fetching from API`);

            // Clean up pending logs
            delete this._pendingLogs[runId];

            // Try to fetch logs from API
            try {
                const response = await fetch(`/api/runner/operations/${runId}/status`);
                if (response.ok) {
                    const data = await response.json();

                    // Create run entry from API data
                    this.runs[runId] = {
                        jobId: data.job_id || null,
                        jobTitle: this._truncateTitle(data.job_title || `Run ${runId.slice(-8)}`),
                        action: data.operation || 'pipeline',
                        status: data.status === 'completed' ? 'success' : (data.status || 'running'),
                        logs: (data.logs || []).map(log => ({
                            ts: Date.now(),
                            type: typeof log === 'string' ? (window.cliDetectLogType?.(log) || 'info') : 'info',
                            text: typeof log === 'string' ? log : JSON.stringify(log)
                        })),
                        layerStatus: data.layer_status || {},
                        startedAt: data.started_at ? new Date(data.started_at).getTime() : Date.now(),
                        completedAt: data.completed_at ? new Date(data.completed_at).getTime() : null,
                        error: data.error || null
                    };

                    // Add to run order using spread for reactivity
                    if (!this.runOrder.includes(runId)) {
                        this.runOrder = [runId, ...this.runOrder];
                    }

                    this.activeRunId = runId;
                    this._cleanup();
                    this._saveStateImmediate();

                    cliDebug(`Recovered run ${runId} from API with ${this.runs[runId].logs.length} logs`);
                }
            } catch (err) {
                console.error(`[CLI] Failed to recover run ${runId} from API:`, err);
            }
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
         *
         * Uses RxJS debounceTime when available, otherwise falls back to setTimeout.
         */
        _saveState() {
            // Use RxJS debounced save if available
            if (this._rxjsAvailable && this._rxjsSubjects?.saveState$) {
                this._rxjsSubjects.saveState$.next();
                return;
            }

            // Legacy debounce implementation
            if (this._saveTimeout) {
                clearTimeout(this._saveTimeout);
            }

            this._saveTimeout = setTimeout(() => {
                this._saveStateImmediate();
            }, SAVE_DEBOUNCE_MS);
        },

        /**
         * Cycle panel height: small → medium → large → xlarge → small
         */
        cyclePanelSize() {
            const sizes = ['small', 'medium', 'large', 'xlarge'];
            const currentIdx = sizes.indexOf(this.panelSize);
            this.panelSize = sizes[(currentIdx + 1) % sizes.length];
            this._saveStateImmediate();
        },

        /**
         * Cycle font size: small → medium → large → small
         */
        cycleFontSize() {
            const sizes = ['small', 'medium', 'large'];
            const currentIdx = sizes.indexOf(this.fontSize);
            this.fontSize = sizes[(currentIdx + 1) % sizes.length];
            this._saveStateImmediate();
        },

        /**
         * Get font size label for display
         */
        getFontSizeLabel() {
            const labels = { small: 'S', medium: 'M', large: 'L' };
            return labels[this.fontSize] || 'M';
        },

        /**
         * Get panel size label for display
         */
        getPanelSizeLabel() {
            const labels = { small: '¼', medium: '½', large: '¾', xlarge: 'Full' };
            return labels[this.panelSize] || '½';
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
                    runOrder: this.runOrder,
                    panelSize: this.panelSize,
                    fontSize: this.fontSize
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
        },

        /**
         * Debug utility - dump current state (for console debugging)
         * Usage: Alpine.store('cli').debugState()
         */
        debugState() {
            const state = {
                expanded: this.expanded,
                activeRunId: this.activeRunId,
                runOrder: [...this.runOrder],
                runOrderLength: this.runOrder.length,
                runsCount: Object.keys(this.runs).length,
                runs: Object.fromEntries(
                    Object.entries(this.runs).map(([id, run]) => [
                        id,
                        {
                            jobId: run.jobId,
                            jobTitle: run.jobTitle,
                            status: run.status,
                            logsCount: run.logs?.length || 0
                        }
                    ])
                ),
                runOrderValid: this.runOrder.every(id =>
                    id !== undefined && id !== null && this.runs[id]
                )
            };
            console.log('[CLI] Current State:', state);
            return state;
        },

        /**
         * Force clear and reset CLI state (for debugging corrupted state)
         * Usage: Alpine.store('cli').clearAll()
         */
        clearAll() {
            this.runs = {};
            this.runOrder = [];
            this.activeRunId = null;
            this.expanded = false;
            sessionStorage.removeItem(CLI_STORAGE_KEY);
            console.log('[CLI] State cleared');
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

/**
 * Parse a log message that might be JSON structured log
 * Handles two formats:
 * 1. Pure JSON: {"event": "...", "metadata": {...}}
 * 2. Prefixed: event_name: {"event": "...", "metadata": {...}}
 *
 * Returns { isStructured, message, event, metadata } or { isStructured: false, message }
 */
window.cliParseStructuredLog = function(text) {
    if (!text || typeof text !== 'string') {
        return { isStructured: false, message: text || '' };
    }

    let jsonStr = text.trim();
    let prefix = '';

    // Check if text starts with JSON directly
    if (!jsonStr.startsWith('{')) {
        // Look for "event_name: {json}" pattern (e.g., "cv_role_gen_subphase_start: {...}")
        const colonBraceIdx = jsonStr.indexOf(': {');
        if (colonBraceIdx === -1) {
            return { isStructured: false, message: text };
        }

        // Extract prefix and JSON portion
        prefix = jsonStr.substring(0, colonBraceIdx);
        jsonStr = jsonStr.substring(colonBraceIdx + 2); // Skip ": "
    }

    try {
        const data = JSON.parse(jsonStr);

        // Check if it's a structured log (has event and metadata)
        if (data.event && typeof data.event === 'string') {
            const message = data.message || data.event;
            const metadata = data.metadata || {};

            // Filter out empty/null metadata fields and 'message' (already shown)
            const filteredMetadata = {};
            for (const [key, value] of Object.entries(metadata)) {
                // Skip 'message' key since it's displayed as the main message
                if (key === 'message') continue;
                if (value !== null && value !== undefined && value !== '') {
                    filteredMetadata[key] = value;
                }
            }

            return {
                isStructured: true,
                message: message,
                event: data.event,
                layer: data.layer,
                layer_name: data.layer_name,
                metadata: filteredMetadata,
                hasMetadata: Object.keys(filteredMetadata).length > 0,
                prefix: prefix // Preserve the original prefix if any
            };
        }

        return { isStructured: false, message: text };
    } catch (e) {
        return { isStructured: false, message: text };
    }
};

/**
 * Get an icon for structured log event types
 */
window.cliGetEventIcon = function(event) {
    if (!event) return '>';

    if (event.includes('_start')) return '🚀';
    if (event.includes('_complete')) return '✅';
    if (event.includes('_failed') || event.includes('_error') || event === 'cv_struct_error') return '❌';
    if (event.includes('error')) return '❌';  // Catch-all for error events
    if (event.includes('llm_call')) return '🤖';
    if (event.includes('decision_point')) return '🎯';
    if (event.includes('validation')) return '🔍';
    if (event.includes('subphase')) return '📍';

    return '📋';
};

/**
 * Format a metadata value for display (handles objects, arrays, long strings)
 */
window.cliFormatMetadataValue = function(value) {
    if (value === null || value === undefined) return '';

    if (typeof value === 'object') {
        // For arrays, show count and first few items
        if (Array.isArray(value)) {
            if (value.length === 0) return '[]';
            if (value.length <= 3) return JSON.stringify(value);
            return `[${value.slice(0, 2).map(v => JSON.stringify(v)).join(', ')}, ... +${value.length - 2} more]`;
        }
        // For objects, show key count
        const keys = Object.keys(value);
        if (keys.length === 0) return '{}';
        if (keys.length <= 2) return JSON.stringify(value);
        return `{${keys.slice(0, 2).join(', ')}, ... +${keys.length - 2} more}`;
    }

    if (typeof value === 'string') {
        // Truncate long strings
        if (value.length > 100) {
            return value.substring(0, 50) + '...' + value.substring(value.length - 30);
        }
        return value;
    }

    return String(value);
};

console.log('[CLI Panel] Module loaded');
