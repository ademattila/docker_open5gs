#!/usr/bin/env python3
import socket, random, string, sys

RTPENGINE_IP   = '172.22.0.16'
RTPENGINE_PORT = 2223
MEDIATION_IP   = '10.0.0.2'
MEDIATION_X3   = 9061

def ng_cookie():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def bencode(obj):
    if isinstance(obj, str): return f'{len(obj)}:{obj}'
    if isinstance(obj, int): return f'i{obj}e'
    if isinstance(obj, list): return 'l' + ''.join(bencode(i) for i in obj) + 'e'
    if isinstance(obj, dict):
        return 'd' + ''.join(bencode(k) + bencode(obj[k]) for k in sorted(obj)) + 'e'

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

def ng_send(cmd):
    cookie = ng_cookie()
    msg = f'{cookie} {bencode(cmd)}'.encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    try:
        s.sendto(msg, (RTPENGINE_IP, RTPENGINE_PORT))
        resp = s.recv(65535).decode('utf-8', errors='replace')
        bdata = resp[resp.index(' ')+1:]
        result, _ = bdecode(bdata)
        return result
    except Exception as e:
        print(f'NG error: {e}'); return None
    finally:
        s.close()

def build_answer_sdp(offer_sdp, ip, port):
    lines = []; audio_count = 0
    for line in offer_sdp.replace('\r','').split('\n'):
        if line.startswith('c='): lines.append(f'c=IN IP4 {ip}')
        elif line.startswith('m=audio'):
            parts = line.split(); parts[1] = str(port + audio_count * 2)
            lines.append(' '.join(parts)); audio_count += 1
        elif line.strip() in ('a=inactive','a=sendonly','a=recvonly'):
            lines.append('a=recvonly')
        else: lines.append(line)
    return '\r\n'.join(lines) + '\r\n'

call_id  = sys.argv[1]
from_tag = sys.argv[2] if len(sys.argv) > 2 else ''
resp = ng_send({'command':'subscribe request','call-id':call_id,'from-tag':from_tag,'flags':['all']})
if resp and resp.get('result') == 'ok':
    sdp = build_answer_sdp(resp.get('sdp',''), MEDIATION_IP, MEDIATION_X3)
    resp2 = ng_send({'command':'subscribe answer','call-id':call_id,'from-tag':from_tag,
                     'to-tag':resp.get('to-tag',''),'sdp':sdp,'flags':['allow transcoding']})
    if resp2 and resp2.get('result') == 'ok':
        print(f'X3 mirror aktif: {call_id} -> {MEDIATION_IP}:{MEDIATION_X3}')
