/**
 * CV Rich Text Editor - TipTap Implementation
 *
 * Features:
 * - TipTap editor with rich formatting (bold, italic, underline, lists, headings)
 * - Side panel UI with collapse/expand
 * - Auto-save to MongoDB after 3 seconds of inactivity
 * - Save indicator with visual feedback
 * - State restoration from MongoDB
 * - Phase 5: Keyboard shortcuts, mobile responsiveness, WCAG 2.1 AA accessibility
 */

class CVEditor {
    constructor(jobId, container) {
        this.jobId = jobId;
        this.container = container;
        this.editor = null;
        this.saveStatus = 'saved';
        this.saveTimeout = null;
        this.AUTOSAVE_DELAY = 3000; // 3 seconds
        this.lastSavedContent = null;
    }

    /**
     * Initialize the TipTap editor with extensions
     */
    async init() {
        try {
            // Show loading animation immediately
            this.showLoadingState();

            // Defensive check: Ensure TipTap library loaded
            if (typeof window.tiptap === 'undefined' || !window.tiptap.Editor) {
                console.error('❌ TipTap library failed to load from CDN');
                console.error('This is usually caused by browser extensions blocking external scripts');
                console.error('Try: (1) Disable ad blockers, (2) Disable VPN, (3) Use different browser');

                this.showErrorState('TipTap library failed to load. Please check your browser extensions and network connection.');
                this.updateSaveIndicator('error');
                return; // Exit early, don't try to initialize editor
            }

            // Load existing CV state from MongoDB
            const editorState = await this.loadEditorState();

            // TipTap loaded successfully, proceed with initialization
            this.editor = new window.tiptap.Editor({
                element: this.container,
                extensions: [
                    window.tiptapStarterKit.StarterKit,
                    window.tiptapUnderline.Underline,
                    window.tiptapTextAlign.TextAlign.configure({
                        types: ['heading', 'paragraph'],
                        alignments: ['left', 'center', 'right', 'justify'],
                        defaultAlignment: 'left',
                    }),
                    window.tiptapFontFamily.FontFamily,
                    window.tiptapTextStyle.TextStyle,
                    window.tiptapColor.Color,
                    window.tiptapFontSize.FontSize,  // Phase 2: Font size control
                    window.tiptapHighlight.Highlight.configure({  // Phase 2: Highlight color
                        multicolor: true
                    }),
                ],
                content: editorState.content || this.getDefaultContent(),
                editorProps: {
                    attributes: {
                        class: 'prose max-w-none focus:outline-none min-h-full p-8',
                        style: `font-family: 'Inter', sans-serif; font-size: 11pt;`,
                        // Phase 5: Accessibility attributes
                        role: 'textbox',
                        'aria-label': 'CV content editor',
                        'aria-multiline': 'true'
                    },
                    handleKeyDown: (view, event) => {
                        // Tab: Increase indent
                        if (event.key === 'Tab' && !event.shiftKey) {
                            event.preventDefault();
                            this.increaseIndent();
                            return true;
                        }
                        // Shift+Tab: Decrease indent
                        if (event.key === 'Tab' && event.shiftKey) {
                            event.preventDefault();
                            this.decreaseIndent();
                            return true;
                        }
                        return false;
                    }
                },
                onUpdate: () => this.handleEditorUpdate(),
                onSelectionUpdate: () => this.updateToolbarState(),
                onTransaction: () => this.updateToolbarState(),
            });

            // Store initial content for comparison
            this.lastSavedContent = JSON.stringify(this.editor.getJSON());

            // Phase 3: Restore document-level styles
            this.restoreDocumentStyles(editorState);

            // Phase 3: Apply document styles to editor
            this.applyDocumentStyles();

            // Hide loading animation, show editor
            this.hideLoadingState();

            console.log('CV Editor initialized successfully');
            this.updateSaveIndicator('saved');
            this.updateToolbarState();

        } catch (error) {
            console.error('Failed to initialize CV editor:', error);
            this.showErrorState(error.message || 'Failed to initialize CV editor');
            this.updateSaveIndicator('error');
            throw error;
        }
    }

