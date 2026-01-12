/**
 * Mobile Annotation Editor
 *
 * Touch-optimized annotation system with bottom sheet UI.
 * Supports tap-to-select with smart sentence detection.
 */

document.addEventListener('alpine:init', () => {
    Alpine.data('mobileAnnotation', () => ({
        // State
        jobId: null,
        jdContent: '',
        annotations: [],
        isLoading: false,
        isSaving: false,

        // Selection state
        selectedText: '',
        selectedRange: null,
        showSheet: false,

        // Current annotation being created/edited
        currentAnnotation: {
            relevance: 'relevant',
            requirement_type: 'neutral',
            identity: 'peripheral',
            passion: 'neutral',
            reframe_note: ''
        },

        // Persona state
        personaStatement: null,
        personaLoading: false,
        hasIdentityAnnotations: false,

        // Auto-generate state
        autoGenerating: false,

        // Undo state (single-level undo for mobile)
        lastDeletedAnnotation: null,

        // Options
        relevanceOptions: [
            { value: 'core_strength', label: 'Core Strength', emoji: '💪', color: 'text-green-400' },
            { value: 'extremely_relevant', label: 'Very Relevant', emoji: '🎯', color: 'text-emerald-400' },
            { value: 'relevant', label: 'Relevant', emoji: '✓', color: 'text-blue-400' },
            { value: 'tangential', label: 'Tangential', emoji: '〰️', color: 'text-yellow-400' },
            { value: 'gap', label: 'Gap', emoji: '❌', color: 'text-red-400' }
        ],

        requirementOptions: [
            { value: 'must_have', label: 'Must Have', emoji: '⚡' },
            { value: 'nice_to_have', label: 'Nice to Have', emoji: '✨' },
            { value: 'neutral', label: 'Neutral', emoji: '➖' },
            { value: 'disqualifier', label: 'Disqualifier', emoji: '🚫' }
        ],

        identityOptions: [
            { value: 'core_identity', label: 'Core Identity', emoji: '🌟', color: 'text-purple-400' },
            { value: 'strong_identity', label: 'Strong', emoji: '💜', color: 'text-purple-300' },
            { value: 'developing', label: 'Developing', emoji: '🌱', color: 'text-green-400' },
            { value: 'peripheral', label: 'Peripheral', emoji: '○', color: 'text-gray-400' },
            { value: 'not_identity', label: 'Not Me', emoji: '✕', color: 'text-red-400' }
        ],

        passionOptions: [
            { value: 'love_it', label: 'Love It', emoji: '❤️', color: 'text-red-400' },
            { value: 'enjoy', label: 'Enjoy', emoji: '😊', color: 'text-orange-400' },
            { value: 'neutral', label: 'Neutral', emoji: '😐', color: 'text-gray-400' },
            { value: 'tolerate', label: 'Tolerate', emoji: '😕', color: 'text-yellow-400' },
            { value: 'avoid', label: 'Avoid', emoji: '😣', color: 'text-red-500' }
        ],

        // Initialize
        async init() {
            // Will be called when job changes
        },

        async loadAnnotations(jobId, jdContent) {
            this.jobId = jobId;
            this.jdContent = jdContent || '';
            this.isLoading = true;

            try {
                const response = await fetch(`/api/jobs/${jobId}/jd-annotations`);
                if (!response.ok) throw new Error('Failed to load annotations');

                const data = await response.json();
                // Issue 1: Auto-approve AI suggestions (auto-apply UX)
                this.annotations = (data.annotations || []).map(ann => ({
                    ...ann,
                    // Auto-approve auto_generated annotations on load
                    status: ann.source === 'auto_generated' && !ann.status ? 'approved' : ann.status
                }));
                this.personaStatement = data.synthesized_persona?.persona_statement || null;

                this.checkIdentityAnnotations();

            } catch (error) {
                console.error('Failed to load annotations:', error);
                this.annotations = [];
            } finally {
                this.isLoading = false;
            }
        },

        // Check if there are identity-relevant annotations for persona
        checkIdentityAnnotations() {
            const identityLevels = ['core_identity', 'strong_identity', 'developing'];
            const passionLevels = ['love_it', 'enjoy'];
            const strengthLevels = ['core_strength', 'extremely_relevant'];

            this.hasIdentityAnnotations = this.annotations.some(a =>
                a.is_active !== false && (
                    identityLevels.includes(a.identity) ||
                    passionLevels.includes(a.passion) ||
                    strengthLevels.includes(a.relevance)
                )
            );
        },

        // Handle text selection (tap or long press)
        handleTextTap(event) {
            // Prevent if tapping on already annotated text
            if (event.target.classList.contains('annotation-highlight')) {
                this.showAnnotationDetails(event.target.dataset.annotationId);
                return;
            }

            // Get selection
            const selection = window.getSelection();

            // If no selection, try smart sentence selection
            if (!selection || selection.isCollapsed) {
                const sentence = this.findSentenceAtPoint(event.target, event.clientX, event.clientY);
                if (sentence) {
                    this.selectedText = sentence.text;
                    this.selectedRange = sentence.range;
                    this.openAnnotationSheet();
                }
                return;
            }

            // Use existing selection
            const text = selection.toString().trim();
            if (text.length > 10) {
                this.selectedText = text;
                this.selectedRange = selection.getRangeAt(0);
                this.openAnnotationSheet();
            }
        },

        // Smart sentence detection at tap point
        findSentenceAtPoint(element, x, y) {
            // Get text content
            const textContent = element.textContent || '';
            if (!textContent.trim()) return null;

            // Find character position at tap point (simplified)
            const range = document.caretRangeFromPoint(x, y);
            if (!range) return null;

            const text = range.startContainer.textContent || '';
            const offset = range.startOffset;

            // Find sentence boundaries
            const sentenceEnders = /[.!?\n]/g;
            let start = 0;
            let end = text.length;

            // Find start of sentence
            for (let i = offset - 1; i >= 0; i--) {
                if (sentenceEnders.test(text[i])) {
                    start = i + 1;
                    break;
                }
            }

            // Find end of sentence
            for (let i = offset; i < text.length; i++) {
                if (sentenceEnders.test(text[i])) {
                    end = i + 1;
                    break;
                }
            }

            const sentence = text.substring(start, end).trim();
            if (sentence.length < 10) return null;

            // Create range for highlighting
            const newRange = document.createRange();
            newRange.setStart(range.startContainer, start);
            newRange.setEnd(range.startContainer, Math.min(end, text.length));

            return { text: sentence, range: newRange };
        },

        // Open annotation bottom sheet
        openAnnotationSheet() {
            // Reset to defaults (Issue 2: use specified defaults)
            this.currentAnnotation = {
                relevance: 'core_strength',  // Default per Issue 2
                requirement_type: 'must_have',  // Default per Issue 2
                identity: 'peripheral',  // Default per Issue 2
                passion: 'neutral',  // Default per Issue 2
                reframe_note: ''
            };
            this.showSheet = true;

            // Haptic feedback
            if ('vibrate' in navigator) {
                navigator.vibrate(30);
            }
        },

        // Close annotation sheet
        closeSheet() {
            this.showSheet = false;
            this.selectedText = '';
            this.selectedRange = null;
            this.editingAnnotationId = null;  // Clear editing state
            window.getSelection()?.removeAllRanges();
        },

        // Save annotation
        async saveAnnotation() {
            if (!this.selectedText || !this.jobId) return;

            this.isSaving = true;

            try {
                // Check if we're editing an existing annotation
                if (this.editingAnnotationId) {
                    // Find and update existing annotation
                    const existingIndex = this.annotations.findIndex(a => a.id === this.editingAnnotationId);
                    if (existingIndex !== -1) {
                        const existing = this.annotations[existingIndex];

                        // Update the annotation values
                        existing.relevance = this.currentAnnotation.relevance;
                        existing.requirement_type = this.currentAnnotation.requirement_type;
                        existing.identity = this.currentAnnotation.identity;
                        existing.passion = this.currentAnnotation.passion;
                        existing.has_reframe = !!this.currentAnnotation.reframe_note;
                        existing.reframe_note = this.currentAnnotation.reframe_note || null;
                        existing.updated_at = new Date().toISOString();

                        // Replace in array to trigger reactivity
                        this.annotations[existingIndex] = { ...existing };
                    }

                    // Clear editing state
                    this.editingAnnotationId = null;
                } else {
                    // Create new annotation
                    const newAnnotation = {
                        id: crypto.randomUUID(),
                        target: {
                            text: this.selectedText,
                            char_start: 0,
                            char_end: this.selectedText.length
                        },
                        annotation_type: 'skill_match',
                        relevance: this.currentAnnotation.relevance,
                        requirement_type: this.currentAnnotation.requirement_type,
                        identity: this.currentAnnotation.identity,
                        passion: this.currentAnnotation.passion,
                        has_reframe: !!this.currentAnnotation.reframe_note,
                        reframe_note: this.currentAnnotation.reframe_note || null,
                        is_active: true,
                        status: 'approved',
                        source: 'manual',  // Changed from 'human' for consistency
                        created_at: new Date().toISOString()
                    };

                    // Add to local array
                    this.annotations.push(newAnnotation);

                    // Issue 3: Capture learning signal for manual annotations
                    this.captureManualAnnotationLearning(newAnnotation);
                }

                // Save to server
                await this.saveAnnotationsToServer();

                // Check for persona eligibility
                this.checkIdentityAnnotations();

                // Haptic feedback
                if ('vibrate' in navigator) {
                    navigator.vibrate([50, 30, 50]);
                }

                window.showToast?.('Annotation saved', 'success');
                this.closeSheet();

            } catch (error) {
                console.error('Failed to save annotation:', error);
                window.showToast?.('Failed to save', 'error');
            } finally {
                this.isSaving = false;
            }
        },

        // Save annotations to server
        async saveAnnotationsToServer() {
            // Capture feedback for auto-generated annotations before saving
            for (const annotation of this.annotations) {
                if (annotation.source === 'auto_generated' &&
                    annotation.original_values &&
                    !annotation.feedback_captured) {
                    // Fire and forget - don't block the save
                    this.captureAnnotationFeedback(annotation, 'save');
                }
            }

            const response = await fetch(`/api/jobs/${this.jobId}/jd-annotations`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    annotations: this.annotations,
                    annotation_version: 1
                })
            });

            if (!response.ok) {
                throw new Error('Failed to save annotations');
            }
        },

        /**
         * Capture feedback for auto-generated annotations with retry logic.
         * Called when user saves or deletes an annotation.
         * Uses direct VPS call to bypass Vercel timeout.
         * Implements exponential backoff (1s, 2s, 4s) for resilience against 502/network errors.
         *
         * @param {Object} annotation - The annotation object
         * @param {string} action - "save" or "delete"
         * @param {number} retryCount - Internal retry counter (default: 0)
         */
        async captureAnnotationFeedback(annotation, action, retryCount = 0) {
            const MAX_RETRIES = 3;
            const BASE_DELAY = 1000; // 1 second

            if (annotation.source !== 'auto_generated') return;
            if (!annotation.original_values) return;
            if (annotation.feedback_captured && action === 'save') return;

            // Show subtle syncing toast only on first attempt
            if (retryCount === 0) {
                window.showToast?.('Syncing feedback...', 'info', 1000);
            }

            try {
                const payload = {
                    annotation_id: annotation.id,
                    action: action,
                    original_values: annotation.original_values,
                    // Include target info for context-aware deletion learning
                    target: {
                        section: annotation.target?.section || null,
                        text: annotation.target?.text || null,
                    },
                };

                if (action === 'save') {
                    payload.final_values = {
                        relevance: annotation.relevance,
                        passion: annotation.passion,
                        identity: annotation.identity,
                        requirement_type: annotation.requirement_type,
                    };
                }

                // Direct VPS call to bypass Vercel timeout (10s limit)
                const runnerUrl = window.RUNNER_URL || '';
                const runnerToken = window.RUNNER_TOKEN || '';

                const response = await fetch(`${runnerUrl}/user/annotation-feedback`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${runnerToken}`,
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        if (action === 'save') {
                            annotation.feedback_captured = true;
                        }
                        // Brief success indicator
                        window.showToast?.('Feedback synced', 'success', 800);
                        return; // Success - exit
                    }
                }

                // Non-OK response (502, 503, etc.) - retry if we have attempts left
                if (retryCount < MAX_RETRIES) {
                    const delay = BASE_DELAY * Math.pow(2, retryCount); // Exponential backoff
                    console.warn(`Feedback capture failed (${response.status}), retrying in ${delay}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
                    setTimeout(() => this.captureAnnotationFeedback(annotation, action, retryCount + 1), delay);
                    return;
                }

                // All retries exhausted
                console.error(`Feedback capture failed after ${MAX_RETRIES} retries for annotation ${annotation.id}`);
            } catch (error) {
                // Network error - retry if we have attempts left
                if (retryCount < MAX_RETRIES) {
                    const delay = BASE_DELAY * Math.pow(2, retryCount);
                    console.warn(`Feedback capture error: ${error.message}, retrying in ${delay}ms... (attempt ${retryCount + 1}/${MAX_RETRIES})`);
                    setTimeout(() => this.captureAnnotationFeedback(annotation, action, retryCount + 1), delay);
                    return;
                }

                // All retries exhausted - silent failure
                console.error(`Feedback capture failed after ${MAX_RETRIES} retries:`, error);
            }
        },

        /**
         * Capture learning signal from manual annotations (Issue 3: Learn from manual annotations)
         * Manual annotations represent positive signals - the user explicitly marked this text as relevant.
         * @param {Object} annotation - The manual annotation object
         * @param {number} retryCount - Internal retry counter (default: 0)
         */
        async captureManualAnnotationLearning(annotation, retryCount = 0) {
            const MAX_RETRIES = 3;
            const BASE_DELAY = 1000;

            // Only capture for manual annotations
            if (annotation.source !== 'manual') return;
            // Skip if already captured
            if (annotation.learning_captured) return;

            try {
                const payload = {
                    annotation_id: annotation.id,
                    action: 'manual_create',
                    target: {
                        section: annotation.target?.section || null,
                        text: annotation.target?.text || null,
                    },
                    values: {
                        relevance: annotation.relevance,
                        passion: annotation.passion,
                        identity: annotation.identity,
                        requirement_type: annotation.requirement_type,
                    },
                };

                const runnerUrl = window.RUNNER_URL || '';
                const runnerToken = window.RUNNER_TOKEN || '';

                const response = await fetch(`${runnerUrl}/user/annotation-feedback`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${runnerToken}`,
                    },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        annotation.learning_captured = true;
                        console.log('[ManualLearning] Captured positive signal:', annotation.target?.text?.substring(0, 50));
                        return;
                    }
                }

                // Retry on failure
                if (retryCount < MAX_RETRIES) {
                    const delay = BASE_DELAY * Math.pow(2, retryCount);
                    setTimeout(() => this.captureManualAnnotationLearning(annotation, retryCount + 1), delay);
                }
            } catch (error) {
                if (retryCount < MAX_RETRIES) {
                    const delay = BASE_DELAY * Math.pow(2, retryCount);
                    setTimeout(() => this.captureManualAnnotationLearning(annotation, retryCount + 1), delay);
                } else {
                    console.error('[ManualLearning] Failed after retries:', error);
                }
            }
        },

        // Generate persona
        async generatePersona() {
            if (!this.jobId || this.personaLoading) return;

            this.personaLoading = true;

            try {
                // Save annotations first
                await this.saveAnnotationsToServer();

                // Call persona synthesis
                const response = await fetch(`/api/jobs/${this.jobId}/synthesize-persona`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                if (!response.ok) throw new Error('Failed to generate persona');

                const data = await response.json();

                if (data.success && data.persona) {
                    this.personaStatement = data.persona;

                    // Save persona
                    await fetch(`/api/jobs/${this.jobId}/save-persona`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            persona_statement: data.persona,
                            is_user_edited: false
                        })
                    });

                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100, 50, 200]);
                    }

                    window.showToast?.('Persona generated!', 'success');
                } else {
                    window.showToast?.('Could not generate persona', 'warning');
                }

            } catch (error) {
                console.error('Failed to generate persona:', error);
                window.showToast?.('Persona generation failed', 'error');
            } finally {
                this.personaLoading = false;
            }
        },

        /**
         * Auto-generate annotations using the suggestion system.
         * Calls the runner service to generate annotations based on
         * sentence embeddings and skill priors.
         */
        async autoAnnotate() {
            if (!this.jobId || this.autoGenerating) return;

            this.autoGenerating = true;

            try {
                const response = await fetch(`/api/runner/jobs/${this.jobId}/generate-annotations`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.error || `HTTP ${response.status}`);
                }

                const data = await response.json();

                if (data.success) {
                    // Reload annotations to show the newly created ones
                    await this.loadAnnotations(this.jobId, this.jdContent);

                    // Haptic feedback
                    if ('vibrate' in navigator) {
                        navigator.vibrate([100, 50, 100]);
                    }

                    window.showToast?.(`Created ${data.created} annotations`, 'success');
                } else {
                    throw new Error(data.error || 'Unknown error');
                }

            } catch (error) {
                console.error('Failed to auto-generate annotations:', error);
                window.showToast?.(`Auto-annotate failed: ${error.message}`, 'error');
            } finally {
                this.autoGenerating = false;
            }
        },

        // Show details for existing annotation - open sheet for editing
        showAnnotationDetails(annotationId) {
            const annotation = this.annotations.find(a => a.id === annotationId);
            if (!annotation) return;

            // Store editing annotation ID
            this.editingAnnotationId = annotationId;

            // Pre-fill the sheet with existing values
            this.selectedText = annotation.target?.text || '';
            this.currentAnnotation = {
                relevance: annotation.relevance || 'relevant',
                requirement_type: annotation.requirement_type || 'neutral',
                identity: annotation.identity || 'peripheral',
                passion: annotation.passion || 'neutral',
                reframe_note: annotation.reframe_note || ''
            };

            // Open the sheet
            this.showSheet = true;

            // Haptic feedback
            if ('vibrate' in navigator) {
                navigator.vibrate(30);
            }
        },

        // Delete annotation with undo support
        async deleteAnnotation(annotationId) {
            // Find annotation before deleting to capture feedback
            const annotation = this.annotations.find(a => a.id === annotationId);
            if (!annotation) return;

            // Store for undo (before deletion)
            this.lastDeletedAnnotation = JSON.parse(JSON.stringify(annotation));

            // Capture negative feedback for auto-generated annotations
            if (annotation.source === 'auto_generated' && annotation.original_values) {
                this.captureAnnotationFeedback(annotation, 'delete');
            }

            this.annotations = this.annotations.filter(a => a.id !== annotationId);
            await this.saveAnnotationsToServer();
            this.checkIdentityAnnotations();

            // Show toast with undo action (5 second timeout)
            if (typeof window.showToastWithAction === 'function') {
                window.showToastWithAction('Annotation deleted', 'info', 5000, 'Undo', () => this.undoDelete());
            } else {
                // Fallback: regular toast with a hint about undo
                window.showToast?.('Annotation deleted', 'info');
            }
        },

        // Undo the last deleted annotation
        async undoDelete() {
            if (!this.lastDeletedAnnotation) {
                window.showToast?.('Nothing to undo', 'info');
                return;
            }

            // Restore the annotation
            this.annotations.push(this.lastDeletedAnnotation);
            await this.saveAnnotationsToServer();
            this.checkIdentityAnnotations();

            // Haptic feedback
            if ('vibrate' in navigator) {
                navigator.vibrate([30, 20, 30]);
            }

            window.showToast?.('Annotation restored', 'success');
            this.lastDeletedAnnotation = null;
        },

        // Get highlight class for annotation
        getHighlightClass(annotation) {
            if (annotation.relevance === 'core_strength') return 'annotation-highlight core-strength';
            if (annotation.relevance === 'gap') return 'annotation-highlight gap';
            return 'annotation-highlight';
        },

        /**
         * Get confidence display data for auto-generated annotations
         * @param {Object} annotation - The annotation object
         * @returns {Object|null} Object with pct and method, or null if not applicable
         */
        getConfidenceDisplay(annotation) {
            // Only show for auto-generated annotations
            if (annotation.source !== 'auto_generated') return null;

            // Get confidence from original_values
            const conf = annotation.original_values?.confidence;
            if (!conf && conf !== 0) return null;

            const pct = Math.round(conf * 100);
            const matchMethod = annotation.original_values?.match_method || 'semantic similarity';

            // Format match method for display
            const methodLabels = {
                'sentence_embedding': 'sentence similarity',
                'keyword_match': 'keyword match',
                'skill_prior': 'skill prior',
                'semantic_similarity': 'semantic similarity',
                'exact_match': 'exact match'
            };
            const displayMethod = methodLabels[matchMethod] || matchMethod;

            return {
                pct: pct,
                method: displayMethod,
                matchedKeyword: annotation.original_values?.matched_keyword || null,
                // Color class based on confidence level
                colorClass: pct >= 85 ? 'text-green-600 bg-green-100'
                          : pct >= 70 ? 'text-amber-600 bg-amber-100'
                          : 'text-gray-600 bg-gray-100'
            };
        },

        /**
         * Get match explanation text for auto-generated annotations
         * @param {Object} annotation - The annotation object
         * @returns {string|null} Match explanation text, or null if not applicable
         */
        getMatchExplanation(annotation) {
            const display = this.getConfidenceDisplay(annotation);
            if (!display) return null;

            if (display.matchedKeyword) {
                return `Matched: "${display.matchedKeyword}" (${display.method})`;
            }
            return `Matched via ${display.method}`;
        },

        // ============================================================================
        // Batch Suggestion Review (Phase 2)
        // ============================================================================

        /**
         * Get pending AI-generated suggestions that haven't been approved or rejected.
         * NOTE: Since Issue 1 auto-apply UX change, AI suggestions are auto-approved on load.
         * This getter now returns an empty array for backward compatibility.
         */
        get pendingSuggestions() {
            // AI suggestions are now auto-approved on load (Issue 1: auto-apply UX)
            return [];
        },

        /**
         * Accept all pending AI suggestions at once.
         */
        async acceptAllSuggestions() {
            const pending = this.pendingSuggestions;
            if (pending.length === 0) return;

            pending.forEach(a => {
                a.status = 'approved';
                a.reviewed_at = new Date().toISOString();
            });

            await this.saveAnnotationsToServer();

            // Haptic feedback
            if ('vibrate' in navigator) {
                navigator.vibrate([50, 30, 50]);
            }

            window.showToast?.(`Accepted ${pending.length} suggestions`, 'success');
        },

        /**
         * Quickly accept a single AI suggestion.
         * @param {string} annotationId - ID of the annotation to accept
         */
        async quickAcceptSuggestion(annotationId) {
            const ann = this.annotations.find(a => a.id === annotationId);
            if (ann) {
                ann.status = 'approved';
                ann.reviewed_at = new Date().toISOString();
                await this.saveAnnotationsToServer();

                // Haptic feedback
                if ('vibrate' in navigator) {
                    navigator.vibrate(30);
                }

                window.showToast?.('Suggestion accepted', 'success');
            }
        },

        /**
         * Quickly reject (delete) a single AI suggestion.
         * @param {string} annotationId - ID of the annotation to reject
         */
        async quickRejectSuggestion(annotationId) {
            const ann = this.annotations.find(a => a.id === annotationId);
            if (!ann) return;

            // Store for undo (before deletion)
            this.lastDeletedAnnotation = JSON.parse(JSON.stringify(ann));

            // Capture feedback before removing
            if (ann.source === 'auto_generated' && ann.original_values) {
                this.captureAnnotationFeedback(ann, 'delete');
            }

            // Remove the annotation
            this.annotations = this.annotations.filter(a => a.id !== annotationId);
            await this.saveAnnotationsToServer();

            // Haptic feedback
            if ('vibrate' in navigator) {
                navigator.vibrate(30);
            }

            // Show toast with undo action (5 second timeout)
            if (typeof window.showToastWithAction === 'function') {
                window.showToastWithAction('Suggestion rejected', 'info', 5000, 'Undo', () => this.undoDelete());
            } else {
                window.showToast?.('Suggestion rejected', 'info');
            }
        }
    }));
});
