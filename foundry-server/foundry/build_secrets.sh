#! /bin/sh 
cat ./foundry-secrets.secret \
| kubeseal \
    --namespace foundry-server \
    > foundry-secrets.json