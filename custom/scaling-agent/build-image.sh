#!/usr/bin/env bash

docker build . -t aphan1um/k8s-python:prod
docker push aphan1um/k8s-python:prod
