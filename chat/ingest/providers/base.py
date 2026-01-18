from dataclasses import dataclass
from typing import Iterable, List, Optional


@dataclass
class DocItem:
    doc_id: str
    title: str
    mime_type: str
    modified_at: str
    parents: List[str]
    web_url: str
    source: str
    space_key: Optional[str] = None


@dataclass
class DocContent:
    text: str
    html: Optional[str]
    version: str


class Provider:
    name: str
    cursor: str

    def list_changed(self, since: Optional[str]) -> Iterable:
        raise NotImplementedError

    def fetch_content(self, item: DocItem) -> DocContent:
        raise NotImplementedError
