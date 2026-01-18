import logging
import os

import requests
from bs4 import BeautifulSoup

from chat.ingest.providers.base import DocContent, DocItem, Provider

logger = logging.getLogger(__name__)
CONF_BASE = os.environ.get("CONF_BASE")
CONF_TOKEN = os.environ.get("CONF_TOKEN")


class ConfluenceProvider(Provider):
    name = "confluence"

    def __init__(self):
        self.disabled = not (CONF_BASE and CONF_TOKEN)
        self.cursor = None

    def _get(self, path, params=None):
        headers = {"Authorization": f"Bearer {CONF_TOKEN}"}
        r = requests.get(f"{CONF_BASE}/rest/api{path}", headers=headers, params=params or {})
        r.raise_for_status()
        return r.json()

    def list_changed(self, since=None):
        if self.disabled:
            return []
        cql = 'type = "page"'
        start = 0
        limit = 100
        while True:
            data = self._get(
                "/content/search", {"cql": cql, "limit": limit, "start": start, "expand": "body.storage,space,version"}
            )
            batch = data.get("results", [])
            for p in batch:
                yield {
                    "item": DocItem(
                        doc_id=p["id"],
                        title=p.get("title", "Untitled"),
                        mime_type="text/html",
                        modified_at=((p.get("version") or {}).get("when", "")),
                        parents=[(p.get("space") or {}).get("key", "")],
                        web_url=f"{CONF_BASE}/pages/{p['id']}",
                        source=self.name,
                        space_key=(p.get("space") or {}).get("key"),
                    )
                }
            if len(batch) < limit:
                break
            start += limit
        self.cursor = "timestamp"
        yield "__cursor__"

    def fetch_content(self, item: DocItem) -> DocContent:
        data = self._get(f"/content/{item.doc_id}", {"expand": "body.storage,version"})
        html = (((data.get("body") or {}).get("storage") or {}).get("value")) or ""
        text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
        version = str(((data.get("version") or {}).get("number") or 0))
        return DocContent(text=text, html=html, version=version)
