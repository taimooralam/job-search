/**
 * Job Pipelines Panel - Alpine.js Store for Detail Page
 *
 * Tracks queue status for each operation type on the current job.
 * Subscribes to WebSocket queue events filtered by job_id.
 *
 * Features:
 * - Real-time status updates via WebSocket
 * - On-demand log viewing via CLI panel
 * - Queue position tracking
 * - Polling fallback for status updates
 *
 * Operations tracked:
 * - structure-jd: Structure JD (Layer 1.4 only)
 * - full-extraction: Full extraction (Layer 1.4 + 2 + 4)
 * - research-company: Company and role research
 * - generate-cv: CV generation
 */

/* ============================================================================
   Configuration
   ============================================================================ */

const PIPELINES_PANEL_CONFIG = {
    // Valid operations to track
    operations: ['structure-jd', 'full-extraction', 'extract', 'research-company', 'generate-cv'],

    // Display labels
    labels: {
        'structure-jd': 'Structure JD',
        'full-extraction': 'Full Extraction',
        'extract': 'Extract JD',
        'research-company': 'Research',
        'generate-cv': 'Generate CV'
    },

    // Status icons
    statusIcons: {
        pending: '\u231B',     // Hourglass
        running: '\u23F3',     // Hourglass flowing
        completed: '\u2705',   // Green check
        failed: '\u274C',      // Red X
        cancelled: '\u26D4',   // No entry
        idle: '\u2022'         // Bullet point
    },

    // Status colors (Tailwind classes)
    statusColors: {
        pending: 'text-yellow-500 dark:text-yellow-400',
        running: 'text-blue-500 dark:text-blue-400',
        completed: 'text-green-500 dark:text-green-400',
        failed: 'text-red-500 dark:text-red-400',
        cancelled: 'text-gray-500 dark:text-gray-400',
        idle: 'text-gray-400 dark:text-gray-500'
    },

    // Polling interval for status updates (fallback)
    pollIntervalMs: 5000,

    // Queue endpoint for status
    queueStatusEndpoint: '/api/runner/jobs/{jobId}/queue-status',

    // Queue operation endpoint
    queueOperationEndpoint: '/api/runner/jobs/{jobId}/operations/{operation}/queue'
};

/* ============================================================================
   Alpine.js Store Initialization
   ============================================================================ */

