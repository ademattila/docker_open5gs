#!/bin/bash
export IP_ADDR=$(awk 'END{print $1}' /etc/hosts)
cp /mnt/ueransim/${COMPONENT_NAME}.yaml /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|MNC|'$MNC'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|MCC|'$MCC'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|UE4_KI|'$UE4_KI'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|UE4_OP|'$UE4_OP'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|UE1_AMF|'$UE1_AMF'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
sed -i 's|NR_GNB_IP|'$NR_GNB_IP'|g' /UERANSIM/config/${COMPONENT_NAME}.yaml
./nr-ue -c ../config/${COMPONENT_NAME}.yaml &
exec bash $@
