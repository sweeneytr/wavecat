#! /bin/sh
# Usage: ./build_secrets.sh <hosted zone id> <access key id> <file holding the secret access key>
# Seals ddns-updater's CONFIG (namespace ddns). The IAM policy for the key is policy.json.
set -e
CONFIG=$(python3 -c '
import json, sys
# The apex record, which the *.wavecat.net wildcard CNAME follows, and the separate plex record.
secret = open(sys.argv[3]).read().strip()
print(json.dumps({"settings": [
    {"provider": "route53", "domain": d, "ip_version": "ipv4", "ttl": 60,
     "zone_id": sys.argv[1], "access_key": sys.argv[2], "secret_key": secret}
    for d in ("wavecat.net", "plex.wavecat.net")]}))
' "$1" "$2" "$3")

kubectl create secret generic ddns-updater \
    --namespace ddns \
    --from-literal=CONFIG="$CONFIG" \
    --dry-run=client -o json \
| kubeseal --controller-name sealed-secrets-controller --controller-namespace kube-system \
    > route53-ddns-secret.json
