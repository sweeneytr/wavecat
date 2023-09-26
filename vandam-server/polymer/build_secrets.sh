#! /bin/sh 
cat ./polymer-secrets.secret \
| kubeseal \
    --namespace vandam-server \
    > polymer-secrets.json