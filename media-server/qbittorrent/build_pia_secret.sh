#! /bin/sh
# Seals the PIA login for gluetun (see deployment.yaml). Same method as build_secrets.sh: the sealed file is safe to commit.
# Asks for the username and password here, so they never appear in a file in the repo, the shell history, or the process list.
# Before sealing, it checks the login with PIA (the same token request PIA's own manual-connections scripts make), so a typo is
# caught here instead of as AUTH_FAILED in the pod. The token PIA returns is thrown away unread.
set -eu
D=$(mktemp -d)
trap 'stty echo 2>/dev/null || true; rm -rf "$D"' EXIT
printf 'PIA username (like p1234567): '
read -r U
printf 'PIA password (not shown): '
stty -echo
read -r P
stty echo
echo

# curl reads its settings from stdin, so the password is not in the process list. Backslashes and quotes are escaped for that format.
esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
CODE=$(printf 'user = "%s:%s"\n' "$(esc "$U")" "$(esc "$P")" \
    | curl -s --max-time 30 -K - -o "$D/reply" -w '%{http_code}' https://www.privateinternetaccess.com/gtoken/generateToken) || CODE=000
if [ "$CODE" = 200 ] && grep -q '"status"[[:space:]]*:[[:space:]]*"OK"' "$D/reply"; then
    echo "PIA accepted this login."
elif [ "$CODE" = 000 ]; then
    echo "Could not reach PIA to check the login (network problem). Nothing was written."
    exit 1
else
    echo "PIA rejected this login (HTTP $CODE). Nothing was written. Check the username and password on your PIA account page."
    exit 1
fi
rm -f "$D/reply"

printf '%s' "$U" > "$D/OPENVPN_USER"
printf '%s' "$P" > "$D/OPENVPN_PASSWORD"
# Set SEALED_SECRETS_CERT to the controller's public certificate to seal without reaching the cluster
# (fetch it with: k3s kubectl get --raw /api/v1/namespaces/kube-system/services/sealed-secrets-controller:8080/proxy/v1/cert.pem).
# Written to a temporary file first so a failure never leaves an empty pia-credentials-secret.json behind.
kubectl create secret generic pia-credentials \
    --namespace media-server \
    --from-file="$D/OPENVPN_USER" \
    --from-file="$D/OPENVPN_PASSWORD" \
    --dry-run=client -o json \
| kubeseal \
    --namespace media-server \
    ${SEALED_SECRETS_CERT:+--cert "$SEALED_SECRETS_CERT"} \
    > "$D/out.json"
[ -s "$D/out.json" ] || { echo "sealing failed, nothing written"; exit 1; }
mv "$D/out.json" pia-credentials-secret.json
echo "wrote pia-credentials-secret.json"
