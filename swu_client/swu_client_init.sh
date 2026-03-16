#!/bin/bash
sleep 2
cd /SWu-IKEv2
python3 swu_emulator.py \
    --imsi=001010000000001 \
    --ki=465B5CE8B199B49FAA5F0A2EE238A6BC \
    --opc=E8ED289DEBA952E4283B54E88E6183CA \
    --dest=172.22.0.41 \
    --source=172.22.0.42 \
    --apn=internet \
    --mcc=001 \
    --mnc=001
