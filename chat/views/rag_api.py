import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from fastapi import APIRouter, Body, Depends, status
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from chat.settings import settings

logger = logging.getLogger(__name__)


class QueryIn(BaseModel):
    query: str = Field(..., min_length=1)
    sources: Optional[List[str]] = None
    space_key: Optional[str] = None


class QueryOut(BaseModel):
    answer: str
    sources: List[str] = []


def get_qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


class RagAPI:
    def __init__(self):
        self.router = APIRouter(prefix="", tags=["RAG"])
        self.router.add_api_route("/ping", self.ping, methods=["GET"])
        self.router.add_api_route(
            "/query", self.query, methods=["POST"], response_model=QueryOut, status_code=status.HTTP_200_OK
        )
        self.router.add_api_route("/reindex", self.reindex, methods=["POST"])
        self.router.add_api_route("/v1/chat/completions", self.chat_completions, methods=["POST"])

    def _ollama_embeddings(self, texts: List[str]) -> List[List[float]]:
        logger.info("_ollama_embeddings at %s/chat/embeddings for %S", settings.ollama_url, texts)
        r = requests.post(
            f"{settings.ollama_url}/api/embeddings", json={"model": settings.embed_model, "input": texts}, timeout=120
        )
        r.raise_for_status()
        data = r.json()
        if "embeddings" in data:
            return data["embeddings"]
        if "embedding" in data:
            return [data["embedding"]]
        raise RuntimeError("Unexpected Ollama embeddings response")

    def _ollama_generate(self, prompt: str) -> str:
        logger.info("_ollama_generate at %s/chat/generate for %S", settings.ollama_url, prompt)
        r = requests.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": settings.chat_model, "prompt": prompt, "stream": False},
            timeout=120,
        )
        r.raise_for_status()
        return (r.json().get("response") or "").strip()

    def _build_filter(self, data: QueryIn) -> Optional[Filter]:
        logger.info("build filter %s", data)
        must = []
        if data.sources:
            must.append(FieldCondition(key="source", match=MatchAny(any=data.sources)))
        if data.space_key:
            must.append(FieldCondition(key="space_key", match=MatchValue(value=data.space_key)))
        return Filter(must=must) if must else None

    def _build_context(self, points) -> str:
        parts, total = [], 0
        for p in points:
            pl = p.payload or {}
            chunk = f"[{pl.get('title','Untitled')}] ({pl.get('source','')})\nURL: {pl.get('url','')}\n---\n{pl.get('text','')}\n"
            if total + len(chunk) > settings.max_context_chars:
                chunk = chunk[: max(0, settings.max_context_chars - total)]
            parts.append(chunk)
            total += len(chunk)
            if total >= settings.max_context_chars:
                break
        return "\n\n".join(parts)

    def _answer_from_points(self, user_q: str, points) -> QueryOut:
        context = self._build_context(points)
        prompt = (
            "You are a knowledge-base assistant. Answer using ONLY the provided context. "
            "If the answer is not in context, say you don't know. "
            "Return a concise answer and include a bullet list of source URLs at the end.\n\n"
            f"CONTEXT:\n{context}\n\nQUESTION: {user_q}\n\nANSWER:"
        )
        answer = self._ollama_generate(prompt)
        cites = sorted({(p.payload or {}).get("url", "") for p in points if (p.payload or {}).get("url")})
        return QueryOut(answer=answer, sources=[c for c in cites if c])

    async def ping(self) -> Dict[str, Any]:
        return {"status": "ok", "time": int(time.time())}

    async def query(self, payload: QueryIn, qdrant: QdrantClient = Depends(get_qdrant)) -> QueryOut:
        vec = self._ollama_embeddings([payload.query])[0]
        flt = self._build_filter(payload)
        points = qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=vec,
            limit=settings.top_k,
            query_filter=flt,
            with_payload=True,
        )
        return self._answer_from_points(payload.query, points)

    async def reindex(self) -> Dict[str, str]:
        import threading

        from chat.ingest.orchestrator import run_incremental

        logger.info("doing reindex")

        threading.Thread(target=run_incremental, daemon=True).start()
        return {"status": "started"}

    async def chat_completions(self, body: Dict[str, Any] = Body(...)):
        logger.onfo("chat_completions %s", body)
        messages = body.get("messages", [])
        user_q = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_q = m.get("content", "")
                break
        if not user_q:
            return {"error": "no user message found"}
        sources = None
        for m in messages:
            if m.get("role") in ("system", "user"):
                content = m.get("content", "")
                if "sources" in content and "{" in content and "}" in content:
                    try:
                        import json

                        j = json.loads(content[content.find("{") : content.rfind("}") + 1])
                        if isinstance(j.get("sources"), list):
                            sources = j["sources"]
                    except Exception:
                        pass
        payload = QueryIn(query=user_q, sources=sources)
        vec = self._ollama_embeddings([payload.query])[0]
        flt = self._build_filter(payload)
        qdrant = get_qdrant()
        points = qdrant.search(
            collection_name=settings.qdrant_collection,
            query_vector=vec,
            limit=settings.top_k,
            query_filter=flt,
            with_payload=True,
        )
        out = self._answer_from_points(payload.query, points)
        now = int(time.time())
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": now,
            "model": settings.chat_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": out.answer
                        + ("\n\nSources:\n" + "\n".join(f"- {u}" for u in out.sources) if out.sources else ""),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


def get_router() -> APIRouter:
    return RagAPI().router