document.addEventListener('alpine:init', () => {
    Alpine.store('detailPipelines', {
        // Job ID for this detail page
        jobId: null,

        // Operation statuses (keyed by operation name)
        // Each entry is null (never queued) or an object with:
        // { status, queue_id, run_id, position, started_at, completed_at, error }
        operations: {
            'structure-jd': null,
            'full-extraction': null,
            'extract': null,
            'research-company': null,
            'generate-cv': null
        },

        // Track if initialized
        initialized: false,

        // Polling interval ID (for cleanup)
        _pollIntervalId: null,

        // WebSocket connected status
        wsConnected: false,

        /**
         * Initialize the pipelines panel for a specific job
         * @param {string} jobId - MongoDB job ID
         */
        init(jobId) {
            if (this.initialized && this.jobId === jobId) {
                console.log('[Pipelines Panel] Already initialized for job:', jobId);
                return;
            }

            this.jobId = jobId;
            this.initialized = true;

            console.log('[Pipelines Panel] Initializing for job:', jobId);

            // Load initial status
            this._loadInitialStatus();

            // Subscribe to WebSocket queue events
            this._subscribeToQueueEvents();

            // Start polling fallback (in case WebSocket is unavailable)
            this._startPolling();
        },

        /**
         * Clean up when navigating away
         */
        destroy() {
            if (this._pollIntervalId) {
                clearInterval(this._pollIntervalId);
                this._pollIntervalId = null;
            }
            this.initialized = false;
        },

        /**
         * Queue an operation for background execution
         * @param {string} operation - Operation type
         * @param {string} tier - Model tier (fast, balanced, quality)
         * @param {Object} options - Additional options (force_refresh, use_llm, use_annotations)
         * @returns {Promise<Object>} Queue response
         */
        async queueOperation(operation, tier = 'balanced', options = {}) {
            if (!this.jobId) {
                console.error('[Pipelines Panel] No job ID set');
                return { success: false, error: 'No job ID set' };
            }

            const endpoint = PIPELINES_PANEL_CONFIG.queueOperationEndpoint
                .replace('{jobId}', this.jobId)
                .replace('{operation}', operation);

            console.log(`[Pipelines Panel] Queuing ${operation} for job ${this.jobId}`);

            try {
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tier, ...options })
                });

                const result = await response.json();

                if (result.success) {
                    // Update local state immediately for responsive UI
                    // Capture run_id from API response if available (for immediate log viewing)
                    this.operations[operation] = {
                        status: 'pending',
                        queue_id: result.queue_id,
                        run_id: result.run_id || null,  // Capture run_id for log viewing
                        position: result.position,
                        started_at: null,
                        completed_at: null,
                        error: null
                    };

                    console.log(`[Pipelines Panel] Queued ${operation} as ${result.queue_id} (position #${result.position})`);

                    // Show toast notification
                    if (typeof showToast === 'function') {
                        showToast(`${PIPELINES_PANEL_CONFIG.labels[operation]} queued (position #${result.position})`, 'success');
                    }
                } else {
                    console.error(`[Pipelines Panel] Failed to queue ${operation}:`, result.error);

                    if (typeof showToast === 'function') {
                        showToast(result.error || 'Failed to queue operation', 'error');
                    }
                }

                return result;

            } catch (error) {
                console.error(`[Pipelines Panel] Error queuing ${operation}:`, error);

                if (typeof showToast === 'function') {
                    showToast(`Failed to queue: ${error.message}`, 'error');
                }

                return { success: false, error: error.message };
            }
        },

        /**
         * Open logs for an operation in the CLI panel
         * @param {string} operation - Operation type
         */
        openLogs(operation) {
            const opStatus = this.operations[operation];

            if (!opStatus) {
                console.log(`[Pipelines Panel] No status for ${operation}`);
                return;
            }

            // If no run_id, show a context-aware message
            if (!opStatus.run_id) {
                console.log(`[Pipelines Panel] No run_id for ${operation}, status: ${opStatus.status}`);
                if (typeof showToast === 'function') {
                    const label = PIPELINES_PANEL_CONFIG.labels[operation] || operation;
                    if (opStatus.status === 'pending') {
                        const position = opStatus.position ? ` (#${opStatus.position} in queue)` : '';
                        showToast(`${label} is queued${position} - logs available when it starts`, 'info');
                    } else {
                        showToast(`Logs not available for ${label}`, 'info');
                    }
                }
                return;
            }

            console.log(`[Pipelines Panel] Opening logs for ${operation} (run: ${opStatus.run_id})`);

            // Dispatch event to CLI panel to show logs
            // Pass full metadata including status so CLI panel can decide whether to stream
            window.dispatchEvent(new CustomEvent('cli:fetch-logs', {
                detail: {
                    runId: opStatus.run_id,
                    jobId: this.jobId,
                    jobTitle: this._getJobTitle(),
                    company: this._getCompany(),
                    action: operation.replace('-', '_'),
                    status: opStatus.status  // 'pending', 'running', 'completed', 'failed'
                }
            }));
        },

        /**
         * Get display status for an operation
         * @param {string} operation - Operation type
         * @returns {Object} { status, icon, color, label, position, canViewLogs }
         */
        getDisplayStatus(operation) {
            const opStatus = this.operations[operation];

            if (!opStatus) {
                return {
                    status: 'idle',
                    icon: PIPELINES_PANEL_CONFIG.statusIcons.idle,
                    color: PIPELINES_PANEL_CONFIG.statusColors.idle,
                    label: 'Not run',
                    position: null,
                    canViewLogs: false
                };
            }

            const status = opStatus.status || 'idle';

            return {
                status,
                icon: PIPELINES_PANEL_CONFIG.statusIcons[status] || PIPELINES_PANEL_CONFIG.statusIcons.idle,
                color: PIPELINES_PANEL_CONFIG.statusColors[status] || PIPELINES_PANEL_CONFIG.statusColors.idle,
                label: this._getStatusLabel(status, opStatus),
                position: status === 'pending' ? opStatus.position : null,
                canViewLogs: !!opStatus.run_id
            };
        },

        /**
         * Check if an operation is currently active (pending or running)
         * @param {string} operation - Operation type
         * @returns {boolean}
         */
        isActive(operation) {
            const opStatus = this.operations[operation];
            return opStatus && ['pending', 'running'].includes(opStatus.status);
        },

        /**
         * Check if any operation is currently active
         * @returns {boolean}
         */
        hasActiveOperations() {
            return PIPELINES_PANEL_CONFIG.operations.some(op => this.isActive(op));
        },

        /**
         * Check if any operation has been run (has any status, including completed/failed)
         * @returns {boolean}
         */
        hasAnyOperations() {
            return PIPELINES_PANEL_CONFIG.operations.some(op => {
                const opStatus = this.operations[op];
                return opStatus && opStatus.status;
            });
        },

        /**
         * Get human-readable label for an operation
         * @param {string} operation - Operation name
         * @returns {string}
         */
        getOperationLabel(operation) {
            return PIPELINES_PANEL_CONFIG.labels[operation] || operation;
        },

        // =====================================================================
        // Private Methods
        // =====================================================================

        /**
         * Load status from queue store (no HTTP request - uses data from QueuePoller)
         * Falls back to HTTP request if queue store is not available
         */
        async _loadInitialStatus() {
            if (!this.jobId) return;

            // Try to use queue store data first (fast, no HTTP request)
            const queueStore = typeof Alpine !== 'undefined' ? Alpine.store('queue') : null;
            if (queueStore && queueStore.pending && queueStore.running && queueStore.history) {
                this._updateFromQueueStore(queueStore);
                return;
            }

            // Fallback: make HTTP request through Flask proxy (slow, may timeout)
            console.log('[Pipelines Panel] Queue store not available, falling back to HTTP request');
            const endpoint = PIPELINES_PANEL_CONFIG.queueStatusEndpoint
                .replace('{jobId}', this.jobId);

            try {
                const response = await fetch(endpoint);
                const data = await response.json();

                if (data.operations) {
                    // Update all operations
                    for (const op of PIPELINES_PANEL_CONFIG.operations) {
                        this.operations[op] = data.operations[op] || null;
                    }
                }

                console.log('[Pipelines Panel] Loaded initial status:', this.operations);

            } catch (error) {
                console.error('[Pipelines Panel] Failed to load initial status:', error);
            }
        },

        /**
         * Update operations from queue store data
         * @param {Object} queueStore - Alpine queue store
         */
        _updateFromQueueStore(queueStore) {
            const allItems = [
                ...queueStore.pending.map(i => ({ ...i, status: 'pending' })),
                ...queueStore.running.map(i => ({ ...i, status: 'running' })),
                ...queueStore.failed.map(i => ({ ...i, status: 'failed' })),
                ...queueStore.history.filter(i => i.job_id === this.jobId).map(i => ({ ...i, status: i.status || 'completed' }))
            ];

            // Find items for this job
            const jobItems = allItems.filter(item => item.job_id === this.jobId);

            // Group by operation and take the most recent
            for (const op of PIPELINES_PANEL_CONFIG.operations) {
                const opItems = jobItems.filter(item => item.operation === op);
                if (opItems.length > 0) {
                    // Take the most recent (first match in order: pending > running > history)
                    const latest = opItems[0];
                    this.operations[op] = {
                        status: latest.status,
                        run_id: latest.run_id,
                        position: latest.position,
                        created_at: latest.created_at,
                        started_at: latest.started_at,
                        completed_at: latest.completed_at,
                        error: latest.error
                    };
                }
            }

            console.log('[Pipelines Panel] Updated from queue store:', this.operations);
        },

        /**
         * Subscribe to queue events for real-time updates
         */
        _subscribeToQueueEvents() {
            // Listen for queue:update events (if dispatched)
            window.addEventListener('queue:update', (event) => {
                this._handleQueueEvent(event.detail);
            });

            // Listen for global queue job events (dispatched by queue-store.js)
            // These provide real-time updates instead of relying solely on polling
            window.addEventListener('queue:job-started', (event) => {
                if (event.detail?.jobId === this.jobId) {
                    console.log('[Pipelines Panel] Job started event received, refreshing status');
                    this._loadInitialStatus();
                }
            });

            window.addEventListener('queue:job-completed', (event) => {
                if (event.detail?.jobId === this.jobId) {
                    console.log('[Pipelines Panel] Job completed event received, refreshing status');
                    this._loadInitialStatus();
                }
            });

            window.addEventListener('queue:job-failed', (event) => {
                if (event.detail?.jobId === this.jobId) {
                    console.log('[Pipelines Panel] Job failed event received, refreshing status');
                    this._loadInitialStatus();
                }
            });

            // Listen for status changes from batch operations (dispatched by batch_processing.html)
            // This enables real-time updates when same job is viewed from detail page while batch runs
            window.addEventListener('queue:job-status-changed', (event) => {
                if (event.detail?.jobId === this.jobId) {
                    const { status, runId, operation } = event.detail;
                    console.log(`[Pipelines Panel] Job status changed: ${operation} -> ${status}`);

                    // Update local operation state if we track this operation
                    if (operation && this.operations[operation] !== undefined) {
                        if (!this.operations[operation]) {
                            this.operations[operation] = {};
                        }
                        this.operations[operation].status = status === 'queued' ? 'pending' : status;
                        if (runId) {
                            this.operations[operation].run_id = runId;
                        }
                        if (event.detail.position) {
                            this.operations[operation].position = event.detail.position;
                        }
                    }

                    // Also refresh from API to get complete data
                    this._loadInitialStatus();
                }
            });

            // Also listen for global queue store updates if available
            if (typeof Alpine !== 'undefined' && Alpine.store('queue')) {
                console.log('[Pipelines Panel] Queue store available, real-time events enabled');
            }
        },

        /**
         * Handle WebSocket queue event
         * @param {Object} event - Queue event from WebSocket
         */
        _handleQueueEvent(event) {
            if (!event || !event.item) return;

            const { action, item } = event;

            // Only process events for this job
            if (item.job_id !== this.jobId) return;

            const operation = item.operation;
            if (!PIPELINES_PANEL_CONFIG.operations.includes(operation)) return;

            console.log(`[Pipelines Panel] Queue event: ${action} for ${operation}`, item);

            // Update local state based on event action
            switch (action) {
                case 'added':
                    this.operations[operation] = {
                        status: 'pending',
                        queue_id: item.queue_id,
                        run_id: item.run_id,
                        position: item.position,
                        started_at: null,
                        completed_at: null,
                        error: null
                    };
                    break;

                case 'started':
                    if (this.operations[operation]) {
                        this.operations[operation].status = 'running';
                        this.operations[operation].run_id = item.run_id;
                        this.operations[operation].started_at = item.started_at;
                        this.operations[operation].position = 0;
                    }
                    break;

                case 'completed':
                    if (this.operations[operation]) {
                        this.operations[operation].status = 'completed';
                        this.operations[operation].completed_at = item.completed_at;
                    }
                    break;

                case 'failed':
                    if (this.operations[operation]) {
                        this.operations[operation].status = 'failed';
                        this.operations[operation].error = item.error;
                        this.operations[operation].completed_at = item.completed_at;
                    }
                    break;

                case 'cancelled':
                    if (this.operations[operation]) {
                        this.operations[operation].status = 'cancelled';
                    }
                    break;

                case 'updated':
                    // Update run_id link
                    if (this.operations[operation] && item.run_id) {
                        this.operations[operation].run_id = item.run_id;
                    }
                    break;
            }
        },

        /**
         * Start polling for status updates (fallback)
         */
        _startPolling() {
            // Clear any existing interval
            if (this._pollIntervalId) {
                clearInterval(this._pollIntervalId);
            }

            // Grace period tracking - continue polling for 30s after operations complete
            // This catches late completion events and ensures final status is captured
            let gracePeriodEnd = null;
            const gracePeriodMs = 30000;  // 30 seconds

            // Poll periodically
            this._pollIntervalId = setInterval(() => {
                if (this.hasActiveOperations()) {
                    // Active operations - reset grace period and poll
                    gracePeriodEnd = null;
                    this._loadInitialStatus();
                } else if (gracePeriodEnd === null) {
                    // Just finished active operations - start grace period
                    gracePeriodEnd = Date.now() + gracePeriodMs;
                    this._loadInitialStatus();
                } else if (Date.now() < gracePeriodEnd) {
                    // Within grace period - continue polling
                    this._loadInitialStatus();
                }
                // After grace period - stop polling to save resources
            }, PIPELINES_PANEL_CONFIG.pollIntervalMs);
        },

        /**
         * Get job title from page context
         * @returns {string} Job title or default
         */
        _getJobTitle() {
            // Try to get from data attribute on body/page element
            const pageEl = document.querySelector('[data-job-title]');
            if (pageEl) return pageEl.dataset.jobTitle;

            // Try to get from page heading
            const heading = document.querySelector('h1.job-title, .job-header h1, [data-testid="job-title"]');
            if (heading) return heading.textContent?.trim() || 'Unknown Job';

            // Try to get from document title (often "Job Title - Company | Site")
            const title = document.title;
            if (title && title.includes('|')) {
                return title.split('|')[0].trim();
            }

            return 'Unknown Job';
        },

        /**
         * Get company name from page context
         * @returns {string} Company name or default
         */
        _getCompany() {
            // Try to get from data attribute on body/page element
            const pageEl = document.querySelector('[data-company]');
            if (pageEl) return pageEl.dataset.company;

            // Try to get from company element
            const companyEl = document.querySelector('.company-name, [data-testid="company-name"]');
            if (companyEl) return companyEl.textContent?.trim() || 'Unknown Company';

            return 'Unknown Company';
        },

        /**
         * Get human-readable status label
         * @param {string} status - Status value
         * @param {Object} opStatus - Full operation status object
         * @returns {string}
         */
        _getStatusLabel(status, opStatus) {
            switch (status) {
                case 'pending':
                    return opStatus.position ? `Queued #${opStatus.position}` : 'Queued';
                case 'running':
                    return 'Running...';
                case 'completed':
                    return 'Completed';
                case 'failed':
                    return opStatus.error ? `Failed: ${opStatus.error.substring(0, 30)}...` : 'Failed';
                case 'cancelled':
                    return 'Cancelled';
                default:
                    return 'Not run';
            }
        }
    });
});

