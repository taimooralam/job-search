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
                this.annotations = data.annotations || [];
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
            // Reset to defaults
            this.currentAnnotation = {
                relevance: 'relevant',
                requirement_type: 'neutral',
                identity: 'peripheral',
                passion: 'neutral',
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
            window.getSelection()?.removeAllRanges();
        },

        // Save annotation
        async saveAnnotation() {
            if (!this.selectedText || !this.jobId) return;

            this.isSaving = true;

            try {
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
                    source: 'human',
                    created_at: new Date().toISOString()
                };

                // Add to local array
                this.annotations.push(newAnnotation);

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
         * Capture feedback for auto-generated annotations.
         * Called when user saves or deletes an annotation.
         */
        async captureAnnotationFeedback(annotation, action) {
            if (annotation.source !== 'auto_generated') return;
            if (!annotation.original_values) return;
            if (annotation.feedback_captured && action === 'save') return;

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

                const response = await fetch('/api/runner/user/annotation-feedback', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success && action === 'save') {
                        annotation.feedback_captured = true;
                    }
                }
            } catch (error) {
                console.warn('Failed to capture annotation feedback:', error);
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

        // Show details for existing annotation
        showAnnotationDetails(annotationId) {
            const annotation = this.annotations.find(a => a.id === annotationId);
            if (!annotation) return;

            // TODO: Show edit sheet with existing values
            console.log('Show annotation:', annotation);
        },

        // Delete annotation
        async deleteAnnotation(annotationId) {
            // Find annotation before deleting to capture feedback
            const annotation = this.annotations.find(a => a.id === annotationId);

            // Capture negative feedback for auto-generated annotations
            if (annotation?.source === 'auto_generated' && annotation?.original_values) {
                this.captureAnnotationFeedback(annotation, 'delete');
            }

            this.annotations = this.annotations.filter(a => a.id !== annotationId);
            await this.saveAnnotationsToServer();
            this.checkIdentityAnnotations();
            window.showToast?.('Annotation deleted', 'info');
        },

        // Get highlight class for annotation
        getHighlightClass(annotation) {
            if (annotation.relevance === 'core_strength') return 'annotation-highlight core-strength';
            if (annotation.relevance === 'gap') return 'annotation-highlight gap';
            return 'annotation-highlight';
        }
    }));
});
