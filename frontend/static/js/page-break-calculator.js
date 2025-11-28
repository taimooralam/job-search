/**
 * Page Break Calculator - Phase 5.1: WYSIWYG Page Break Visualization
 *
 * Calculates where page breaks occur in a document based on:
 * - Page size (Letter vs A4)
 * - Margins (top, right, bottom, left)
 * - Content element heights
 *
 * This module mirrors the Python reference implementation in:
 * tests/frontend/test_cv_editor_phase5_page_breaks.py
 *
 * Algorithm:
 * 1. Calculate available page height = page_height - top_margin - bottom_margin
 * 2. Iterate through content elements sequentially
 * 3. Track cumulative height on current page
 * 4. When adding element would exceed page height:
 *    - Insert page break BEFORE that element
 *    - Reset cumulative height for new page
 *    - Continue iteration
 * 5. Return list of Y positions where breaks occur
 *
 * Key Design Decisions:
 * - Breaks occur BEFORE elements, not mid-element
 * - Elements are atomic (don't split across pages in this version)
 * - First break starts at top_margin + accumulated_height
 * - Subsequent breaks are spaced by available_height
 *
 * @module page-break-calculator
 */

/**
 * Page dimensions in pixels at 96 DPI (standard web DPI)
 */
const PAGE_DIMENSIONS = {
    letter: {
        widthPx: 816,   // 8.5 inches * 96 DPI
        heightPx: 1056  // 11 inches * 96 DPI
    },
    a4: {
        widthPx: 794,   // 210mm / 25.4 * 96 DPI
        heightPx: 1123  // 297mm / 25.4 * 96 DPI
    }
};

const DPI = 96;  // Standard web DPI

/**
 * Calculate page break positions based on content height and page settings.
 *
 * @param {string} pageSize - "letter" or "a4"
 * @param {Object} margins - {top, right, bottom, left} in inches
 * @param {HTMLElement} contentElement - DOM element containing the CV content
 * @returns {Array<number>} - Array of Y positions (in pixels) where page breaks occur
 *
 * @example
 * const breaks = calculatePageBreaks(
 *     'letter',
 *     {top: 1.0, right: 1.0, bottom: 1.0, left: 1.0},
 *     document.querySelector('.ProseMirror')
 * );
 * // Returns: [960, 1824] for a 3-page document
 */
function calculatePageBreaks(pageSize, margins, contentElement) {
    if (!contentElement) {
        console.warn('[PageBreakCalculator] No content element provided');
        return [];
    }

    // Get page dimensions
    const pageDims = PAGE_DIMENSIONS[pageSize.toLowerCase()] || PAGE_DIMENSIONS.letter;

    // Convert margin inches to pixels (96 DPI)
    const topMarginPx = (margins.top || 1.0) * DPI;
    const bottomMarginPx = (margins.bottom || 1.0) * DPI;

    // Calculate available content height per page
    const availableHeight = pageDims.heightPx - topMarginPx - bottomMarginPx;

    if (availableHeight <= 0) {
        console.warn('[PageBreakCalculator] Margins too large, no space for content');
        return [];
    }

    // Get all child elements (paragraphs, headings, lists, etc.)
    const children = Array.from(contentElement.children);

    if (children.length === 0) {
        return []; // Empty document, no page breaks
    }

    const breakPositions = [];
    let currentPageHeight = 0;
    let absoluteY = topMarginPx; // Start after top margin

    // Iterate through all elements and calculate cumulative height
    for (const child of children) {
        const rect = child.getBoundingClientRect();
        let elementHeight = rect.height;

        // Skip zero-height elements
        if (elementHeight === 0) {
            continue;
        }

        // Check if adding this element would exceed current page
        if (currentPageHeight + elementHeight > availableHeight) {
            // Page break needed
            if (currentPageHeight > 0) {
                // Break before this element
                breakPositions.push(Math.round(absoluteY));
                currentPageHeight = 0;
            }

            // Handle case where single element is taller than page height
            while (elementHeight > availableHeight) {
                // This element spans multiple pages
                currentPageHeight = 0;
                absoluteY += availableHeight;
                breakPositions.push(Math.round(absoluteY));
                elementHeight -= availableHeight;
            }

            // Add remaining height of element
            currentPageHeight = elementHeight;
            absoluteY += elementHeight;
        } else {
            // Element fits on current page
            currentPageHeight += elementHeight;
            absoluteY += elementHeight;
        }
    }

    return breakPositions;
}

/**
 * Render page break indicators in the editor container
 *
 * @param {Array<number>} breakPositions - Array of Y positions where breaks occur
 * @param {HTMLElement} container - Container element to render breaks in
 *
 * @example
 * const breaks = calculatePageBreaks('letter', margins, editorContent);
 * renderPageBreaks(breaks, editorContainer);
 */
function renderPageBreaks(breakPositions, container) {
    if (!container) {
        console.warn('[PageBreakCalculator] No container provided for rendering');
        return;
    }

    // Remove existing page break indicators
    const existingBreaks = container.querySelectorAll('.page-break-indicator');
    existingBreaks.forEach(el => el.remove());

    // Add new page break indicators
    breakPositions.forEach((yPosition, index) => {
        const breakDiv = document.createElement('div');
        breakDiv.className = 'page-break-indicator';

        // Style the break line
        Object.assign(breakDiv.style, {
            position: 'absolute',
            top: `${yPosition}px`,
            left: '0',
            width: '100%',
            height: '2px',
            backgroundColor: '#e0e0e0',
            borderTop: '1px dashed #999',
            zIndex: '10',
            pointerEvents: 'none',
            userSelect: 'none'
        });

        breakDiv.setAttribute('data-page-break', index + 1);
        breakDiv.setAttribute('aria-label', `Page ${index + 1} break`);

        // Add label
        const label = document.createElement('span');
        label.textContent = `Page ${index + 1}`;
        Object.assign(label.style, {
            position: 'absolute',
            top: '-10px',
            right: '10px',
            fontSize: '0.75rem',
            color: '#999',
            backgroundColor: 'white',
            padding: '2px 6px',
            borderRadius: '3px',
            border: '1px solid #e0e0e0'
        });

        breakDiv.appendChild(label);
        container.appendChild(breakDiv);
    });

    console.log(`[PageBreakCalculator] Rendered ${breakPositions.length} page breaks`);
}

/**
 * Clear all page break indicators from a container
 *
 * @param {HTMLElement} container - Container element to clear breaks from
 */
function clearPageBreaks(container) {
    if (!container) return;

    const existingBreaks = container.querySelectorAll('.page-break-indicator');
    existingBreaks.forEach(el => el.remove());
}

// Export functions for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    // Node.js/CommonJS
    module.exports = {
        calculatePageBreaks,
        renderPageBreaks,
        clearPageBreaks,
        PAGE_DIMENSIONS,
        DPI
    };
}

// Also expose globally for browser use
if (typeof window !== 'undefined') {
    window.PageBreakCalculator = {
        calculatePageBreaks,
        renderPageBreaks,
        clearPageBreaks,
        PAGE_DIMENSIONS,
        DPI
    };
}
