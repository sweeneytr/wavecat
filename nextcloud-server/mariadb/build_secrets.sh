#! /bin/sh
# Usage: ./build_secrets.sh <file holding the MariaDB root password> <file holding the nextcloud database user's password>
# Seals them as mariadb-credentials (namespace nextcloud-server). The image reads these only when it first creates the database:
# to rotate, change the passwords with ALTER USER and in Nextcloud's config.php (dbpassword) first, then reseal so a rebuild matches.
set -e
kubectl create secret generic mariadb-credentials \
    --namespace nextcloud-server \
    --from-file=MYSQL_ROOT_PASSWORD="$1" \
    --from-file=MYSQL_PASSWORD="$2" \
    --dry-run=client -o json \
| kubeseal --controller-name sealed-secrets-controller --controller-namespace kube-system \
    > mariadb-credentials-secret.json
