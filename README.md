The FLAME Node Result Service is responsible for handling result files for federated analyses within FLAME.
It uses a local object storage to store intermediate files, as well as to enqueue files for upload to the FLAME Hub.

# Setup

You will need access to a MinIO instance and an identification provider that offers a JWKS endpoint for the access
tokens it issues.

For manual installation, you will need Python 3.10 or higher and [Poetry](https://python-poetry.org/) installed.
Clone the repository and run `poetry install` in the root directory.
Create a copy of `.env.example`, name it `.env` and configure to your needs.
Finally, use the command `flame-result` to start the service.

```
$ git clone https://github.com/PrivateAIM/node-result-service.git
$ cd node-result-service
$ poetry install
$ cp .env.example .env
$ poetry shell
$ flame-result
```

To run an ephemeral version of the Node Result Service with all services it needs pre-configured,
simply run `docker compose up -d`.
You can best explore the API by checking the documentation out at http://localhost:8080/docs.
To acquire a JWT for use with the API, [use the corresponding script](./docker/keycloak/issue-jwt.sh).
Be aware that, unless you test against your own Hub instance, the actual responses of this service will not be
very helpful.

Alternatively, if you're using
Docker, [pull a recent image from the GitHub container registry](https://github.com/PrivateAIM/node-result-service/pkgs/container/node-result-service).
Pass in the configuration options using `-e` flags and forward port 8080 from your host to the container.

```
$ docker run --rm -p 8080:8080 -e HUB__ROBOT_AUTH__ID=beepboop \
    -e HUB__ROBOT_AUTH__SECRET=super_secret \
    -e HUB__AUTH_METHOD=robot \
    -e MINIO__ENDPOINT=localhost:9000 \
    -e MINIO__ACCESS_KEY=admin \
    -e MINIO__SECRET_KEY=super_secret \
    -e MINIO__BUCKET=flame \
    -e MINIO__USE_SSL=false \
    -e POSTGRES__HOST=localhost \
    -e POSTGRES__USER=flame \
    -e POSTGRES__PASSWORD=super_secret \
    -e POSTGRES__DB=flame \
    -e OIDC__CERTS_URL="http://my.idp.org/realms/flame/protocol/openid-connect/certs" \
    ghcr.io/privateaim/node-result-service:dev-20250117T115251Z
```

# Configuration

The following table shows all available configuration options.

| **Environment variable**      | **Description**                                                                     | **Default**                    |  **Required**  |
|-------------------------------|-------------------------------------------------------------------------------------|--------------------------------|:--------------:|
| HUB__CORE_BASE_URL            | Base URL for the FLAME Core API                                                     | https://core.privateaim.net    |                |
| HUB__STORAGE_BASE_URL         | Base URL for the FLAME Storage API                                                  | https://storage.privateaim.net |                |
| HUB__AUTH_BASE_URL            | Base URL for the FLAME Auth API                                                     | https://auth.privateaim.net    |                |
| HUB__AUTH__FLOW               | Authentication flow to use for central FLAME services (`password` or `robot`)       |                                |       x        |
| HUB__AUTH__USERNAME           | Username to use for obtaining access tokens using password auth scheme              |                                | x<sup>1)</sup> |
| HUB__AUTH__PASSWORD           | Password to use for obtaining access tokens using password auth scheme              |                                | x<sup>1)</sup> |
| HUB__AUTH__ID                 | Robot ID to use for obtaining access tokens using robot credentials auth scheme     |                                | x<sup>2)</sup> |
| HUB__AUTH__SECRET             | Robot secret to use for obtaining access tokens using robot credentials auth scheme |                                | x<sup>2)</sup> |
| MINIO__ENDPOINT               | MinIO S3 API endpoint (without scheme)                                              |                                |       x        |
| MINIO__ACCESS_KEY             | Access key for interacting with MinIO S3 API                                        |                                |       x        |
| MINIO__SECRET_KEY             | Secret key for interacting with MinIO S3 API                                        |                                |       x        |
| MINIO__BUCKET                 | Name of S3 bucket to store result files in                                          |                                |       x        |
| MINIO__REGION                 | Region of S3 bucket to store result files in                                        | us-east-1                      |                |
| MINIO__USE_SSL                | Flag for en-/disabling encrypted traffic to MinIO S3 API                            | 0                              |                |
| OIDC__CERTS_URL               | URL to OIDC-complaint JWKS endpoint for validating JWTs                             |                                |       x        |
| OIDC__CLIENT_ID_CLAIM_NAME    | JWT claim to identify authenticated requests with                                   | client_id                      |                |
| POSTGRES__HOST                | Hostname of Postgres instance                                                       |                                |       x        |
| POSTGRES__PORT                | Port of Postgres instance                                                           | 5432                           |                |
| POSTGRES__USER                | Username for access to Postgres instance                                            |                                |       x        |
| POSTGRES__PASSWORD            | Password for access to Postgres instance                                            |                                |       x        |
| POSTGRES__DB                  | Database of Postgres instance                                                       |                                |       x        |
| CRYPTO__PROVIDER              | Provider for ECDH private key (`raw` or `file`)                                     |                                |       x        |
| CRYPTO__ECDH_PRIVATE_KEY      | Contents of ECDH private key file                                                   |                                | x<sup>3)</sup> |
| CRYPTO__ECDH_PRIVATE_KEY_PATH | Path to ECDH private key file                                                       |                                | x<sup>4)</sup> |

<sup>1)</sup> Only if `HUB__AUTH__FLOW` is set to `password`  
<sup>2)</sup> Only if `HUB__AUTH__FLOW` is set to `robot`  
<sup>3)</sup> Only if `CRYPTO__PROVIDER` is set to `raw`  
<sup>4)</sup> Only if `CRYPTO__PROVIDER` is set to `file`

## Note on running tests

Set up tests by copying `.env.example` into a new file called `.env.test`.
Add a line to the end of the copied file to enable the use of [testcontainers](https://testcontainers.com/).
This will automatically start up and tear down containers used only for testing.

```
$ cp .env.example .env.test
$ echo "PYTEST__USE_TESTCONTAINERS=1" >> .env.test
```

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
To run **all** tests, append `-m "live or not live"`.

The tests expect that robot **and** password credentials are provided in order to test both authentication flows.
Set `HUB__AUTH__FLOW` to `robot`, but make sure to not only set `HUB__AUTH__ID` and `HUB__AUTH__SECRET`, but also
`HUB__AUTH__USERNAME` and `HUB__AUTH__PASSWORD`.

# License

The FLAME Node Result Service is released under the Apache 2.0 license.
