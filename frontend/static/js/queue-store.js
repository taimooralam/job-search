/**
 * Queue Store - Alpine.js Reactive State
 *
 * Manages queue state and syncs with HTTP polling updates.
 * Provides reactive data for UI components across all pages.
 *
 * Uses QueuePoller for reliable state updates (replaces WebSocket).
 */

document.addEventListener('alpine:init', () => {
    Alpine.store('queue', {
        // Connection state
        connected: false,
        connecting: false,
        error: null,
        lastUpdated: null,

        // Queue data
        pending: [],
        running: [],
        failed: [],
        history: [],

        // UI state
        queueDropdownOpen: false,
        failedDropdownOpen: false,

        // Internal: poller instance
        _poller: null,

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

        // Get time since last update (for UI display)
        get lastUpdatedAgo() {
            if (!this.lastUpdated) return null;
            return Date.now() - this.lastUpdated;
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

        // Initialize and start polling
        init() {
            // Check if QueuePoller is available
            if (typeof window.QueuePoller === 'undefined') {
                console.warn('[QueueStore] QueuePoller not available, waiting...');
                // Retry after short delay (script loading order)
                setTimeout(() => this.init(), 100);
                return;
            }

            this.connecting = true;

            // Create poller instance
            this._poller = new window.QueuePoller({
                debug: false, // Set to true for debugging
            });

            // Handle state updates
            this._poller.onState((state) => {
                this.updateState(state);
                this.lastUpdated = Date.now();
            });

            // Handle connection status
            this._poller.onConnection((connected) => {
                this.connected = connected;
                this.connecting = false;
                if (connected) {
                    this.error = null;
                }
            });

            // Handle errors
            this._poller.onError((error) => {
                this.error = error?.message || 'Connection error';
            });

            // Start polling
            this._poller.start();
            console.log('[QueueStore] Initialized with HTTP polling');
        },

        // Update full state (with transition detection for completed jobs)
        updateState(state) {
            // Track running items BEFORE update to detect transitions
            const oldRunningIds = new Set(this.running.map(i => i.job_id));

            // Update state arrays
            this.pending = state.pending || [];
            this.running = state.running || [];
            this.failed = state.failed || [];
            this.history = state.history || [];

            // Detect items that completed/failed since last poll
            const newRunningIds = new Set(this.running.map(i => i.job_id));
            const newHistoryIds = new Set(this.history.map(i => i.job_id));
            const newFailedIds = new Set(this.failed.map(i => i.job_id));

            oldRunningIds.forEach(jobId => {
                // Item was running but is no longer running
                if (!newRunningIds.has(jobId)) {
                    if (newHistoryIds.has(jobId)) {
                        // Moved to history = completed
                        this.dispatchJobCompleted(jobId);
                    } else if (newFailedIds.has(jobId)) {
                        // Moved to failed
                        const failedItem = this.failed.find(i => i.job_id === jobId);
                        this.dispatchJobFailed(jobId, failedItem?.error);
                    }
                }
            });

            // Detect newly started jobs
            this.running.forEach(item => {
                if (!oldRunningIds.has(item.job_id)) {
                    this.dispatchJobStarted(item.job_id, item.run_id);
                }
            });
        },

        // Actions - use direct HTTP calls
        async retry(queueId) {
            try {
                const response = await fetch(`/api/runner/queue/${queueId}/retry`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                });
                if (response.ok) {
                    // Force immediate refresh
                    this._poller?.refresh();
                } else {
                    console.warn(`[QueueStore] Retry failed: ${response.status}`);
                }
            } catch (e) {
                console.error('[QueueStore] Retry error:', e);
            }
        },

        async cancel(queueId) {
            try {
                const response = await fetch(`/api/runner/queue/${queueId}/cancel`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                });
                if (response.ok) {
                    this._poller?.refresh();
                } else {
                    console.warn(`[QueueStore] Cancel failed: ${response.status}`);
                }
            } catch (e) {
                console.error('[QueueStore] Cancel error:', e);
            }
        },

        async dismiss(queueId) {
            try {
                const response = await fetch(`/api/runner/queue/${queueId}/dismiss`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    credentials: 'same-origin',
                });
                if (response.ok) {
                    this._poller?.refresh();
                } else {
                    console.warn(`[QueueStore] Dismiss failed: ${response.status}`);
                }
            } catch (e) {
                console.error('[QueueStore] Dismiss error:', e);
            }
        },

        refresh() {
            this._poller?.refresh();
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
