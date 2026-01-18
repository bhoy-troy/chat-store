import hashlib
import logging

from .providers.base import DocItem, Provider
from .providers.gdrive import GDriveProvider
from .qdrant_ops import delete_doc, upsert_chunks
from .store import EmbeddingCache, StateStore

logger = logging.getLogger(__name__)


def chunk(text, window_chars=4500, overlap_chars=600):
    out = []
    i = 0
    n = len(text or "")
    while i < n:
        c = text[i : i + window_chars]
        if not c:
            break
        h = hashlib.sha1(c.encode("utf-8")).hexdigest()
        out.append((h, c))
        i += max(1, window_chars - overlap_chars)
    return out


def run_provider(provider: Provider, cache: EmbeddingCache):
    logger.info("run_provider Provider %s cache %s", provider, cache)
    try:
        cursor = StateStore.get(provider.name, "cursor")
        for change in provider.list_changed(cursor):
            logger.info("change found in %s", change)
            # import pdb
            # pdb.set_trace()
            if isinstance(change, dict) and change.get("deleted"):
                logger.info("change is deleted  for %s", change)
                delete_doc(source=provider.name, doc_id=change["doc_id"])
                continue
            if change == "__cursor__":
                logger.info("change is only cursor  for %s", change)

                StateStore.set(provider.name, "cursor", provider.cursor)
                continue
            item: DocItem = change["item"]
            content = provider.fetch_content(item)
            chunks = chunk(content.text)
            logger.info(
                "up-serting new change for  provider.name-> %s, item-> %s, content.version-> %s, chunks-> %s, cache-> %s",
                provider.name,
                item,
                content.version,
                chunks,
                cache,
            )
            upsert_chunks(provider.name, item, content.version, chunks, cache)
    except Exception as e:
        logger.exception("[ingest] provider %s error: %s", getattr(provider, "name", "?"), e)
        print(f"[ingest] provider {getattr(provider, 'name', '?')} error: {e}")


def run_incremental():
    logger.info("run_incremental")
    cache = EmbeddingCache()
    # for P in (ConfluenceProvider, GDriveProvider, OneDriveProvider):
    for P in [GDriveProvider]:
        logger.info("running for %s with %s", P, cache)

        run_provider(P(), cache)
