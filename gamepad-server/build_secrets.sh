#! /bin/sh 

if [ -z "$1" ]
  then
    echo "No argument supplied"
fi

if [ -z "$2" ]
  then
    echo "No argument supplied"
fi

cat << EOF > ghcr.secret
{
    "auths":
    {
        "ghcr.io":
            {
                "auth":"$(echo $1 | base64)"
            }
    }
}
EOF

kubectl create secret docker-registry \
    ghcr-secret --docker-server=https://ghcr.io \
    --namespace gamepad-server \
    --docker-server=https://ghcr.io \
    --docker-username="$1" \
    --docker-password="$2" \
    --dry-run=client -o json | kubeseal \
    --namespace gamepad-server \
    > ghcr-secret.json