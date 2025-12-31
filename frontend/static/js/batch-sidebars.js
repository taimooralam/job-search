/**
 * Batch Page Sidebar Management
 *
 * Handles opening/closing of sidebars from badge clicks on the batch processing page.
 * Ensures only one sidebar is open at a time and implements click-outside-to-close.
 */

// Track currently open sidebar (exposed globally for jd-prefetch integration)
// Using window object directly so jd-prefetch.js can modify these
window.window.currentBatchSidebar = null;
window.window.currentBatchJobId = null;

// Batch annotation manager instance (separate from job detail page's annotationManager)
let batchAnnotationManager = null;

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
 * Open JD Preview sidebar for a job
 * @param {string} jobId - The job ID to preview JD for
 */
async function openJDPreviewSidebar(jobId) {
    await openBatchSidebar('jd-preview', jobId);
}

/**
 * Generic sidebar opener
 * @param {string} type - 'annotation', 'contacts', 'cv', or 'jd-preview'
 * @param {string} jobId - The job ID
 */
async function openBatchSidebar(type, jobId) {
    // Close any currently open sidebar first (without animation if switching)
    if (window.currentBatchSidebar) {
        await closeBatchSidebar(false);
    }

    const sidebarId = `batch-${type}-sidebar`;
    const sidebar = document.getElementById(sidebarId);
    const overlay = document.getElementById('batch-sidebar-overlay');

    if (!sidebar || !overlay) {
        console.error(`Sidebar elements not found for type: ${type}`);
        return;
    }

    window.currentBatchSidebar = type;
    window.currentBatchJobId = jobId;

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
            cv: `/partials/batch-cv/${jobId}`,
            'jd-preview': `/partials/jd-preview/${jobId}`
        };

        try {
            const response = await fetch(endpoints[type]);
            if (response.ok) {
                contentContainer.innerHTML = await response.text();

                // Initialize type-specific functionality
                if (type === 'cv') {
                    initBatchCVEditor(jobId);
                } else if (type === 'annotation') {
                    initBatchAnnotationManager(jobId);
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

        if (window.currentBatchSidebar) {
            const sidebar = document.getElementById(`batch-${window.currentBatchSidebar}-sidebar`);

            if (sidebar) {
                sidebar.classList.add('translate-x-full');
            }

            // Clean up CV editor if it was open
            if (window.currentBatchSidebar === 'cv' && typeof cleanupBatchCVEditor === 'function') {
                cleanupBatchCVEditor();
            }

            // Clean up annotation manager if it was open
            if (window.currentBatchSidebar === 'annotation' && typeof cleanupBatchAnnotationManager === 'function') {
                cleanupBatchAnnotationManager();
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
            window.currentBatchSidebar = null;
            window.currentBatchJobId = null;
            resolve();
        }, duration);
    });
}

/**
 * Keyboard handler for Escape to close
 */
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && window.currentBatchSidebar) {
        e.preventDefault();
        closeBatchSidebar();
    }
});

/**
 * Initialize batch CV editor (TipTap)
 * Reuses CVEditor class from cv-editor.js with batch-specific enhancements
 */
let batchCVEditorInstance = null;

/**
 * Wait for TipTap library to be available
 * TipTap loads asynchronously via ES modules and dispatches 'tiptap-loaded' event when ready
 * @returns {Promise<boolean>} True if TipTap is available
 */
function waitForTipTap(timeoutMs = 5000) {
    return new Promise((resolve) => {
        // Already loaded
        if (typeof window.tiptap !== 'undefined' && window.tiptap.Editor) {
            resolve(true);
            return;
        }

        const startTime = Date.now();

        // Listen for the tiptap-loaded event from base.html
        const handler = () => {
            window.removeEventListener('tiptap-loaded', handler);
            resolve(true);
        };
        window.addEventListener('tiptap-loaded', handler);

        // Fallback: poll for availability in case event was already fired
        const checkInterval = setInterval(() => {
            if (typeof window.tiptap !== 'undefined' && window.tiptap.Editor) {
                clearInterval(checkInterval);
                window.removeEventListener('tiptap-loaded', handler);
                resolve(true);
            } else if (Date.now() - startTime > timeoutMs) {
                clearInterval(checkInterval);
                window.removeEventListener('tiptap-loaded', handler);
                resolve(false);
            }
        }, 100);
    });
}

