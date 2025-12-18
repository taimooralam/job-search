/**
 * LogPoller - HTTP polling replacement for SSE log streaming
 *
 * This class replaces EventSource SSE streaming with HTTP polling.
 * It enables the "replay + live tail" pattern:
 * 1. On start, fetch all past logs (since=0)
 * 2. Poll every 200ms for new logs
 * 3. Stop polling when status is completed/failed
 *
 * Key features:
 * - Index-based catchup (never miss logs)
 * - 200ms polling for near-instant feel
 * - Automatic completion detection
 * - Layer status updates
 * - Direct browser → runner communication (bypasses Flask proxy for speed)
 *
 * Architecture Note:
 * Log polling calls the runner service DIRECTLY (not through Flask proxy).
 * This eliminates Vercel cold-start latency and synchronous HTTP bottlenecks.
 * The log endpoint is public (no auth required) - run IDs are unguessable UUIDs.
 *
 * Usage:
 *   const poller = new LogPoller('op_generate-cv_abc123');
 *   poller.onLog((log) => console.log(log.message));
 *   poller.onComplete((status) => console.log('Done:', status));
 *   poller.onLayerStatus((layers) => console.log('Layers:', layers));
 *   poller.start();
 *   // Later: poller.stop();
 */

(function(global) {
    'use strict';

    // Direct runner URL - bypasses Flask proxy for faster log polling
    // The runner service has CORS enabled for the Vercel domain
    const RUNNER_URL = global.RUNNER_URL || 'https://runner.uqab.digital';

    class LogPoller {
        constructor(runId, options = {}) {
            if (!runId) {
                throw new Error('runId is required');
            }

            this.runId = runId;

            // Polling interval (200ms for near-instant feel)
            this.pollInterval = options.pollInterval || 200;
            this.errorInterval = options.errorInterval || 1000;

            // Endpoint base - direct to runner service (not Flask proxy)
            // This eliminates Vercel cold-start latency and sync HTTP bottlenecks
            this.endpointBase = options.endpointBase || `${RUNNER_URL}/api/logs`;

            // State tracking
            this.polling = false;
            this.nextIndex = 0;
            this.totalCount = 0;
            this.status = 'unknown';
            this.lastLayerStatus = null;

            // Callbacks
            this._onLogCallbacks = [];
            this._onCompleteCallbacks = [];
            this._onLayerStatusCallbacks = [];
            this._onErrorCallbacks = [];

            // Debug mode
            this._debug = options.debug || false;
        }

        /**
         * Register callback for each log entry.
         *
         * @param {function} callback - Function called with (log) for each entry
         *   log = { index: number, message: string }
         */
        onLog(callback) {
            if (typeof callback === 'function') {
                this._onLogCallbacks.push(callback);
            }
        }

        /**
         * Register callback for completion.
         *
         * @param {function} callback - Function called with (status, error) when done
         */
        onComplete(callback) {
            if (typeof callback === 'function') {
                this._onCompleteCallbacks.push(callback);
            }
        }

        /**
         * Register callback for layer status updates.
         *
         * @param {function} callback - Function called with (layerStatus) on changes
         */
        onLayerStatus(callback) {
            if (typeof callback === 'function') {
                this._onLayerStatusCallbacks.push(callback);
            }
        }

        /**
         * Register callback for errors.
         *
         * @param {function} callback - Function called with (error) on poll failure
         */
        onError(callback) {
            if (typeof callback === 'function') {
                this._onErrorCallbacks.push(callback);
            }
        }

        /**
         * Start polling for logs.
         * Will first fetch all existing logs, then continue polling for new ones.
         */
        async start() {
            if (this.polling) {
                this._log('Already polling');
                return;
            }

            this._log('Starting log polling for', this.runId);
            this.polling = true;

            // Start the poll loop
            await this._pollLoop();
        }

        /**
         * Stop polling.
         */
        stop() {
            this._log('Stopping log polling');
            this.polling = false;
        }

        /**
         * Get current status.
         */
        get currentStatus() {
            return this.status;
        }

        /**
         * Get total logs received.
         */
        get logsReceived() {
            return this.nextIndex;
        }

        /**
         * Internal: Main poll loop.
         */
        async _pollLoop() {
            while (this.polling) {
                try {
                    const data = await this._fetchLogs();

                    if (data === null) {
                        // Error occurred, wait and retry
                        await this._sleep(this.errorInterval);
                        continue;
                    }

                    // Emit each log
                    for (const log of data.logs) {
                        this._emitLog(log);
                    }

                    // Update index for next poll
                    this.nextIndex = data.next_index;
                    this.totalCount = data.total_count;
                    this.status = data.status;

                    // Emit layer status if changed
                    if (data.layer_status && Object.keys(data.layer_status).length > 0) {
                        const layerJson = JSON.stringify(data.layer_status);
                        if (layerJson !== this.lastLayerStatus) {
                            this.lastLayerStatus = layerJson;
                            this._emitLayerStatus(data.layer_status);
                        }
                    }

                    // Check for completion
                    // IMPORTANT: Don't stop until all logs are fetched, even if status is completed
                    // This prevents the race condition where pipeline finishes fast but we haven't
                    // fetched all logs yet (e.g., 150 logs but only fetched first 100)
                    if (data.status === 'completed' || data.status === 'failed') {
                        const allLogsFetched = this.nextIndex >= this.totalCount;

                        if (allLogsFetched) {
                            this._log('Run completed with status:', data.status, `(${this.nextIndex}/${this.totalCount} logs)`);
                            this._emitComplete(data.status, data.error);
                            this.stop();
                            break;
                        } else {
                            // Status is completed but we haven't fetched all logs yet
                            // Continue polling until we have all logs
                            this._log('Run completed but still fetching logs:', `${this.nextIndex}/${this.totalCount}`);
                        }
                    }

                    // Wait before next poll
                    await this._sleep(this.pollInterval);

                } catch (e) {
                    this._log('Unexpected error:', e);
                    await this._sleep(this.errorInterval);
                }
            }
        }

        /**
         * Internal: Fetch logs from server.
         * Calls runner directly (cross-origin) - no credentials needed.
         */
        async _fetchLogs() {
            const url = `${this.endpointBase}/${this.runId}?since=${this.nextIndex}&limit=100`;

            // Dispatch poll-start event for visual indicator
            this._dispatchPollEvent('poller:poll-start');

            try {
                // Note: No 'credentials' option for cross-origin requests to runner
                // The log endpoint is public (no auth required)
                const response = await fetch(url, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                    mode: 'cors',
                });

                // Dispatch poll-end event (success)
                this._dispatchPollEvent('poller:poll-end', { success: true });

                if (response.status === 404) {
                    // Run not found - could be too early or expired
                    this._log('Run not found (404)');
                    return null;
                }

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                return await response.json();

            } catch (error) {
                this._log('Fetch error:', error.message);

                // Dispatch poll-end event (failure)
                this._dispatchPollEvent('poller:poll-end', { success: false, error: error.message });

                // Notify error listeners
                for (const callback of this._onErrorCallbacks) {
                    try {
                        callback(error);
                    } catch (e) {
                        console.error('[LogPoller] Error callback error:', e);
                    }
                }

                return null;
            }
        }

        /**
         * Internal: Dispatch polling events for UI feedback.
         */
        _dispatchPollEvent(eventName, detail = {}) {
            if (typeof global.dispatchEvent === 'function') {
                global.dispatchEvent(new CustomEvent(eventName, {
                    detail: { runId: this.runId, ...detail }
                }));
            }
        }

        /**
         * Internal: Emit log to listeners.
         */
        _emitLog(log) {
            for (const callback of this._onLogCallbacks) {
                try {
                    callback(log);
                } catch (e) {
                    console.error('[LogPoller] Log callback error:', e);
                }
            }
        }

        /**
         * Internal: Emit layer status to listeners.
         */
        _emitLayerStatus(layerStatus) {
            for (const callback of this._onLayerStatusCallbacks) {
                try {
                    callback(layerStatus);
                } catch (e) {
                    console.error('[LogPoller] Layer status callback error:', e);
                }
            }
        }

        /**
         * Internal: Emit completion to listeners.
         */
        _emitComplete(status, error) {
            for (const callback of this._onCompleteCallbacks) {
                try {
                    callback(status, error);
                } catch (e) {
                    console.error('[LogPoller] Complete callback error:', e);
                }
            }
        }

        /**
         * Internal: Sleep helper.
         */
        _sleep(ms) {
            return new Promise(resolve => setTimeout(resolve, ms));
        }

        /**
         * Internal: Debug logging.
         */
        _log(...args) {
            if (this._debug) {
                console.log('[LogPoller]', ...args);
            }
        }
    }

    // Export
    global.LogPoller = LogPoller;

    console.log('[LogPoller] Log polling module loaded');

})(typeof window !== 'undefined' ? window : this);
