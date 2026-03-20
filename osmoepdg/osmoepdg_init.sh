#!/bin/bash

[ ${#MNC} == 3 ] && EPC_DOMAIN="epc.mnc${MNC}.mcc${MCC}.3gppnetwork.org" || EPC_DOMAIN="epc.mnc0${MNC}.mcc${MCC}.3gppnetwork.org"

mkdir -p /usr/local/etc/swanctl
mkdir -p /usr/local/etc/strongswan.d
mkdir -p /usr/local/etc/strongswan.d/charon
mkdir -p /etc/osmocom
mkdir -p /wireshark_keys
cp /mnt/osmoepdg/osmo-epdg.config /etc/osmocom
cp /mnt/osmoepdg/swanctl/swanctl.conf /etc/swanctl/swanctl.conf
cp /mnt/osmoepdg/strongswan.d/charon/kernel-netlink.conf /etc/strongswan.d/charon/kernel-netlink.conf
cp /mnt/osmoepdg/strongswan.d/charon.conf /etc/strongswan.d/charon.conf
cp /mnt/osmoepdg/eap-aka.conf /etc/strongswan.d/charon/eap-aka.conf
cp /mnt/osmoepdg/save-keys.conf /etc/strongswan.d/charon/save-keys.conf

OSMOEPDG_COMMA_SEPARATED_IP="${OSMOEPDG_IP//./,}"

export COMPONENT_NAME=osmoepdg
export IPSEC_TRAFFIC_FWMARK=2
export GTP_TRAFFIC_FWMARK=4
export EPDG_TUN_INTERFACE=gtp0
export EPDG_ROUTING_TABLE_NUMBER=2
export EPDG_ROUTING_TABLE_NAME=epdg

sed -i 's|OSMOEPDG_IP|'$OSMOEPDG_IP'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|OSMOEPDG_COMMA_SEPARATED_IP|'$OSMOEPDG_COMMA_SEPARATED_IP'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|HSS_IP|'$PYHSS_IP'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|EPC_DOMAIN|'$EPC_DOMAIN'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|SMF_IP|'$SMF_IP'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|EPDG_TUN_INTERFACE|'$EPDG_TUN_INTERFACE'|g' /etc/osmocom/osmo-epdg.config
sed -i 's|GTP_TRAFFIC_FWMARK|'$GTP_TRAFFIC_FWMARK'|g' /etc/strongswan.d/charon/kernel-netlink.conf
sed -i 's|GTP_TRAFFIC_FWMARK|'$GTP_TRAFFIC_FWMARK'|g' /etc/swanctl/swanctl.conf
sed -i 's|OSMOEPDG_IP|'$OSMOEPDG_IP'|g' /etc/swanctl/swanctl.conf
sed -i 's|IPSEC_TRAFFIC_FWMARK|'$IPSEC_TRAFFIC_FWMARK'|g' /etc/swanctl/swanctl.conf

mkdir -p /mnt/osmoepdg/log
cat /dev/null > /mnt/osmoepdg/log/console.log
cat /dev/null > /mnt/osmoepdg/log/error.log
cat /dev/null > /mnt/osmoepdg/log/erlang.log
cat /dev/null > /mnt/osmoepdg/log/crash.log

# Create routing table entry
grep -qE "^${EPDG_ROUTING_TABLE_NUMBER} ${EPDG_ROUTING_TABLE_NAME}$" /etc/iproute2/rt_tables || \
    echo "${EPDG_ROUTING_TABLE_NUMBER} ${EPDG_ROUTING_TABLE_NAME}" >> /etc/iproute2/rt_tables

# Configure ipsec fwmark (nft)
cp /mnt/osmoepdg/nftables.conf /etc/nftables.conf
sed -i 's|EPDG_TUN_INTERFACE|'$EPDG_TUN_INTERFACE'|g' /etc/nftables.conf
sed -i 's|GTP_TRAFFIC_FWMARK|'$GTP_TRAFFIC_FWMARK'|g' /etc/nftables.conf
sed -i 's|IPSEC_TRAFFIC_FWMARK|'$IPSEC_TRAFFIC_FWMARK'|g' /etc/nftables.conf
nft -f /etc/nftables.conf

# Start osmo-epdg FIRST
cd /mnt/osmoepdg
export ERL_FLAGS="-config /etc/osmocom/osmo-epdg.config"
/osmo-epdg/_build/default/bin/osmo-epdg &

# Wait for GSUP port to be ready
echo "Waiting for GSUP port 4222..."
for i in $(seq 1 30); do
    bash -c "echo > /dev/tcp/127.0.0.1/4222" 2>/dev/null && echo "GSUP ready!" && break
    sleep 1
done

# Start strongSwan AFTER osmo-epdg is ready
ipsec start --nofork &

sleep 3
chmod 660 /var/run/charon.vici
swanctl --load-all

# Start configuration script
/mnt/osmoepdg/configure_interface.sh &

# Keep container alive
wait
