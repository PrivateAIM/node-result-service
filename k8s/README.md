# Kubernetes deployment

This directory contains files for setting up the Node Result Service in a k8s cluster.
Make sure you have a k8s cluster running and accessible, e.g. by
installing [minikube](https://minikube.sigs.k8s.io/docs/) on your local
machine.

## Secret setup to pull from ghcr.io

Container images will be pulled from the GitHub container registry.
You will need to provide the login credentials as a secret to k8s.
[Follow the GitHub documentation on acquiring a personal access token.](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-to-the-container-registry)

To save yourself some work, you'll find a script which generates the configuration file to correctly provision the
access token to your k8s instance in this directory.
Simply run the following commands.

```
$ ./generate-k8s-secret-yaml.sh "<GitHub username>" "<GitHub access token>" > ghcr-secret.yaml
$ kubectl apply -f ghcr-secret.yaml
```

**It is highly encouraged to delete the resulting YAML file afterwards since it contains your access token in
(obfuscated) plain text.**

## Deploy to k8s

To deploy, simply run the following commands.

```
$ kubectl apply -f ./node-result-deployment.yaml
$ kubectl apply -f ./node-result-service.yaml
```
