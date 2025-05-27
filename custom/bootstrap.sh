#!/usr/bin/env bash

# setup autoscaler admission webhook
kubectl apply -f scaler-ns.yaml
kubectl apply -f admin-rbac.yaml

# create configmap storing current cpu and memory limits of microservices (scaler k8s namespace created in last step already)
./custom/pod-limit-enforcer/bootstrap.sh
kubectl apply -f pod-limit-enforcer/k8s-spec

# install prometheus and grafana stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install prometheus \
  prometheus-community/kube-prometheus-stack \
  --create-namespace \
  --namespace monitor \
  --set alertmanager.enabled=false


# kube-prometheus-stack has been installed. Check its status by running:
#   kubectl --namespace monitor get pods -l "release=prometheus"

# Get Grafana 'admin' user password by running:

#   kubectl --namespace monitor get secrets prometheus-grafana -o jsonpath="{.data.admin-password}" | base64 -d ; echo

# Access Grafana local instance:

# export POD_NAME=$(kubectl --namespace monitor get pod -l "app.kubernetes.io/name=grafana,app.kubernetes.io/instance=prometheus" -oname)
# kubectl --namespace monitor port-forward $POD_NAME 3000

# export POD_NAME=$(kubectl --namespace monitor get pod -l "app.kubernetes.io/name=prometheus,app.kubernetes.io/instance=prometheus-kube-prometheus-prometheus" -oname)
# kubectl --namespace monitor port-forward $POD_NAME 9090
