#!/usr/bin/env bash

# create random key, along with CSR
mkdir -p output
openssl genrsa -out output/cert.key 2048
openssl req -new -key output/cert.key -out output/cert.csr -config cert.conf -subj '/CN=pod-limit-enforcer.scaler.svc'

# create cert, signed with CA as the cert itself
openssl x509 -req -in output/cert.csr -signkey output/cert.key -out output/cert.crt -days 3650 -extensions req_ext -extfile cert.conf

echo -e '\n\n'
cat output/cert.key | base64 -w 0
echo -e '\n\n'
cat output/cert.crt | base64 -w 0
echo -e '\n\n'