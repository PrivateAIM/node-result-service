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
def server(reload: bool):
    uvicorn.run("project.server:app", host="0.0.0.0", port=8080, reload=reload)


if __name__ == "__main__":
    cli()
