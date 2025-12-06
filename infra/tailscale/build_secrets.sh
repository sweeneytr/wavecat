#! /bin/sh 
kubectl create secret generic operator-oauth \
  --dry-run=client --namespace=tailscale \
  --from-literal=client_id=$1 --from-literal=client_secret=$2 \
  -o json > ./operator-oauth.secret
cat ./operator-oauth.secret \
| kubeseal \
    --namespace tailscale \
    > operator-oauth.json