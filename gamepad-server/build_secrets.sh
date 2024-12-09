#! /bin/sh 

if [ -z "$1" ]
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

kubectl create secret generic \
    ghcr-secret \
    --from-file=.dockerconfigjson=./ghcr.secret \
    --dry-run=client -o json \
| kubeseal \
    --namespace gamepad-server \
    > ghcr-secret.json