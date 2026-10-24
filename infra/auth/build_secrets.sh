#! /bin/sh
# Usage: ./build_secrets.sh <file with the Google OAuth client id on line 1 and the secret on line 2>
# The oauth2-proxy client secret and cookie secret are generated here and never stored in plaintext.
set -e
GOOGLE_CLIENT_ID=$(sed -n 1p "$1")
GOOGLE_CLIENT_SECRET=$(sed -n 2p "$1")
PROXY_SECRET=$(openssl rand -hex 24)
COOKIE_SECRET=$(openssl rand -hex 16)

kubectl create secret generic dex-secrets \
    --namespace auth \
    --from-literal=GOOGLE_CLIENT_ID="$GOOGLE_CLIENT_ID" \
    --from-literal=GOOGLE_CLIENT_SECRET="$GOOGLE_CLIENT_SECRET" \
    --from-literal=OAUTH2_PROXY_CLIENT_SECRET="$PROXY_SECRET" \
    --dry-run=client -o json \
| kubeseal --controller-name sealed-secrets-controller --controller-namespace kube-system \
    > dex-secrets.json

kubectl create secret generic oauth2-proxy-secrets \
    --namespace auth \
    --from-literal=client-id=oauth2-proxy \
    --from-literal=client-secret="$PROXY_SECRET" \
    --from-literal=cookie-secret="$COOKIE_SECRET" \
    --dry-run=client -o json \
| kubeseal --controller-name sealed-secrets-controller --controller-namespace kube-system \
    > oauth2-proxy-secrets.json
