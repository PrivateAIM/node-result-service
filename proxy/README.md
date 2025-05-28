This directory contains the setup for a simple forward proxy based on OpenResty.
To run tests using this forward proxy, run `docker compose up -d` in this directory.
This will make a forward proxy available on port 3128.

To run tests against live infrastructure using the forward proxy, navigate to the root of this repository.
Run `PROXY__HTTP_URL="http://foobar:s3cr3t@localhost:3128" pytest -m live`.
You may also want to keep an eye on the logs from the forward proxy using `docker compose logs -f`.
If everything works, you should see `CONNECT` requests reaching nginx which will then forward the actual requests from the service.
