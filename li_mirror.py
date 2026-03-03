#!/usr/bin/env python3
import socket, json, threading, argparse, logging, random, string
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('li_mirror')

def ng_cookie():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def bencode(obj):
    if isinstance(obj, str): return f'{len(obj)}:{obj}'
    if isinstance(obj, int): return f'i{obj}e'
    if isinstance(obj, list): return 'l' + ''.join(bencode(i) for i in obj) + 'e'
    if isinstance(obj, dict):
        return 'd' + ''.join(bencode(k) + bencode(obj[k]) for k in sorted(obj)) + 'e'
    return ''

def bdecode(data, idx=0):
    if isinstance(data, bytes): data = data.decode('utf-8', errors='replace')
    c = data[idx]
    if c == 'd':
        idx += 1; d = {}
        while data[idx] != 'e':
            key, idx = bdecode(data, idx); val, idx = bdecode(data, idx); d[key] = val
        return d, idx + 1
    if c == 'l':
        idx += 1; lst = []
        while data[idx] != 'e':
            val, idx = bdecode(data, idx); lst.append(val)
        return lst, idx + 1
    if c == 'i':
        end = data.index('e', idx); return int(data[idx+1:end]), end + 1
    if c.isdigit():
        colon = data.index(':', idx); length = int(data[idx:colon]); start = colon + 1
        return data[start:start+length], start + length

def ng_send(ip, port, cmd):
    cookie = ng_cookie()
    msg = f'{cookie} {bencode(cmd)}'.encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(msg, (ip, port))
        resp = s.recv(65535).decode('utf-8', errors='replace')
        bdata = resp[resp.index(' ')+1:]
        result, _ = bdecode(bdata)
        return result
    except Exception as e:
        log.error(f'NG error: {e}'); return None
    finally:
        s.close()

def build_answer_sdp(offer_sdp, ip, port):
    """Her m=audio stream'i için ayrı artan port kullan"""
    lines = []
    audio_count = 0
    for line in offer_sdp.replace('\r','').split('\n'):
        if line.startswith('c='):
            lines.append(f'c=IN IP4 {ip}')
        elif line.startswith('m=audio'):
            parts = line.split()
            parts[1] = str(port + audio_count * 2)  # her stream için +2 port
            # sendonly/inactive -> recvonly yapma, sadece port set et
            lines.append(' '.join(parts))
            audio_count += 1
        elif line.strip() in ('a=inactive', 'a=sendonly', 'a=recvonly'):
            lines.append('a=recvonly')
        else:
            lines.append(line)
    sdp = '\r\n'.join(lines) + '\r\n'
    log.info(f'Answer SDP ({audio_count} streams):\n{sdp}')
    return sdp

def do_subscribe(rtp_ip, rtp_port, med_ip, med_port, call_id, from_tag):
    log.info(f'Subscribing: {call_id} -> {med_ip}:{med_port}')
    resp = ng_send(rtp_ip, rtp_port, {
        'command': 'subscribe request',
        'call-id': call_id,
        'from-tag': from_tag,
        'flags': ['all']
    })
    log.info(f'Subscribe request: {resp}')
    if not resp or resp.get('result') != 'ok':
        log.error(f'Failed: {resp}'); return False

    offer_sdp = resp.get('sdp', '')
    sub_to_tag = resp.get('to-tag', '')
    answer_sdp = build_answer_sdp(offer_sdp, med_ip, med_port)

    resp2 = ng_send(rtp_ip, rtp_port, {
        'command': 'subscribe answer',
        'call-id': call_id,
        'from-tag': from_tag,
        'to-tag': sub_to_tag,
        'sdp': answer_sdp,
        'flags': ['allow transcoding']
    })
    log.info(f'Subscribe answer: {resp2}')
    if resp2 and resp2.get('result') == 'ok':
        log.info(f'Mirror aktif: {call_id} -> {med_ip}:{med_port}'); return True
    log.error(f'Failed: {resp2}'); return False

RTPENGINE_IP='172.22.0.16'; RTPENGINE_PORT=2223
MEDIATION_IP='172.22.0.1'; MEDIATION_PORT=2049

class LIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/li': self.send_response(404); self.end_headers(); return
        length = int(self.headers.get('Content-Length', 0))
        data = json.loads(self.rfile.read(length))
        threading.Thread(target=do_subscribe, daemon=True,
            args=(RTPENGINE_IP, RTPENGINE_PORT, MEDIATION_IP, MEDIATION_PORT,
                  data.get('call_id',''), data.get('from_tag',''))).start()
        self.send_response(200); self.end_headers(); self.wfile.write(b'OK')
    def log_message(self, *a): pass

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--rtpengine', default='172.22.0.16:2223')
    p.add_argument('--mediation', default='172.22.0.1:2049')
    p.add_argument('--listen', default='0.0.0.0:9090')
    p.add_argument('--call-id')
    p.add_argument('--from-tag', default='')
    a = p.parse_args()
    rtp_ip, rtp_port = a.rtpengine.rsplit(':',1)
    med_ip, med_port = a.mediation.rsplit(':',1)
    global RTPENGINE_IP, RTPENGINE_PORT, MEDIATION_IP, MEDIATION_PORT
    RTPENGINE_IP=rtp_ip; RTPENGINE_PORT=int(rtp_port)
    MEDIATION_IP=med_ip; MEDIATION_PORT=int(med_port)
    if a.call_id:
        do_subscribe(rtp_ip, int(rtp_port), med_ip, int(med_port), a.call_id, a.from_tag)
        return
    log.info(f'Daemon | RTPEngine:{rtp_ip}:{rtp_port} | Mediation:{med_ip}:{med_port}')
    HTTPServer((a.listen.rsplit(':',1)[0], int(a.listen.rsplit(':',1)[1])), LIHandler).serve_forever()

if __name__ == '__main__':
    main()
