# Kubernetes deployment

This directory contains files for setting up the Node Result Service in a k8s cluster.
Make sure you have a k8s cluster running and accessible, e.g. by
installing [minikube](https://minikube.sigs.k8s.io/docs/) on your local
machine.

To deploy, simply run the following commands.

```
$ kubectl apply -f ./minio-deployment.yaml
$ kubectl apply -f ./minio-service.yaml
$ kubectl apply -f ./node-result-deployment.yaml
$ kubectl apply -f ./node-result-service.yaml
```
