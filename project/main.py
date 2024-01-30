import click
import uvicorn


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--reload/--no-reload",
    default=False,
    help="Enable hot reloading.",
)
@click.option(
    "--port",
    "-p",
    type=int,
    default=8000,
    help="Port for the server to listen on.",
)
def server(
    reload: bool,
    port: int,
):
    uvicorn.run("project.server:app", host="0.0.0.0", port=port, reload=reload)


if __name__ == "__main__":
    cli()
