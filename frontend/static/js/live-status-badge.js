/**
 * Live Status Badge - Alpine.js Component
 *
 * Reactive component that displays real-time pipeline status
 * for individual jobs based on WebSocket queue updates.
 */

function liveStatusBadge(jobId) {
    return {
        jobId: jobId,
        status: null,        // 'pending' | 'running' | 'failed' | 'completed' | null
        position: null,      // Queue position (for pending)
        runId: null,         // Run ID (for running)
        error: null,         // Error message (for failed)
        fadeOut: false,      // For completed animation
        _syntheticStatus: false, // Track if status came from event (vs store)

        init() {
            // Check current queue state
            this.updateFromStore();

            // Listen for queue events
            window.addEventListener('queue:job-started', (e) => {
                if (e.detail.jobId === this.jobId) {
                    this.status = 'running';
                    this.runId = e.detail.runId;
                    this.position = null;
                    this._syntheticStatus = true; // Mark as event-driven update
                }
            });

            // Listen for batch operation status changes (dispatched by batch_processing.html)
            window.addEventListener('queue:job-status-changed', (e) => {
                if (e.detail.jobId === this.jobId) {
                    const status = e.detail.status;
                    if (status === 'running' || status === 'queued') {
                        this.status = 'running';  // Show running for both queued and running
                        this.runId = e.detail.runId || null;
                        this.position = null;
                        this._syntheticStatus = true; // Mark as event-driven update
                    } else if (status === 'pending') {
                        this.status = 'pending';
                        this.position = e.detail.position || null;
                        this.runId = e.detail.runId || null;  // Capture runId for log viewing
                        this._syntheticStatus = true;
                    } else if (status === 'completed') {
                        this.status = 'completed';
                        this.runId = null;
                        this._syntheticStatus = false; // Clear on completion
                    } else if (status === 'failed') {
                        this.status = 'failed';
                        this.error = e.detail.error || null;
                        this._syntheticStatus = false; // Clear on failure
                    }
                }
            });

            window.addEventListener('queue:job-completed', (e) => {
                if (e.detail.jobId === this.jobId) {
                    this.status = 'completed';
                    this.runId = null;
                    this._syntheticStatus = false; // Clear on completion
                    // Fade out after 5 seconds
                    setTimeout(() => {
                        this.fadeOut = true;
                        // Clear status after fade
                        setTimeout(() => {
                            this.status = null;
                        }, 500);
                    }, 5000);
                }
            });

            window.addEventListener('queue:job-failed', (e) => {
                if (e.detail.jobId === this.jobId) {
                    this.status = 'failed';
                    this.error = e.detail.error;
                    this.runId = null;
                    this._syntheticStatus = false; // Clear on failure
                }
            });

            // Watch for Alpine store updates
            if (window.Alpine) {
                this.$watch('$store.queue.pending', () => this.updateFromStore());
                this.$watch('$store.queue.running', () => this.updateFromStore());
                this.$watch('$store.queue.failed', () => this.updateFromStore());
            }
        },

        updateFromStore() {
            if (!window.Alpine || !Alpine.store('queue')) {
                return;
            }

            const queueItem = Alpine.store('queue').getItemByJobId(this.jobId);

            if (queueItem) {
                // Store has this job - use authoritative data
                this.status = queueItem.queueStatus;
                this.runId = queueItem.run_id;
                this.error = queueItem.error;
                this._syntheticStatus = false; // Store is authoritative

                if (queueItem.queueStatus === 'pending') {
                    this.position = Alpine.store('queue').getPosition(this.jobId);
                } else {
                    this.position = null;
                }
            } else if (this.status !== 'completed' && !this._syntheticStatus) {
                // Only clear if not in completed fade-out state AND no synthetic status
                // This prevents race condition where event sets status but store hasn't polled yet
                if (!this.fadeOut) {
                    this.status = null;
                    this.position = null;
                    this.runId = null;
                    this.error = null;
                }
            }
        },

        async openCLI() {
            if (window.Alpine && Alpine.store('cli')) {
                Alpine.store('cli').showPanel();

                // If we have a run_id, try to show logs
                if (this.runId) {
                    const cliStore = Alpine.store('cli');

                    // If logs are in memory, just switch to them
                    if (cliStore.runs[this.runId]) {
                        cliStore.activeRunId = this.runId;
                    } else {
                        // Fetch logs on-demand from API
                        await cliStore.fetchRunLogs(this.runId, this.jobId);
                    }
                } else {
                    // No run ID, show queued tab placeholder
                    Alpine.store('cli').addTab(this.jobId);
                }
            }
        },

        showError() {
            // Show error in an alert or modal
            if (this.error) {
                alert(`Pipeline Error:\n\n${this.error}`);
            }
        }
    };
}

// Make globally available
window.liveStatusBadge = liveStatusBadge;