    /**
     * Restore document-level styles from saved state (Phase 3)
     */
    restoreDocumentStyles(editorState) {
        if (!editorState.documentStyles) return;

        const styles = editorState.documentStyles;

        // Restore line height
        const lineHeightSelect = document.getElementById('cv-line-height');
        if (lineHeightSelect && styles.lineHeight) {
            lineHeightSelect.value = styles.lineHeight;
        }

        // Restore margins
        if (styles.margins) {
            const marginTop = document.getElementById('cv-margin-top');
            const marginRight = document.getElementById('cv-margin-right');
            const marginBottom = document.getElementById('cv-margin-bottom');
            const marginLeft = document.getElementById('cv-margin-left');

            if (marginTop) marginTop.value = styles.margins.top || 1.0;
            if (marginRight) marginRight.value = styles.margins.right || 1.0;
            if (marginBottom) marginBottom.value = styles.margins.bottom || 1.0;
            if (marginLeft) marginLeft.value = styles.margins.left || 1.0;
        }

        // Restore page size
        const pageSizeSelect = document.getElementById('cv-page-size');
        if (pageSizeSelect && styles.pageSize) {
            pageSizeSelect.value = styles.pageSize;
        }

        // Restore header and footer
        if (editorState.header) {
            const headerInput = document.getElementById('cv-header-text');
            if (headerInput) headerInput.value = editorState.header;
        }

        if (editorState.footer) {
            const footerInput = document.getElementById('cv-footer-text');
            if (footerInput) footerInput.value = editorState.footer;
        }
    }

    /**
     * Load editor state from MongoDB
     */
    async loadEditorState() {
        try {
            const response = await fetch(`/api/jobs/${this.jobId}/cv-editor`);

            if (!response.ok) {
                throw new Error(`Failed to load editor state: ${response.statusText}`);
            }

            const data = await response.json();
            return data.editor_state || { content: this.getDefaultContent() };

        } catch (error) {
            console.error('Error loading editor state:', error);
            // Return default content if load fails
            return { content: this.getDefaultContent() };
        }
    }

    /**
     * Get default CV content structure
     */
    getDefaultContent() {
        return {
            type: 'doc',
            content: [
                {
                    type: 'heading',
                    attrs: { level: 1 },
                    content: [{ type: 'text', text: 'Your Name' }]
                },
                {
                    type: 'paragraph',
                    content: [{ type: 'text', text: 'Software Engineer | your.email@example.com' }]
                },
                {
                    type: 'heading',
                    attrs: { level: 2 },
                    content: [{ type: 'text', text: 'EXPERIENCE' }]
                },
                {
                    type: 'bulletList',
                    content: [
                        {
                            type: 'listItem',
                            content: [{
                                type: 'paragraph',
                                content: [{ type: 'text', text: 'Add your experience here...' }]
                            }]
                        }
                    ]
                }
            ]
        };
    }

    /**
     * Show loading animation while CV is loading from MongoDB
     */
    showLoadingState() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div id="cv-editor-loading"
                 class="flex flex-col items-center justify-center h-full p-8"
                 role="status"
                 aria-live="polite"
                 aria-label="Loading CV editor">

                <!-- Skeleton Content (mimics CV structure) -->
                <div class="w-full max-w-2xl space-y-6 animate-pulse">
                    <!-- Skeleton Header -->
                    <div class="space-y-3">
                        <div class="h-8 bg-gray-300 rounded w-3/4"></div>
                        <div class="h-4 bg-gray-200 rounded w-1/2"></div>
                    </div>

                    <!-- Skeleton Section 1 -->
                    <div class="space-y-2 mt-6">
                        <div class="h-6 bg-gray-300 rounded w-1/3"></div>
                        <div class="h-4 bg-gray-200 rounded w-full"></div>
                        <div class="h-4 bg-gray-200 rounded w-full"></div>
                        <div class="h-4 bg-gray-200 rounded w-5/6"></div>
                    </div>

                    <!-- Skeleton Section 2 -->
                    <div class="space-y-2 mt-6">
                        <div class="h-6 bg-gray-300 rounded w-2/5"></div>
                        <div class="h-4 bg-gray-200 rounded w-4/5"></div>
                        <div class="h-4 bg-gray-200 rounded w-4/5"></div>
                        <div class="h-4 bg-gray-200 rounded w-3/4"></div>
                    </div>

