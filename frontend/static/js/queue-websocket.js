/**
 * Queue WebSocket Client
 *
 * Manages WebSocket connection to the queue service for real-time updates.
 * Provides automatic reconnection with exponential backoff.
 *
 * Debug Mode:
 * - Enable via: localStorage.setItem('ws_debug', 'true') or ?ws_debug=true
 * - Check history: queueWebSocket.getHistory()
 * - Toggle: queueWebSocket.setDebug(true/false)
 */

class QueueWebSocket {
    constructor() {
        // Debug mode - enabled via localStorage or URL param
        this.debug = localStorage.getItem('ws_debug') === 'true' ||
                     window.location.search.includes('ws_debug=true');

        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.baseReconnectDelay = 1000;
        this.maxReconnectDelay = 30000;
        this.isConnecting = false;
        this.shouldReconnect = true;
        this.pingInterval = null;
        this.eventHandlers = new Map();

        // Queue for messages to send when connected
        this.messageQueue = [];

        // Ping/pong tracking for connection health
        this.lastPingTime = null;
        this.lastPongTime = null;
        this.pongTimeoutMs = 5000; // 5 seconds to receive pong

        // Connection history for debugging
        this.connectionHistory = [];
        this.maxHistoryLength = 20;

        if (this.debug) {
            console.log('[QueueWS] Debug mode enabled');
        }
    }

    /**
     * Debug logging helper - only logs when debug mode is enabled
     */
    _debug(...args) {
        if (this.debug) {
            console.log('[QueueWS DEBUG]', new Date().toISOString(), ...args);
        }
    }

    /**
     * Record event in connection history for debugging
     */
    _recordHistory(event, data = {}) {
        this.connectionHistory.push({
            event,
            timestamp: Date.now(),
            time: new Date().toISOString(),
            ...data
        });

        // Keep history bounded
        if (this.connectionHistory.length > this.maxHistoryLength) {
            this.connectionHistory.shift();
        }
    }

    /**
     * Get connection history (for debugging via console)
     */
    getHistory() {
        return this.connectionHistory;
    }

    /**
     * Enable/disable debug mode
     */
    setDebug(enabled) {
        this.debug = enabled;
        localStorage.setItem('ws_debug', enabled ? 'true' : 'false');
        console.log(`[QueueWS] Debug mode ${enabled ? 'enabled' : 'disabled'}`);
    }

    /**
     * Get WebSocket URL based on current location or runner URL config
     *
     * On Vercel/serverless: Uses RUNNER_WS_URL from window config (direct to runner)
     * On Flask/VPS: Uses current host (proxied through Flask)
     */
    getWsUrl() {
        this._debug('Building WebSocket URL', {
            RUNNER_WS_URL: window.RUNNER_WS_URL,
            protocol: window.location.protocol,
            host: window.location.host
        });

        // Check for explicit runner WebSocket URL (for serverless deployments like Vercel)
        if (window.RUNNER_WS_URL) {
            this._debug('Using explicit RUNNER_WS_URL:', window.RUNNER_WS_URL);
            return window.RUNNER_WS_URL;
        }

        // Default: use current host (works when Flask proxies WebSocket)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws/queue`;
        this._debug('Using derived URL:', url);
        return url;
    }

    /**
     * Check if WebSocket connection would cause mixed content error
     * (ws:// from https:// page is blocked by browsers)
     */
    wouldCauseMixedContent(wsUrl) {
        const isSecurePage = window.location.protocol === 'https:';
        const isInsecureWs = wsUrl.startsWith('ws://');
        return isSecurePage && isInsecureWs;
    }

    /**
     * Connect to WebSocket server
     */
    connect() {
        const connectState = {
            wsState: this.ws?.readyState,
            wsStateText: this._readyStateText(this.ws?.readyState),
            isConnecting: this.isConnecting,
            shouldReconnect: this.shouldReconnect,
            reconnectAttempts: this.reconnectAttempts
        };

        this._debug('connect() called', connectState);

        if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
            this._debug('Skipping connect - already connected/connecting');
            return;
        }

        this.isConnecting = true;
        const url = this.getWsUrl();
        console.log('[QueueWS] Connecting to:', url);

        // Record connection attempt in history
        this._recordHistory('connect_attempt', { url, state: connectState });

