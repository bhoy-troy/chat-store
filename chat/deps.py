from typing import Annotated

from fastapi import Depends


class DB:
    # pretend DB connection / session
    def __init__(self): ...
    def close(self): ...


def get_db():
    db = DB()
    try:
        yield db
    finally:
        db.close()


DBDep = Annotated[DB, Depends(get_db)]