                    <!-- Skeleton List -->
                    <div class="space-y-2 mt-6">
                        <div class="h-6 bg-gray-300 rounded w-1/4"></div>
                        <div class="flex items-start space-x-2">
                            <div class="w-2 h-2 bg-gray-300 rounded-full mt-2"></div>
                            <div class="flex-1 h-4 bg-gray-200 rounded"></div>
                        </div>
                        <div class="flex items-start space-x-2">
                            <div class="w-2 h-2 bg-gray-300 rounded-full mt-2"></div>
                            <div class="flex-1 h-4 bg-gray-200 rounded"></div>
                        </div>
                        <div class="flex items-start space-x-2">
                            <div class="w-2 h-2 bg-gray-300 rounded-full mt-2"></div>
                            <div class="flex-1 h-4 bg-gray-200 rounded w-4/5"></div>
                        </div>
                    </div>
                </div>

                <!-- Loading Indicator -->
                <div class="flex items-center justify-center mt-8 text-indigo-600">
                    <svg class="animate-spin h-5 w-5 mr-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span class="text-sm font-medium">Loading your CV...</span>
                </div>
                <p class="text-xs text-gray-500 mt-2">This may take a few seconds</p>
            </div>
        `;
    }

    /**
     * Hide loading animation with smooth fade-out
     */
    hideLoadingState() {
        const loading = document.getElementById('cv-editor-loading');
        if (loading) {
            // Smooth fade-out
            loading.style.opacity = '0';
            loading.style.transition = 'opacity 0.3s ease-out';

            setTimeout(() => {
                if (loading.parentNode) {
                    loading.remove();
                }
            }, 300);
        }
    }

    /**
     * Show error state when loading or initialization fails
     */
    showErrorState(message) {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="flex flex-col items-center justify-center h-full p-8 text-center">
                <div class="text-red-600 mb-4">
                    <svg class="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>
                <h3 class="text-xl font-bold text-gray-800 mb-2">Failed to Load CV</h3>
                <p class="text-gray-600 mb-4 max-w-md">${this.escapeHtml(message)}</p>
                <div class="bg-yellow-50 border border-yellow-200 rounded p-4 text-left max-w-md">
                    <p class="font-semibold text-gray-800 mb-2">Common causes:</p>
                    <ul class="list-disc ml-4 text-sm text-gray-700 space-y-1">
                        <li>Browser extension blocking CDN scripts (ad blocker, VPN, privacy tool)</li>
                        <li>Corporate firewall blocking external resources</li>
                        <li>Network connectivity issues</li>
                        <li>MongoDB connection problems</li>
                    </ul>
                    <p class="font-semibold text-gray-800 mt-4 mb-2">Try these steps:</p>
                    <ol class="list-decimal ml-4 text-sm text-gray-700 space-y-1">
                        <li>Disable browser extensions temporarily</li>
                        <li>Refresh the page (Ctrl/Cmd + R)</li>
                        <li>Try a different browser</li>
                        <li>Check browser console for specific errors</li>
                    </ol>
                </div>
                <button onclick="location.reload()"
                        class="mt-6 px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 transition">
                    Reload Page
                </button>
            </div>
        `;
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Handle editor content updates
     */
    handleEditorUpdate() {
        const currentContent = JSON.stringify(this.editor.getJSON());

        // Only trigger save if content actually changed
        if (currentContent !== this.lastSavedContent) {
            this.saveStatus = 'unsaved';
            this.updateSaveIndicator('unsaved');
            this.scheduleAutoSave();
        }
    }

    /**
     * Schedule auto-save after delay
     */
    scheduleAutoSave() {
        // Clear existing timeout
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }

