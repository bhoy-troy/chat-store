import json
import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)
STATE_PATH = os.environ.get("STATE_PATH", "/app_state/state.json")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
_lock = threading.Lock()


def _load():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


class StateStore:
    @staticmethod
    def get(namespace: str, key: str, default=None):
        with _lock:
            d = _load()
            return (d.get(namespace) or {}).get(key, default)

    @staticmethod
    def set(namespace: str, key: str, value):
        with _lock:
            d = _load()
            d.setdefault(namespace, {})[key] = value
            _save(d)


class EmbeddingCache:
    def __init__(self):
        self._cache = _load().get("_embed_cache") or {}

    def _persist(self):
        with _lock:
            d = _load()
            d["_embed_cache"] = self._cache
            _save(d)

    def get_or_embed(self, chunk_hash: str, text: str):
        key = f"{EMBED_MODEL}:{chunk_hash}"
        if key in self._cache:
            return self._cache[key]
        r = requests.post(f"{OLLAMA_URL}/api/embeddings", json={"model": EMBED_MODEL, "input": text}, timeout=120)
        r.raise_for_status()
        data = r.json()
        vec = data.get("embedding") or (data.get("embeddings") or [None])[0]
        if vec is None:
            raise RuntimeError("No embedding returned from Ollama")
        self._cache[key] = vec
        self._persist()
        return vec
