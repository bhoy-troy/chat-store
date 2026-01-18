import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI

from chat.ingest.orchestrator import run_incremental
from chat.settings import settings
from chat.views.rag_api import get_router

log_path=Path((Path(__file__).parent),'logging.conf')
# logging.config.fileConfig(log_path)
logger = logging.getLogger("Chat With Docs")
logging.basicConfig(filename="/tmp/logs/log.log", encoding="utf-8", level=logging.DEBUG)
#
# # create console handler and set level to debug
# ch = logging.StreamHandler()
# ch.setLevel(logging.DEBUG)


scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(" start lifespan scheduler")
    scheduler.add_job(run_incremental, "interval", minutes=settings.ingest_interval_minutes, id="incremental_ingest")
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Chat With Docs)", lifespan=lifespan)


@app.get("/health", tags=["_meta"])
async def health():
    logger.info("(health api")
    return {"status": "ok"}


app.include_router(get_router())