/* ============================================================================
   Alpine.js Component for Pipeline Card
   ============================================================================ */

/**
 * Alpine.js component for a single pipeline operation card
 *
 * Usage:
 * <div x-data="pipelineCard({ operation: 'full-extraction' })">
 *   <button @click="queue()" :disabled="isActive">
 *     <span x-text="statusLabel"></span>
 *   </button>
 *   <button x-show="canViewLogs" @click="viewLogs()">View Logs</button>
 * </div>
 */
function pipelineCard(config) {
    return {
        operation: config.operation,
        tier: config.tier || 'balanced',

        get displayStatus() {
            return Alpine.store('detailPipelines').getDisplayStatus(this.operation);
        },

        get statusLabel() {
            return this.displayStatus.label;
        },

        get statusIcon() {
            return this.displayStatus.icon;
        },

        get statusColor() {
            return this.displayStatus.color;
        },

        get isActive() {
            return Alpine.store('detailPipelines').isActive(this.operation);
        },

        get canViewLogs() {
            return this.displayStatus.canViewLogs;
        },

        get label() {
            return PIPELINES_PANEL_CONFIG.labels[this.operation] || this.operation;
        },

        async queue() {
            if (this.isActive) return;

            const store = Alpine.store('detailPipelines');
            await store.queueOperation(this.operation, this.tier);
        },

        viewLogs() {
            Alpine.store('detailPipelines').openLogs(this.operation);
        }
    };
}