        // Check for mixed content (https page + ws:// URL)
        if (this.wouldCauseMixedContent(url)) {
            this._debug('Mixed content detected', {
                pageProtocol: window.location.protocol,
                wsUrl: url
            });
            console.warn('[QueueWS] Mixed content blocked: Cannot connect to ws:// from https:// page.');
            console.warn('[QueueWS] Real-time queue updates disabled. Runner needs HTTPS/WSS for this feature.');
            this._recordHistory('mixed_content_blocked', { url });
            this.isConnecting = false;
            this.shouldReconnect = false;  // Don't keep retrying
            this.emit('error', { message: 'Mixed content: WebSocket requires HTTPS on runner', code: 'MIXED_CONTENT' });
            return;
        }

        try {
            this._debug('Creating WebSocket instance');
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                this._debug('WebSocket opened successfully');
                this._recordHistory('connected', { url });
                console.log('[QueueWS] Connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.emit('connected');

                // Start ping interval
                this.startPingInterval();

                // Send any queued messages
                const queuedCount = this.messageQueue.length;
                while (this.messageQueue.length > 0) {
                    const msg = this.messageQueue.shift();
                    this.send(msg);
                }
                if (queuedCount > 0) {
                    this._debug(`Sent ${queuedCount} queued messages`);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('[QueueWS] Error parsing message:', e);
                    this._debug('Message parse error', { raw: event.data?.substring(0, 200), error: e.message });
                }
            };

            this.ws.onclose = (event) => {
                const closeInfo = {
                    code: event.code,
                    reason: event.reason || '<empty>',
                    wasClean: event.wasClean,
                    url: url
                };

                this._debug('WebSocket closed', closeInfo);
                this._recordHistory('disconnected', closeInfo);

                console.log('[QueueWS] Disconnected:', event.code, event.reason || '<empty string>');

                // Enhanced close code interpretation
                if (event.code === 1006) {
                    console.warn('[QueueWS] Abnormal closure (1006) - possible causes:');
                    console.warn('  - Server down/unreachable');
                    console.warn('  - Network connection interrupted');
                    console.warn('  - Proxy/load balancer timeout');
                    console.warn('  - SSL/TLS handshake failure');
                    this._debug('Code 1006 details', {
                        hint: 'Check if runner service is running and accessible',
                        url: url
                    });
                }

                this.isConnecting = false;
                this.stopPingInterval();
                this.emit('disconnected');

                if (this.shouldReconnect) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                // Note: Browser security limits error info available
                this._debug('WebSocket error event', {
                    type: error.type,
                    readyState: this.ws?.readyState,
                    readyStateText: this._readyStateText(this.ws?.readyState)
                });
                this._recordHistory('error', { type: error.type });
                console.error('[QueueWS] Error:', error);
                this.emit('error', error);
            };

        } catch (error) {
            this._debug('Connection creation failed', {
                error: error.message,
                stack: error.stack
            });
            this._recordHistory('connect_exception', { error: error.message });
            console.error('[QueueWS] Connection error:', error);
            this.isConnecting = false;
            this.scheduleReconnect();
        }
    }

    /**
     * Convert WebSocket readyState to human-readable text
     */
    _readyStateText(state) {
        const states = {
            0: 'CONNECTING',
            1: 'OPEN',
            2: 'CLOSING',
            3: 'CLOSED'
        };
        return states[state] || 'UNKNOWN';
    }

    /**
     * Handle incoming WebSocket message
     */
    handleMessage(data) {
        const { type, payload } = data;

        switch (type) {
            case 'queue_state':
                this.emit('queue_state', payload);
                break;

            case 'queue_update':
                this.emit('queue_update', payload);
                break;

            case 'action_result':
                this.emit('action_result', payload);
                break;

            case 'error':
                console.error('[QueueWS] Server error:', payload.message);
                // Check for permanent errors that shouldn't trigger reconnection
                if (payload.message?.includes('not configured') ||
                    payload.message?.includes('Redis') ||
                    payload.code === 'SERVICE_UNAVAILABLE') {
                    console.warn('[QueueWS] Permanent error detected, disabling reconnection');
                    this.shouldReconnect = false;
                }
                this.emit('error', payload);
                break;

            case 'ping':
                // Server-initiated ping, respond with pong
                this._debug('Received server ping, sending pong');
                this.send({ type: 'pong' });
                break;

            case 'pong':
                // Keepalive response - track for timeout detection
                this.lastPongTime = Date.now();
                this._debug('Received pong', {
                    lastPingTime: this.lastPingTime,
                    lastPongTime: this.lastPongTime,
                    roundTripMs: this.lastPingTime ? this.lastPongTime - this.lastPingTime : null
                });
                break;

            default:
                console.warn('[QueueWS] Unknown message type:', type);
        }
    }

    /**
     * Send message to server
     */
    send(data) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            // Queue message for when connected
            this.messageQueue.push(data);
        }
    }

    /**
     * Request queue retry
     */
    retry(queueId) {
        this.send({ type: 'retry', payload: { queue_id: queueId } });
    }

    /**
     * Request queue cancel
     */
    cancel(queueId) {
        this.send({ type: 'cancel', payload: { queue_id: queueId } });
    }

    /**
     * Request queue dismiss
     */
    dismiss(queueId) {
        this.send({ type: 'dismiss', payload: { queue_id: queueId } });
    }

    /**
     * Request refresh of queue state
     */
    refresh() {
        this.send({ type: 'refresh' });
    }

    /**
     * Force reconnection (close and re-establish connection)
     */
    reconnect() {
        this._debug('Manual reconnect triggered');
        this._recordHistory('manual_reconnect', {});

        // Close existing connection if any
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        this.isConnecting = false;
        this.connect();
    }

    /**
     * Start ping interval for keepalive
     */
    startPingInterval() {
        this.stopPingInterval();

        // Reset ping/pong tracking on fresh connection
        this.lastPingTime = null;
        this.lastPongTime = Date.now(); // Initialize to now to avoid false timeout on first ping

        this.pingInterval = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                // Check if previous pong was received (timeout detection)
                if (this.lastPingTime !== null && this.lastPongTime < this.lastPingTime) {
                    const elapsed = Date.now() - this.lastPingTime;
                    if (elapsed > this.pongTimeoutMs) {
                        console.warn('[QueueWS] Pong timeout detected, reconnecting...');
                        this._debug('Pong timeout', {
                            lastPingTime: this.lastPingTime,
                            lastPongTime: this.lastPongTime,
                            elapsed,
                            timeout: this.pongTimeoutMs
                        });
                        this._recordHistory('pong_timeout', { elapsed });
                        this.reconnect();
                        return;
                    }
                }

                // Send new ping
                this.lastPingTime = Date.now();
                this._debug('Sending ping', { lastPingTime: this.lastPingTime });
                this.send({ type: 'ping' });
            }
        }, 15000); // Ping every 15 seconds
    }

    /**
     * Stop ping interval
     */
    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    /**
     * Schedule reconnection with exponential backoff
     */
    scheduleReconnect() {
        this._debug('scheduleReconnect called', {
            attempts: this.reconnectAttempts,
            maxAttempts: this.maxReconnectAttempts,
            shouldReconnect: this.shouldReconnect
        });

        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[QueueWS] Max reconnect attempts reached');
            this._recordHistory('max_reconnects_reached', {
                attempts: this.reconnectAttempts
            });
            this.emit('max_reconnects');
            return;
        }

        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );

        this._debug('Scheduling reconnect', {
            delay,
            attempt: this.reconnectAttempts + 1,
            formula: `${this.baseReconnectDelay} * 2^${this.reconnectAttempts} = ${delay}ms`
        });
        this._recordHistory('reconnect_scheduled', { delay, attempt: this.reconnectAttempts + 1 });

        console.log(`[QueueWS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);

        setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
        }, delay);
    }

    /**
     * Disconnect from WebSocket server
     */
    disconnect() {
        this.shouldReconnect = false;
        this.stopPingInterval();

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Register event handler
     */
    on(event, handler) {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, []);
        }
        this.eventHandlers.get(event).push(handler);
    }

    /**
     * Remove event handler
     */
    off(event, handler) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            const index = handlers.indexOf(handler);
            if (index > -1) {
                handlers.splice(index, 1);
            }
        }
    }

    /**
     * Emit event to handlers
     */
    emit(event, data) {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (e) {
                    console.error(`[QueueWS] Error in ${event} handler:`, e);
                }
            });
        }
    }

    /**
     * Check if connected
     */
    get isConnected() {
        return this.ws?.readyState === WebSocket.OPEN;
    }
}

// Create singleton instance
window.queueWebSocket = new QueueWebSocket();
