#!/bin/bash
set -euxo pipefail
exec > /var/log/openvpn-relay-startup.log 2>&1

MARKER=/root/.openvpn-relay-startup-done
if [ -f "$MARKER" ]; then
  echo "Startup script already completed, skipping."
  exit 0
fi

EXTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")

cd /root
curl -o openvpn-install.sh https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh
chmod +x openvpn-install.sh

./openvpn-install.sh install \
  --endpoint "$EXTERNAL_IP" \
  --port 1194 \
  --protocol udp \
  --client-to-client \
  --client nas \
  --dns cloudflare

./openvpn-install.sh client add demo-laptop --output /root/demo-laptop.ovpn

chmod 644 /root/nas.ovpn /root/demo-laptop.ovpn
touch "$MARKER"
