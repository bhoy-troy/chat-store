# Confluence + Google Drive + OneDrive RAG

Pluggable providers feed a shared chunk → embed → Qdrant pipeline. APScheduler keeps it fresh.


echo "GDRIVE_AUTH_JSON_B64=$(base64 -w0 bob-the-builder-jt-6e0345ed5a9c.json 2>/dev/null || base64 bob-the-builder-jt-6e0345ed5a9c.json | tr -d '\n')" >> .env


## Quickstart
1) `docker exec -it ollama sh`
2) `ollama pull llama3.1 && ollama pull nomic-embed-text`
2) `cp .env.example .env` and set provider creds you want
3) `docker compose up -d --build`
4) Trigger initial ingest: `curl -X POST http://localhost:8000/reindex`

## Query
POST /query with
```json
{ "query": "Runbook?", "sources": ["confluence","gdrive","onedrive"], "space_key": "ENG" }
```

# GPU

    sudo apt update && sudo apt install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker

## Notes
- Provider change detection is simplified; swap in Drive Changes API and Graph delta/webhooks for production.
- Embeddings cached by chunk hash to avoid re-embedding.
- Deletions handled via Qdrant filter delete per (source, doc_id).
