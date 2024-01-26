from fastapi import FastAPI

from project.routers import upload, scratch

app = FastAPI()

app.include_router(
    upload.router,
    prefix="/upload",
)

app.include_router(scratch.router, prefix="/scratch")
