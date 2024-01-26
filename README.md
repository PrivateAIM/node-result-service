# Node Result Service

```
$ flame-result server --reload
```

## Running tests

Integration tests require a MinIO instance.
Configuration is passed in using environment variables.
The names are the same, except they are prepended with `PYTEST__`.
At least, the MinIO endpoint, access key, secret key and bucket name need to be provided.
If unspecified, the region is set to `us-east-1` and HTTPS is disabled.

```
$ PYTEST__MINIO__ENDPOINT="localhost:9000" \
    PYTEST__MINIO__ACCESS_KEY="admin" \
    PYTEST__MINIO__SECRET_KEY="s3cr3t_p4ssw0rd" \
    PYTEST__MINIO__BUCKET="flame" pytest
```

OIDC does not need to be configured.
Running integration tests will spawn a minimal webserver that provides an OIDC-compliant JWKS endpoint.
A [pre-generated keypair](tests/assets/keypair.pem) is used for this purpose.
This allows all tests to generate valid JWTs as well as the service to validate them.
The keypair is for development purposes only and should not be used in a productive setting.