async function initBatchCVEditor(jobId) {
    const container = document.getElementById('batch-cv-editor-content');
    if (!container) {
        console.log('CV editor container not found, editor will be read-only');
        return;
    }

    // Check if CVEditor class is available
    if (typeof CVEditor === 'undefined') {
        console.error('CVEditor class not available. Make sure cv-editor.js is loaded.');
        showBatchCVEditorError('CV editor library not loaded');
        return;
    }

    // Wait for TipTap library to be available (async ES module loading)
    const tiptapReady = await waitForTipTap();
    if (!tiptapReady) {
        console.error('TipTap library failed to load within timeout');
        showBatchCVEditorError('TipTap library not loaded. Check browser extensions or network.');
        return;
    }

    try {
        // Create editor instance with batch-specific ID prefix (GAP-100)
        batchCVEditorInstance = new CVEditor(jobId, container, { idPrefix: 'batch-cv' });

        // Override updateSaveIndicator to use batch-specific indicator
        const originalUpdateSaveIndicator = batchCVEditorInstance.updateSaveIndicator.bind(batchCVEditorInstance);
        batchCVEditorInstance.updateSaveIndicator = (status) => {
            // Call original (for screen reader announcements)
            originalUpdateSaveIndicator(status);

            // Also update batch-specific indicator
            if (typeof updateBatchCVSaveIndicator === 'function') {
                updateBatchCVSaveIndicator(status);
            }
        };

        // Override updateToolbarState to use batch-specific toolbar
        const originalUpdateToolbarState = batchCVEditorInstance.updateToolbarState.bind(batchCVEditorInstance);
        batchCVEditorInstance.updateToolbarState = () => {
            // Call original
            originalUpdateToolbarState();

            // Also update batch-specific toolbar
            if (typeof updateBatchCVToolbarState === 'function') {
                updateBatchCVToolbarState();
            }
        };

        // Initialize the editor
        await batchCVEditorInstance.init();

        // Show save indicator
        const saveIndicator = document.getElementById('batch-cv-save-indicator');
        if (saveIndicator) {
            saveIndicator.classList.remove('hidden');
        }

        console.log('Batch CV editor initialized successfully');

    } catch (error) {
        console.error('Error initializing batch CV editor:', error);
        showBatchCVEditorError(error.message || 'Failed to initialize CV editor');
    }
}

/**
 * Show error state in batch CV editor container
 */
function showBatchCVEditorError(message) {
    const container = document.getElementById('batch-cv-editor-container');
    if (!container) return;

    container.innerHTML = `
        <div class="flex flex-col items-center justify-center h-96 p-8 text-center">
            <div class="text-red-500 mb-4">
                <svg class="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            </div>
            <h3 class="text-lg font-bold theme-text-primary mb-2">Failed to Load CV Editor</h3>
            <p class="theme-text-secondary text-sm mb-4 max-w-sm">${escapeHtml(message)}</p>
            <div class="text-xs theme-text-tertiary">
                <p class="mb-2">Common causes:</p>
                <ul class="list-disc list-inside text-left">
                    <li>Browser extension blocking CDN scripts</li>
                    <li>Network connectivity issues</li>
                    <li>Try refreshing the page</li>
                </ul>
            </div>
            <button onclick="closeBatchSidebar()"
                    class="mt-4 px-4 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 rounded-lg transition">
                Close
            </button>
        </div>
    `;
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
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
 * Apply formatting command to batch CV editor
 * Global function called from inline onclick handlers in the sidebar HTML
 */
function applyBatchCVFormat(command, value = null) {
    if (batchCVEditorInstance && batchCVEditorInstance.applyFormat) {
        batchCVEditorInstance.applyFormat(command, value);
    }
}

/**
 * Export batch CV to PDF
 * Global function called from PDF export button in the sidebar HTML
 */
async function exportBatchCVToPDF() {
    if (!batchCVEditorInstance) {
        if (typeof showToast === 'function') {
            showToast('CV editor not initialized', 'error');
        }
        return;
    }

    try {
        // Show loading state
        if (typeof showToast === 'function') {
            showToast('Generating PDF...', 'info');
        }

        // Save first to ensure latest content
        await batchCVEditorInstance.save();

        // Call PDF generation endpoint
        const response = await fetch(`/api/jobs/${batchCVEditorInstance.jobId}/cv-editor/pdf`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'same-origin'
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'PDF generation failed');
        }

        // Download the PDF file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // Get filename from Content-Disposition header
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'CV.pdf';
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
            if (filenameMatch) {
                filename = filenameMatch[1];
            }
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

        if (typeof showToast === 'function') {
            showToast('PDF downloaded successfully!', 'success');
        }

    } catch (error) {
        console.error('PDF export failed:', error);
        if (typeof showToast === 'function') {
            showToast(`PDF export failed: ${error.message}`, 'error');
        }
    }
}

