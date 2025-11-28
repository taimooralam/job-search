RESOLVED (2025-11-28):

1. [RESOLVED] the process button is not working - Fixed by adding missing showToast function and improved error handling
2. [RESOLVED] the CV is showing sleek in the main editor but not on the detail page. The WSIWGYG is not synced. - Fixed by replacing markdown rendering with TipTap JSON rendering
3. [RESOLVED 2025-11-28] The PDF service is not available - Root cause: Old docker-compose.runner.yml on VPS didn't include PDF service. CI/CD workflow was only copying master-cv.md but NOT docker-compose.runner.yml. Fix: Updated workflow to copy both files, added Playwright startup validation, increased wait time from 10s to 20s. All 58 tests passing (49 PDF service + 9 runner integration). See `plans/pdf-service-debug-plan.md` for implementation details.

OPEN/PENDING:

4. Update the prompts for opportunity mapper according to Layer 3 – Opportunity Mapper

5. Update cover letter generation based on the prompting guide.

5.9 Pick up the entire CV will all job descriptions, not only the last two companies

6. The CV generation needs a major overhaul because of how to interpret the master-cv.md, how to chose text, how to create nuance for the different roles, and how to role play and use prompts.

7. Create an iframe to open the job directly in the iframe in a collapsible or a better UX. Have a button to export to pdf for the entire iframe as a bonus.

8. Create AI agents that bypass firecrawl not allowed filters and reason into truly researching company info if firecrawl failes. That are cheap as well.

9. Research ATS based algorithms and best practises to create ATS compliant CVs. Add ATS compliant keywords in text for matching? Can it back fire?

10. Are the pdf files saved on the docker container? Is the dossier also saved on the docker container.
    - **Answer**: PDFs are NOT stored - generated on-the-fly and streamed to user
    - **Dossier**: Saved to `./applications/<company>/<role>/dossier.txt` via volume mount on runner
    - **CV Markdown**: Saved to `./applications/<company>/<role>/CV.md` via volume mount on runner
    - **See**: `plans/pdf-service-debug-plan.md` Architecture section for details