// Make component available globally
window.pipelineCard = pipelineCard;

/* ============================================================================
   Claude Extraction Button Component
   ============================================================================ */

/**
 * Alpine.js component for Claude extraction button
 * Uses the queue system for live tail logs, same as GPT-4o extraction
 *
 * @param {string} jobId - MongoDB job ID
 * @returns {Object} Alpine.js component
 */
function claudeExtractionButton(jobId) {
    return {
        jobId: jobId,
        loading: false,

        /**
         * Queue Claude extraction via the pipeline queue system
         */
        async queueExtract() {
            if (this.loading) return;

            this.loading = true;

            try {
                // Use the pipelines store to queue the operation
                const store = Alpine.store('detailPipelines');
                if (store) {
                    const result = await store.queueOperation('extract', 'balanced', {});

                    if (result.success) {
                        // Show toast notification
                        if (window.showToast) {
                            window.showToast('JD extraction queued! Check the Pipelines panel for progress.', 'success');
                        }
                    } else {
                        if (window.showToast) {
                            window.showToast(`Failed to queue extraction: ${result.error}`, 'error');
                        }
                    }
                } else {
                    // Fallback: direct API call if store not available
                    const endpoint = `/api/runner/jobs/${this.jobId}/operations/extract/queue`;
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ tier: 'balanced' })
                    });

                    const data = await response.json();

                    if (data.success) {
                        if (window.showToast) {
                            window.showToast('JD extraction queued!', 'success');
                        }
                    } else {
                        if (window.showToast) {
                            window.showToast(`Failed: ${data.error}`, 'error');
                        }
                    }
                }
            } catch (error) {
                console.error('[Extract Button] Queue error:', error);
                if (window.showToast) {
                    window.showToast(`Error: ${error.message}`, 'error');
                }
            } finally {
                this.loading = false;
            }
        }
    };
}

// Make extraction button available globally (backwards compatible alias)
window.claudeExtractionButton = claudeExtractionButton;
window.extractionButton = claudeExtractionButton;

/* ============================================================================
   Event Listeners
   ============================================================================ */

// Clean up when page is unloaded
window.addEventListener('beforeunload', () => {
    const store = Alpine.store('detailPipelines');
    if (store) {
        store.destroy();
    }
});

// Expose config for debugging
window.PIPELINES_PANEL_CONFIG = PIPELINES_PANEL_CONFIG;
