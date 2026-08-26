#!/bin/bash
set -euxo pipefail
exec > /var/log/openvpn-relay-startup.log 2>&1

MARKER=/root/.openvpn-relay-startup-done

EXTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")

# Only the OpenVPN install itself is one-time - the marker used to guard the whole script and
# `exit 0` before reaching this point, which meant nothing below it (including the DNS update)
# ever ran again after the VM's first boot, since the marker persists on the boot disk across
# stop/start cycles (the disk isn't recreated). The DNS update below must run every boot, since
# the external IP is ephemeral and changes on every start.
if [ -f "$MARKER" ]; then
  echo "OpenVPN already installed, skipping install."
else

cd /root
curl -o openvpn-install.sh https://raw.githubusercontent.com/angristan/openvpn-install/master/openvpn-install.sh
chmod +x openvpn-install.sh

# --tls-sig crypt (static key) instead of the default crypt-v2 (per-session dynamic key):
# QNAP QVPN Service Center's OpenVPN client fails to renegotiate crypt-v2 on its automatic
# ping-restart reconnect ("TLS Error: could not determine wrapping"), forcing a manual
# disconnect/reconnect in the QTS UI every ~4 minutes. The static key has no such renegotiation
# step, so QNAP's client reconnects on its own. Verified live 2026-08-25.
#
# --endpoint is the stable Cloud DNS hostname, not $EXTERNAL_IP - it's baked verbatim into
# /etc/openvpn/server/client-template.txt and reused for every client generated from this server
# from now on (including ones added later by hand via `client add`), so using the ephemeral IP
# here would silently defeat the whole point of the DNS work below: every .ovpn would still need
# regenerating on every restart.
./openvpn-install.sh install \
  --endpoint vpn.gcloud.lenie-ai.eu \
  --port 1194 \
  --protocol udp \
  --client-to-client \
  --tls-sig crypt \
  --client nas \
  --dns cloudflare

./openvpn-install.sh client add demo-laptop --output /root/demo-laptop.ovpn

# 192.168.200.0/24 (the NAS's LAN) sits behind the "nas" client, not behind this server, so the
# installer's --local-network flag (for networks behind the server) doesn't apply. Wire it as a
# per-client route: ccd/iroute tells the server which client owns that subnet, and the matching
# `route` in server.conf adds it to the server's routing table. push-reset stops this specific
# client from receiving the server's default full-tunnel push (redirect-gateway/DNS/block-ipv6),
# so the NAS keeps its own default internet gateway instead of routing all its traffic via GCP.
cat >/etc/openvpn/server/ccd/nas <<'EOF'
iroute 192.168.200.0 255.255.255.0
push-reset
EOF
echo 'route 192.168.200.0 255.255.255.0' >>/etc/openvpn/server/server.conf

# The installer's firewall script rejects VPN clients reaching any RFC1918 range, including the
# NAS's own subnet — carve out an exception. Edit the persisted script (so the exception survives
# a reboot's iptables-openvpn re-apply) and mirror it into the live table for this boot; look up
# the REJECT rule's position instead of hardcoding one, since the script's own rule count can
# change between openvpn-install versions.
sed -i '/-d 192\.168\.0\.0\/16 -j REJECT/i iptables -I OPENVPN_INSTALL_FORWARD 7 -d 192.168.200.0/24 -j ACCEPT' /etc/iptables/add-openvpn-rules.sh
REJECT_LINE=$(iptables -L OPENVPN_INSTALL_FORWARD -n --line-numbers | awk '/192\.168\.0\.0\/16/{print $1; exit}')
iptables -I OPENVPN_INSTALL_FORWARD "$REJECT_LINE" -d 192.168.200.0/24 -j ACCEPT

systemctl restart openvpn-server@server

chmod 644 /root/nas.ovpn /root/demo-laptop.ovpn
touch "$MARKER"

fi

# Keep the hostname current with the ephemeral IP - runs every boot (unlike the OpenVPN
# install above), since a new IP is assigned each time the VM starts. Authenticates via the
# service account attached to this VM (roles/dns.admin scoped to this one zone, see dns.tf) -
# no credentials stored on the instance.
if ! command -v gcloud &>/dev/null; then
  curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    >/etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update -qq
  apt-get install -y -qq google-cloud-cli
fi

DNS_ZONE=gcloud-lenie-ai-eu
DNS_RECORD=vpn.gcloud.lenie-ai.eu.
DNS_TTL=60

if gcloud dns record-sets describe "$DNS_RECORD" --zone="$DNS_ZONE" --type=A &>/dev/null; then
  gcloud dns record-sets update "$DNS_RECORD" --zone="$DNS_ZONE" --type=A --ttl="$DNS_TTL" --rrdatas="$EXTERNAL_IP"
else
  gcloud dns record-sets create "$DNS_RECORD" --zone="$DNS_ZONE" --type=A --ttl="$DNS_TTL" --rrdatas="$EXTERNAL_IP"
fi
