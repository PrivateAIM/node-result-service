The FLAME Node Result Service is responsible for handling result files for federated analyses within FLAME.
It uses a local object storage to store intermediate files, as well as to enqueue files for upload to the FLAME Hub.

# Setup

You will need access to a MinIO instance and an identification provider that offers a JWKS endpoint for the access
tokens it issues.

For manual installation, you will need Python 3.10 or higher and [Poetry](https://python-poetry.org/) installed.
Clone the repository and run `poetry install` in the root directory.
Create a copy of `.env.example`, name it `.env` and configure to your needs.
Finally, use the command line tool `flame-result` to start the service.

```
$ git clone https://github.com/PrivateAIM/node-result-service.git
$ cd node-result-service
$ poetry install
$ cp .env.example .env
$ poetry shell
$ flame-result server
```

Alternatively, if you're using
Docker, [pull a recent image from the GitHub container registry](https://github.com/PrivateAIM/node-result-service/pkgs/container/node-result-service).
Pass in the configuration options using `-e` flags and forward port 8080 from your host to the container.

```
$ docker run --rm -p 8080:8080 -e HUB__AUTH_USERNAME=admin \
    -e HUB__AUTH_PASSWORD=super_secret \
    -e MINIO__ENDPOINT=localhost:9000 \
    -e MINIO__ACCESS_KEY=admin \
    -e MINIO__SECRET_KEY=super_secret \
    -e MINIO__BUCKET=flame \
    -e MINIO__USE_SSL=false \
    -e OIDC__CERTS_URL="http://my.idp.org/realms/flame/protocol/openid-connect/certs" \
    ghcr.io/privateaim/node-result-service:sha-c1970cf
```

# Configuration

The following table shows all available configuration options.

| **Environment variable**   | **Description**                                          | **Default**                 | **Required** |
|----------------------------|----------------------------------------------------------|-----------------------------|:------------:|
| HUB__API_BASE_URL          | Base URL for the FLAME Hub API                           | https://api.privateaim.net  |              |
| HUB__AUTH_BASE_URL         | Base URL for the FLAME Auth API                          | https://auth.privateaim.net |              |
| HUB__AUTH_USERNAME         | Username to use for obtaining access tokens              |                             |      x       |
| HUB__AUTH_PASSWORD         | Password to use for obtaining access tokens              |                             |      x       |
| MINIO__ENDPOINT            | MinIO S3 API endpoint (without scheme)                   |                             |      x       |
| MINIO__ACCESS_KEY          | Access key for interacting with MinIO S3 API             |                             |      x       |
| MINIO__SECRET_KEY          | Secret key for interacting with MinIO S3 API             |                             |      x       |
| MINIO__BUCKET              | Name of S3 bucket to store result files in               |                             |      x       |
| MINIO__REGION              | Region of S3 bucket to store result files in             | us-east-1                   |              |
| MINIO__USE_SSL             | Flag for en-/disabling encrypted traffic to MinIO S3 API | 0                           |              |
| OIDC__CERTS_URL            | URL to OIDC-complaint JWKS endpoint for validating JWTs  |                             |      x       |
| OIDC__CLIENT_ID_CLAIM_NAME | JWT claim to identify authenticated requests with        | client_id                   |              |

## Note on running tests

Set up tests by copying `.env.example` into a new file called `.env.test`.
You can then execute tests by running `pytest`.
Pre-existing environment variables take precedence and will not be overwritten by the contents of `.env.test`.

OIDC does not need to be configured, since an OIDC-compatible endpoint will be spawned alongside the tests that are
being run.
A [pre-generated keypair](tests/assets/keypair.pem) is used for this purpose.
This allows all tests to generate valid JWTs as well as the service to validate them.
The keypair is for development purposes only and should not be used in a productive setting.

Some tests need to be run against live infrastructure.
Since a proper test instance is not available yet, these tests are hidden behind a flag and are not explicitly run in
CI.
To run these tests, append `-m live` to the command above.
Make sure to configure `HUB__AUTH_USERNAME` and `HUB__AUTH_PASSWORD` in your `.env.test` file before running tests.

# License

The FLAME Node Result Service is released under the Apache 2.0 license.
