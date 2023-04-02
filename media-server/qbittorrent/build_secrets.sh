#! /bin/sh 
kubectl create secret generic \
    wireguard-config-secret \
    --from-file=wg0.conf=./wg0.conf.secret \
    --dry-run=client -o json \
| kubeseal \
    --namespace media-server \
    > wireguard-config-secret.json