        // Schedule new save
        this.saveTimeout = setTimeout(() => {
            this.save();
        }, this.AUTOSAVE_DELAY);
    }

    /**
     * Save editor state to MongoDB (Phases 1, 2, 3)
     */
    async save() {
        this.saveStatus = 'saving';
        this.updateSaveIndicator('saving');

        try {
            const editorState = {
                version: 1,
                content: this.editor.getJSON(),
                documentStyles: this.getDocumentStyles(),
                lastModified: new Date().toISOString(),
            };

            // Phase 3: Add header and footer if present
            const headerText = this.getHeaderText();
            const footerText = this.getFooterText();
            if (headerText) {
                editorState.header = headerText;
            }
            if (footerText) {
                editorState.footer = footerText;
            }

            const response = await fetch(`/api/jobs/${this.jobId}/cv-editor`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(editorState),
            });

            if (!response.ok) {
                throw new Error(`Save failed: ${response.statusText}`);
            }

            const result = await response.json();

            // Update saved content reference
            this.lastSavedContent = JSON.stringify(this.editor.getJSON());
            this.saveStatus = 'saved';
            this.updateSaveIndicator('saved');

            console.log('CV saved successfully at', result.savedAt);

        } catch (error) {
            console.error('Save failed:', error);
            this.saveStatus = 'error';
            this.updateSaveIndicator('error');
        }
    }

    /**
     * Get current document styles (Phases 2 & 3)
     */
    getDocumentStyles() {
        // Get current values from UI controls (if they exist)
        const lineHeight = this.getCurrentLineHeight();
        const margins = this.getCurrentMargins();
        const pageSize = this.getCurrentPageSize();

        return {
            fontFamily: 'Inter',
            fontSize: 11,
            lineHeight: lineHeight,
            margins: margins,
            pageSize: pageSize
        };
    }

    /**
     * Get current line height from UI control
     */
    getCurrentLineHeight() {
        const lineHeightSelect = document.getElementById('cv-line-height');
        if (lineHeightSelect) {
            return parseFloat(lineHeightSelect.value);
        }
        return 1.15; // Default: standard resume spacing
    }

    /**
     * Get current margins from UI controls
     */
    getCurrentMargins() {
        const topMargin = document.getElementById('cv-margin-top');
        const rightMargin = document.getElementById('cv-margin-right');
        const bottomMargin = document.getElementById('cv-margin-bottom');
        const leftMargin = document.getElementById('cv-margin-left');

        return {
            top: topMargin ? parseFloat(topMargin.value) : 1.0,
            right: rightMargin ? parseFloat(rightMargin.value) : 1.0,
            bottom: bottomMargin ? parseFloat(bottomMargin.value) : 1.0,
            left: leftMargin ? parseFloat(leftMargin.value) : 1.0
        };
    }

    /**
     * Get current page size from UI control
     */
    getCurrentPageSize() {
        const pageSizeSelect = document.getElementById('cv-page-size');
        if (pageSizeSelect) {
            return pageSizeSelect.value;
        }
        return 'letter'; // Default: US Letter (8.5" x 11")
    }

    /**
     * Get header text (Phase 3)
     */
    getHeaderText() {
        const headerInput = document.getElementById('cv-header-text');
        return headerInput ? headerInput.value : '';
    }

    /**
     * Get footer text (Phase 3)
     */
    getFooterText() {
        const footerInput = document.getElementById('cv-footer-text');
        return footerInput ? footerInput.value : '';
    }

    /**
     * Apply document-level styles to editor container (Phase 3)
     */
    applyDocumentStyles() {
        if (!this.container) return;

        const lineHeight = this.getCurrentLineHeight();
        const margins = this.getCurrentMargins();
        const pageSize = this.getCurrentPageSize();

        // Apply line height to all paragraphs
        const editorElement = this.container.querySelector('.ProseMirror');
        if (editorElement) {
            editorElement.style.lineHeight = lineHeight;

            // Apply margins as padding
            editorElement.style.paddingTop = `${margins.top}in`;
            editorElement.style.paddingRight = `${margins.right}in`;
            editorElement.style.paddingBottom = `${margins.bottom}in`;
            editorElement.style.paddingLeft = `${margins.left}in`;

            // Apply page size
            if (pageSize === 'a4') {
                editorElement.style.maxWidth = '210mm';
                editorElement.style.minHeight = '297mm';
            } else {
                // Letter (8.5" x 11")
                editorElement.style.maxWidth = '8.5in';
                editorElement.style.minHeight = '11in';
            }
        }
    }

    /**
     * Update save indicator UI (Phase 5: Enhanced with ARIA live region)
     */
    updateSaveIndicator(status) {
        const indicator = document.getElementById('cv-save-indicator');
        if (!indicator) return;

        const states = {
            unsaved: {
                icon: '○',
                text: 'Unsaved',
                class: 'text-gray-500',
                ariaLabel: 'CV has unsaved changes'
            },
            saving: {
                icon: '◐',
                text: 'Saving...',
                class: 'text-blue-500 animate-pulse',
                ariaLabel: 'Saving CV to server'
            },
            saved: {
                icon: '●',
                text: 'Saved',
                class: 'text-green-500',
                ariaLabel: 'CV saved successfully'
            },
            error: {
                icon: '⚠️',
                text: 'Error',
                class: 'text-red-500',
                ariaLabel: 'Error saving CV'
            }
        };

        const state = states[status] || states.saved;

        // Update indicator with ARIA attributes
        indicator.innerHTML = `<span class="${state.class}" aria-label="${state.ariaLabel}">${state.icon} ${state.text}</span>`;

        // Update aria-live region for screen readers (only announce important states)
        if (status === 'saved' || status === 'error') {
            this.announceToScreenReader(state.text);
        }
    }

    /**
     * Announce message to screen readers via aria-live region (Phase 5)
     */
    announceToScreenReader(message) {
        let liveRegion = document.getElementById('cv-editor-sr-announcements');

        // Create live region if it doesn't exist
        if (!liveRegion) {
            liveRegion = document.createElement('div');
            liveRegion.id = 'cv-editor-sr-announcements';
            liveRegion.setAttribute('role', 'status');
            liveRegion.setAttribute('aria-live', 'polite');
            liveRegion.setAttribute('aria-atomic', 'true');
            liveRegion.className = 'sr-only';
            liveRegion.style.position = 'absolute';
            liveRegion.style.left = '-10000px';
            liveRegion.style.width = '1px';
            liveRegion.style.height = '1px';
            liveRegion.style.overflow = 'hidden';
            document.body.appendChild(liveRegion);
        }

        // Announce message
        liveRegion.textContent = message;

        // Clear after 1 second to allow for repeated announcements
        setTimeout(() => {
            liveRegion.textContent = '';
        }, 1000);
    }

    /**
     * Apply formatting command (Phase 2: Enhanced)
     */
    applyFormat(command, value = null) {
        if (!this.editor) return;

        switch (command) {
            case 'bold':
                this.editor.chain().focus().toggleBold().run();
                break;
            case 'italic':
                this.editor.chain().focus().toggleItalic().run();
                break;
            case 'underline':
                this.editor.chain().focus().toggleUnderline().run();
                break;
            case 'bulletList':
                this.editor.chain().focus().toggleBulletList().run();
                break;
            case 'orderedList':
                this.editor.chain().focus().toggleOrderedList().run();
                break;
            case 'heading1':
                this.editor.chain().focus().toggleHeading({ level: 1 }).run();
                break;
            case 'heading2':
                this.editor.chain().focus().toggleHeading({ level: 2 }).run();
                break;
            case 'heading3':
                this.editor.chain().focus().toggleHeading({ level: 3 }).run();
                break;
            case 'fontFamily':
                this.editor.chain().focus().setFontFamily(value).run();
                break;
            case 'fontSize':
                this.editor.chain().focus().setFontSize(value).run();
                break;
            case 'textAlign':
                this.editor.chain().focus().setTextAlign(value).run();
                break;
            case 'color':
                this.editor.chain().focus().setColor(value).run();
                break;
            case 'highlight':
                this.editor.chain().focus().setHighlight({ color: value }).run();
                break;
            case 'removeHighlight':
                this.editor.chain().focus().unsetHighlight().run();
                break;
            default:
                console.warn('Unknown format command:', command);
        }

        // Update toolbar state after formatting
        setTimeout(() => this.updateToolbarState(), 50);
    }

    /**
     * Increase paragraph indentation (Phase 2)
     */
    increaseIndent() {
        if (!this.editor) return;

        // Get current paragraph node
        const { state } = this.editor;
        const { selection } = state;
        const { $from } = selection;

        // Apply margin-left increment (0.5 inches)
        this.editor.chain().focus().command(({ tr, state }) => {
            const { selection } = state;
            const { $from } = selection;

            // Find paragraph node
            let depth = $from.depth;
            while (depth > 0) {
                const node = $from.node(depth);
                if (node.type.name === 'paragraph') {
                    const pos = $from.before(depth);
                    const currentMargin = parseFloat(node.attrs.style?.match(/margin-left:\s*([\d.]+)in/)?.[1] || '0');
                    const newMargin = currentMargin + 0.5;

                    tr.setNodeMarkup(pos, null, {
                        ...node.attrs,
                        style: `margin-left: ${newMargin}in`
                    });
                    return true;
                }
                depth--;
            }
            return false;
        }).run();
    }

    /**
     * Decrease paragraph indentation (Phase 2)
     */
    decreaseIndent() {
        if (!this.editor) return;

        this.editor.chain().focus().command(({ tr, state }) => {
            const { selection } = state;
            const { $from } = selection;

            // Find paragraph node
            let depth = $from.depth;
            while (depth > 0) {
                const node = $from.node(depth);
                if (node.type.name === 'paragraph') {
                    const pos = $from.before(depth);
                    const currentMargin = parseFloat(node.attrs.style?.match(/margin-left:\s*([\d.]+)in/)?.[1] || '0');
                    const newMargin = Math.max(0, currentMargin - 0.5);

                    if (newMargin > 0) {
                        tr.setNodeMarkup(pos, null, {
                            ...node.attrs,
                            style: `margin-left: ${newMargin}in`
                        });
                    } else {
                        // Remove margin-left if 0
                        const { style, ...otherAttrs } = node.attrs;
                        tr.setNodeMarkup(pos, null, otherAttrs);
                    }
                    return true;
                }
                depth--;
            }
            return false;
        }).run();
    }

    /**
     * Update toolbar button active states (Phase 2, Phase 5: ARIA support)
     */
    updateToolbarState() {
        if (!this.editor) return;

        // Update alignment buttons
        const alignments = ['left', 'center', 'right', 'justify'];
        alignments.forEach(align => {
            const btn = document.querySelector(`button[data-align="${align}"]`);
            if (btn) {
                const isActive = this.editor.isActive({ textAlign: align });
                btn.classList.toggle('bg-blue-100', isActive);
                btn.classList.toggle('border-blue-300', isActive);
                // Phase 5: Update ARIA pressed state
                btn.setAttribute('aria-pressed', isActive.toString());
            }
        });

        // Update formatting buttons
        ['bold', 'italic', 'underline', 'bulletList', 'orderedList'].forEach(format => {
            const btn = document.querySelector(`button[data-format="${format}"]`);
            if (btn) {
                const isActive = this.editor.isActive(format);
                btn.classList.toggle('bg-gray-300', isActive);
                // Phase 5: Update ARIA pressed state
                btn.setAttribute('aria-pressed', isActive.toString());
            }
        });

        // Update heading buttons
        [1, 2, 3].forEach(level => {
            const btn = document.querySelector(`button[data-heading="${level}"]`);
            if (btn) {
                const isActive = this.editor.isActive('heading', { level });
                btn.classList.toggle('bg-gray-300', isActive);
                // Phase 5: Update ARIA pressed state
                btn.setAttribute('aria-pressed', isActive.toString());
            }
        });
    }

    /**
     * Check if format is active
     */
    isFormatActive(format) {
        if (!this.editor) return false;

        switch (format) {
            case 'bold':
                return this.editor.isActive('bold');
            case 'italic':
                return this.editor.isActive('italic');
            case 'underline':
                return this.editor.isActive('underline');
            case 'bulletList':
                return this.editor.isActive('bulletList');
            case 'orderedList':
                return this.editor.isActive('orderedList');
            default:
                return false;
        }
    }

    /**
     * Destroy editor instance
     */
    destroy() {
        if (this.editor) {
            this.editor.destroy();
            this.editor = null;
        }
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
    }
}

