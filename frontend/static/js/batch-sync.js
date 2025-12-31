/**
 * Batch Sync - Polling for batch job count updates
 * Keeps the batch count badge in sync with actual database count
 */

(function() {
    'use strict';

    // Configuration
    const POLL_INTERVAL = 60000; // 1 minute
    const ENDPOINT = '/api/jobs/batch/count'; // Uses existing endpoint

    // State
    let syncInterval = null;
    let isRunning = false;
    let lastCount = null;

    /**
     * Fetch current batch count from server
     * @returns {Promise<number|null>}
     */
    async function fetchBatchCount() {
        try {
            const response = await fetch(ENDPOINT, {
                method: 'GET',
                credentials: 'same-origin',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();
            return data.count;
        } catch (error) {
            console.warn('Failed to fetch batch count:', error);
            return null;
        }
    }

    /**
     * Update all batch count badge elements in the DOM
     * @param {number} count - New count value
     */
    function updateBadges(count) {
        if (count === null || count === undefined) return;

        // Update all elements with batch count badge
        const badges = document.querySelectorAll(
            '#batch-count-badge, ' +
            '[data-batch-count], ' +
            '.batch-count-badge'
        );

        badges.forEach(badge => {
            const currentText = badge.textContent.trim();
            const newText = count.toString();

            // Only update if changed (avoid unnecessary DOM updates)
            if (currentText !== newText) {
                badge.textContent = newText;

                // Add subtle animation on update
                badge.classList.add('batch-count-updated');
                setTimeout(() => {
                    badge.classList.remove('batch-count-updated');
                }, 300);
            }
        });

        // Also update any badge in the sidebar nav icon
        const navBadge = document.querySelector('.batch-nav-badge, [data-nav-batch-count]');
        if (navBadge) {
            navBadge.textContent = count.toString();
        }

        lastCount = count;
    }

    /**
     * Sync batch count - fetch and update badges
     */
    async function syncBatchCount() {
        const count = await fetchBatchCount();
        if (count !== null) {
            updateBadges(count);
        }
    }

    /**
     * Start the batch sync polling
     */
    function startSync() {
        if (isRunning) return;

        isRunning = true;

        // Initial sync immediately
        syncBatchCount();

        // Start interval polling
        syncInterval = setInterval(syncBatchCount, POLL_INTERVAL);

        console.log('Batch sync started (polling every', POLL_INTERVAL / 1000, 'seconds)');
    }

    /**
     * Stop the batch sync polling
     */
    function stopSync() {
        if (!isRunning) return;

        if (syncInterval) {
            clearInterval(syncInterval);
            syncInterval = null;
        }

        isRunning = false;
        console.log('Batch sync stopped');
    }

    /**
     * Check if sync is currently running
     * @returns {boolean}
     */
    function isActive() {
        return isRunning;
    }

    /**
     * Get the last known count
     * @returns {number|null}
     */
    function getLastCount() {
        return lastCount;
    }

    /**
     * Force an immediate sync
     */
    function forceSync() {
        return syncBatchCount();
    }

    // Expose functions globally
    window.BatchSync = {
        start: startSync,
        stop: stopSync,
        sync: forceSync,
        isActive: isActive,
        getLastCount: getLastCount
    };

    // Auto-start on page load if on batch page
    document.addEventListener('DOMContentLoaded', function() {
        // Check if we're on a page that has batch count badges
        const hasBatchBadge = document.querySelector(
            '#batch-count-badge, [data-batch-count], .batch-count-badge'
        );

        if (hasBatchBadge) {
            startSync();
        }
    });

    // Stop sync when leaving page
    window.addEventListener('beforeunload', function() {
        stopSync();
    });

    // Handle visibility change (pause when tab hidden, resume when visible)
    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            // Tab is hidden, stop polling to save resources
            if (isRunning) {
                clearInterval(syncInterval);
                syncInterval = null;
            }
        } else {
            // Tab is visible again, resume polling
            if (isRunning && !syncInterval) {
                syncBatchCount(); // Immediate sync
                syncInterval = setInterval(syncBatchCount, POLL_INTERVAL);
            }
        }
    });

})();
