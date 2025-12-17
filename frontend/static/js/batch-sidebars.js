/**
 * Batch Page Sidebar Management
 *
 * Handles opening/closing of sidebars from badge clicks on the batch processing page.
 * Ensures only one sidebar is open at a time and implements click-outside-to-close.
 */

// Track currently open sidebar
let currentBatchSidebar = null;
let currentBatchJobId = null;

/**
 * Open JD Annotation sidebar for a job
 * @param {string} jobId - The job ID to load annotations for
 */
async function openBatchAnnotationPanel(jobId) {
    await openBatchSidebar('annotation', jobId);
}

/**
 * Open Contacts sidebar for a job
 * @param {string} jobId - The job ID to load contacts for
 */
async function openBatchContactsSidebar(jobId) {
    await openBatchSidebar('contacts', jobId);
}

/**
 * Open CV Editor sidebar for a job
 * @param {string} jobId - The job ID to load CV for
 */
async function openBatchCVEditor(jobId) {
    await openBatchSidebar('cv', jobId);
}

/**
 * Generic sidebar opener
 * @param {string} type - 'annotation', 'contacts', or 'cv'
 * @param {string} jobId - The job ID
 */
async function openBatchSidebar(type, jobId) {
    // Close any currently open sidebar first (without animation if switching)
    if (currentBatchSidebar) {
        await closeBatchSidebar(false);
    }

    const sidebarId = `batch-${type}-sidebar`;
    const sidebar = document.getElementById(sidebarId);
    const overlay = document.getElementById('batch-sidebar-overlay');

    if (!sidebar || !overlay) {
        console.error(`Sidebar elements not found for type: ${type}`);
        return;
    }

    currentBatchSidebar = type;
    currentBatchJobId = jobId;

    // Update detail link to point to job detail page
    const detailLink = sidebar.querySelector(`#batch-${type}-detail-link`);
    if (detailLink) {
        detailLink.href = `/job/${jobId}`;
    }

    // Show overlay with fade-in
    overlay.classList.remove('hidden');
    // Force reflow for transition
    overlay.offsetHeight;
    overlay.classList.add('opacity-100');
    overlay.classList.remove('opacity-0');

    // Slide in sidebar
    requestAnimationFrame(() => {
        sidebar.classList.remove('translate-x-full');
    });

    // Prevent body scroll
    document.body.style.overflow = 'hidden';

    // Load content via fetch
    const contentContainer = sidebar.querySelector(`#batch-${type}-content`);
    if (contentContainer) {
        // Show loading state
        contentContainer.innerHTML = `
            <div class="flex items-center justify-center h-full">
                <svg class="animate-spin h-8 w-8 text-accent-500" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
            </div>
        `;

        // Fetch content based on type
        const endpoints = {
            annotation: `/partials/batch-annotation/${jobId}`,
            contacts: `/partials/batch-contacts/${jobId}`,
            cv: `/partials/batch-cv/${jobId}`
        };

        try {
            const response = await fetch(endpoints[type]);
            if (response.ok) {
                contentContainer.innerHTML = await response.text();

                // Initialize type-specific functionality
                if (type === 'cv') {
                    initBatchCVEditor(jobId);
                }
            } else {
                contentContainer.innerHTML = `
                    <div class="flex flex-col items-center justify-center h-full text-center p-4">
                        <svg class="h-12 w-12 text-red-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                        </svg>
                        <p class="theme-text-secondary">Failed to load content</p>
                        <p class="theme-text-tertiary text-sm mt-1">Please try again</p>
                    </div>
                `;
            }
        } catch (error) {
            console.error('Error loading sidebar content:', error);
            contentContainer.innerHTML = `
                <div class="flex flex-col items-center justify-center h-full text-center p-4">
                    <svg class="h-12 w-12 text-red-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/>
                    </svg>
                    <p class="theme-text-secondary">Network error</p>
                    <p class="theme-text-tertiary text-sm mt-1">${error.message}</p>
                </div>
            `;
        }
    }

    // Focus the sidebar for accessibility
    sidebar.focus();
}

/**
 * Close any open sidebar
 * @param {boolean} animate - Whether to animate the close (default true)
 * @returns {Promise} Resolves when animation completes
 */