// Global editor instance
let cvEditorInstance = null;

/**
 * Open CV editor side panel
 */
async function openCVEditorPanel() {
    const panel = document.getElementById('cv-editor-panel');
    const overlay = document.getElementById('cv-editor-overlay');
    const editorContainer = document.getElementById('cv-editor-content');

    if (!panel || !overlay || !editorContainer) {
        console.error('CV editor panel elements not found');
        return;
    }

    // Show panel and overlay
    overlay.classList.remove('hidden');
    setTimeout(() => {
        panel.classList.remove('translate-x-full');
    }, 10);

    // Initialize editor if not already initialized
    if (!cvEditorInstance) {
        cvEditorInstance = new CVEditor(jobId, editorContainer);
        await cvEditorInstance.init();
    }
}

/**
 * Close CV editor side panel
 */
function closeCVEditorPanel() {
    const panel = document.getElementById('cv-editor-panel');
    const overlay = document.getElementById('cv-editor-overlay');

    if (panel && overlay) {
        panel.classList.add('translate-x-full');
        setTimeout(() => {
            overlay.classList.add('hidden');
        }, 300);
    }

    // Update main CV display with editor content (Fix Issue #1: Immediate Update)
    if (cvEditorInstance && cvEditorInstance.editor) {
        updateMainCVDisplay();
    }

    // Optionally destroy editor instance to free memory
    // Note: Keeping it alive for better UX on reopen
    // if (cvEditorInstance) {
    //     cvEditorInstance.destroy();
    //     cvEditorInstance = null;
    // }
}

