import uvicorn

from project.server import get_server_instance

app = get_server_instance()


def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_server()
