from typing import Annotated

from fastapi import FastAPI, Depends

from project.dependencies import get_client_id
from project.routers import upload, scratch

app = FastAPI()

app.include_router(
    upload.router,
    prefix="/upload",
)

app.include_router(
    scratch.router,
    prefix="/scratch",
)


@app.get("/")
async def test(client_id: Annotated[str, Depends(get_client_id)]):
    return {
        "client_id": client_id,
    }
