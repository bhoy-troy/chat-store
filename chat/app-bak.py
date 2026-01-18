# import logging
# import os
# import threading
# import time
# import uuid
#
# import requests
# from apscheduler.schedulers.background import BackgroundScheduler
# from flask import Flask, jsonify, request
# from flask_cors import CORS
# from qdrant_client import QdrantClient
# from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
#
# logger = logging.getLogger("chat-with-docs-chat")
#
# OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama:11434")
# EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
# CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3.1")
# QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
# COLLECTION = os.environ.get("QDRANT_COLLECTION", "confluence")
# TOP_K = int(os.environ.get("TOP_K", "6"))
# MAX_CONTEXT_CHARS = int(os.environ.get("MAX_CONTEXT_CHARS", "12000"))
# INGEST_INTERVAL_MINUTES = int(os.environ.get("INGEST_INTERVAL_MINUTES", "10"))
#
# chat = Flask(__name__)
# CORS(chat)
# qdrant = QdrantClient(url=QDRANT_URL)
#
#
# def run_incremental_ingest():
#     logger.info("run_incremental_ingest")
#     try:
#         from chat.ingest.orchestrator import run_incremental
#
#         run_incremental()
#     except Exception as e:
#         chat.logger.exception("Incremental ingest failed: %s", e)
#
#
# scheduler = BackgroundScheduler(daemon=True)
# scheduler.add_job(run_incremental_ingest, "interval", minutes=INGEST_INTERVAL_MINUTES, id="incremental_ingest")
# scheduler.start()
#
#
# def _ollama_embeddings(payload):
#     logger.info("_ollama_embeddings at %s/chat/embeddings for %S", OLLAMA, payload)
#     r = requests.post(f"{OLLAMA}/chat/embeddings", json=payload, timeout=120)
#     r.raise_for_status()
#     return r.json()
#
#
# def _ollama_generate(payload):
#     logger.info("_ollama_generate at %s/chat/generate for %S", OLLAMA, payload)
#     r = requests.post(f"{OLLAMA}/chat/generate", json=payload, timeout=120)
#     r.raise_for_status()
#     return r.json()
#
#
# def embed_texts(texts):
#     logger.info("embed text for %S", text)
#     data = _ollama_embeddings({"model": EMBED_MODEL, "input": texts})
#     if "embeddings" in data:
#         return data["embeddings"]
#     if "embedding" in data:
#         return [data["embedding"]]
#     raise RuntimeError("Unexpected embeddings response from Ollama")
#
#
# def embed_one(q):
#     logger.info("embed once %s", q)
#     return embed_texts([q])[0]
#
#
# def build_filter_from_request(data):
#     logger.info("build_filter_from_request %S", data)
#     must = []
#     sources = data.get("sources")
#     if sources and isinstance(sources, list):
#         must.append(FieldCondition(key="source", match=MatchAny(any=sources)))
#     space_key = data.get("space_key")
#     if space_key:
#         must.append(FieldCondition(key="space_key", match=MatchValue(value=space_key)))
#     return Filter(must=must) if must else None
#
#
# def search_qdrant(vec, k=TOP_K, flt=None):
#     logger.info("search qdrant query_vector %s, limit %S, query_filter %s", vec, k, flt)
#     return qdrant.search(collection_name=COLLECTION, query_vector=vec, limit=k, query_filter=flt, with_payload=True)
#
#
# def build_context(points):
#     ctx, total = [], 0
#     for p in points:
#         pl = p.payload or {}
#         chunk = f"[{pl.get('title', 'Untitled')}] ({pl.get('source', '')})\nURL: {pl.get('url', '')}\n---\n{pl.get('text', '')}\n"
#         if total + len(chunk) > MAX_CONTEXT_CHARS:
#             chunk = chunk[: max(0, MAX_CONTEXT_CHARS - total)]
#         ctx.append(chunk)
#         total += len(chunk)
#         if total >= MAX_CONTEXT_CHARS:
#             break
#     return "\n\n".join(ctx)
#
#
# def generate_answer(user_q, points):
#     context = build_context(points)
#     sys_prompt = (
#         "You are a knowledge-base assistant. Answer using ONLY the provided context. "
#         "If the answer is not in context, say you don't know. "
#         "Return a concise answer and include a bullet list of source URLs at the end.\n\n"
#         f"CONTEXT:\n{context}\n\nQUESTION: {user_q}\n\nANSWER:"
#     )
#     res = _ollama_generate({"model": CHAT_MODEL, "prompt": sys_prompt, "stream": False})
#     answer = res.get("response", "").strip()
#     cites = sorted({(p.payload or {}).get("url", "") for p in points if (p.payload or {}).get("url")})
#     return answer, cites
#
#
# @chat.get("/ping")
# def ping():
#     return {"status": "ok", "time": int(time.time())}
#
#
# @chat.post("/query")
# def query():
#     logger.info("query")
#     data = request.get_json(force=True)
#     user_q = data.get("query", "").strip()
#     if not user_q:
#         return jsonify({"error": "query is required"}), 400
#     v = embed_one(user_q)
#     flt = build_filter_from_request(data)
#     res = search_qdrant(v, k=TOP_K, flt=flt)
#     answer, citations = generate_answer(user_q, res)
#     return jsonify({"answer": answer, "sources": citations})
#
#
# @chat.post("/reindex")
# def reindex():
#     threading.Thread(target=run_incremental_ingest, daemon=True).start()
#     return jsonify({"status": "started"})
#
#
# @chat.post("/v1/chat/completions")
# def chat_completions():
#     payload = request.get_json(force=True)
#     messages = payload.get("messages", [])
#     user_q = ""
#     for m in reversed(messages):
#         if m.get("role") == "user":
#             user_q = m.get("content", "")
#             break
#     if not user_q:
#         return jsonify({"error": "no user message found"}), 400
#     sources = None
#     for m in messages:
#         if m.get("role") in ("system", "user"):
#             content = m.get("content", "")
#             if "sources" in content and "{" in content and "}" in content:
#                 try:
#                     start = content.find("{")
#                     end = content.rfind("}")
#                     conf = __import__("json").loads(content[start : end + 1])
#                     if isinstance(conf.get("sources"), list):
#                         sources = conf["sources"]
#                 except Exception:
#                     pass
#     data = {"query": user_q}
#     if sources:
#         data["sources"] = sources
#     v = embed_one(user_q)
#     flt = build_filter_from_request(data)
#     res = search_qdrant(v, k=TOP_K, flt=flt)
#     answer, citations = generate_answer(user_q, res)
#     now = int(time.time())
#     return jsonify(
#         {
#             "id": f"chatcmpl-{uuid.uuid4().hex}",
#             "object": "chat.completion",
#             "created": now,
#             "model": CHAT_MODEL,
#             "choices": [
#                 {
#                     "index": 0,
#                     "message": {
#                         "role": "assistant",
#                         "content": answer
#                         + ("\n\nSources:\n" + "\n".join(f"- {u}" for u in citations) if citations else ""),
#                     },
#                     "finish_reason": "stop",
#                 }
#             ],
#             "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
#         }
#     )