function closeBatchSidebar(animate = true) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('batch-sidebar-overlay');

        if (currentBatchSidebar) {
            const sidebar = document.getElementById(`batch-${currentBatchSidebar}-sidebar`);

            if (sidebar) {
                sidebar.classList.add('translate-x-full');
            }

            // Clean up CV editor if it was open
            if (currentBatchSidebar === 'cv' && typeof cleanupBatchCVEditor === 'function') {
                cleanupBatchCVEditor();
            }
        }

        // Restore body scroll
        document.body.style.overflow = '';

        const duration = animate ? 300 : 0;

        if (overlay) {
            overlay.classList.remove('opacity-100');
            overlay.classList.add('opacity-0');
        }

        setTimeout(() => {
            if (overlay) overlay.classList.add('hidden');
            currentBatchSidebar = null;
            currentBatchJobId = null;
            resolve();
        }, duration);
    });
}

/**
 * Keyboard handler for Escape to close
 */
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && currentBatchSidebar) {
        e.preventDefault();
        closeBatchSidebar();
    }
});

/**
 * Initialize batch CV editor (TipTap) - placeholder for now
 * Will reuse CVEditor class from cv-editor.js
 */
let batchCVEditorInstance = null;

function initBatchCVEditor(jobId) {
    const container = document.getElementById('batch-cv-editor-container');
    if (!container) {
        console.log('CV editor container not found, editor will be read-only');
        return;
    }

    // Reuse CVEditor class from cv-editor.js if available
    if (typeof CVEditor !== 'undefined') {
        try {
            batchCVEditorInstance = new CVEditor(jobId, container);
            batchCVEditorInstance.init();

            // Show save indicator on changes
            const saveIndicator = document.getElementById('batch-cv-save-indicator');
            if (saveIndicator) {
                saveIndicator.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Error initializing CV editor:', error);
        }
    }
}

function cleanupBatchCVEditor() {
    if (batchCVEditorInstance) {
        if (typeof batchCVEditorInstance.destroy === 'function') {
            batchCVEditorInstance.destroy();
        }
        batchCVEditorInstance = null;
    }

    // Hide save indicator
    const saveIndicator = document.getElementById('batch-cv-save-indicator');
    if (saveIndicator) {
        saveIndicator.classList.add('hidden');
    }
}

/**
 * Helper to copy text to clipboard (used in contacts sidebar)
 * @param {string} text - Text to copy
 * @param {string} label - Label for toast message
 * @param {HTMLElement} button - Button element for visual feedback
 */
async function copyToClipboard(text, label, button) {
    try {
        await navigator.clipboard.writeText(text);

        // Visual feedback on button
        if (button) {
            const originalHTML = button.innerHTML;
            button.innerHTML = `
                <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                Copied!
            `;
            button.classList.add('text-green-600');

            setTimeout(() => {
                button.innerHTML = originalHTML;
                button.classList.remove('text-green-600');
            }, 2000);
        }

        // Show toast if available
        if (typeof showToast === 'function') {
            showToast(`${label} copied to clipboard`, 'success');
        }
    } catch (error) {
        console.error('Failed to copy:', error);
        if (typeof showToast === 'function') {
            showToast('Failed to copy to clipboard', 'error');
        }
    }
}

/**
 * Generate outreach message for a contact (placeholder - will call API)
 * @param {string} contactType - 'primary' or 'secondary'
 * @param {number} contactIndex - Index in the contacts array
 * @param {string} messageType - 'inmail' or 'connection'
 * @param {HTMLElement} button - Button element for loading state
 */
async function generateOutreach(contactType, contactIndex, messageType, button) {
    if (!currentBatchJobId) {
        console.error('No job ID set');
        return;
    }

    // Show loading state
    const originalHTML = button.innerHTML;
    button.disabled = true;
    button.innerHTML = `
        <svg class="animate-spin h-3 w-3 inline mr-1" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        Generating...
    `;

    try {
        const response = await fetch(`/api/jobs/${currentBatchJobId}/generate-outreach`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                contact_type: contactType,
                contact_index: contactIndex,
                message_type: messageType
            })
        });

        if (response.ok) {
            const data = await response.json();
            // Refresh the contacts content
            const contentContainer = document.getElementById('batch-contacts-content');
            if (contentContainer) {
                const refreshResponse = await fetch(`/partials/batch-contacts/${currentBatchJobId}`);
                if (refreshResponse.ok) {
                    contentContainer.innerHTML = await refreshResponse.text();
                }
            }
            if (typeof showToast === 'function') {
                showToast('Message generated successfully', 'success');
            }
        } else {
            throw new Error('Failed to generate message');
        }
    } catch (error) {
        console.error('Error generating outreach:', error);
        button.innerHTML = originalHTML;
        button.disabled = false;
        if (typeof showToast === 'function') {
            showToast('Failed to generate message', 'error');
        }
    }
}
