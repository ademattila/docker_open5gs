#!/bin/bash
# LI Test Script - UE1 "Alo" UE2 "Efendim" ses simülasyonu

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== LI Ses Testi Başlatılıyor ===${NC}"

# 1. li_agent çalışıyor mu?
if ! ps aux | grep -q "[l]i_agent.py"; then
    echo -e "${RED}[!] li_agent çalışmıyor, başlatılıyor...${NC}"
    pkill -f li_agent.py 2>/dev/null; sleep 1
    python3 ~/docker_open5gs/li_agent.py \
        --mediation-ip 10.0.0.2 \
        --x2-port 9060 \
        --x3-port 9061 \
        --rtpengine 172.22.0.16:2223 \
        --listen 172.22.0.1:9091 >> /tmp/li_agent.log 2>&1 &
    sleep 2
fi
echo -e "${GREEN}[✓] li_agent çalışıyor${NC}"

# 2. X2/X3 trafik izleme başlat
echo -e "${YELLOW}[*] X2/X3 trafik izleme başlatılıyor...${NC}"
> /tmp/x2_traffic.log
> /tmp/x3_traffic.log
sudo tcpdump -i any -nn "tcp and host 10.0.0.2 and port 9060" > /tmp/x2_traffic.log 2>/dev/null &
TCPDUMP_X2=$!
sudo tcpdump -i any -nn "udp and host 10.0.0.2 and port 9061" > /tmp/x3_traffic.log 2>/dev/null &
TCPDUMP_X3=$!

# 3. UE2 UAS başlat
echo -e "${YELLOW}[*] UE2 dinlemeye alınıyor...${NC}"
docker exec -d nr_ue2 sipp -sn uas \
    -sf /tmp/uas_rtp_li.xml \
    -i 172.22.0.25 -p 5060 -t t1 -m 1 \
    -mp 7000
sleep 2
echo -e "${GREEN}[✓] UE2 hazır (efendim.pcmu)${NC}"

# 4. UE1 çağrı başlat
echo -e "${YELLOW}[*] UE1 -> UE2 çağrı başlatılıyor (alo.pcmu)...${NC}"
docker exec nr_ue sipp 172.22.0.21:5060 \
    -sf /tmp/invite_rtp_li.xml -m 1 -l 1 \
    -i 172.22.0.24 -p 5060 -mp 6000 \
    -trace_msg -message_file /tmp/sipp_msg.log 2>/dev/null
echo -e "${GREEN}[✓] Çağrı tamamlandı${NC}"

sleep 2

# 5. tcpdump durdur
kill $TCPDUMP_X2 $TCPDUMP_X3 2>/dev/null
sleep 1

# 6. Sonuçları göster
echo ""
echo -e "${YELLOW}=== SONUÇLAR ===${NC}"

X2_COUNT=$(wc -l < /tmp/x2_traffic.log)
if [ "$X2_COUNT" -gt 0 ]; then
    echo -e "${GREEN}[✓] X2 (IRI/SIP) → 10.0.0.2:9060 TCP: $X2_COUNT paket${NC}"
else
    echo -e "${RED}[✗] X2 trafik yok${NC}"
fi

X3_COUNT=$(wc -l < /tmp/x3_traffic.log)
if [ "$X3_COUNT" -gt 0 ]; then
    echo -e "${GREEN}[✓] X3 (RTP fork) → 10.0.0.2:9061 UDP: $X3_COUNT paket${NC}"
else
    echo -e "${RED}[✗] X3 trafik yok${NC}"
fi

echo ""
echo -e "${YELLOW}=== li_agent Son Loglar ===${NC}"
tail -10 /tmp/li_agent.log

echo ""
echo -e "${YELLOW}=== WAV Kayıtları ===${NC}"
ls -lht ~/docker_open5gs/rtpengine/recordings/*.wav 2>/dev/null | head -3 || echo "WAV dosyası yok"

echo ""
echo -e "${GREEN}=== Test Tamamlandı ===${NC}"
