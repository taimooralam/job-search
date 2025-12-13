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

        init() {
            // Check current queue state
            this.updateFromStore();

            // Listen for queue events
            window.addEventListener('queue:job-started', (e) => {
                if (e.detail.jobId === this.jobId) {
                    this.status = 'running';
                    this.runId = e.detail.runId;
                    this.position = null;
                }
            });

            window.addEventListener('queue:job-completed', (e) => {
                if (e.detail.jobId === this.jobId) {
                    this.status = 'completed';
                    this.runId = null;
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
                this.status = queueItem.queueStatus;
                this.runId = queueItem.run_id;
                this.error = queueItem.error;

                if (queueItem.queueStatus === 'pending') {
                    this.position = Alpine.store('queue').getPosition(this.jobId);
                } else {
                    this.position = null;
                }
            } else if (this.status !== 'completed') {
                // Only clear if not in completed fade-out state
                if (!this.fadeOut) {
                    this.status = null;
                    this.position = null;
                    this.runId = null;
                    this.error = null;
                }
            }
        },

        openCLI() {
            if (window.Alpine && Alpine.store('cli')) {
                Alpine.store('cli').showPanel();

                // If we have a run_id, add/switch to that tab
                if (this.runId) {
                    Alpine.store('cli').addTab(this.jobId, this.runId);
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