/**
 * Update main CV display with current editor content
 * Converts TipTap JSON to HTML and updates the #cv-markdown-display element
 */
function updateMainCVDisplay() {
    if (!cvEditorInstance || !cvEditorInstance.editor) {
        console.warn('Cannot update CV display: editor not initialized');
        return;
    }

    try {
        // Get TipTap HTML output
        const htmlContent = cvEditorInstance.editor.getHTML();

        // Update the main CV display container
        const cvDisplay = document.getElementById('cv-markdown-display');
        if (cvDisplay) {
            cvDisplay.innerHTML = htmlContent;
            console.log('✅ Main CV display updated with editor content');
        } else {
            console.warn('CV display element not found');
        }

        // Also update the textarea backup (for legacy edit mode)
        const cvTextarea = document.getElementById('cv-markdown-editor');
        if (cvTextarea) {
            // Convert HTML back to markdown (basic conversion)
            const markdownContent = htmlToMarkdown(htmlContent);
            cvTextarea.value = markdownContent;
            window.cvContent = markdownContent;
        }
    } catch (error) {
        console.error('Failed to update main CV display:', error);
    }
}

/**
 * Convert HTML to Markdown (basic conversion for backward compatibility)
 */
function htmlToMarkdown(html) {
    // Create a temporary div to parse HTML
    const temp = document.createElement('div');
    temp.innerHTML = html;

    let markdown = '';

    // Process each child node
    temp.childNodes.forEach(node => {
        markdown += processNodeToMarkdown(node);
    });

    return markdown.trim();
}

