/**
 * Interview Prep & Outcome Tracker JavaScript (Phase 7)
 *
 * Handles AJAX interactions for:
 * - Interview question generation
 * - Question practice status updates
 * - Question notes saving
 * - Application outcome tracking
 *
 * Dependencies:
 * - Expects window.JOB_DETAIL_CONFIG.jobId to be set
 * - Works with _interview_prep_panel.html and _outcome_tracker.html templates
 */

// =============================================================================
// INTERVIEW PREP FUNCTIONS
// =============================================================================

/**
 * Generate interview prep questions from job annotations.
 * Calls the backend API to generate questions using LLM.
 *
 * @param {string} jobId - MongoDB job document ID
 */
async function generateInterviewPrep(jobId) {
    const buttons = document.querySelectorAll('#generate-prep-btn, #generate-prep-btn-empty, #regenerate-prep-btn');
    const originalTexts = [];

    // Disable buttons and show loading state
    buttons.forEach((btn, i) => {
        if (btn) {
            originalTexts[i] = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = `
                <svg class="inline-block h-3 w-3 mr-1 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Generating...
            `;
        }
    });

    try {
        const response = await fetch(`/api/jobs/${jobId}/interview-prep/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to generate interview prep');
        }

        // Reload page to show new questions
        // In future, we could update the DOM directly for a smoother UX
        window.location.reload();

    } catch (error) {
        console.error('Error generating interview prep:', error);
        alert(`Failed to generate interview prep: ${error.message}`);

        // Restore buttons
        buttons.forEach((btn, i) => {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalTexts[i];
            }
        });
    }
}

/**
 * Update the practice status of an interview question.
 *
 * @param {string} jobId - MongoDB job document ID
 * @param {string} questionId - Question UUID
 * @param {string} status - New status: "not_started", "practiced", "confident"
 */
async function updateQuestionStatus(jobId, questionId, status) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/interview-prep/questions/${questionId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ practice_status: status }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to update question status');
        }

        // Update the question card's visual state (optional enhancement)
        const questionCard = document.querySelector(`[data-question-id="${questionId}"]`);
        if (questionCard) {
            // Could add visual feedback here
            console.log(`Question ${questionId} status updated to ${status}`);
        }

    } catch (error) {
        console.error('Error updating question status:', error);
        // Silently fail or show subtle error indicator
    }
}

/**
 * Save user notes for an interview question.
 *
 * @param {string} jobId - MongoDB job document ID
 * @param {string} questionId - Question UUID
 * @param {string} notes - User's notes text
 */
async function saveQuestionNotes(jobId, questionId, notes) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/interview-prep/questions/${questionId}`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ user_notes: notes }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to save question notes');
        }

        console.log(`Notes saved for question ${questionId}`);

    } catch (error) {
        console.error('Error saving question notes:', error);
    }
}


// =============================================================================
// OUTCOME TRACKER FUNCTIONS
// =============================================================================

/**
 * Update the application outcome status.
 * Also updates the UI visibility of related fields.
 *
 * @param {string} jobId - MongoDB job document ID
 * @param {string} status - New outcome status
 */
async function updateOutcomeStatus(jobId, status) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/outcome`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ status }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to update outcome status');
        }

        // Update UI based on new status
        updateOutcomeUI(status);

        // Update badge
        updateOutcomeBadge(status);

        console.log(`Outcome status updated to ${status}`);

    } catch (error) {
        console.error('Error updating outcome status:', error);
        alert(`Failed to update outcome: ${error.message}`);
    }
}

/**
 * Update a specific field in the application outcome.
 *
 * @param {string} jobId - MongoDB job document ID
 * @param {string} field - Field name (applied_via, interview_rounds, etc.)
 * @param {*} value - New value
 */
async function updateOutcomeField(jobId, field, value) {
    try {
        const response = await fetch(`/api/jobs/${jobId}/outcome`, {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ [field]: value }),
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `Failed to update ${field}`);
        }

        console.log(`Outcome field ${field} updated`);

    } catch (error) {
        console.error(`Error updating outcome field ${field}:`, error);
    }
}

/**
 * Update the outcome UI visibility based on status.
 * Shows/hides fields appropriate for the current status.
 *
 * @param {string} status - Current outcome status
 */
function updateOutcomeUI(status) {
    const appliedViaContainer = document.getElementById('applied-via-container');
    const interviewRoundsContainer = document.getElementById('interview-rounds-container');
    const responseTypeContainer = document.getElementById('response-type-container');

    // Show/hide Applied Via (visible for all statuses except not_applied)
    if (appliedViaContainer) {
        if (status === 'not_applied') {
            appliedViaContainer.classList.add('hidden');
        } else {
            appliedViaContainer.classList.remove('hidden');
        }
    }

    // Show/hide Interview Rounds
    const interviewStatuses = ['interview_scheduled', 'interviewing', 'offer_received', 'offer_accepted'];
    if (interviewRoundsContainer) {
        if (interviewStatuses.includes(status)) {
            interviewRoundsContainer.classList.remove('hidden');
        } else {
            interviewRoundsContainer.classList.add('hidden');
        }
    }

    // Show/hide Response Type
    const responseStatuses = ['response_received', 'screening_scheduled', 'interview_scheduled', 'interviewing', 'offer_received', 'offer_accepted', 'rejected'];
    if (responseTypeContainer) {
        if (responseStatuses.includes(status)) {
            responseTypeContainer.classList.remove('hidden');
        } else {
            responseTypeContainer.classList.add('hidden');
        }
    }
}

/**
 * Update the outcome badge appearance based on status.
 *
 * @param {string} status - Current outcome status
 */
function updateOutcomeBadge(status) {
    const badge = document.getElementById('outcome-badge');
    if (!badge) return;

    // Remove all existing color classes
    badge.className = 'outcome-badge px-2 py-1 text-xs font-medium rounded-full';

    // Add appropriate color class
    const colorClasses = {
        'offer_received': 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400',
        'offer_accepted': 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-400',
        'interviewing': 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-400',
        'interview_scheduled': 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-400',
        'response_received': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-400',
        'screening_scheduled': 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-400',
        'applied': 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-400',
        'rejected': 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-400',
        'withdrawn': 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
        'not_applied': 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
    };

    const colorClass = colorClasses[status] || colorClasses['not_applied'];
    badge.classList.add(...colorClass.split(' '));

    // Update badge text
    badge.textContent = status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}


// =============================================================================
// INITIALIZATION
// =============================================================================

// Make functions globally available
window.generateInterviewPrep = generateInterviewPrep;
window.updateQuestionStatus = updateQuestionStatus;
window.saveQuestionNotes = saveQuestionNotes;
window.updateOutcomeStatus = updateOutcomeStatus;
window.updateOutcomeField = updateOutcomeField;

console.log('Interview Prep & Outcome Tracker JS loaded');