/**
 * Upload CV PDF to Google Drive via n8n webhook (batch page version).
 *
 * This function:
 * 1. Saves the current CV state
 * 2. Calls the backend to generate PDF and upload to Google Drive
 * 3. Updates button state to show upload progress (orange pulse)
 * 4. On success, button turns green and stays green (persisted in MongoDB)
 */
async function uploadBatchCVToGDrive() {
    if (!batchCVEditorInstance) {
        if (typeof showToast === 'function') {
            showToast('CV editor not initialized', 'error');
        }
        return;
    }

    const jobId = batchCVEditorInstance.jobId;

    // Find all Google Drive upload buttons to update state
    const buttons = document.querySelectorAll('.gdrive-btn');

    try {
        // Update UI: uploading state (orange pulse)
        buttons.forEach(btn => {
            btn.classList.add('uploading');
            btn.classList.remove('gdrive-uploaded', 'upload-error');
            btn.disabled = true;
            const textSpan = btn.querySelector('.gdrive-btn-text');
            if (textSpan) textSpan.textContent = 'Uploading';
        });

        if (typeof showToast === 'function') {
            showToast('Uploading CV to Google Drive...', 'info');
        }

        // Save first to ensure latest content
        await batchCVEditorInstance.save();

        // Call upload endpoint
        const response = await fetch(`/api/jobs/${jobId}/cv/upload-drive`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || 'Upload failed');
        }

        // Success: update UI to green (persists on page refresh via MongoDB)
        buttons.forEach(btn => {
            btn.classList.remove('uploading');
            btn.classList.add('gdrive-uploaded');
            btn.disabled = false;
            const textSpan = btn.querySelector('.gdrive-btn-text');
            if (textSpan) textSpan.textContent = 'Done';
        });

        // Dispatch event to update CV badge to indigo
        window.dispatchEvent(new CustomEvent('cv:uploaded-to-drive', {
            detail: { jobId }
        }));

        if (typeof showToast === 'function') {
            showToast('CV uploaded to Google Drive!', 'success');
        }

    } catch (error) {
        console.error('Google Drive upload failed:', error);

        // Error: show error state briefly, then reset
        buttons.forEach(btn => {
            btn.classList.remove('uploading');
            btn.classList.add('upload-error');
            btn.disabled = false;
            const textSpan = btn.querySelector('.gdrive-btn-text');
            if (textSpan) textSpan.textContent = 'Failed';

            // Reset error state after animation
            setTimeout(() => {
                btn.classList.remove('upload-error');
                if (textSpan) textSpan.textContent = 'Drive';
            }, 2000);
        });

        if (typeof showToast === 'function') {
            showToast(`Upload failed: ${error.message}`, 'error');
        }
    }
}

/**
 * Update toolbar button states based on current selection
 * Called from editor selection change events
 */
function updateBatchCVToolbarState() {
    if (!batchCVEditorInstance || !batchCVEditorInstance.editor) return;

    const editor = batchCVEditorInstance.editor;

    // Update format buttons
    const formatButtons = {
        'batch-cv-bold-btn': 'bold',
        'batch-cv-italic-btn': 'italic',
        'batch-cv-underline-btn': 'underline'
    };

    for (const [btnId, format] of Object.entries(formatButtons)) {
        const btn = document.getElementById(btnId);
        if (btn) {
            if (editor.isActive(format)) {
                btn.classList.add('bg-gray-200', 'dark:bg-gray-600');
            } else {
                btn.classList.remove('bg-gray-200', 'dark:bg-gray-600');
            }
        }
    }
}

