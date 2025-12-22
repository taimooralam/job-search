/**
 * LogPoller - HTTP polling for pipeline log streaming
 *
 * Replaces EventSource SSE streaming with HTTP polling.
 * Enables the "replay + live tail" pattern:
 * 1. On start, fetch all past logs (since=0)
 * 2. Poll every 200ms for new logs
 * 3. Stop polling when status is completed/failed
 *
 * Key features:
 * - Index-based catchup (never miss logs)
 * - 200ms polling for near-instant feel
 * - Automatic completion detection
 * - Layer status updates
 * - Backend attribution (Claude CLI vs LangChain)
 * - Tier tracking (low, middle, high)
 * - Cost tracking per log entry
 * - Direct browser -> runner communication (bypasses Flask proxy for speed)
 * - Dispatches events to execution store for unified state management
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

    // Shared service status coordination between QueuePoller and LogPoller
    // Prevents duplicate toast messages when both pollers detect service unavailability
    // May already be initialized by QueuePoller
    if (!global._pollerServiceStatus) {
        global._pollerServiceStatus = {
            isUnavailable: false,
            lastToastTime: 0,
            toastCooldownMs: 5000  // Don't show duplicate toasts within 5 seconds
        };
    }

    class LogPoller {
        constructor(runId, options = {}) {
            if (!runId) {
                throw new Error('runId is required');
            }

            this.runId = runId;

            // Polling interval (200ms for near-instant feel)
            this.pollInterval = options.pollInterval || 200;
            this.errorInterval = options.errorInterval || 1000;

            // Backoff configuration for service unavailability (502/503)
            this._serviceUnavailableBackoff = 1000;  // Start at 1 second
            this._maxServiceUnavailableBackoff = 30000;  // Max 30 seconds
            this._isServiceUnavailable = false;  // Track if service is currently unavailable

            // Endpoint base - direct to runner service (not Flask proxy)
            // This eliminates Vercel cold-start latency and sync HTTP bottlenecks
            this.endpointBase = options.endpointBase || `${RUNNER_URL}/api/logs`;

            // State tracking
            this.polling = false;
            this.nextIndex = 0;
            this.totalCount = 0;
            this.status = 'unknown';
            this.lastLayerStatus = null;
            this._consecutiveErrors = 0;

            // Callbacks
            this._onLogCallbacks = [];
            this._onCompleteCallbacks = [];
            this._onLayerStatusCallbacks = [];
            this._onErrorCallbacks = [];
            this._onServiceStatusCallbacks = [];

            // Debug mode
            this._debug = options.debug || false;
        }

        /**
         * Register callback for each log entry.
         *
         * @param {function} callback - Function called with (log) for each entry
         *   log = { index: number, message: string, backend: string|null, tier: string|null, cost_usd: number }
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
         * Register callback for service status changes (available/unavailable).
         * Used to show user-friendly messages during service restarts.
         *
         * @param {function} callback - Function called with (isUnavailable, message)
         */
        onServiceStatus(callback) {
            if (typeof callback === 'function') {
                this._onServiceStatusCallbacks.push(callback);
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

            console.log('[LogPoller] Starting poll loop for:', this.runId);
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
            console.log('[LogPoller] Poll loop started for:', this.runId);
            while (this.polling) {
                try {
                    const data = await this._fetchLogs();

                    if (data === null) {
                        // Error occurred, wait and retry with backoff
                        await this._sleep(this._getBackoffInterval());
                        continue;
                    }

                    // Reset error counter on success
                    this._consecutiveErrors = 0;

                    // Emit each log with backend attribution
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
         * Calculate backoff interval for consecutive errors
         * Uses service unavailable backoff for 502/503/network errors
         */
        _getBackoffInterval() {
            // Use dedicated backoff for service unavailability
            if (this._isServiceUnavailable) {
                return this._serviceUnavailableBackoff;
            }

            if (this._consecutiveErrors <= 3) {
                return this.errorInterval;
            }
            // Exponential backoff with max of 10 seconds
            const backoff = this.errorInterval * Math.pow(2, this._consecutiveErrors - 3);
            return Math.min(backoff, 10000);
        }

        /**
         * Internal: Fetch logs from server.
         * Calls runner directly (cross-origin) - no credentials needed.
         *
         * Handles special cases:
         * - 502/503: Service unavailable (deployment restart) - uses exponential backoff
         * - Network/CORS errors: Treated as service unavailable
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

                // Handle service unavailable (502/503 from Traefik during restarts)
                if (response.status === 502 || response.status === 503) {
                    this._dispatchPollEvent('poller:poll-end', { success: false, error: `Service unavailable (${response.status})` });
                    this._handleServiceUnavailable(`Service restarting (${response.status})`);
                    return null;
                }

                // Dispatch poll-end event (success)
                this._dispatchPollEvent('poller:poll-end', { success: true });

                if (response.status === 404) {
                    // Run not found - could be too early or expired
                    this._log('Run not found (404)');
                    this._consecutiveErrors++;
                    return null;
                }

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                // Service is back online - reset backoff and notify
                this._handleServiceRestored();

                return await response.json();

            } catch (error) {
                this._log('Fetch error:', error.message);
                this._consecutiveErrors++;

                // Dispatch poll-end event (failure)
                this._dispatchPollEvent('poller:poll-end', { success: false, error: error.message });

                // Check if this is a network/CORS error (service unavailable)
                if (this._isNetworkOrCorsError(error)) {
                    this._handleServiceUnavailable('Service temporarily unavailable');
                } else {
                    // Notify error listeners for other errors
                    for (const callback of this._onErrorCallbacks) {
                        try {
                            callback(error);
                        } catch (e) {
                            console.error('[LogPoller] Error callback error:', e);
                        }
                    }
                }

                return null;
            }
        }

        /**
         * Check if an error is likely a network or CORS error
         * These occur when the service is completely unreachable
         * @private
         */
        _isNetworkOrCorsError(error) {
            if (!error) return false;
            const message = error.message?.toLowerCase() || '';
            // TypeErrors with 'failed to fetch' indicate network issues
            // CORS errors also manifest as fetch failures
            return error.name === 'TypeError' ||
                   message.includes('failed to fetch') ||
                   message.includes('network') ||
                   message.includes('cors') ||
                   message.includes('load failed');
        }

        /**
         * Handle service unavailable state (502/503 or network errors)
         * Shows toast message and applies exponential backoff
         * Uses shared state to prevent duplicate toasts from multiple pollers
         * @private
         */
        _handleServiceUnavailable(reason) {
            const wasUnavailable = this._isServiceUnavailable;
            this._isServiceUnavailable = true;
            global._pollerServiceStatus.isUnavailable = true;

            // Only show toast on first occurrence (not every retry)
            // Also check shared state to prevent duplicate toasts from QueuePoller
            const now = Date.now();
            const canShowToast = now - global._pollerServiceStatus.lastToastTime > global._pollerServiceStatus.toastCooldownMs;

            if (!wasUnavailable && canShowToast) {
                this._log('Service unavailable:', reason);
                global._pollerServiceStatus.lastToastTime = now;

                // Show user-friendly toast
                if (typeof global.showToast === 'function') {
                    global.showToast('Runner service restarting, please wait...', 'warning');
                }

                // Notify service status listeners
                this._notifyServiceStatus(true, reason);
            }

            // Increase backoff for next retry
            this._serviceUnavailableBackoff = Math.min(
                this._serviceUnavailableBackoff * 2,
                this._maxServiceUnavailableBackoff
            );

            this._log(`Next retry in ${this._serviceUnavailableBackoff}ms`);
        }

        /**
         * Handle service restored after being unavailable
         * Resets backoff and notifies listeners
         * Uses shared state to prevent duplicate toasts from multiple pollers
         * @private
         */
        _handleServiceRestored() {
            if (this._isServiceUnavailable) {
                this._log('Service restored');

                // Only show toast if shared state still shows unavailable
                // (prevents duplicate "reconnected" toasts from multiple pollers)
                const now = Date.now();
                const canShowToast = global._pollerServiceStatus.isUnavailable &&
                                     now - global._pollerServiceStatus.lastToastTime > global._pollerServiceStatus.toastCooldownMs;

                if (canShowToast) {
                    global._pollerServiceStatus.lastToastTime = now;

                    // Show success toast
                    if (typeof global.showToast === 'function') {
                        global.showToast('Runner service reconnected', 'success');
                    }
                }

                // Notify service status listeners
                this._notifyServiceStatus(false, 'Service restored');

                // Reset local state
                this._isServiceUnavailable = false;
                this._serviceUnavailableBackoff = 1000;  // Reset to initial backoff

                // Reset shared state
                global._pollerServiceStatus.isUnavailable = false;
            }
        }

        /**
         * Notify service status listeners
         * @private
         */
        _notifyServiceStatus(isUnavailable, message) {
            for (const callback of this._onServiceStatusCallbacks) {
                try {
                    callback(isUnavailable, message);
                } catch (e) {
                    console.error('[LogPoller] Service status callback error:', e);
                }
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
         * Includes backend attribution, tier, and cost data.
         */
        _emitLog(log) {
            // Normalize log entry with backend attribution
            const rawMessage = log.message || log.text;
            const messageText = typeof rawMessage === 'string'
                ? rawMessage
                : (rawMessage != null ? JSON.stringify(rawMessage) : '');

            const normalizedLog = {
                index: log.index,
                message: messageText,
                backend: log.backend || this._detectBackend(messageText),
                tier: log.tier || null,
                cost_usd: log.cost_usd || 0,
                timestamp: log.timestamp || Date.now()
            };

            for (const callback of this._onLogCallbacks) {
                try {
                    callback(normalizedLog);
                } catch (e) {
                    console.error('[LogPoller] Log callback error:', e);
                }
            }
        }

        /**
         * Internal: Detect backend from log message text
         */
        _detectBackend(text) {
            if (!text) return null;
            if (text.includes('[Claude CLI]')) return 'claude_cli';
            if (text.includes('[Fallback]') || text.includes('[LangChain]')) return 'langchain';
            return null;
        }

        /**
         * Internal: Emit layer status to listeners.
         */
        _emitLayerStatus(layerStatus) {
            // Dispatch to execution store for unified tracking
            if (typeof global.dispatchEvent === 'function') {
                global.dispatchEvent(new CustomEvent('execution:layer-status', {
                    detail: { runId: this.runId, layerStatus }
                }));
            }

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
            // Dispatch to execution store for unified tracking
            if (typeof global.dispatchEvent === 'function') {
                global.dispatchEvent(new CustomEvent('execution:complete', {
                    detail: { runId: this.runId, status, error }
                }));
            }

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
