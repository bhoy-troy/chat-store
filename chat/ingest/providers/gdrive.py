import base64
import json
import logging
import os,binascii

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from chat.ingest.providers.base import DocContent, DocItem, Provider

logger = logging.getLogger(__name__)
GDRIVE_AUTH_JSON_B64 = os.environ.get("GDRIVE_AUTH_JSON_B64")
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

def _load_sa_info(val: str):
    if not val:
        return None
    # Accept either base64 **or** raw JSON for convenience
    if val.startswith("{"):
        return json.loads(val)
    try:
        # add padding just in case
        raw = base64.b64decode(val + "==")
        return json.loads(raw.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError):
        raise RuntimeError("GDRIVE_AUTH_JSON_B64 is neither valid base64 nor JSON")


# def _service():
#     info = _load_sa_info(GDRIVE_AUTH_JSON_B64)
#     if not GDRIVE_AUTH_JSON_B64:
#         return None
#     logger.info("loading GDRIVE_AUTH_JSON_B64 %s", GDRIVE_AUTH_JSON_B64)
#     info = json.loads(base64.b64decode(GDRIVE_AUTH_JSON_B64).decode("utf-8"))
#     logger.info("decoded GDRIVE_AUTH_JSON_B64 %s", info)
#     creds = Credentials.from_service_account_info(info, scopes=SCOPES)
#     return build("drive", "v3", credentials=creds, cache_discovery=False)
def _service():
    info = _load_sa_info(GDRIVE_AUTH_JSON_B64)
    if not info:
        return None
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)

class GDriveProvider(Provider):
    name = "gdrive"

    def __init__(self):
        self.svc = _service()
        self.cursor = None

    def list_changed(self, since=None):
        logger.info("list changes since %s", since)


        if not self.svc:
            return []
        try:
            q = "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
            resp = self.svc.files().list(
                q=q,
                pageSize=100,
                fields="files(id,name,mimeType,modifiedTime,parents,webViewLink)"
            ).execute()
        except HttpError as e:
            raise RuntimeError(f"Drive API error: {e}")

        files = resp.get("files")
        # Defensive checks
        if files is None:
            raise RuntimeError(f"Drive response missing 'files' key: {resp!r}")
        if isinstance(files, str):
            # Likely an HTML error page via proxy; bubble up a clearer message
            snippet = files[:200].replace("\n", "\\n")
            raise RuntimeError(f"Drive 'files' is a string (proxy/HTML?): {snippet}")
        if not isinstance(files, list):
            raise RuntimeError(f"Drive 'files' has unexpected type: {type(files).__name__}")

        for f in files:
            if not isinstance(f, dict):
                # Skip bad entries gracefully
                continue
            yield {"item": DocItem(
                doc_id=f.get("id", ""),
                title=f.get("name", "Untitled"),
                mime_type=f.get("mimeType", ""),
                modified_at=f.get("modifiedTime", ""),
                parents=f.get("parents", []) or [],
                web_url=f.get("webViewLink", ""),
                source=self.name
            )}
        self.cursor = "timestamp"
        yield "__cursor__"

        if not self.svc:
            return []
        q = "mimeType != 'application/vnd.google-apps.folder' and trashed = false"
        req = self.svc.files().list(q=q, fields="files(id,name,mimeType,modifiedTime,parents,webViewLink)")
        resp = req.execute()
        logger.info('list_changed resp %s', resp)
        for f in resp.get("files", []):
            yield {
                "item": DocItem(
                    doc_id=f["id"],
                    title=f.get("name", "Untitled"),
                    mime_type=f.get("mimeType", ""),
                    modified_at=f.get("modifiedTime", ""),
                    parents=f.get("parents", []),
                    web_url=f.get("webViewLink", ""),
                    source=self.name,
                )
            }
        self.cursor = "timestamp"
        yield "__cursor__"

    def fetch_content(self, item: DocItem) -> DocContent:

        logger.info("fetch_content %s", item)
        mt = item.mime_type or ""
        # Export Google Docs to text if possible
        export_map = {"application/vnd.google-apps.document": "text/plain"}
        try:
            if mt in export_map:
                data = self.svc.files().export(fileId=item.doc_id, mimeType=export_map[mt]).execute()
                text = data.decode("utf-8", errors="ignore")
                return DocContent(text=text, html=None, version=item.modified_at)

            # Binary download
            data = self.svc.files().get_media(fileId=item.doc_id).execute()
            text = ""
            try:
                if mt.startswith("text/") or item.title.lower().endswith(
                        (".txt", ".md", ".csv", ".json", ".yaml", ".yml")):
                    text = data.decode("utf-8", errors="ignore")
            except Exception:
                pass
            return DocContent(text=text, html=None, version=item.modified_at)
        except HttpError as e:
            raise RuntimeError(f"Drive download/export error for {item.doc_id}: {e}")
