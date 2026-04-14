#!/bin/bash
sleep 2
[ ${#MNC} == 3 ] && THREE_DIGIT_MNC="${MNC}" || THREE_DIGIT_MNC="0${MNC}"
cp /mnt/swu_client2/swu_emulator.py /SWu-IKEv2/swu_emulator.py

cd /SWu-IKEv2

python3 swu_emulator.py \
    --imsi=$UE1_IMSI \
    --ki=$UE1_KI \
    --op=$UE1_OP \
    --dest=$OSMOEPDG_IP \
    --source=$SWU_CLIENT_IP \
    --apn=$SWU_CLIENT_APN \
    --mcc=$MCC \
    --mnc=$THREE_DIGIT_MNC &

echo "Waiting for tunnel..."
for i in $(seq 1 30); do
    ip addr show tun1 2>/dev/null | grep "192.168" && echo "Tunnel up!" && break
    sleep 2
done

TUN_IP=$(ip addr show tun1 2>/dev/null | grep "inet " | awk '{print $2}' | cut -d/ -f1)
echo "Tunnel IP: $TUN_IP"

DOMAIN="ims.mnc${THREE_DIGIT_MNC}.mcc${MCC}.3gppnetwork.org"
MSISDN="0000000009"

sipp ${PCSCF_IP}:5060 \
    -sf /mnt/swu_client2/register_auth.xml \
    -m 1 -l 1 \
    -i $TUN_IP \
    -p 5060 \
    -trace_msg

wait
