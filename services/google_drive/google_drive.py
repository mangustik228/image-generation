import io
import os
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from loguru import logger

SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveService:
    """Service for uploading files to Google Drive."""

    def __init__(self, folder_id: str, token_path: str = "token.json"):
        """
        Initialize Google Drive service using OAuth credentials.

        Args:
            folder_id: ID of the "generated" folder in Google Drive
            token_path: Path to OAuth token file
        """
        self.folder_id = folder_id
        creds = self._get_credentials(token_path)
        self.service = build("drive", "v3", credentials=creds)
        logger.info(f"Google Drive service initialized, target folder: {folder_id}")

    def _get_credentials(self, token_path: str) -> Credentials:
        """Load OAuth credentials from token file."""
        if not os.path.exists(token_path):
            raise FileNotFoundError(
                f"Token file '{token_path}' not found. "
                "Run 'uv run auth_google.py' first to authenticate."
            )

        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing OAuth token...")
                creds.refresh(Request())
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            else:
                raise ValueError(
                    "Token is invalid. Run 'uv run auth_google.py' to re-authenticate."
                )

        return creds

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        mime_type: str = "image/png",
    ) -> Optional[str]:
        """
        Upload file bytes directly to Google Drive folder.

        Args:
            file_bytes: File content as bytes
            filename: Name for the file in Google Drive
            mime_type: MIME type of the file

        Returns:
            File ID in Google Drive or None if upload failed
        """
        try:
            file_metadata = {
                "name": filename,
                "parents": [self.folder_id],
            }

            media = MediaIoBaseUpload(
                io.BytesIO(file_bytes),
                mimetype=mime_type,
                resumable=True,
            )

            file = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink",
                    supportsAllDrives=True,
                )
                .execute()
            )

            file_id = file.get("id")
            web_link = file.get("webViewLink")
            logger.info(f"Uploaded '{filename}' to Google Drive: {web_link}")
            return file_id

        except Exception as e:
            logger.error(f"Failed to upload '{filename}' to Google Drive: {e}")
            return None

    def get_file_link(self, file_id: str) -> Optional[str]:
        """
        Get web view link for a file.

        Args:
            file_id: Google Drive file ID

        Returns:
            Web view link or None if failed
        """
        try:
            file = (
                self.service.files().get(fileId=file_id, fields="webViewLink").execute()
            )
            return file.get("webViewLink")
        except Exception as e:
            logger.error(f"Failed to get link for file {file_id}: {e}")
            return None

    def list_files(self, page_size: int = 1000) -> list[dict]:
        """
        List all files in the target folder.

        Args:
            page_size: Maximum number of files to return per page

        Returns:
            List of file info dicts with id, name, mimeType
        """
        files = []
        page_token = None

        try:
            while True:
                query = f"'{self.folder_id}' in parents and trashed = false"
                response = (
                    self.service.files()
                    .list(
                        q=query,
                        spaces="drive",
                        fields="nextPageToken, files(id, name, mimeType)",
                        pageToken=page_token,
                        pageSize=page_size,
                        supportsAllDrives=True,
                        includeItemsFromAllDrives=True,
                    )
                    .execute()
                )

                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")

                if not page_token:
                    break

            logger.info(f"Found {len(files)} files in Google Drive folder")
            return files

        except Exception as e:
            logger.error(f"Failed to list files from Google Drive: {e}")
            return []

    def check_file_exists(self, file_id: str) -> bool:
        """
        Check if a file exists in the target folder and is not trashed.

        Args:
            file_id: Google Drive file ID

        Returns:
            True if file exists in target folder, False otherwise
        """
        try:
            file = (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id, name, trashed, parents",
                    supportsAllDrives=True,
                )
                .execute()
            )
            is_trashed = file.get("trashed", False)
            parents = file.get("parents", [])
            file_name = file.get("name", "unknown")

            if is_trashed:
                logger.debug(f"Файл {file_id} ({file_name}) в корзине")
                return False

            if self.folder_id not in parents:
                logger.warning(
                    f"Файл {file_id} ({file_name}) не в целевой папке. "
                    f"Ожидается: {self.folder_id}, фактически: {parents}"
                )
                return False

            logger.debug(f"Файл {file_id} ({file_name}) найден в целевой папке")
            return True
        except Exception as e:
            logger.debug(f"Файл {file_id} не найден: {e}")
            return False

    def download_file(self, file_id: str) -> Optional[bytes]:
        """
        Download file content from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            File content as bytes or None if failed
        """
        try:
            request = self.service.files().get_media(fileId=file_id)
            file_bytes = io.BytesIO()
            downloader = request.execute()
            if isinstance(downloader, bytes):
                return downloader
            file_bytes.write(downloader)
            return file_bytes.getvalue()
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return None

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from Google Drive.

        Args:
            file_id: Google Drive file ID

        Returns:
            True if file was deleted, False otherwise
        """
        try:
            self.service.files().delete(
                fileId=file_id,
                supportsAllDrives=True,
            ).execute()
            logger.info(f"Deleted file from Google Drive: {file_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False
