/**
 * QueuePoller - HTTP polling replacement for WebSocket queue updates
 *
 * This class replaces the complex WebSocket infrastructure with simple HTTP polling.
 * It polls GET /queue/state at configurable intervals and notifies listeners of changes.
 *
 * Key features:
 * - State version tracking for efficient change detection
 * - Adaptive polling: faster when jobs are active (1s), slower when idle (30s)
 * - Automatic retry with backoff on errors
 * - Self-healing: always returns full truth on each poll
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

    class QueuePoller {
        constructor(options = {}) {
            // Polling intervals
            this.activeInterval = options.activeInterval || 1000;  // 1s when jobs active
            this.idleInterval = options.idleInterval || 30000;     // 30s when idle
            this.errorInterval = options.errorInterval || 5000;    // 5s on error

            // Endpoint
            this.endpoint = options.endpoint || '/queue/state';

            // State tracking
            this.polling = false;
            this.lastVersion = null;
            this.lastError = null;
            this.pollCount = 0;

            // Callbacks
            this._onStateCallbacks = [];
            this._onErrorCallbacks = [];
            this._onConnectionCallbacks = [];

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
         * Start polling for queue state.
         */
        start() {
            if (this.polling) {
                this._log('Already polling');
                return;
            }

            this._log('Starting queue polling');
            this.polling = true;
            this._poll();
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
                // Error occurred, use error interval
                interval = this.errorInterval;
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
         * Internal: Fetch state from server.
         */
        async _fetchState() {
            this.pollCount++;

            try {
                const response = await fetch(this.endpoint, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                    },
                    credentials: 'same-origin',
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const state = await response.json();

                // Update connection status
                this._updateConnection(true);
                this.lastError = null;

                // Check if state actually changed (using version)
                const newVersion = state.state_version;
                if (newVersion !== this.lastVersion) {
                    this._log(`State changed: v${this.lastVersion} -> v${newVersion}`);
                    this.lastVersion = newVersion;

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

                // Update connection status
                this._updateConnection(false);

                // Notify error listeners
                for (const callback of this._onErrorCallbacks) {
                    try {
                        callback(error);
                    } catch (e) {
                        console.error('[QueuePoller] Error callback error:', e);
                    }
                }

                return null;
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
