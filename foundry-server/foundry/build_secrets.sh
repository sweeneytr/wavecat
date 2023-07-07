#! /bin/sh 
kubectl create secret generic \
    foundry-secrets \
    --from-file=./foundry-secrets.secret \
    --dry-run=client -o json \
| kubeseal \
    --namespace foundry \
    > foundry-secrets.json