/**
 * Apply document-level styles (margins, page size, headers, footers)
 * Called from document settings controls
 */
function applyBatchDocumentStyle(property) {
    if (!batchCVEditorInstance) return;

    // Get value from the corresponding input element
    let value;
    switch (property) {
        case 'lineHeight':
            value = document.getElementById('batch-cv-line-height')?.value;
            break;
        case 'margins':
            value = document.getElementById('batch-cv-margins')?.value;
            break;
        case 'pageSize':
            value = document.getElementById('batch-cv-page-size')?.value;
            break;
        case 'header':
            value = document.getElementById('batch-cv-header-text')?.value;
            break;
        case 'footer':
            value = document.getElementById('batch-cv-footer-text')?.value;
            break;
    }

    if (batchCVEditorInstance.applyDocumentStyle) {
        batchCVEditorInstance.applyDocumentStyle(property, value);
    }
}

// ============================================================================
// Batch Annotation Manager Initialization
// ============================================================================

/**
 * Initialize batch annotation manager for the annotation sidebar
 * Uses batch-specific element IDs to avoid conflicts with job detail page
 * @param {string} jobId - The job ID to load annotations for
 */
async function initBatchAnnotationManager(jobId) {
    // Check if AnnotationManager class is available
    if (typeof AnnotationManager === 'undefined') {
        console.error('AnnotationManager class not available. Make sure jd-annotation.js is loaded.');
        showBatchAnnotationError('Annotation manager not loaded');
        return;
    }

    // Clean up any existing instance
    cleanupBatchAnnotationManager();

    try {
        // Create annotation manager with batch-specific element IDs
        batchAnnotationManager = new AnnotationManager(jobId, {
            panelId: 'batch-annotation-sidebar',
            contentId: 'batch-jd-processed-content',
            popoverId: 'annotation-popover',  // Shared popover element
            listId: 'batch-annotation-items',
            loadingId: 'batch-jd-loading',
            emptyId: 'batch-jd-empty',
            saveIndicatorId: 'batch-annotation-save-indicator',
            overlayId: 'batch-sidebar-overlay',
            listContainerId: 'batch-annotation-list',
            listCountId: 'batch-annotation-list-count',
            listEmptyId: 'batch-annotation-list-empty',
            annotationCountId: 'batch-annotation-count',
            activeAnnotationCountId: 'batch-active-annotation-count',
            coverageBarId: 'batch-annotation-coverage-bar',
            coveragePctId: 'batch-annotation-coverage-pct',
            boostValueId: 'batch-total-boost-value',
            personaPanelId: 'batch-persona-panel-container'
        });

        // Initialize the manager
        await batchAnnotationManager.init();

        console.log('Batch annotation manager initialized for job:', jobId);

    } catch (error) {
        console.error('Error initializing batch annotation manager:', error);
        showBatchAnnotationError(error.message || 'Failed to initialize annotation manager');
    }
}

/**
 * Show error state in batch annotation content
 */
function showBatchAnnotationError(message) {
    const contentEl = document.getElementById('batch-jd-processed-content');
    const loadingEl = document.getElementById('batch-jd-loading');
    const emptyEl = document.getElementById('batch-jd-empty');

    if (loadingEl) loadingEl.classList.add('hidden');
    if (emptyEl) emptyEl.classList.add('hidden');

    if (contentEl) {
        contentEl.classList.remove('hidden');
        contentEl.innerHTML = `
            <div class="flex flex-col items-center justify-center py-12 text-center">
                <div class="text-red-500 mb-4">
                    <svg class="w-12 h-12 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>
                <h3 class="text-lg font-bold theme-text-primary mb-2">Failed to Load Annotations</h3>
                <p class="theme-text-secondary text-sm mb-4 max-w-sm">${escapeHtml(message)}</p>
            </div>
        `;
    }
}

/**
 * Clean up batch annotation manager
 */
function cleanupBatchAnnotationManager() {
    if (batchAnnotationManager) {
        if (typeof batchAnnotationManager.destroy === 'function') {
            batchAnnotationManager.destroy();
        }
        batchAnnotationManager = null;
    }

    // Hide any open popover
    const popover = document.getElementById('annotation-popover');
    if (popover) {
        popover.classList.add('hidden');
    }
}

