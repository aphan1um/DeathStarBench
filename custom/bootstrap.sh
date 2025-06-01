#!/usr/bin/env bash

# setup autoscaler admission webhook
kubectl apply -f bootstrap-k8s.yaml

# create configmap storing current cpu and memory limits of microservices (scaler k8s namespace created in last step already)
./pod-limit-enforcer/bootstrap.sh
kubectl apply -f pod-limit-enforcer/k8s-spec.yaml

# install prometheus and grafana stack
helm repo add \
  prometheus-community \
  https://prometheus-community.github.io/helm-charts

helm install --debug prometheus \
  prometheus-community/kube-prometheus-stack \
  --create-namespace \
  --namespace monitor \
  --set alertmanager.enabled=false \
  --set prometheus.prometheusSpec.scrapeInterval=10s

kubectl apply -f bootstrap-k8s-prometheus.yaml
