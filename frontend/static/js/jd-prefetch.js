/**
 * JD Prefetch - Hover-based prefetching for job descriptions
 * Loads JD content on hover for instant panel display
 */

(function() {
    'use strict';

    // In-memory cache with timestamps
    const jdCache = new Map();
    const CACHE_TTL = 30000; // 30 seconds

    // Track pending requests to avoid duplicates
    const pendingRequests = new Set();

    /**
     * Prefetch job description on hover
     * @param {string} jobId - MongoDB job ID
     */
    function prefetchJD(jobId) {
        // Skip if already cached or request pending
        if (jdCache.has(jobId) || pendingRequests.has(jobId)) {
            return;
        }

        pendingRequests.add(jobId);

        fetch(`/partials/jd-preview/${jobId}`, {
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            if (!response.ok) throw new Error('Network response was not ok');
            return response.text();
        })
        .then(html => {
            // Store in cache with timestamp
            jdCache.set(jobId, {
                html: html,
                timestamp: Date.now()
            });

            // Schedule cleanup after TTL
            setTimeout(() => {
                jdCache.delete(jobId);
            }, CACHE_TTL);

            pendingRequests.delete(jobId);
        })
        .catch(error => {
            console.warn('JD prefetch failed for job:', jobId, error);
            pendingRequests.delete(jobId);
        });
    }

    /**
     * Get cached JD content if available
     * @param {string} jobId - MongoDB job ID
     * @returns {string|null} Cached HTML or null
     */
    function getCachedJD(jobId) {
        const cached = jdCache.get(jobId);
        if (cached) {
            // Check if still within TTL (extra safety check)
            if (Date.now() - cached.timestamp < CACHE_TTL) {
                return cached.html;
            }
            // Expired, remove from cache
            jdCache.delete(jobId);
        }
        return null;
    }

    /**
     * Check if JD is cached
     * @param {string} jobId - MongoDB job ID
     * @returns {boolean}
     */
    function isCached(jobId) {
        return getCachedJD(jobId) !== null;
    }

    /**
     * Clear all cached entries
     */
    function clearCache() {
        jdCache.clear();
        pendingRequests.clear();
    }

    /**
     * Get cache statistics
     * @returns {object} Cache stats
     */
    function getCacheStats() {
        return {
            size: jdCache.size,
            pending: pendingRequests.size,
            entries: Array.from(jdCache.keys())
        };
    }

    /**
     * Enhanced openJDPreviewSidebar that checks cache first
     * This overrides the default behavior in batch-sidebars.js
     * @param {string} jobId - MongoDB job ID
     */
    function openJDPreviewSidebarCached(jobId) {
        const cached = getCachedJD(jobId);

        if (cached) {
            // Set global state for close functionality (shared with batch-sidebars.js)
            window.currentBatchSidebar = 'jd-preview';
            window.currentBatchJobId = jobId;

            // Instant display from cache
            const contentEl = document.getElementById('batch-jd-preview-content');
            if (contentEl) {
                contentEl.innerHTML = cached;

                // Apply JD formatting if formatter is available
                if (window.JDFormatter) {
                    const jdTextEl = contentEl.querySelector('[data-jd-format="auto"]');
                    if (jdTextEl) {
                        window.JDFormatter.formatElement(jdTextEl);
                    }
                }
            }

            // Update detail link
            const detailLink = document.getElementById('batch-jd-preview-detail-link');
            if (detailLink) {
                detailLink.href = `/job/${jobId}`;
            }

            // Show sidebar
            const sidebar = document.getElementById('batch-jd-preview-sidebar');
            const overlay = document.getElementById('batch-sidebar-overlay');

            if (sidebar) {
                sidebar.classList.remove('translate-x-full');
                sidebar.classList.add('translate-x-0');
            }
            if (overlay) {
                overlay.classList.remove('hidden');
                // Trigger opacity transition
                requestAnimationFrame(() => {
                    overlay.classList.remove('opacity-0');
                    overlay.classList.add('opacity-100');
                });
            }

            // Prevent body scroll
            document.body.style.overflow = 'hidden';
        } else {
            // Fall back to original function if available
            if (typeof window._originalOpenJDPreviewSidebar === 'function') {
                window._originalOpenJDPreviewSidebar(jobId);
            } else {
                // Direct fetch fallback
                fetchJDAndShowSidebar(jobId);
            }
        }
    }

    /**
     * Fetch JD and show sidebar (fallback when not cached)
     * @param {string} jobId - MongoDB job ID
     */
    function fetchJDAndShowSidebar(jobId) {
        // Set global state for close functionality (must match openJDPreviewSidebarCached)
        window.currentBatchSidebar = 'jd-preview';
        window.currentBatchJobId = jobId;

        const contentEl = document.getElementById('batch-jd-preview-content');
        if (contentEl) {
            contentEl.innerHTML = '<div class="flex items-center justify-center p-8"><div class="animate-spin h-8 w-8 border-2 border-indigo-500 border-t-transparent rounded-full"></div></div>';
        }

        // Update detail link
        const detailLink = document.getElementById('batch-jd-preview-detail-link');
        if (detailLink) {
            detailLink.href = `/job/${jobId}`;
        }

        // Show sidebar immediately with loading state
        const sidebar = document.getElementById('batch-jd-preview-sidebar');
        const overlay = document.getElementById('batch-sidebar-overlay');

        if (sidebar) {
            sidebar.classList.remove('translate-x-full');
            sidebar.classList.add('translate-x-0');
        }
        if (overlay) {
            overlay.classList.remove('hidden');
            // Trigger opacity transition
            requestAnimationFrame(() => {
                overlay.classList.remove('opacity-0');
                overlay.classList.add('opacity-100');
            });
        }
        document.body.style.overflow = 'hidden';

        // Fetch content
        fetch(`/partials/jd-preview/${jobId}`, {
            credentials: 'same-origin'
        })
        .then(response => response.text())
        .then(html => {
            if (contentEl) {
                contentEl.innerHTML = html;

                // Apply JD formatting
                if (window.JDFormatter) {
                    const jdTextEl = contentEl.querySelector('[data-jd-format="auto"]');
                    if (jdTextEl) {
                        window.JDFormatter.formatElement(jdTextEl);
                    }
                }
            }

            // Cache for future use
            jdCache.set(jobId, {
                html: html,
                timestamp: Date.now()
            });

            setTimeout(() => jdCache.delete(jobId), CACHE_TTL);
        })
        .catch(error => {
            console.error('Failed to load JD preview:', error);
            if (contentEl) {
                contentEl.innerHTML = '<div class="p-4 text-red-600">Failed to load job description</div>';
            }
        });
    }

    /**
     * Initialize prefetch behavior on job rows
     * Call this after job rows are loaded/updated
     */
    function initPrefetchListeners() {
        // Use event delegation on the job list container
        const jobListContainer = document.getElementById('job-list') ||
                                 document.querySelector('[data-job-list]') ||
                                 document.querySelector('.job-rows-container');

        if (jobListContainer) {
            // Remove existing listener to avoid duplicates
            jobListContainer.removeEventListener('mouseenter', handleRowHover, true);
            // Add event listener with capture to catch hover on child elements
            jobListContainer.addEventListener('mouseenter', handleRowHover, true);
        }
    }

    /**
     * Handle hover on job rows
     * @param {Event} event - Mouse event
     */
    function handleRowHover(event) {
        // Find the closest job row element
        const row = event.target.closest('[data-job-id]');
        if (row) {
            const jobId = row.dataset.jobId;
            if (jobId) {
                prefetchJD(jobId);
            }
        }
    }

    // Store reference to original function before overriding
    if (typeof window.openJDPreviewSidebar === 'function') {
        window._originalOpenJDPreviewSidebar = window.openJDPreviewSidebar;
    }

    // Expose functions globally
    window.JDPrefetch = {
        prefetch: prefetchJD,
        getCached: getCachedJD,
        isCached: isCached,
        clearCache: clearCache,
        getStats: getCacheStats,
        initListeners: initPrefetchListeners,
        openSidebar: openJDPreviewSidebarCached
    };

    // Also expose the enhanced sidebar opener
    window.openJDPreviewSidebarCached = openJDPreviewSidebarCached;

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        initPrefetchListeners();
    });

    // Re-initialize after HTMX content swaps
    document.body.addEventListener('htmx:afterSwap', function(event) {
        // Re-attach listeners after new content is loaded
        initPrefetchListeners();
    });

})();
