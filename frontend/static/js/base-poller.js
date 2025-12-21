/**
 * BasePoller - Base class for all HTTP pollers
 *
 * Provides consistent error handling, backoff, and lifecycle management.
 * Both QueuePoller and LogPoller extend this class.
 *
 * Features:
 * - Adaptive polling intervals (active/idle/error states)
 * - Exponential backoff on errors with max retries
 * - Connection status tracking
 * - Debug mode support
 * - Clean start/stop lifecycle
 *
 * Usage:
 *   class MyPoller extends BasePoller {
 *       constructor(options) {
 *           super({
 *               endpoint: '/api/my-endpoint',
 *               activeInterval: 1000,
 *               ...options
 *           });
 *       }
 *
 *       async _fetch() {
 *           // Implement fetch logic
 *           return await fetch(this.endpoint);
 *       }
 *
 *       _handleResponse(data) {
 *           // Handle the response data
 *       }
 *   }
 */

(function(global) {
    'use strict';

    // Default configuration
    const DEFAULTS = {
        activeInterval: 1000,     // 1s when actively polling
        idleInterval: 30000,      // 30s when idle
        errorInterval: 5000,      // 5s on error (initial)
        maxRetries: 5,            // Max consecutive errors before backing off
        maxBackoffInterval: 60000, // Max backoff interval (1 minute)
        debug: false
    };

    class BasePoller {
        /**
         * Create a new BasePoller
         * @param {Object} options - Configuration options
         * @param {string} options.endpoint - The endpoint URL to poll
         * @param {number} [options.activeInterval=1000] - Polling interval when active (ms)
         * @param {number} [options.idleInterval=30000] - Polling interval when idle (ms)
         * @param {number} [options.errorInterval=5000] - Initial interval on error (ms)
         * @param {number} [options.maxRetries=5] - Max consecutive errors before exponential backoff
         * @param {number} [options.maxBackoffInterval=60000] - Max backoff interval (ms)
         * @param {boolean} [options.debug=false] - Enable debug logging
         */
        constructor(options = {}) {
            // Merge with defaults
            const config = { ...DEFAULTS, ...options };

            // Core configuration
            this.endpoint = config.endpoint;
            this.activeInterval = config.activeInterval;
            this.idleInterval = config.idleInterval;
            this.errorInterval = config.errorInterval;
            this.maxRetries = config.maxRetries;
            this.maxBackoffInterval = config.maxBackoffInterval;

            // State tracking
            this._polling = false;
            this._timer = null;
            this._isActive = true;  // Start in active mode
            this._retryCount = 0;
            this._consecutiveErrors = 0;
            this._lastError = null;
            this._pollCount = 0;

            // Connection status
            this._connected = false;
            this._lastPollTime = null;
            this._lastSuccessTime = null;

            // Callbacks
            this._errorCallbacks = [];
            this._connectionCallbacks = [];

            // Debug mode
            this._debug = config.debug;
        }

        /* ==========================================================================
           Public API
           ========================================================================== */

        /**
         * Start polling
         */
        start() {
            if (this._polling) {
                this._log('Already polling');
                return;
            }

            this._log('Starting polling');
            this._polling = true;
            this._poll();
        }

        /**
         * Stop polling
         */
        stop() {
            this._log('Stopping polling');
            this._polling = false;

            if (this._timer) {
                clearTimeout(this._timer);
                this._timer = null;
            }
        }

        /**
         * Force an immediate poll (useful after user actions)
         */
        async refresh() {
            this._log('Force refresh requested');
            await this._executePoll();
        }

        /**
         * Switch between active and idle polling intervals
         * @param {boolean} active - True for active (faster) polling
         */
        setActive(active) {
            this._isActive = active;
            this._log(`Polling mode: ${active ? 'active' : 'idle'}`);
        }

        /**
         * Register error callback
         * @param {Function} callback - Called with (error) on poll failure
         */
        onError(callback) {
            if (typeof callback === 'function') {
                this._errorCallbacks.push(callback);
            }
        }

        /**
         * Register connection status callback
         * @param {Function} callback - Called with (connected, lastPollTime) on status change
         */
        onConnection(callback) {
            if (typeof callback === 'function') {
                this._connectionCallbacks.push(callback);
            }
        }

        /**
         * Get current connection status
         */
        get connected() {
            return this._connected;
        }

        /**
         * Get time since last successful poll (ms)
         */
        get lastPollAge() {
            if (!this._lastPollTime) return null;
            return Date.now() - this._lastPollTime;
        }

        /**
         * Get poll count
         */
        get pollCount() {
            return this._pollCount;
        }

        /**
         * Get last error
         */
        get lastError() {
            return this._lastError;
        }

        /* ==========================================================================
           Abstract Methods - Override in subclasses
           ========================================================================== */

        /**
         * Execute the fetch operation
         * Override in subclass to implement actual fetch logic
         * @returns {Promise<Response>} - The fetch response
         */
        async _fetch() {
            throw new Error('_fetch() must be implemented in subclass');
        }

        /**
         * Handle successful response data
         * Override in subclass to process the data
         * @param {*} data - The parsed response data
         * @returns {boolean} - True if data indicates active state (faster polling)
         */
        _handleResponse(data) {
            throw new Error('_handleResponse() must be implemented in subclass');
        }

        /**
         * Determine if response indicates active state (optional override)
         * @param {*} data - The parsed response data
         * @returns {boolean} - True if should use active polling interval
         */
        _isActiveState(data) {
            return this._isActive;
        }

        /* ==========================================================================
           Internal Methods
           ========================================================================== */

        /**
         * Main poll loop
         * @private
         */
        async _poll() {
            if (!this._polling) return;

            const isActive = await this._executePoll();

            // Determine next interval based on state
            let interval;
            if (this._lastError) {
                // Error occurred - use backoff interval
                interval = this._getBackoffInterval();
            } else if (isActive) {
                // Active state - poll faster
                interval = this.activeInterval;
            } else {
                // Idle state - poll slower
                interval = this.idleInterval;
            }

            // Schedule next poll
            if (this._polling) {
                this._timer = setTimeout(() => this._poll(), interval);
            }
        }

        /**
         * Execute a single poll
         * @private
         * @returns {Promise<boolean>} - True if in active state
         */
        async _executePoll() {
            this._pollCount++;
            this._lastPollTime = Date.now();

            try {
                // Dispatch poll start event
                this._dispatchEvent('poller:poll-start');

                const response = await this._fetch();

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();

                // Success - reset error state
                this._consecutiveErrors = 0;
                this._lastError = null;
                this._lastSuccessTime = Date.now();
                this._updateConnection(true);

                // Dispatch poll end event (success)
                this._dispatchEvent('poller:poll-end', { success: true });

                // Let subclass handle the response
                this._handleResponse(data);

                // Return active state for interval calculation
                return this._isActiveState(data);

            } catch (error) {
                this._consecutiveErrors++;
                this._lastError = error;
                this._log('Poll error:', error.message);

                // Update connection status
                this._updateConnection(false);

                // Dispatch poll end event (failure)
                this._dispatchEvent('poller:poll-end', { success: false, error: error.message });

                // Notify error callbacks
                this._notifyError(error);

                return false;
            }
        }

        /**
         * Calculate backoff interval based on consecutive errors
         * Uses exponential backoff with a cap
         * @private
         * @returns {number} - Backoff interval in ms
         */
        _getBackoffInterval() {
            if (this._consecutiveErrors <= this.maxRetries) {
                return this.errorInterval;
            }

            // Exponential backoff: errorInterval * 2^(errors - maxRetries)
            const exponent = this._consecutiveErrors - this.maxRetries;
            const backoff = this.errorInterval * Math.pow(2, exponent);
            return Math.min(backoff, this.maxBackoffInterval);
        }

        /**
         * Update connection status and notify listeners
         * @private
         * @param {boolean} connected - Connection status
         */
        _updateConnection(connected) {
            const wasConnected = this._connected;
            this._connected = connected;

            // Only notify on status change
            if (wasConnected !== connected) {
                this._log(`Connection status: ${connected ? 'connected' : 'disconnected'}`);
                for (const callback of this._connectionCallbacks) {
                    try {
                        callback(connected, this._lastPollTime);
                    } catch (e) {
                        console.error('[BasePoller] Connection callback error:', e);
                    }
                }
            }
        }

        /**
         * Notify error callbacks
         * @private
         * @param {Error} error - The error
         */
        _notifyError(error) {
            for (const callback of this._errorCallbacks) {
                try {
                    callback(error);
                } catch (e) {
                    console.error('[BasePoller] Error callback error:', e);
                }
            }
        }

        /**
         * Dispatch custom event
         * @private
         * @param {string} eventName - Event name
         * @param {Object} detail - Event detail
         */
        _dispatchEvent(eventName, detail = {}) {
            if (typeof global.dispatchEvent === 'function') {
                global.dispatchEvent(new CustomEvent(eventName, {
                    detail: { poller: this.constructor.name, ...detail }
                }));
            }
        }

        /**
         * Debug logging
         * @private
         */
        _log(...args) {
            if (this._debug) {
                const name = this.constructor.name || 'BasePoller';
                console.log(`[${name}]`, ...args);
            }
        }
    }

    // Export
    global.BasePoller = BasePoller;

    console.log('[BasePoller] Base polling class loaded');

})(typeof window !== 'undefined' ? window : this);
