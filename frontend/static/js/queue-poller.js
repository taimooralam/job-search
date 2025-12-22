/**
 * QueuePoller - HTTP polling for queue state updates
 *
 * Extends BasePoller with queue-specific functionality.
 * Polls GET /queue/state at configurable intervals and notifies listeners of changes.
 *
 * Key features:
 * - State version tracking for efficient change detection
 * - Adaptive polling: faster when jobs are active (1s), slower when idle (30s)
 * - Automatic retry with backoff on errors
 * - Self-healing: always returns full truth on each poll
 * - Direct browser -> runner communication (bypasses Flask proxy for speed)
 * - Dispatches events to execution store for unified state management
 *
 * Architecture Note:
 * Queue polling calls the runner service DIRECTLY (not through Flask proxy).
 * This eliminates Vercel cold-start latency and synchronous HTTP bottlenecks.
 * The queue state endpoint is public (no auth required).
 *
 * Usage:
 *   const poller = new QueuePoller();
 *   poller.onState((state) => {
 *       // Update UI with new state
 *       console.log('Queue state:', state);
 *   });
 *   poller.start();
 *   // Later: poller.stop();
 */

(function(global) {
    'use strict';

    // Direct runner URL - bypasses Flask proxy for faster queue state polling
    // The runner service has CORS enabled for the Vercel domain
    const RUNNER_URL = global.RUNNER_URL || 'https://runner.uqab.digital';

    // Shared service status coordination between QueuePoller and LogPoller
    // Prevents duplicate toast messages when both pollers detect service unavailability
    if (!global._pollerServiceStatus) {
        global._pollerServiceStatus = {
            isUnavailable: false,
            lastToastTime: 0,
            toastCooldownMs: 5000  // Don't show duplicate toasts within 5 seconds
        };
    }

    /**
     * QueuePoller - Extends BasePoller for queue state polling
     */
    class QueuePoller {
        constructor(options = {}) {
            // Polling intervals
            this.activeInterval = options.activeInterval || 1000;  // 1s when jobs active
            this.idleInterval = options.idleInterval || 30000;     // 30s when idle
            this.errorInterval = options.errorInterval || 5000;    // 5s on error

            // Backoff configuration for service unavailability (502/503)
            this._serviceUnavailableBackoff = 1000;  // Start at 1 second
            this._maxServiceUnavailableBackoff = 30000;  // Max 30 seconds
            this._isServiceUnavailable = false;  // Track if service is currently unavailable

            // Endpoint - direct to runner service (not Flask proxy)
            // This eliminates Vercel cold-start latency and sync HTTP bottlenecks
            this.endpoint = options.endpoint || `${RUNNER_URL}/queue/state`;

            // State tracking
            this.polling = false;
            this.lastVersion = null;
            this.lastError = null;
            this.pollCount = 0;
            this._consecutiveErrors = 0;

            // Callbacks
            this._onStateCallbacks = [];
            this._onErrorCallbacks = [];
            this._onConnectionCallbacks = [];
            this._onServiceStatusCallbacks = [];

            // Connection status for UI indicator
            this._connected = false;
            this._lastPollTime = null;

            // Debug mode
            this._debug = options.debug || false;
        }

        /**
         * Register callback for state updates.
         * Callback receives full queue state on each change.
         *
         * @param {function} callback - Function called with (state) on each update
         */
        onState(callback) {
            if (typeof callback === 'function') {
                this._onStateCallbacks.push(callback);
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
         * Register callback for connection status changes.
         *
         * @param {function} callback - Function called with (connected, lastPollTime)
         */
        onConnection(callback) {
            if (typeof callback === 'function') {
                this._onConnectionCallbacks.push(callback);
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
         * Start polling for queue state.
         * Returns a Promise for consistent API with LogPoller.
         */
        async start() {
            if (this.polling) {
                this._log('Already polling');
                return;
            }

            this._log('Starting queue polling');
            this.polling = true;
            await this._poll();
        }

        /**
         * Stop polling.
         */
        stop() {
            this._log('Stopping queue polling');
            this.polling = false;
        }

        /**
         * Force an immediate poll (useful after user actions).
         */
        async refresh() {
            this._log('Force refresh requested');
            await this._fetchState();
        }

        /**
         * Get current connection status.
         */
        get connected() {
            return this._connected;
        }

        /**
         * Get time since last successful poll.
         */
        get lastPollAge() {
            if (!this._lastPollTime) return null;
            return Date.now() - this._lastPollTime;
        }

        /**
         * Internal: Main poll loop.
         */
        async _poll() {
            if (!this.polling) return;

            const state = await this._fetchState();

            // Determine next poll interval based on state
            let interval;
            if (state === null) {
                // Error occurred, use exponential backoff
                interval = this._getBackoffInterval();
            } else if (state.running.length > 0 || state.pending.length > 0) {
                // Jobs active, poll faster
                interval = this.activeInterval;
            } else {
                // Idle, poll slower
                interval = this.idleInterval;
            }

            // Schedule next poll
            if (this.polling) {
                setTimeout(() => this._poll(), interval);
            }
        }

        /**
         * Calculate backoff interval for errors
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
            // Exponential backoff with max of 60 seconds
            const backoff = this.errorInterval * Math.pow(2, this._consecutiveErrors - 3);
            return Math.min(backoff, 60000);
        }

        /**
         * Internal: Fetch state from server.
         * Calls runner directly (cross-origin) - no credentials needed.
         *
         * Handles special cases:
         * - 502/503: Service unavailable (deployment restart) - uses exponential backoff
         * - Network/CORS errors: Treated as service unavailable
         */
        async _fetchState() {
            this.pollCount++;

            try {
                // Note: No 'credentials' option for cross-origin requests to runner
                // The queue state endpoint is public (no auth required)
                const response = await fetch(this.endpoint, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                    mode: 'cors',
                });

                // Handle service unavailable (502/503 from Traefik during restarts)
                if (response.status === 502 || response.status === 503) {
                    this._handleServiceUnavailable(`Service restarting (${response.status})`);
                    return null;
                }

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const state = await response.json();

                // Service is back online - reset backoff and notify
                this._handleServiceRestored();

                // Update connection status
                this._updateConnection(true);
                this.lastError = null;
                this._consecutiveErrors = 0;

                // Check if state actually changed (using version)
                const newVersion = state.state_version;
                if (newVersion !== this.lastVersion) {
                    this._log(`State changed: v${this.lastVersion} -> v${newVersion}`);
                    this.lastVersion = newVersion;

                    // Dispatch to execution store for unified tracking
                    if (typeof global.dispatchEvent === 'function') {
                        global.dispatchEvent(new CustomEvent('execution:queue-update', {
                            detail: state
                        }));
                    }

                    // Notify all state listeners
                    for (const callback of this._onStateCallbacks) {
                        try {
                            callback(state);
                        } catch (e) {
                            console.error('[QueuePoller] Callback error:', e);
                        }
                    }
                } else {
                    this._log(`No change (v${newVersion}), poll #${this.pollCount}`);
                }

                return state;

            } catch (error) {
                this._log('Poll error:', error.message);
                this.lastError = error;
                this._consecutiveErrors++;

                // Check if this is a network/CORS error (service unavailable)
                // These errors have no response status and typically occur during deployments
                if (this._isNetworkOrCorsError(error)) {
                    this._handleServiceUnavailable('Service temporarily unavailable');
                } else {
                    // Update connection status for other errors
                    this._updateConnection(false);

                    // Notify error listeners
                    for (const callback of this._onErrorCallbacks) {
                        try {
                            callback(error);
                        } catch (e) {
                            console.error('[QueuePoller] Error callback error:', e);
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
            // Also check shared state to prevent duplicate toasts from LogPoller
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

            // Update connection status
            this._updateConnection(false);

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
                    console.error('[QueuePoller] Service status callback error:', e);
                }
            }
        }

        /**
         * Internal: Update connection status and notify listeners.
         */
        _updateConnection(connected) {
            const wasConnected = this._connected;
            this._connected = connected;

            if (connected) {
                this._lastPollTime = Date.now();
            }

            // Only notify on status change
            if (wasConnected !== connected) {
                for (const callback of this._onConnectionCallbacks) {
                    try {
                        callback(connected, this._lastPollTime);
                    } catch (e) {
                        console.error('[QueuePoller] Connection callback error:', e);
                    }
                }
            }
        }

        /**
         * Internal: Debug logging.
         */
        _log(...args) {
            if (this._debug) {
                console.log('[QueuePoller]', ...args);
            }
        }
    }

    // Export
    global.QueuePoller = QueuePoller;

    console.log('[QueuePoller] Queue polling module loaded');

})(typeof window !== 'undefined' ? window : this);
