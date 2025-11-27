/**
 * CV Rich Text Editor - TipTap Implementation
 *
 * Features:
 * - TipTap editor with rich formatting (bold, italic, underline, lists, headings)
 * - Side panel UI with collapse/expand
 * - Auto-save to MongoDB after 3 seconds of inactivity
 * - Save indicator with visual feedback
 * - State restoration from MongoDB
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
                        style: `font-family: 'Inter', sans-serif; font-size: 11pt;`
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
     * Save editor state to MongoDB
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
     * Get current document styles
     */
    getDocumentStyles() {
        return {
            fontFamily: 'Inter',
            fontSize: 11,
            lineHeight: 1.4,
            margins: {
                top: 0.75,
                right: 0.75,
                bottom: 0.75,
                left: 0.75
            },
            pageSize: 'letter'
        };
    }

    /**
     * Update save indicator UI
     */
    updateSaveIndicator(status) {
        const indicator = document.getElementById('cv-save-indicator');
        if (!indicator) return;

        const states = {
            unsaved: {
                icon: '○',
                text: 'Unsaved',
                class: 'text-gray-500'
            },
            saving: {
                icon: '◐',
                text: 'Saving...',
                class: 'text-blue-500 animate-pulse'
            },
            saved: {
                icon: '●',
                text: 'Saved',
                class: 'text-green-500'
            },
            error: {
                icon: '⚠️',
                text: 'Error',
                class: 'text-red-500'
            }
        };

        const state = states[status] || states.saved;
        indicator.innerHTML = `<span class="${state.class}">${state.icon} ${state.text}</span>`;
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
     * Update toolbar button active states (Phase 2)
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
            }
        });

        // Update formatting buttons
        ['bold', 'italic', 'underline', 'bulletList', 'orderedList'].forEach(format => {
            const btn = document.querySelector(`button[data-format="${format}"]`);
            if (btn) {
                const isActive = this.editor.isActive(format);
                btn.classList.toggle('bg-gray-300', isActive);
            }
        });

        // Update heading buttons
        [1, 2, 3].forEach(level => {
            const btn = document.querySelector(`button[data-heading="${level}"]`);
            if (btn) {
                const isActive = this.editor.isActive('heading', { level });
                btn.classList.toggle('bg-gray-300', isActive);
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
 * Export CV to PDF
 */
async function exportCVToPDF() {
    if (!cvEditorInstance) {
        alert('Please open the CV editor first');
        return;
    }

    // For Phase 1, show a placeholder message
    // TODO: Implement PDF export in Phase 4
    alert('PDF export will be implemented in Phase 4. For now, you can save your CV and use the existing "Export PDF" button.');
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (!cvEditorInstance || !cvEditorInstance.editor) return;

    // Ctrl+S to save
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        cvEditorInstance.save();
    }

    // Esc to close panel
    if (e.key === 'Escape') {
        closeCVEditorPanel();
    }
});
