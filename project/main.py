import click
import uvicorn
from minio import Minio, S3Error


@click.group()
def cli():
    pass


@cli.command()
@click.option("--endpoint", default="localhost:9000", help="S3 API endpoint.")
@click.option("--region", default="us-east-1", help="AWS region.")
@click.option(
    "--exist-ok",
    is_flag=True,
    default=False,
    help="If set, will not throw an error if bucket already exists.",
)
@click.option(
    "--verify/--no-verify", default=True, help="Enable certificate validation."
)
@click.argument("access_key", metavar="ACCESS_KEY")
@click.argument("secret_key", metavar="SECRET_KEY")
@click.argument("bucket_name", metavar="BUCKET_NAME")
def migrate(
    endpoint: str,
    region: str,
    exist_ok: bool,
    verify: bool,
    access_key: str,
    secret_key: str,
    bucket_name: str,
):
    minio = Minio(endpoint, access_key, secret_key, secure=verify, region=region)

    try:
        minio.make_bucket(bucket_name)
        print(f"Successfully created bucket `{bucket_name}` on `{endpoint}`.")
    except S3Error as e:
        match e.code:
            case "BucketAlreadyOwnedByYou":
                if not exist_ok:
                    raise e

                print(f"Bucket `{bucket_name}` already exists.")
            case _:
                raise e


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
