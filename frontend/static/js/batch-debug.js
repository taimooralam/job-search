/**
 * BatchDebug - Debug logging utility for batch processing operations
 *
 * Enable debugging by running in browser console:
 *   BatchDebug.enable()
 *
 * Disable debugging:
 *   BatchDebug.disable()
 *
 * Categories:
 *   - SSE: Server-Sent Events connection and messages
 *   - QUEUE: Queue state changes and synthetic events
 *   - BATCH: Batch operation lifecycle (start, progress, complete)
 *   - PROGRESS: Progress badge and panel updates
 */

const BatchDebug = {
    enabled: localStorage.getItem('batch_debug') === 'true',

    /**
     * Log a debug message with category and optional data
     * @param {string} category - Log category (SSE, QUEUE, BATCH, PROGRESS)
     * @param {string} message - Log message
     * @param {any} data - Optional data to log
     */
    log(category, message, data = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString().substr(11, 12);
        const prefix = `[${timestamp}] [BATCH:${category}]`;

        if (data !== null && data !== undefined) {
            console.log(prefix, message, data);
        } else {
            console.log(prefix, message);
        }
    },

    /**
     * Log an error message (always shown when debug is enabled)
     * @param {string} category - Log category
     * @param {string} message - Error message
     * @param {Error|any} error - Error object or data
     */
    error(category, message, error = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString().substr(11, 12);
        const prefix = `[${timestamp}] [BATCH:${category}:ERROR]`;

        if (error) {
            console.error(prefix, message, error);
        } else {
            console.error(prefix, message);
        }
    },

    /**
     * Log a warning message
     * @param {string} category - Log category
     * @param {string} message - Warning message
     * @param {any} data - Optional data
     */
    warn(category, message, data = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString().substr(11, 12);
        const prefix = `[${timestamp}] [BATCH:${category}:WARN]`;

        if (data !== null && data !== undefined) {
            console.warn(prefix, message, data);
        } else {
            console.warn(prefix, message);
        }
    },

    /**
     * Enable debug logging
     */
    enable() {
        this.enabled = true;
        localStorage.setItem('batch_debug', 'true');
        console.log('[BatchDebug] Debug logging ENABLED. Refresh the page to see all debug logs.');
        console.log('[BatchDebug] Categories: SSE, QUEUE, BATCH, PROGRESS');
        console.log('[BatchDebug] Run BatchDebug.disable() to turn off.');
    },

    /**
     * Disable debug logging
     */
    disable() {
        this.enabled = false;
        localStorage.removeItem('batch_debug');
        console.log('[BatchDebug] Debug logging DISABLED.');
    },

    /**
     * Check if debug is enabled
     * @returns {boolean}
     */
    isEnabled() {
        return this.enabled;
    },

    /**
     * Log the current state of the batch operation
     */
    logState() {
        if (!this.enabled) return;

        console.group('[BatchDebug] Current State');

        // Log Alpine queue store if available
        if (window.Alpine && Alpine.store('queue')) {
            console.log('Queue Store:', JSON.parse(JSON.stringify(Alpine.store('queue'))));
        } else {
            console.log('Queue Store: Not initialized');
        }

        // Log Alpine CLI store if available
        if (window.Alpine && Alpine.store('cli')) {
            const cliStore = Alpine.store('cli');
            console.log('CLI Store runs:', Object.keys(cliStore.runs || {}).length);
        }

        // Log batch operation state if available
        if (typeof batchOperationState !== 'undefined') {
            console.log('Batch Operation State:', {
                active: batchOperationState.active,
                total: batchOperationState.totalJobs,
                completed: batchOperationState.completedJobs,
                cancelled: batchOperationState.cancelled,
                jobCount: batchOperationState.jobStatuses?.size || 0
            });
        }

        // Log active SSE connections
        if (typeof activeBatchSSE !== 'undefined' && activeBatchSSE) {
            console.log('Active SSE Connection:', {
                url: activeBatchSSE.url,
                readyState: activeBatchSSE.readyState
            });
        } else {
            console.log('Active SSE Connection: None');
        }

        console.groupEnd();
    }
};

// Expose globally
window.BatchDebug = BatchDebug;

// Log initialization if debug is already enabled
if (BatchDebug.enabled) {
    console.log('[BatchDebug] Debug logging is ENABLED (from localStorage)');
}
