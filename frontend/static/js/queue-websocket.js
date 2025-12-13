/**
 * Queue WebSocket Client
 *
 * Manages WebSocket connection to the queue service for real-time updates.
 * Provides automatic reconnection with exponential backoff.
 */

class QueueWebSocket {
    constructor() {
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
    }

    /**
     * Get WebSocket URL based on current location
     */
    getWsUrl() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        return `${protocol}//${window.location.host}/ws/queue`;
    }

    /**
     * Connect to WebSocket server
     */
    connect() {
        if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
            return;
        }

        this.isConnecting = true;
        const url = this.getWsUrl();
        console.log('[QueueWS] Connecting to:', url);

        try {
            this.ws = new WebSocket(url);

            this.ws.onopen = () => {
                console.log('[QueueWS] Connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.emit('connected');

                // Start ping interval
                this.startPingInterval();

                // Send any queued messages
                while (this.messageQueue.length > 0) {
                    const msg = this.messageQueue.shift();
                    this.send(msg);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (e) {
                    console.error('[QueueWS] Error parsing message:', e);
                }
            };

            this.ws.onclose = (event) => {
                console.log('[QueueWS] Disconnected:', event.code, event.reason);
                this.isConnecting = false;
                this.stopPingInterval();
                this.emit('disconnected');

                if (this.shouldReconnect) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                console.error('[QueueWS] Error:', error);
                this.emit('error', error);
            };

        } catch (error) {
            console.error('[QueueWS] Connection error:', error);
            this.isConnecting = false;
            this.scheduleReconnect();
        }
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
                this.emit('error', payload);
                break;

            case 'pong':
                // Keepalive response, no action needed
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
     * Start ping interval for keepalive
     */
    startPingInterval() {
        this.stopPingInterval();
        this.pingInterval = setInterval(() => {
            if (this.ws?.readyState === WebSocket.OPEN) {
                this.send({ type: 'ping' });
            }
        }, 30000); // Ping every 30 seconds
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
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[QueueWS] Max reconnect attempts reached');
            this.emit('max_reconnects');
            return;
        }

        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
            this.maxReconnectDelay
        );

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
