/**
 * JD Formatter - Regex-based job description formatting
 * Converts plain text job descriptions into structured HTML
 */

(function() {
    'use strict';

    /**
     * Format a job description text into structured HTML
     * @param {string} text - Raw job description text
     * @returns {string} Formatted HTML
     */
    function formatJobDescription(text) {
        if (!text) return '<p class="text-gray-500 italic">No description available</p>';

        // Step 1: Escape HTML entities
        let html = escapeHtml(text);

        // Step 2: Normalize line endings
        html = html.replace(/\r\n/g, '\n').replace(/\r/g, '\n');

        // Step 3: Detect and format section headers
        // Pattern: ALL CAPS lines, or lines ending with colon that look like headers
        html = html.replace(/^([A-Z][A-Z\s&\/\-]{2,}):?\s*$/gm, '<h4 class="jd-section-header">$1</h4>');

        // Pattern: Title Case headers with colon (e.g., "About Us:", "Requirements:")
        html = html.replace(/^((?:About|Requirements|Qualifications|Responsibilities|Benefits|What|Why|How|Who|Our|The|Your|Key|Essential|Preferred|Nice|Must|Skills|Experience|Education|Salary|Compensation|Location|Team|Role|Position|Job|Company|Culture|Perks|Offer)[^:\n]{0,40}):\s*$/gim,
            '<h4 class="jd-section-header">$1</h4>');

        // Step 4: Convert bullet points to list items
        // Match various bullet characters: •, -, *, ○, ▪, ▸, ►, ·, ●
        const bulletPattern = /^[\s]*[•\-\*○▪▸►·●]\s*(.+)$/gm;
        html = html.replace(bulletPattern, '<li class="jd-list-item">$1</li>');

        // Step 5: Convert numbered lists
        // Match: 1. or 1) or 1] or (1) patterns
        const numberedPattern = /^[\s]*(?:\(?\d+[.)\]]\)?|\d+\.)\s*(.+)$/gm;
        html = html.replace(numberedPattern, '<li class="jd-list-item jd-numbered">$1</li>');

        // Step 6: Wrap consecutive list items in <ul>
        html = wrapListItems(html);

        // Step 7: Convert double newlines to paragraph breaks
        html = html.replace(/\n\n+/g, '</p><p class="jd-paragraph">');

        // Step 8: Convert remaining single newlines to <br> within paragraphs
        html = html.replace(/\n/g, '<br>');

        // Step 9: Wrap in paragraph if not already structured
        if (!html.startsWith('<')) {
            html = '<p class="jd-paragraph">' + html + '</p>';
        } else {
            html = '<p class="jd-paragraph">' + html + '</p>';
        }

        // Step 10: Clean up empty paragraphs and fix structure
        html = html.replace(/<p class="jd-paragraph"><\/p>/g, '');
        html = html.replace(/<p class="jd-paragraph">(<h4)/g, '$1');
        html = html.replace(/(<\/h4>)<\/p>/g, '$1');
        html = html.replace(/<p class="jd-paragraph">(<ul)/g, '$1');
        html = html.replace(/(<\/ul>)<\/p>/g, '$1');
        html = html.replace(/<br><h4/g, '<h4');
        html = html.replace(/<\/h4><br>/g, '</h4>');
        html = html.replace(/<br>(<ul)/g, '$1');
        html = html.replace(/(<\/ul>)<br>/g, '$1');

        // Step 11: Highlight keywords (optional - can be extended)
        html = highlightKeyTerms(html);

        return html;
    }

    /**
     * Escape HTML entities to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Wrap consecutive <li> elements in <ul> tags
     */
    function wrapListItems(html) {
        const lines = html.split('\n');
        const result = [];
        let inList = false;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const isListItem = line.trim().startsWith('<li');

            if (isListItem && !inList) {
                result.push('<ul class="jd-list">');
                inList = true;
            } else if (!isListItem && inList) {
                result.push('</ul>');
                inList = false;
            }

            result.push(line);
        }

        if (inList) {
            result.push('</ul>');
        }

        return result.join('\n');
    }

    /**
     * Highlight common job-related key terms
     */
    function highlightKeyTerms(html) {
        // Highlight years of experience patterns
        html = html.replace(/(\d+\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp))/gi,
            '<span class="jd-highlight-experience">$1</span>');

        // Highlight salary/compensation mentions
        html = html.replace(/(\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:k|K|per\s+(?:year|annum|month)))?)/g,
            '<span class="jd-highlight-salary">$1</span>');

        // Highlight "required" and "must have"
        html = html.replace(/\b(required|must have|must-have|mandatory|essential)\b/gi,
            '<span class="jd-highlight-required">$1</span>');

        // Highlight "preferred" and "nice to have"
        html = html.replace(/\b(preferred|nice to have|nice-to-have|bonus|plus|ideal(?:ly)?)\b/gi,
            '<span class="jd-highlight-preferred">$1</span>');

        return html;
    }

    /**
     * Apply formatting to an element containing job description text
     * @param {HTMLElement} element - Element containing raw text
     */
    function formatElement(element) {
        if (!element) return;

        const rawText = element.textContent || element.innerText;
        element.innerHTML = formatJobDescription(rawText);
        element.classList.add('jd-formatted');
    }

    /**
     * Format all elements with a specific selector
     * @param {string} selector - CSS selector for elements to format
     */
    function formatAll(selector) {
        const elements = document.querySelectorAll(selector);
        elements.forEach(formatElement);
    }

    // Expose functions globally
    window.JDFormatter = {
        format: formatJobDescription,
        formatElement: formatElement,
        formatAll: formatAll
    };

    // Auto-format on DOM ready if data attribute is present
    document.addEventListener('DOMContentLoaded', function() {
        formatAll('[data-jd-format="auto"]');
    });

})();
