#! /bin/sh 
kubectl create secret generic \
    route53-credentials-secret \
    --from-file=secret-access-key=./aws-secret-key.secret \
    --dry-run=client -o json \
| kubeseal \
    --namespace cert-manager \
    > route53-credentials-secret.json