/**
 * Global filter function for annotations - works with both job detail and batch
 * @param {string} filter - Filter type (all, core_strength, gap, must_have, etc.)
 */
window.filterAnnotations = function(filter) {
    // Use batch annotation manager if available and in batch context
    if (batchAnnotationManager && window.currentBatchSidebar === 'annotation') {
        batchAnnotationManager.setFilter(filter);
    } else if (typeof annotationManager !== 'undefined' && annotationManager) {
        // Fall back to global annotation manager (job detail page)
        annotationManager.setFilter(filter);
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
 * Generate outreach message for a contact
 * @param {string} contactName - Name of the contact
 * @param {string} contactRole - Role/title of the contact
 * @param {string} messageType - 'inmail' or 'connection'
 * @param {HTMLElement} button - Button element for loading state
 */
async function generateOutreach(contactName, contactRole, messageType, button) {
    if (!window.currentBatchJobId) {
        console.error('No job ID set');
        return;
    }

    const messageLabel = messageType === 'connection' ? 'Connection request' : 'InMail';

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
        const response = await fetch(`/api/jobs/${window.currentBatchJobId}/contacts/generate-message`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                contact_name: contactName,
                contact_role: contactRole,
                message_type: messageType
            })
        });

        const result = await response.json();

        if (result.success && result.message) {
            // Copy to clipboard
            await navigator.clipboard.writeText(result.message);
            if (typeof showToast === 'function') {
                showToast(`${messageLabel} copied to clipboard!`, 'success');
            }
            // Refresh the contacts content to show the saved message
            const contentContainer = document.getElementById('batch-contacts-content');
            if (contentContainer) {
                const refreshResponse = await fetch(`/partials/batch-contacts/${window.currentBatchJobId}`);
                if (refreshResponse.ok) {
                    contentContainer.innerHTML = await refreshResponse.text();
                }
            }
        } else {
            throw new Error(result.error || 'Failed to generate message');
        }
    } catch (error) {
        console.error('Error generating outreach:', error);
        button.innerHTML = originalHTML;
        button.disabled = false;
        if (typeof showToast === 'function') {
            showToast(`Failed to generate ${messageLabel}: ${error.message}`, 'error');
        }
    }
}

/**
 * Upload dossier PDF to Google Drive for a batch job.
 * Uses best-effort generation if no pre-generated dossier exists.
 *
 * @param {string} jobId - The job ID to upload dossier for
 */
async function uploadBatchDossierToGDrive(jobId) {
    const btn = document.querySelector(`[data-dossier-btn="${jobId}"]`);
    if (!btn) return;

    // Store original state
    const originalHTML = btn.innerHTML;

    try {
        // Update UI: uploading state
        btn.disabled = true;
        btn.classList.add('uploading');
        btn.classList.remove('gdrive-uploaded', 'upload-error');
        btn.innerHTML = `
            <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
        `;

        if (typeof showToast === 'function') {
            showToast('Uploading dossier to Google Drive...', 'info');
        }

        // Call upload endpoint
        const response = await fetch(`/api/jobs/${jobId}/dossier/upload-drive`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || result.detail || 'Upload failed');
        }

        // Success: update UI
        btn.disabled = false;
        btn.classList.remove('uploading');
        btn.classList.add('gdrive-uploaded');
        btn.title = 'Dossier uploaded to Drive';
        btn.innerHTML = `
            <svg class="h-4 w-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
        `;

        if (typeof showToast === 'function') {
            showToast('Dossier uploaded to Google Drive!', 'success');
        }

    } catch (error) {
        console.error('Dossier upload failed:', error);

        // Error state
        btn.disabled = false;
        btn.classList.remove('uploading');
        btn.classList.add('upload-error');
        btn.innerHTML = `
            <svg class="h-4 w-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
        `;

        if (typeof showToast === 'function') {
            showToast(`Dossier upload failed: ${error.message}`, 'error');
        }

        // Reset after 3 seconds
        setTimeout(() => {
            btn.innerHTML = originalHTML;
            btn.classList.remove('upload-error');
            btn.title = 'Upload dossier to Drive';
        }, 3000);
    }
}
