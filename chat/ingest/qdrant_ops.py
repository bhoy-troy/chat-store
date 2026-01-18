import logging
import os

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "confluence")
qdrant = QdrantClient(url=QDRANT_URL)


def ensure_collection(dim: int):
    logger.info("ensure_collection dim %s ", dim)
    cols = [c.name for c in qdrant.get_collections().collections]
    if COLLECTION not in cols:
        qdrant.create_collection(COLLECTION, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))


def upsert_chunks(source, doc, version, chunks, cache):
    logger.info("upsert_chunks source %s, doc %s, version %s, chunks %s, cache %s", source, doc, version, chunks, cache)
    points = []
    for h, text in chunks:
        vec = cache.get_or_embed(h, text)
        pid = f"{source}:{doc.doc_id}:{h}"
        points.append(
            PointStruct(
                id=pid,
                vector=vec,
                payload={
                    "source": source,
                    "doc_id": doc.doc_id,
                    "chunk_hash": h,
                    "version": version,
                    "title": doc.title,
                    "url": doc.web_url,
                    "parents": getattr(doc, "parents", []),
                    "modified_at": doc.modified_at,
                    "text": text,
                    "space_key": getattr(doc, "space_key", None),
                },
            )
        )
    if points:
        qdrant.upsert(collection_name=COLLECTION, wait=True, points=points)


def delete_doc(source, doc_id):
    logger.info("delete doc -> source %s, doc_id -> %S ", source, doc_id)
    flt = Filter(
        must=[
            FieldCondition(key="source", match=MatchValue(value=source)),
            FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
        ]
    )
    qdrant.delete(collection_name=COLLECTION, points_selector=flt, wait=True)
