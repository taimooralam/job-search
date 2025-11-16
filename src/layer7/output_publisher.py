"""
Layer 7: Output Publisher

Publishes outputs to Google Drive and Google Sheets.
This is the SIMPLIFIED version for today's vertical slice.

FUTURE: Will expand to include notifications (Telegram), metadata storage in MongoDB.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.state import JobState


class OutputPublisher:
    """
    Publishes job application outputs to Google Drive and Sheets.
    """

    def __init__(self):
        """Initialize Google API clients."""
        # Set up credentials
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
        Main function to publish outputs to Drive and Sheets.

        Creates folder structure: /applications/<company>/<role>/
        Uploads cover letter and CV
        Logs tracking row to Sheets

        Args:
            state: JobState with cover_letter and cv_path

        Returns:
            Dict with drive_folder_url and sheet_row_id
        """
        try:
            # Step 1: Create folder structure
            print(f"   Creating folder structure...")

            # Find or create 'applications' folder
            applications_folder_id = self._find_or_create_folder(
                'applications',
                parent_folder_id=Config.GOOGLE_DRIVE_FOLDER_ID
            )
            print(f"   ✓ Applications folder: {applications_folder_id}")

            # Create company folder
            company_folder_id = self._find_or_create_folder(
                state["company"],
                parent_folder_id=applications_folder_id
            )
            print(f"   ✓ Company folder: {company_folder_id}")

            # Create role folder
            role_folder_name = state["title"][:50]  # Limit length for folder names
            role_folder_id = self._find_or_create_folder(
                role_folder_name,
                parent_folder_id=company_folder_id
            )
            print(f"   ✓ Role folder: {role_folder_id}")

            folder_url = self._get_folder_url(role_folder_id)

            # Step 2: Upload cover letter
            upload_errors = []
            if state.get("cover_letter"):
                try:
                    print(f"   Uploading cover letter...")

                    # Save cover letter to temp file
                    import tempfile
                    cover_letter_path = os.path.join(
                        tempfile.gettempdir(),
                        f"cover_letter_{state['company'].replace(' ', '_')}.txt"
                    )
                    with open(cover_letter_path, 'w') as f:
                        f.write(state["cover_letter"])

                    self._upload_file_to_drive(
                        cover_letter_path,
                        role_folder_id,
                        "cover_letter.txt"
                    )
                    print(f"   ✓ Cover letter uploaded")

                    # Cleanup temp file
                    os.remove(cover_letter_path)
                except Exception as e:
                    error_msg = f"Cover letter upload failed (folder created): {str(e)[:100]}"
                    print(f"   ⚠️  {error_msg}")
                    upload_errors.append(error_msg)

            # Step 3: Upload CV
            if state.get("cv_path") and os.path.exists(state["cv_path"]):
                try:
                    print(f"   Uploading CV...")
                    self._upload_file_to_drive(
                        state["cv_path"],
                        role_folder_id,
                        f"CV_{state['company'].replace(' ', '_')}.docx"
                    )
                    print(f"   ✓ CV uploaded")
                except Exception as e:
                    error_msg = f"CV upload failed (folder created): {str(e)[:100]}"
                    print(f"   ⚠️  {error_msg}")
                    upload_errors.append(error_msg)

            # Step 4: Log to Google Sheets
            print(f"   Logging to Google Sheets...")
            sheet_row_id = self._log_to_sheets(state, folder_url)
            print(f"   ✓ Logged to row {sheet_row_id}")

            result = {
                "drive_folder_url": folder_url,
                "sheet_row_id": sheet_row_id
            }

            # Add upload errors if any (non-fatal warnings)
            if upload_errors:
                existing_errors = state.get("errors") or []
                if isinstance(existing_errors, str):
                    existing_errors = [existing_errors]
                result["errors"] = existing_errors + upload_errors

            return result

        except Exception as e:
            error_msg = f"Layer 7 (Output Publisher) failed: {str(e)}"
            print(f"   ✗ {error_msg}")

            errors_list = state.get("errors") or []
            if isinstance(errors_list, str):
                errors_list = [errors_list]

            return {
                "drive_folder_url": None,
                "sheet_row_id": None,
                "errors": errors_list + [error_msg]
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
    print("\n" + "="*60)
    print("LAYER 7: Output Publisher")
    print("="*60)

    publisher = OutputPublisher()
    updates = publisher.publish(state)

    # Print results
    if updates.get("drive_folder_url"):
        print(f"\n📁 Drive Folder: {updates['drive_folder_url']}")
    else:
        print("\n⚠️  No Drive folder created")

    if updates.get("sheet_row_id"):
        print(f"📊 Sheets Row: {updates['sheet_row_id']}")
    else:
        print("\n⚠️  No Sheets row logged")

    print("="*60 + "\n")

    return updates
