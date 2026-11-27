#! /bin/sh
# Seals the PIA login for gluetun (see deployment.yaml). Same method as build_secrets.sh: the sealed file is safe to commit.
# Asks for the username and password here, so they never appear in a file in the repo, the shell history, or the process list.
set -eu
D=$(mktemp -d)
trap 'rm -rf "$D"' EXIT
printf 'PIA username (like p1234567): '
read -r U
printf 'PIA password (not shown): '
stty -echo
read -r P
stty echo
echo
printf '%s' "$U" > "$D/OPENVPN_USER"
printf '%s' "$P" > "$D/OPENVPN_PASSWORD"
kubectl create secret generic pia-credentials \
    --namespace media-server \
    --from-file="$D/OPENVPN_USER" \
    --from-file="$D/OPENVPN_PASSWORD" \
    --dry-run=client -o json \
| kubeseal \
    --namespace media-server \
    > pia-credentials-secret.json
echo "wrote pia-credentials-secret.json"
