#!/bin/bash
sleep 2
[ ${#MNC} == 3 ] && THREE_DIGIT_MNC="${MNC}" || THREE_DIGIT_MNC="0${MNC}"
cp /mnt/swu_client/swu_emulator.py /SWu-IKEv2/swu_emulator.py
cd /SWu-IKEv2
python3 swu_emulator.py \
    --imsi=$UE1_IMSI \
    --ki=$UE1_KI \
    --opc=$UE1_OPC \
    --dest=$OSMOEPDG_IP \
    --source=$SWU_CLIENT_IP \
    --apn=$SWU_CLIENT_APN \
    --mcc=$MCC \
    --mnc=$THREE_DIGIT_MNC
