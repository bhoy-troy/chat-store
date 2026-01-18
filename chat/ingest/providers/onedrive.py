import logging
import os

import requests

from chat.ingest.providers.base import DocContent, DocItem, Provider

logger = logging.getLogger(__name__)

TENANT = os.environ.get("GRAPH_TENANT_ID")
CLIENT_ID = os.environ.get("GRAPH_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET")
SITE_ID = os.environ.get("ONEDRIVE_SITE_ID")


class OneDriveProvider(Provider):
    name = "onedrive"

    def __init__(self):
        self._token = None
        self.cursor = None

    def _get_token(self):
        if not (TENANT and CLIENT_ID and CLIENT_SECRET):
            return None
        url = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default",
        }
        r = requests.post(url, data=data, timeout=60)
        r.raise_for_status()
        return r.json()["access_token"]

    def _graph(self, path, params=None, binary=False):
        if not self._token:
            self._token = self._get_token()
        if not self._token:
            return None
        headers = {"Authorization": f"Bearer {self._token}"}
        r = requests.get(f"https://graph.microsoft.com/v1.0/{path}", headers=headers, params=params or {}, timeout=60)
        if binary:
            r.raise_for_status()
            return r.content
        r.raise_for_status()
        return r.json()

    def list_changed(self, since=None):
        if not (TENANT and CLIENT_ID and CLIENT_SECRET):
            return []
        drive_path = f"sites/{SITE_ID}/drive" if SITE_ID else "me/drive"
        data = self._graph(f"{drive_path}/root/children?$top=100")
        for it in (data or {}).get("value", []):
            if it.get("folder"):
                continue
            yield {
                "item": DocItem(
                    doc_id=it["id"],
                    title=it.get("name", "Untitled"),
                    mime_type=it.get("file", {}).get("mimeType", ""),
                    modified_at=it.get("lastModifiedDateTime", ""),
                    parents=[it.get("parentReference", {}).get("path", "")],
                    web_url=it.get("webUrl", ""),
                    source=self.name,
                )
            }
        self.cursor = "timestamp"
        yield "__cursor__"

    def fetch_content(self, item: DocItem) -> DocContent:
        drive_path = f"sites/{SITE_ID}/drive" if SITE_ID else "me/drive"
        content = self._graph(f"{drive_path}/items/{item.doc_id}/content", binary=True)
        text = ""
        try:
            if item.mime_type and item.mime_type.startswith("text/"):
                text = content.decode("utf-8", errors="ignore")
            elif item.title.lower().endswith((".txt", ".md", ".csv", ".json", ".yaml", ".yml")):
                text = content.decode("utf-8", errors="ignore")
        except Exception:
            pass
        return DocContent(text=text, html=None, version=item.modified_at)
