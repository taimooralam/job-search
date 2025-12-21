/**
 * Execution Store - Unified state management for pipeline operations
 *
 * This module provides a single source of truth for all pipeline execution state
 * across all pages (index, job_detail, batch). It integrates with the CLI panel
 * and provides backend visibility (Claude CLI vs LangChain).
 *
 * Features:
 * - Unified queue state (pending, running, failed, completed)
 * - Operation tracking by runId with logs, layer status, backend attribution
 * - Real-time backend statistics (Claude CLI calls, LangChain fallback, costs)
 * - Session persistence via sessionStorage
 * - Integration with Alpine.js store system
 *
 * Usage:
 *   // Access via Alpine.js
 *   const stats = $store.execution.getBackendStats(runId);
 *
 *   // Dispatch events for log updates
 *   window.dispatchEvent(new CustomEvent('execution:log', {
 *       detail: { runId, log: { message, backend, tier, cost_usd } }
 *   }));
 *
 * Debug Mode:
 *   localStorage.setItem('execution_debug', 'true')
 *   Alpine.store('execution').debugState()
 */

(function(global) {
    'use strict';

    const EXECUTION_STORAGE_KEY = 'execution_state';
    const MAX_OPERATIONS = 50;  // Max operations to keep in history
    const SAVE_DEBOUNCE_MS = 1000;

    // Debug mode
    const EXECUTION_DEBUG = localStorage.getItem('execution_debug') === 'true' ||
                            window.location.search.includes('execution_debug=true');

    function debugLog(...args) {
        if (EXECUTION_DEBUG) {
            console.log('[ExecutionStore]', new Date().toISOString(), ...args);
        }
    }

    /**
     * Initialize the execution store when Alpine.js is ready
     */
    document.addEventListener('alpine:init', () => {
        Alpine.store('execution', {
            /* ======================================================================
               State
               ====================================================================== */

            // Queue state (synced with queue-poller)
            queue: {
                pending: [],
                running: [],
                failed: [],
                history: [],
                version: 0
            },

            // Operations indexed by runId
            // Each operation: { logs, layerStatus, status, backend, costs, jobId, jobTitle, startedAt, ... }
            operations: {},

            // Currently active operation (for display)
            activeRunId: null,

            // Internal state
            _initialized: false,
            _saveTimeout: null,

            /* ======================================================================
               Initialization
               ====================================================================== */

            /**
             * Initialize the store - restore from sessionStorage
             */
            init() {
                if (this._initialized) return;
                this._initialized = true;

                debugLog('Initializing execution store');

                // Restore state from sessionStorage
                try {
                    const saved = sessionStorage.getItem(EXECUTION_STORAGE_KEY);
                    if (saved) {
                        const state = JSON.parse(saved);
                        this.queue = state.queue || this.queue;
                        this.operations = state.operations || {};
                        this.activeRunId = state.activeRunId || null;
                        debugLog('Restored state:', Object.keys(this.operations).length, 'operations');
                    }
                } catch (e) {
                    console.error('[ExecutionStore] Failed to restore state:', e);
                    sessionStorage.removeItem(EXECUTION_STORAGE_KEY);
                }

                // Set up event listeners
                this._setupEventListeners();

                console.log('[ExecutionStore] Initialized');
            },

            /**
             * Set up event listeners for queue and log updates
             */
            _setupEventListeners() {
                // Queue state updates (from queue-poller)
                window.addEventListener('execution:queue-update', (e) => {
                    this.updateQueueState(e.detail);
                });

                // Log entry (from log-poller or CLI panel)
                window.addEventListener('execution:log', (e) => {
                    const { runId, log } = e.detail;
                    if (runId && log) {
                        this.addLog(runId, log);
                    }
                });

                // Operation start
                window.addEventListener('execution:start', (e) => {
                    const { runId, jobId, jobTitle, action } = e.detail;
                    this.startOperation(runId, { jobId, jobTitle, action });
                });

                // Operation complete
                window.addEventListener('execution:complete', (e) => {
                    const { runId, status, error } = e.detail;
                    this.completeOperation(runId, status, error);
                });

                // Layer status update
                window.addEventListener('execution:layer-status', (e) => {
                    const { runId, layerStatus } = e.detail;
                    if (runId && layerStatus) {
                        this.updateLayerStatus(runId, layerStatus);
                    }
                });
            },

            /* ======================================================================
               Queue State Management
               ====================================================================== */

            /**
             * Update queue state from poller
             * @param {Object} queueState - { pending, running, failed, history, state_version }
             */
            updateQueueState(queueState) {
                if (!queueState) return;

                this.queue.pending = queueState.pending || [];
                this.queue.running = queueState.running || [];
                this.queue.failed = queueState.failed || [];
                this.queue.history = queueState.history || [];
                this.queue.version = queueState.state_version || this.queue.version + 1;

                debugLog('Queue updated, version:', this.queue.version);
                this._saveState();
            },

            /* ======================================================================
               Operation Management
               ====================================================================== */

            /**
             * Start tracking a new operation
             * @param {string} runId - The operation run ID
             * @param {Object} details - { jobId, jobTitle, action }
             */
            startOperation(runId, details = {}) {
                if (!runId) return;

                debugLog('Starting operation:', runId, details);

                this.operations[runId] = {
                    runId,
                    jobId: details.jobId || null,
                    jobTitle: details.jobTitle || 'Unknown',
                    action: details.action || 'pipeline',
                    status: 'running',
                    logs: [],
                    layerStatus: {},
                    startedAt: Date.now(),
                    completedAt: null,
                    error: null,
                    // Backend tracking
                    backendStats: {
                        claudeCli: 0,
                        langchain: 0,
                        claudeCliCost: 0,
                        langchainCost: 0
                    }
                };

                this.activeRunId = runId;
                this._cleanup();
                this._saveState();
            },

            /**
             * Complete an operation
             * @param {string} runId - The operation run ID
             * @param {string} status - 'completed' or 'failed'
             * @param {string} error - Error message if failed
             */
            completeOperation(runId, status, error = null) {
                if (!runId || !this.operations[runId]) return;

                debugLog('Completing operation:', runId, status);

                this.operations[runId].status = status;
                this.operations[runId].completedAt = Date.now();
                if (error) {
                    this.operations[runId].error = error;
                }

                this._saveStateImmediate();
            },

            /**
             * Add a log entry to an operation
             * @param {string} runId - The operation run ID
             * @param {Object} logEntry - { message, backend, tier, cost_usd, ... }
             */
            addLog(runId, logEntry) {
                if (!runId) return;

                // Create operation if it doesn't exist
                if (!this.operations[runId]) {
                    this.startOperation(runId, {});
                }

                const op = this.operations[runId];

                // Normalize log entry
                const log = {
                    index: op.logs.length,
                    timestamp: logEntry.timestamp || Date.now(),
                    message: logEntry.message || logEntry.text || '',
                    backend: logEntry.backend || this._detectBackend(logEntry.message || logEntry.text || ''),
                    tier: logEntry.tier || null,
                    cost_usd: logEntry.cost_usd || 0,
                    type: logEntry.type || 'info'
                };

                // Add to logs
                op.logs.push(log);

                // Update backend stats
                this._updateBackendStats(op, log);

                // Debounced save
                this._saveState();
            },

            /**
             * Update layer status for an operation
             * @param {string} runId - The operation run ID
             * @param {Object} layerStatus - { layer1: 'running', layer2: 'complete', ... }
             */
            updateLayerStatus(runId, layerStatus) {
                if (!runId || !this.operations[runId]) return;

                this.operations[runId].layerStatus = {
                    ...this.operations[runId].layerStatus,
                    ...layerStatus
                };

                this._saveState();
            },

            /* ======================================================================
               Backend Statistics
               ====================================================================== */

            /**
             * Get backend usage statistics for a specific run
             * @param {string} runId - The run ID to analyze
             * @returns {Object} - { claudeCli, langchain, claudeCliCost, langchainCost, totalCost }
             */
            getBackendStats(runId) {
                const op = this.operations[runId];
                if (!op) {
                    return {
                        claudeCli: 0,
                        langchain: 0,
                        claudeCliCost: 0,
                        langchainCost: 0,
                        totalCost: 0
                    };
                }

                const stats = op.backendStats || { claudeCli: 0, langchain: 0, claudeCliCost: 0, langchainCost: 0 };
                return {
                    ...stats,
                    totalCost: (stats.claudeCliCost || 0) + (stats.langchainCost || 0)
                };
            },

            /**
             * Get Claude CLI call count for a run
             */
            getClaudeCliCount(runId) {
                return this.getBackendStats(runId).claudeCli;
            },

            /**
             * Get LangChain fallback call count for a run
             */
            getLangchainCount(runId) {
                return this.getBackendStats(runId).langchain;
            },

            /**
             * Get total cost for a run
             */
            getTotalCost(runId) {
                return this.getBackendStats(runId).totalCost;
            },

            /**
             * Check if a run has any backend tracking data
             */
            hasBackendData(runId) {
                const stats = this.getBackendStats(runId);
                return stats.claudeCli > 0 || stats.langchain > 0;
            },

            /**
             * Get aggregated backend stats across all operations
             * @returns {Object} - { claudeCli, langchain, claudeCliCost, langchainCost, totalCost }
             */
            getAggregatedStats() {
                let claudeCli = 0, langchain = 0, claudeCliCost = 0, langchainCost = 0;

                for (const op of Object.values(this.operations)) {
                    const stats = op.backendStats || {};
                    claudeCli += stats.claudeCli || 0;
                    langchain += stats.langchain || 0;
                    claudeCliCost += stats.claudeCliCost || 0;
                    langchainCost += stats.langchainCost || 0;
                }

                return {
                    claudeCli,
                    langchain,
                    claudeCliCost,
                    langchainCost,
                    totalCost: claudeCliCost + langchainCost
                };
            },

            /* ======================================================================
               Internal Methods
               ====================================================================== */

            /**
             * Update backend stats from a log entry
             * @private
             */
            _updateBackendStats(op, log) {
                if (!op.backendStats) {
                    op.backendStats = { claudeCli: 0, langchain: 0, claudeCliCost: 0, langchainCost: 0 };
                }

                if (log.backend === 'claude_cli') {
                    op.backendStats.claudeCli++;
                    op.backendStats.claudeCliCost += log.cost_usd || 0;
                } else if (log.backend === 'langchain') {
                    op.backendStats.langchain++;
                    op.backendStats.langchainCost += log.cost_usd || 0;
                }
            },

            /**
             * Detect backend from log message text
             * @private
             */
            _detectBackend(text) {
                if (!text) return null;
                if (text.includes('[Claude CLI]')) return 'claude_cli';
                if (text.includes('[Fallback]') || text.includes('[LangChain]')) return 'langchain';
                return null;
            },

            /**
             * Cleanup old operations to stay within limits
             * @private
             */
            _cleanup() {
                const runIds = Object.keys(this.operations);
                if (runIds.length <= MAX_OPERATIONS) return;

                // Sort by startedAt, oldest first
                runIds.sort((a, b) => {
                    const opA = this.operations[a];
                    const opB = this.operations[b];
                    return (opA.startedAt || 0) - (opB.startedAt || 0);
                });

                // Remove oldest operations (but keep running ones)
                const toRemove = runIds.length - MAX_OPERATIONS;
                let removed = 0;
                for (const runId of runIds) {
                    if (removed >= toRemove) break;
                    if (this.operations[runId].status !== 'running') {
                        delete this.operations[runId];
                        removed++;
                    }
                }

                debugLog(`Cleaned up ${removed} old operations`);
            },

            /**
             * Save state to sessionStorage (debounced)
             * @private
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
             * @private
             */
            _saveStateImmediate() {
                try {
                    const state = {
                        queue: this.queue,
                        operations: this.operations,
                        activeRunId: this.activeRunId
                    };
                    sessionStorage.setItem(EXECUTION_STORAGE_KEY, JSON.stringify(state));
                } catch (e) {
                    console.error('[ExecutionStore] Failed to save state:', e);
                    // If quota exceeded, cleanup and retry
                    if (e.name === 'QuotaExceededError') {
                        this._cleanup();
                    }
                }
            },

            /* ======================================================================
               Debug Utilities
               ====================================================================== */

            /**
             * Debug utility - dump current state
             * Usage: Alpine.store('execution').debugState()
             */
            debugState() {
                const state = {
                    queueVersion: this.queue.version,
                    pendingCount: this.queue.pending.length,
                    runningCount: this.queue.running.length,
                    operationsCount: Object.keys(this.operations).length,
                    activeRunId: this.activeRunId,
                    aggregatedStats: this.getAggregatedStats(),
                    operations: Object.fromEntries(
                        Object.entries(this.operations).map(([id, op]) => [
                            id,
                            {
                                status: op.status,
                                logsCount: op.logs?.length || 0,
                                backendStats: op.backendStats
                            }
                        ])
                    )
                };
                console.log('[ExecutionStore] State:', state);
                return state;
            },

            /**
             * Clear all state
             * Usage: Alpine.store('execution').clearAll()
             */
            clearAll() {
                this.queue = { pending: [], running: [], failed: [], history: [], version: 0 };
                this.operations = {};
                this.activeRunId = null;
                sessionStorage.removeItem(EXECUTION_STORAGE_KEY);
                console.log('[ExecutionStore] State cleared');
            }
        });
    });

    console.log('[ExecutionStore] Module loaded');

})(typeof window !== 'undefined' ? window : this);