/**
 * Process a single DOM node to Markdown
 */
function processNodeToMarkdown(node, depth = 0) {
    if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent;
    }

    if (node.nodeType !== Node.ELEMENT_NODE) {
        return '';
    }

    const tag = node.tagName.toLowerCase();
    let content = '';
    let prefix = '';
    let suffix = '';

    // Get inner content recursively
    node.childNodes.forEach(child => {
        content += processNodeToMarkdown(child, depth + 1);
    });

    // Convert tags to markdown
    switch (tag) {
        case 'h1':
            return `# ${content}\n\n`;
        case 'h2':
            return `## ${content}\n\n`;
        case 'h3':
            return `### ${content}\n\n`;
        case 'h4':
            return `#### ${content}\n\n`;
        case 'h5':
            return `##### ${content}\n\n`;
        case 'h6':
            return `###### ${content}\n\n`;
        case 'p':
            return `${content}\n\n`;
        case 'strong':
        case 'b':
            return `**${content}**`;
        case 'em':
        case 'i':
            return `*${content}*`;
        case 'u':
            return `<u>${content}</u>`; // Markdown doesn't have native underline
        case 'ul':
            return `${content}\n`;
        case 'ol':
            return `${content}\n`;
        case 'li':
            const indent = '  '.repeat(depth);
            if (node.parentNode.tagName.toLowerCase() === 'ol') {
                return `${indent}1. ${content}\n`;
            } else {
                return `${indent}- ${content}\n`;
            }
        case 'br':
            return '\n';
        case 'mark':
            return `==${content}==`;
        case 'code':
            return `\`${content}\``;
        case 'pre':
            return `\`\`\`\n${content}\n\`\`\`\n\n`;
        case 'blockquote':
            return `> ${content}\n\n`;
        case 'a':
            const href = node.getAttribute('href');
            return `[${content}](${href})`;
        default:
            return content;
    }
}

