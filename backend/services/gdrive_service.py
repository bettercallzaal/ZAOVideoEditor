"""Google Drive upload service for ZAO Video Editor.

Uploads transcript, caption, and metadata files to Google Drive
under a "ZAO Transcripts/{project_name}/" folder structure.

Requires:
  - credentials.json in the backend/ directory (OAuth client from Google Cloud Console)
  - google-api-python-client, google-auth-httplib2, google-auth-oauthlib
"""

import os
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).parent.parent
CREDENTIALS_PATH = BACKEND_DIR / "credentials.json"
TOKEN_PATH = BACKEND_DIR / "token.json"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# Extensions to upload from each subdirectory
UPLOAD_EXTENSIONS = {".json", ".txt", ".srt", ".ass"}
UPLOAD_SUBDIRS = ["transcripts", "captions", "metadata"]


def is_gdrive_configured() -> bool:
    """Check if Google Drive credentials.json exists."""
    return CREDENTIALS_PATH.exists()


def authenticate():
    """Authenticate with Google Drive via OAuth.

    First time: opens browser for consent, saves token.json.
    Subsequent calls: reuses saved token, refreshing if expired.

    Returns an authorized Google Drive API service object.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds: Optional[Credentials] = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def _find_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """Find a folder by name (under parent), or create it. Returns folder ID."""
    query = (
        f"mimeType='application/vnd.google-apps.folder' "
        f"and name='{name}' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = (
        service.files()
        .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )

    files = results.get("files", [])
    if files:
        return files[0]["id"]

    # Create the folder
    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_project_to_drive(project_name: str, project_dir: str) -> list[dict]:
    """Upload transcript/caption/metadata files to Google Drive.

    Creates folder structure: ZAO Transcripts > {project_name}
    Uploads all .json, .txt, .srt, .ass files from transcripts/, captions/, metadata/.

    Returns a list of dicts with {name, id, link} for each uploaded file.
    """
    from googleapiclient.http import MediaFileUpload

    service = authenticate()
    project_path = Path(project_dir)

    # Create folder hierarchy
    root_folder_id = _find_or_create_folder(service, "ZAO Transcripts")
    project_folder_id = _find_or_create_folder(service, project_name, root_folder_id)

    uploaded = []

    for subdir_name in UPLOAD_SUBDIRS:
        subdir = project_path / subdir_name
        if not subdir.exists():
            continue

        for file_path in sorted(subdir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in UPLOAD_EXTENSIONS:
                continue

            display_name = f"{subdir_name}/{file_path.name}"

            # Determine MIME type
            mime_map = {
                ".json": "application/json",
                ".txt": "text/plain",
                ".srt": "text/plain",
                ".ass": "text/plain",
            }
            mime_type = mime_map.get(file_path.suffix.lower(), "application/octet-stream")

            # Check if file already exists in project folder (update instead of duplicate)
            upload_name = f"{subdir_name}_{file_path.name}"
            existing_query = (
                f"name='{upload_name}' "
                f"and '{project_folder_id}' in parents "
                f"and trashed=false"
            )
            existing = (
                service.files()
                .list(q=existing_query, spaces="drive", fields="files(id)", pageSize=1)
                .execute()
                .get("files", [])
            )

            media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)

            if existing:
                # Update existing file
                file_meta = (
                    service.files()
                    .update(
                        fileId=existing[0]["id"],
                        media_body=media,
                        fields="id, webViewLink",
                    )
                    .execute()
                )
            else:
                # Create new file
                file_metadata = {
                    "name": upload_name,
                    "parents": [project_folder_id],
                }
                file_meta = (
                    service.files()
                    .create(
                        body=file_metadata,
                        media_body=media,
                        fields="id, webViewLink",
                    )
                    .execute()
                )

            uploaded.append(
                {
                    "name": display_name,
                    "id": file_meta["id"],
                    "link": file_meta.get("webViewLink", ""),
                }
            )

    return uploaded
