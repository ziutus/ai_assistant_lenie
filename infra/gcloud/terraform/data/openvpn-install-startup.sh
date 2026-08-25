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

# --tls-sig crypt (static key) instead of the default crypt-v2 (per-session dynamic key):
# QNAP QVPN Service Center's OpenVPN client fails to renegotiate crypt-v2 on its automatic
# ping-restart reconnect ("TLS Error: could not determine wrapping"), forcing a manual
# disconnect/reconnect in the QTS UI every ~4 minutes. The static key has no such renegotiation
# step, so QNAP's client reconnects on its own. Verified live 2026-08-25.
./openvpn-install.sh install \
  --endpoint "$EXTERNAL_IP" \
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