/**
 * Toggle panel size (collapse/expand)
 */
function toggleCVPanelSize() {
    const panel = document.getElementById('cv-editor-panel');
    if (!panel) return;

    // Toggle between different width classes
    if (panel.classList.contains('w-full')) {
        panel.classList.remove('w-full');
        panel.classList.add('w-11/12', 'sm:w-2/3', 'lg:w-1/2');
    } else {
        panel.classList.remove('w-11/12', 'sm:w-2/3', 'lg:w-1/2');
        panel.classList.add('w-full');
    }
}

/**
 * Apply formatting from toolbar
 */
function applyCVFormat(command, value = null) {
    if (cvEditorInstance) {
        cvEditorInstance.applyFormat(command, value);
    }
}

/**
 * Apply document-level style changes (Phase 3)
 */
function applyDocumentStyle(styleType) {
    if (cvEditorInstance) {
        // Apply styles to editor immediately
        cvEditorInstance.applyDocumentStyles();

        // Trigger auto-save
        cvEditorInstance.scheduleAutoSave();
    }
}

/**
 * Export CV to PDF (Phase 4: Playwright-based PDF generation)
 */
async function exportCVToPDF() {
    if (!cvEditorInstance) {
        alert('Please open the CV editor first');
        return;
    }

    try {
        // Show loading state
        notifyUser('Generating PDF...', 'info');

        // Trigger auto-save first to ensure latest content is saved
        await cvEditorInstance.save();

        // Call PDF generation endpoint
        const response = await fetch(`/api/jobs/${cvEditorInstance.jobId}/cv-editor/pdf`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
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

        notifyUser('PDF downloaded successfully!', 'success');

    } catch (error) {
        console.error('PDF export failed:', error);
        notifyUser(`PDF export failed: ${error.message}`, 'error');
    }
}

/**
 * Show toast notification using global function from base.html
 *
 * This helper safely calls the global showToast without creating recursion.
 * Uses a different function name to avoid conflicts.
 */
function notifyUser(message, type = 'info') {
    // Use global showToast from base.html if available
    if (typeof window.showToast === 'function') {
        window.showToast(message, type);
    } else {
        // Fallback for when base.html toast isn't available
        console.log(`[${type.toUpperCase()}] ${message}`);
        if (type === 'error') {
            alert(message);
        }
    }
}

// ============================================================================
// Phase 5: Keyboard Shortcuts
// ============================================================================
// The following shortcuts are supported:
// - Ctrl/Cmd+B: Bold (handled by TipTap)
// - Ctrl/Cmd+I: Italic (handled by TipTap)
// - Ctrl/Cmd+U: Underline (handled by TipTap)
// - Ctrl/Cmd+Z: Undo (handled by TipTap)
// - Ctrl/Cmd+Y or Ctrl/Cmd+Shift+Z: Redo (handled by TipTap)
// - Ctrl/Cmd+S: Save CV manually
// - Esc: Close editor panel
// - Tab: Increase indent (handled in editor)
// - Shift+Tab: Decrease indent (handled in editor)
// ============================================================================

document.addEventListener('keydown', (e) => {
    if (!cvEditorInstance || !cvEditorInstance.editor) return;

    // Ctrl+S to save (override browser default)
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        cvEditorInstance.save();
        cvEditorInstance.announceToScreenReader('CV saved');
        return;
    }

    // Esc to close panel
    if (e.key === 'Escape') {
        closeCVEditorPanel();
        return;
    }
});
