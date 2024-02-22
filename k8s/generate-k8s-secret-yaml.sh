#!/bin/sh
if [ "$#" -ne 2 ]; then
  echo "usage: $0 github_username github_access_token"
  exit 1
fi

B64_BASIC_AUTH=$(printf "%s:%s" "$1" "$2" | base64 -w0)
B64_DOCKER_CONFIG_JSON=$(printf '{"auths": {"ghcr.io": {"auth": "%s"}}}' "$B64_BASIC_AUTH" | base64 -w0)

cat <<EOF
kind: Secret
type: kubernetes.io/dockerconfigjson
apiVersion: v1
metadata:
  name: dockerconfigjson-github-com
data:
  .dockerconfigjson: $B64_DOCKER_CONFIG_JSON
EOF
