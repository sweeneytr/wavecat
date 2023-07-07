#! /bin/sh 
kubectl create secret generic \
    route53-credentials-secret \
    --from-file=./foundry-secrets.secret \
    --dry-run=client -o json \
| kubeseal \
    --namespace foundry \
    > foundry-secrets.json