/**
 * Queue Store - Alpine.js Reactive State
 *
 * Manages queue state and syncs with WebSocket updates.
 * Provides reactive data for UI components across all pages.
 */

document.addEventListener('alpine:init', () => {
    Alpine.store('queue', {
        // Connection state
        connected: false,
        connecting: false,
        error: null,

        // Queue data
        pending: [],
        running: [],
        failed: [],
        history: [],

        // UI state
        queueDropdownOpen: false,
        failedDropdownOpen: false,

        // Computed properties
        get pendingCount() {
            return this.pending.length;
        },

        get runningCount() {
            return this.running.length;
        },

        get failedCount() {
            return this.failed.length;
        },

        get totalActive() {
            return this.pendingCount + this.runningCount;
        },

        get hasRunning() {
            return this.runningCount > 0;
        },

        get hasFailed() {
            return this.failedCount > 0;
        },

        // Get queue item by job ID
        getItemByJobId(jobId) {
            // Check running first
            let item = this.running.find(i => i.job_id === jobId);
            if (item) return { ...item, queueStatus: 'running' };

            // Then pending
            item = this.pending.find(i => i.job_id === jobId);
            if (item) return { ...item, queueStatus: 'pending' };

            // Then failed
            item = this.failed.find(i => i.job_id === jobId);
            if (item) return { ...item, queueStatus: 'failed' };

            return null;
        },

        // Get queue position for a job
        getPosition(jobId) {
            const idx = this.pending.findIndex(i => i.job_id === jobId);
            return idx >= 0 ? idx + 1 : null;
        },

        // Initialize and connect
        init() {
            if (!window.queueWebSocket) {
                console.warn('[QueueStore] WebSocket client not available');
                return;
            }

            this.connecting = true;

            // Set up event handlers
            window.queueWebSocket.on('connected', () => {
                this.connected = true;
                this.connecting = false;
                this.error = null;
            });

            window.queueWebSocket.on('disconnected', () => {
                this.connected = false;
                this.connecting = false;
            });

            window.queueWebSocket.on('error', (err) => {
                this.error = err?.message || 'Connection error';
            });

            window.queueWebSocket.on('queue_state', (state) => {
                this.updateState(state);
            });

            window.queueWebSocket.on('queue_update', (update) => {
                this.handleUpdate(update);
            });

            window.queueWebSocket.on('action_result', (result) => {
                this.handleActionResult(result);
            });

            // Connect
            window.queueWebSocket.connect();
        },

        // Update full state
        updateState(state) {
            this.pending = state.pending || [];
            this.running = state.running || [];
            this.failed = state.failed || [];
            this.history = state.history || [];
        },

        // Handle incremental update
        handleUpdate(update) {
            const { action, item } = update;

            switch (action) {
                case 'added':
                    // New item added to pending
                    if (!this.pending.find(i => i.queue_id === item.queue_id)) {
                        this.pending.push(item);
                    }
                    break;

                case 'started':
                    // Item moved from pending to running
                    this.pending = this.pending.filter(i => i.queue_id !== item.queue_id);
                    if (!this.running.find(i => i.queue_id === item.queue_id)) {
                        this.running.push(item);
                    }
                    // Trigger event for UI components
                    this.dispatchJobStarted(item.job_id, item.run_id);
                    break;

                case 'completed':
                    // Item completed
                    this.running = this.running.filter(i => i.queue_id !== item.queue_id);
                    // Add to history (keep limited)
                    this.history.unshift(item);
                    if (this.history.length > 20) {
                        this.history = this.history.slice(0, 20);
                    }
                    // Trigger event for UI components
                    this.dispatchJobCompleted(item.job_id);
                    break;

                case 'failed':
                    // Item failed
                    this.running = this.running.filter(i => i.queue_id !== item.queue_id);
                    if (!this.failed.find(i => i.queue_id === item.queue_id)) {
                        this.failed.push(item);
                    }
                    // Trigger event for UI components
                    this.dispatchJobFailed(item.job_id, item.error);
                    break;

                case 'cancelled':
                    // Item cancelled
                    this.pending = this.pending.filter(i => i.queue_id !== item.queue_id);
                    this.running = this.running.filter(i => i.queue_id !== item.queue_id);
                    break;

                case 'retried':
                    // Item moved from failed to pending
                    this.failed = this.failed.filter(i => i.queue_id !== item.queue_id);
                    if (!this.pending.find(i => i.queue_id === item.queue_id)) {
                        this.pending.push(item);
                    }
                    break;

                case 'dismissed':
                    // Item removed from failed
                    this.failed = this.failed.filter(i => i.queue_id !== item.queue_id);
                    break;
            }
        },

        // Handle action result
        handleActionResult(result) {
            const { action, success, queue_id } = result;

            if (!success) {
                console.warn(`[QueueStore] Action ${action} failed for ${queue_id}`);
            }
        },

        // Actions
        retry(queueId) {
            window.queueWebSocket?.retry(queueId);
        },

        cancel(queueId) {
            window.queueWebSocket?.cancel(queueId);
        },

        dismiss(queueId) {
            window.queueWebSocket?.dismiss(queueId);
        },

        refresh() {
            window.queueWebSocket?.refresh();
        },

        // Toggle dropdowns
        toggleQueueDropdown() {
            this.queueDropdownOpen = !this.queueDropdownOpen;
            if (this.queueDropdownOpen) {
                this.failedDropdownOpen = false;
            }
        },

        toggleFailedDropdown() {
            this.failedDropdownOpen = !this.failedDropdownOpen;
            if (this.failedDropdownOpen) {
                this.queueDropdownOpen = false;
            }
        },

        closeDropdowns() {
            this.queueDropdownOpen = false;
            this.failedDropdownOpen = false;
        },

        // Dispatch custom events for other components
        dispatchJobStarted(jobId, runId) {
            window.dispatchEvent(new CustomEvent('queue:job-started', {
                detail: { jobId, runId }
            }));
        },

        dispatchJobCompleted(jobId) {
            window.dispatchEvent(new CustomEvent('queue:job-completed', {
                detail: { jobId }
            }));
        },

        dispatchJobFailed(jobId, error) {
            window.dispatchEvent(new CustomEvent('queue:job-failed', {
                detail: { jobId, error }
            }));
        },

        // Format time ago
        formatTimeAgo(dateStr) {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            const now = new Date();
            const seconds = Math.floor((now - date) / 1000);

            if (seconds < 60) return 'just now';
            if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
            if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
            return `${Math.floor(seconds / 86400)}d ago`;
        },

        // Truncate text
        truncate(text, maxLength = 30) {
            if (!text || text.length <= maxLength) return text;
            return text.substring(0, maxLength) + '...';
        }
    });

    // Initialize store when page loads
    Alpine.store('queue').init();
});
