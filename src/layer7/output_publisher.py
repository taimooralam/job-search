"""
Layer 7: Output Publisher

Publishes outputs to:
1. Local file system (./applications/<company>/<role>/)
2. MongoDB (updates job record with generated outputs)
3. Google Drive (uploads files)
4. Google Sheets (logs tracking row)
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_exponential
from pymongo import MongoClient

from src.common.config import Config
from src.common.state import JobState
from src.common.utils import sanitize_path_component
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.layer7.dossier_generator import DossierGenerator


class OutputPublisher:
    """
    Publishes job application outputs to local disk, MongoDB, Google Drive and Sheets.
    """

    def __init__(self):
        """Initialize Google API clients and MongoDB connection."""
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)

        self.enable_remote = Config.ENABLE_REMOTE_PUBLISHING

        if self.enable_remote:
            # Set up Google credentials
            scopes = [
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/spreadsheets'
            ]

            self.creds = Credentials.from_service_account_file(
                Config.GOOGLE_CREDENTIALS_PATH,
                scopes=scopes
            )

            # Initialize Drive API client
            self.drive_service = build('drive', 'v3', credentials=self.creds)

            # Initialize Sheets client (using gspread for simpler API)
            self.sheets_client = gspread.authorize(self.creds)
        else:
            self.creds = None
            self.drive_service = None
            self.sheets_client = None

        # Initialize MongoDB client
        self.mongo_client = MongoClient(Config.MONGODB_URI)
        self.db = self.mongo_client['jobs']

        # Initialize dossier generator
        self.dossier_gen = DossierGenerator()

    def _find_or_create_folder(self, folder_name: str, parent_folder_id: Optional[str] = None) -> str:
        """
        Find or create a folder in Google Drive.

        Args:
            folder_name: Name of the folder
            parent_folder_id: ID of parent folder (None for root)

        Returns:
            Folder ID
        """
        # Search for existing folder
        query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"

        results = self.drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name)',
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()

        files = results.get('files', [])

        if files:
            # Folder exists, return ID
            return files[0]['id']
        else:
            # Create new folder
            folder_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }

            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]

            folder = self.drive_service.files().create(
                body=folder_metadata,
                fields='id',
                supportsAllDrives=True
            ).execute()

            return folder['id']

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _upload_file_to_drive(
        self,
        file_path: str,
        folder_id: str,
        file_name: Optional[str] = None
    ) -> str:
        """
        Upload a file to Google Drive.

        Args:
            file_path: Local path to file
            folder_id: ID of destination folder
            file_name: Optional custom filename (defaults to original)

        Returns:
            File ID in Drive
        """
        if not file_name:
            file_name = os.path.basename(file_path)

        # Determine MIME type
        if file_path.endswith('.docx'):
            mime_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        elif file_path.endswith('.txt'):
            mime_type = 'text/plain'
        else:
            mime_type = 'application/octet-stream'

        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()

        return file['id']

    def _get_folder_url(self, folder_id: str) -> str:
        """Get web URL for a folder."""
        return f"https://drive.google.com/drive/folders/{folder_id}"

    def _save_files_locally(self, state: JobState, dossier_content: str) -> Dict[str, str]:
        """
        Save all outputs to local file system.

        Creates directory structure: ./applications/<company>/<role>/
        Saves: dossier.txt, cover_letter.txt, contacts_outreach.txt, CV

        Args:
            state: JobState with all outputs
            dossier_content: Generated dossier text

        Returns:
            Dict with local file paths
        """
        # Create directory structure with sanitized names (no spaces, safe chars)
        # Use shared utility to ensure consistent naming with Layer 6 (generator.py)
        company_safe = sanitize_path_component(state['company'], max_length=80)
        role_safe = sanitize_path_component(state['title'], max_length=80)

        local_dir = Path('./applications') / company_safe / role_safe
        local_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Saving files locally to: {local_dir}")

        saved_paths = {}

        # 1. Save dossier
        dossier_path = local_dir / 'dossier.txt'
        with open(dossier_path, 'w', encoding='utf-8') as f:
            f.write(dossier_content)
        saved_paths['dossier'] = str(dossier_path)
        self.logger.info(f"Saved dossier: {dossier_path}")

        # 2. Save cover letter
        if state.get('cover_letter'):
            cover_letter_path = local_dir / 'cover_letter.txt'
            with open(cover_letter_path, 'w', encoding='utf-8') as f:
                f.write(state['cover_letter'])
            saved_paths['cover_letter'] = str(cover_letter_path)
            self.logger.info(f"Saved cover letter: {cover_letter_path}")

        # 2b. Save fallback cover letters when no contacts were found
        if state.get('fallback_cover_letters'):
            fallback_path = local_dir / 'fallback_cover_letters.txt'
            with open(fallback_path, 'w', encoding='utf-8') as f:
                f.write("\n\n---\n\n".join(state['fallback_cover_letters']))
            saved_paths['fallback_cover_letters'] = str(fallback_path)
            self.logger.info(f"Saved fallback cover letters: {fallback_path}")

        # 3. Save contacts outreach
        if state.get('people'):
            contacts_content = self._format_contacts_file(state['people'], state)
            contacts_path = local_dir / 'contacts_outreach.txt'
            with open(contacts_path, 'w', encoding='utf-8') as f:
                f.write(contacts_content)
            saved_paths['contacts'] = str(contacts_path)
            self.logger.info(f"Saved contacts: {contacts_path}")

        # 4. Verify CV exists (already saved to correct location by Layer 6)
        if state.get('cv_path') and os.path.exists(state['cv_path']):
            saved_paths['cv'] = state['cv_path']
            self.logger.info(f"CV already saved: {state['cv_path']}")

        return saved_paths

    def _persist_to_mongodb(self, state: JobState, dossier_content: str) -> bool:
        """
        Update MongoDB job record with generated outputs.

        Updates level-2 collection with:
        - generated_dossier
        - cover_letter
        - fit_analysis (score + rationale)
        - selected_stars (STAR IDs)
        - people (contact names and roles)
        - pain_points (4 dimensions: pain_points, strategic_needs, risks_if_unfilled, success_metrics)
        - company_summary
        - pipeline_run_at timestamp
        - pipeline_status

        Args:
            state: JobState with all outputs
            dossier_content: Generated dossier text

        Returns:
            True if successful, False otherwise
        """
        from bson import ObjectId

        try:
            job_id = state['job_id']
            self.logger.info(f"Persisting to MongoDB for job_id: {job_id}")

            # Find the job record - try multiple strategies
            collection = self.db['level-2']
            job_record = None

            # Strategy 1: Try as ObjectId (_id field) - most common case
            try:
                object_id = ObjectId(job_id)
                job_record = collection.find_one({"_id": object_id})
                if job_record:
                    self.logger.info(f"Found job by _id (ObjectId): {job_id}")
            except Exception:
                pass  # Not a valid ObjectId, try other strategies

            # Strategy 2: Try as integer jobId field (legacy schema)
            if not job_record:
                try:
                    job_id_int = int(job_id)
                    job_record = collection.find_one({"jobId": job_id_int})
                    if job_record:
                        self.logger.info(f"Found job by jobId (int): {job_id_int}")
                except ValueError:
                    pass

            # Strategy 3: Try as string jobId field
            if not job_record:
                job_record = collection.find_one({"jobId": job_id})
                if job_record:
                    self.logger.info(f"Found job by jobId (string): {job_id}")

            if not job_record:
                self.logger.warning(f"Job {job_id} not found in MongoDB level-2 collection (tried _id, jobId int/string)")
                return False

            # Prepare update data
            # Set status to "ready for applying" when pipeline completes successfully
            update_data = {
                'pipeline_run_at': datetime.now(),
                'generated_dossier': dossier_content,
                'pipeline_status': state.get('status', 'completed'),
                'status': 'ready for applying',  # Mark job ready for user to apply
            }

            # Add fit analysis
            if state.get('fit_score') is not None:
                update_data['fit_score'] = state['fit_score']

            if state.get('fit_rationale'):
                update_data['fit_rationale'] = state['fit_rationale']

            # Add cover letter
            if state.get('cover_letter'):
                update_data['cover_letter'] = state['cover_letter']

            # Add CV text and path for frontend display and persistence
            if state.get('cv_text'):
                update_data['cv_text'] = state['cv_text']

            if state.get('cv_path'):
                update_data['cv_path'] = state['cv_path']

            if state.get('cv_reasoning'):
                update_data['cv_reasoning'] = state['cv_reasoning']

            # Add selected STAR IDs
            if state.get('selected_stars'):
                update_data['selected_star_ids'] = [
                    star['id'] for star in state['selected_stars']
                ]

            # Add primary and secondary contacts with FULL outreach data
            if state.get('primary_contacts'):
                update_data['primary_contacts'] = state['primary_contacts']

            if state.get('secondary_contacts'):
                update_data['secondary_contacts'] = state['secondary_contacts']

            # Add pain points (4 dimensions - Phase 1.3)
            if state.get('pain_points'):
                update_data['pain_points'] = state['pain_points']

            if state.get('strategic_needs'):
                update_data['strategic_needs'] = state['strategic_needs']

            if state.get('risks_if_unfilled'):
                update_data['risks_if_unfilled'] = state['risks_if_unfilled']

            if state.get('success_metrics'):
                update_data['success_metrics'] = state['success_metrics']

            # Add company summary
            if state.get('company_summary'):
                update_data['company_summary'] = state['company_summary']

            # Add extracted JD from Layer 1.4 (CV Gen V2)
            if state.get('extracted_jd'):
                update_data['extracted_jd'] = state['extracted_jd']

            # Add Drive/Sheets references
            if state.get('drive_folder_url'):
                update_data['drive_folder_url'] = state['drive_folder_url']

            if state.get('sheet_row_id'):
                update_data['sheet_row_id'] = state['sheet_row_id']

            # Perform update
            result = collection.update_one(
                {"_id": job_record['_id']},
                {"$set": update_data}
            )

            if result.modified_count > 0:
                self.logger.info(f"Updated MongoDB record (jobId: {job_id})")
                return True
            else:
                self.logger.info("MongoDB record not modified (may already have same data)")
                return True  # Still success, just no changes needed

        except Exception as e:
            self.logger.warning(f"MongoDB update failed: {str(e)}")
            return False

    def _format_contacts_file(self, people: list, state: JobState) -> str:
        """Format per-person outreach into a single file."""
        lines = []
        lines.append("="*80)
        lines.append(f"OUTREACH CONTACTS: {state['company']} - {state['title']}")
        lines.append("="*80)
        lines.append("")

        for i, person in enumerate(people, 1):
            lines.append(f"\n{'='*80}")
            lines.append(f"CONTACT #{i}")
            lines.append(f"{'='*80}\n")

            lines.append(f"NAME: {person['name']}")
            lines.append(f"ROLE: {person['role']}")
            lines.append(f"LINKEDIN: {person['linkedin_url']}")
            lines.append(f"WHY RELEVANT: {person['why_relevant']}")
            lines.append("")

            lines.append("-" * 80)
            lines.append("LINKEDIN MESSAGE (150-200 chars):")
            lines.append("-" * 80)
            lines.append(person['linkedin_message'])
            lines.append("")

            lines.append("-" * 80)
            lines.append(f"EMAIL")
            lines.append("-" * 80)
            lines.append(f"Subject: {person['email_subject']}")
            lines.append("")
            lines.append(person['email_body'])
            lines.append("")

            lines.append("-" * 80)
            lines.append("REASONING:")
            lines.append("-" * 80)
            lines.append(person['reasoning'])
            lines.append("")

        return "\n".join(lines)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _log_to_sheets(self, state: JobState, folder_url: str) -> int:
        """
        Log job application to Google Sheets.

        Args:
            state: JobState with all job details
            folder_url: URL to Drive folder with outputs

        Returns:
            Row number where data was appended
        """
        # Open the tracking sheet
        sheet = self.sheets_client.open_by_key(Config.GOOGLE_SHEET_ID).sheet1

        # Prepare row data
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp
            state["company"],
            state["title"],
            state.get("job_url", ""),
            state.get("fit_score", ""),
            state.get("fit_rationale", ""),
            folder_url,
            state.get("status", "processed"),
            state.get("source", "")
        ]

        # Append row
        sheet.append_row(row)

        # Get current row count (the row we just added)
        all_values = sheet.get_all_values()
        row_number = len(all_values)

        return row_number

    def publish(self, state: JobState) -> Dict[str, Any]:
        """
        Main function to publish outputs to all destinations.

        1. Generates comprehensive dossier
        2. Saves files locally (./applications/<company>/<role>/)
        3. Persists to MongoDB (updates job record)
        4. Uploads to Google Drive
        5. Logs to Google Sheets

        Args:
            state: JobState with all outputs

        Returns:
            Dict with file paths, drive_folder_url, sheet_row_id, and any errors
        """
        result = {}
        errors = []

        try:
            # Step 0: Generate comprehensive dossier
            self.logger.info("Generating dossier")
            dossier_content = self.dossier_gen.generate_dossier(state)
            result['dossier_generated'] = True
            self.logger.info(f"Dossier generated ({len(dossier_content)} chars)")

        except Exception as e:
            error_msg = f"Dossier generation failed: {str(e)[:100]}"
            self.logger.warning(error_msg)
            errors.append(error_msg)
            dossier_content = "Dossier generation failed"
            result['dossier_generated'] = False

        try:
            # Step 1: Save files locally
            self.logger.info("Saving files to local disk")
            local_paths = self._save_files_locally(state, dossier_content)
            result['local_paths'] = local_paths
            result['local_save_success'] = True

        except Exception as e:
            error_msg = f"Local file save failed: {str(e)[:100]}"
            self.logger.warning(error_msg)
            errors.append(error_msg)
            result['local_save_success'] = False

        try:
            # Step 2: Persist to MongoDB
            self.logger.info("Updating MongoDB")
            mongo_success = self._persist_to_mongodb(state, dossier_content)
            result['mongodb_persisted'] = mongo_success

        except Exception as e:
            error_msg = f"MongoDB persistence failed: {str(e)[:100]}"
            self.logger.warning(error_msg)
            errors.append(error_msg)
            result['mongodb_persisted'] = False

        # If remote publishing is disabled, exit early after local + Mongo
        if not self.enable_remote:
            result['drive_folder_url'] = None
            result['sheet_row_id'] = None
            if errors:
                existing_errors = state.get("errors") or []
                if isinstance(existing_errors, str):
                    existing_errors = [existing_errors]
                result["errors"] = existing_errors + errors
            return result

        try:
            # Step 3: Create Google Drive folder structure
            self.logger.info("Creating Google Drive folders")

            # Find or create 'applications' folder
            applications_folder_id = self._find_or_create_folder(
                'applications',
                parent_folder_id=Config.GOOGLE_DRIVE_FOLDER_ID
            )
            self.logger.info(f"Applications folder: {applications_folder_id}")

            # Create company folder
            company_folder_id = self._find_or_create_folder(
                state["company"],
                parent_folder_id=applications_folder_id
            )
            self.logger.info(f"Company folder: {company_folder_id}")

            # Create role folder (use shared utility for consistent naming)
            role_folder_name = sanitize_path_component(state["title"], max_length=80)
            role_folder_id = self._find_or_create_folder(
                role_folder_name,
                parent_folder_id=company_folder_id
            )
            self.logger.info(f"Role folder: {role_folder_id}")

            folder_url = self._get_folder_url(role_folder_id)
            result['drive_folder_url'] = folder_url

            # Step 4: Upload dossier to Drive
            try:
                self.logger.info("Uploading dossier to Drive")
                dossier_temp_path = local_paths.get('dossier')
                if dossier_temp_path and os.path.exists(dossier_temp_path):
                    self._upload_file_to_drive(
                        dossier_temp_path,
                        role_folder_id,
                        "dossier.txt"
                    )
                    self.logger.info("Dossier uploaded")
            except Exception as e:
                error_msg = f"Dossier upload failed: {str(e)[:100]}"
                self.logger.warning(error_msg)
                errors.append(error_msg)

            # Step 5: Upload cover letter
            upload_errors = []
            if state.get("cover_letter"):
                try:
                    self.logger.info("Uploading cover letter")

                    # Save cover letter to temp file
                    import tempfile
                    company_safe_temp = (state['company']
                                        .replace(' ', '_')
                                        .replace(',', '')
                                        .replace('.', '')
                                        .replace('/', '_')
                                        .replace('\\', '_'))
                    cover_letter_path = os.path.join(
                        tempfile.gettempdir(),
                        f"cover_letter_{company_safe_temp}.txt"
                    )
                    with open(cover_letter_path, 'w') as f:
                        f.write(state["cover_letter"])

                    self._upload_file_to_drive(
                        cover_letter_path,
                        role_folder_id,
                        "cover_letter.txt"
                    )
                    self.logger.info("Cover letter uploaded")

                    # Cleanup temp file
                    os.remove(cover_letter_path)
                except Exception as e:
                    error_msg = f"Cover letter upload failed (folder created): {str(e)[:100]}"
                    self.logger.warning(error_msg)
                    upload_errors.append(error_msg)

            # Step 6: Upload CV
            if state.get("cv_path") and os.path.exists(state["cv_path"]):
                try:
                    self.logger.info("Uploading CV")
                    company_safe_cv = (state['company']
                                      .replace(' ', '_')
                                      .replace(',', '')
                                      .replace('.', '')
                                      .replace('/', '_')
                                      .replace('\\', '_'))
                    self._upload_file_to_drive(
                        state["cv_path"],
                        role_folder_id,
                        f"CV_{company_safe_cv}.docx"
                    )
                    self.logger.info("CV uploaded")
                except Exception as e:
                    error_msg = f"CV upload failed (folder created): {str(e)[:100]}"
                    self.logger.warning(error_msg)
                    upload_errors.append(error_msg)

            # Step 7: Upload per-person outreach files (Phase 1.3)
            people = state.get("people", [])
            if people:
                try:
                    self.logger.info(f"Generating outreach files for {len(people)} contacts")

                    # Create a consolidated contacts file
                    import tempfile
                    contacts_content = self._format_contacts_file(people, state)
                    company_safe_contacts = (state['company']
                                            .replace(' ', '_')
                                            .replace(',', '')
                                            .replace('.', '')
                                            .replace('/', '_')
                                            .replace('\\', '_'))
                    contacts_path = os.path.join(
                        tempfile.gettempdir(),
                        f"contacts_{company_safe_contacts}.txt"
                    )
                    with open(contacts_path, 'w') as f:
                        f.write(contacts_content)

                    self._upload_file_to_drive(
                        contacts_path,
                        role_folder_id,
                        "contacts_outreach.txt"
                    )
                    self.logger.info("Contact outreach file uploaded")

                    # Cleanup
                    os.remove(contacts_path)

                except Exception as e:
                    error_msg = f"Contacts upload failed: {str(e)[:100]}"
                    self.logger.warning(error_msg)
                    upload_errors.append(error_msg)

            # Step 8: Log to Google Sheets
            self.logger.info("Logging to Google Sheets")
            sheet_row_id = self._log_to_sheets(state, folder_url)
            self.logger.info(f"Logged to row {sheet_row_id}")

            result['sheet_row_id'] = sheet_row_id

            # Add all collected errors
            all_errors = errors + upload_errors
            if all_errors:
                existing_errors = state.get("errors") or []
                if isinstance(existing_errors, str):
                    existing_errors = [existing_errors]
                result["errors"] = existing_errors + all_errors

            return result

        except Exception as e:
            error_msg = f"Layer 7 (Output Publisher) catastrophic failure: {str(e)}"
            self.logger.error(error_msg)

            errors_list = state.get("errors") or []
            if isinstance(errors_list, str):
                errors_list = [errors_list]

            return {
                "dossier_generated": False,
                "local_save_success": False,
                "mongodb_persisted": False,
                "drive_folder_url": None,
                "sheet_row_id": None,
                "errors": errors_list + errors + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def output_publisher_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 7: Output Publisher.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer7")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("="*60)
    logger.info("LAYER 7: Output Publisher")
    logger.info("="*60)

    with LayerContext(struct_logger, 7, "output_publisher") as ctx:
        publisher = OutputPublisher()
        updates = publisher.publish(state)

        # Log results summary
        logger.info("="*60)
        logger.info("LAYER 7 OUTPUT SUMMARY")
        logger.info("="*60)

        # Dossier
        if updates.get("dossier_generated"):
            logger.info("✅ Dossier: Generated")
        else:
            logger.error("❌ Dossier: Failed")

        # Local files
        if updates.get("local_save_success"):
            local_paths = updates.get("local_paths", {})
            logger.info(f"✅ Local Files: {len(local_paths)} files saved")
            if local_paths.get('dossier'):
                logger.info(f"   📄 Dossier: {local_paths['dossier']}")
        else:
            logger.error("❌ Local Files: Save failed")

        # MongoDB
        if updates.get("mongodb_persisted"):
            logger.info("✅ MongoDB: Job record updated")
        else:
            logger.warning("MongoDB: Update failed or skipped")

        # Drive
        if updates.get("drive_folder_url"):
            logger.info(f"✅ Drive Folder: {updates['drive_folder_url']}")
        else:
            logger.warning("Drive: No folder created")

        # Sheets
        if updates.get("sheet_row_id"):
            logger.info(f"✅ Sheets: Logged to row {updates['sheet_row_id']}")
        else:
            logger.warning("Sheets: Not logged")

        logger.info("="*60)

        # Add metadata for structured logging
        ctx.add_metadata("dossier_generated", updates.get("dossier_generated", False))
        ctx.add_metadata("local_save_success", updates.get("local_save_success", False))
        ctx.add_metadata("mongodb_persisted", updates.get("mongodb_persisted", False))
        ctx.add_metadata("drive_uploaded", updates.get("drive_folder_url") is not None)
        ctx.add_metadata("sheets_logged", updates.get("sheet_row_id") is not None)

        return updates
