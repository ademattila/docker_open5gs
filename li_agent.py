#!/usr/bin/env python3
"""
LI Agent - Tam X1/X2/X3 LI Stack
X1: REST API - hedef ekle/sil/listele (li_watchlist tablosu)
X2: SIP IRI forwarder - raw SIP olaylarını mediation'a gönderir
X3: RTPEngine subscribe - RTP mirror (li_mirror.py ile aynı mekanizma)

Kullanim:
  python3 li_agent.py --db-host 172.22.0.17 --db-pass ims_db_pass \
                      --mediation-ip 172.22.0.1 \
                      --rtpengine 172.22.0.16:2223 \
                      --listen 0.0.0.0:9091
"""

import socket, json, threading, argparse, logging, random, string, time
import mysql.connector
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import re

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('li_agent')

# ─── Config (override via args) ──────────────────────────────────────────────
DB_HOST     = '172.22.0.17'
DB_USER     = 'pyhss'
DB_PASS     = 'ims_db_pass'
DB_NAME     = 'ims_hss_db'
MEDIATION_IP   = '172.22.0.1'
MEDIATION_X2   = 2048   # HI2 - IRI (SIP events)
MEDIATION_X3   = 2049   # HI3 - CC  (RTP media)
RTPENGINE_IP   = '172.22.0.16'
RTPENGINE_PORT = 2223

# ─── DB ──────────────────────────────────────────────────────────────────────
def db_conn():
    return mysql.connector.connect(host=DB_HOST, user=DB_USER,
                                   password=DB_PASS, database=DB_NAME)

def db_get_targets():
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM li_watchlist WHERE active=1")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def db_add_target(phone_number, imsi=None, notes=None):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("""INSERT INTO li_watchlist (phone_number, imsi, notes, active)
                   VALUES (%s, %s, %s, 1)
                   ON DUPLICATE KEY UPDATE imsi=%s, notes=%s, active=1""",
                (phone_number, imsi, notes, imsi, notes))
    conn.commit(); cur.close(); conn.close()
    log.info(f'X1: Target added: {phone_number} / {imsi}')

def db_delete_target(phone_number):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("UPDATE li_watchlist SET active=0 WHERE phone_number=%s", (phone_number,))
    conn.commit(); cur.close(); conn.close()
    log.info(f'X1: Target deactivated: {phone_number}')

def db_list_targets():
    conn = db_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM li_watchlist ORDER BY created_at DESC")
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

# ─── X2/HI2 - SIP IRI Forwarder ──────────────────────────────────────────────
def send_iri(sip_message, call_id, event_type, caller=None, callee=None):
    """Raw SIP mesajını IRI wrapper ile mediation'a UDP gönderir"""
    timestamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    header = json.dumps({
        'li_iri': True,
        'version': '1.0',
        'event': event_type,       # INVITE, BYE, REGISTER, 200OK, etc.
        'call_id': call_id,
        'caller': caller or '',
        'callee': callee or '',
        'timestamp': timestamp,
        'sip_message_length': len(sip_message)
    })
    # Format: [4-byte header len][header JSON][SIP message]
    header_bytes = header.encode()
    sip_bytes = sip_message.encode() if isinstance(sip_message, str) else sip_message
    payload = len(header_bytes).to_bytes(4, 'big') + header_bytes + sip_bytes

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(payload, (MEDIATION_IP, MEDIATION_X2))
        s.close()
        log.info(f'X2/HI2: IRI sent: {event_type} {call_id} -> {MEDIATION_IP}:{MEDIATION_X2}')
    except Exception as e:
        log.error(f'X2/HI2: Send error: {e}')

# ─── X3/HI3 - RTPEngine Subscribe ────────────────────────────────────────────
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
        log.error(f'NG error: {e}'); return None
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

def start_x3_mirror(call_id, from_tag):
    log.info(f'X3/HI3: Subscribing {call_id} -> {MEDIATION_IP}:{MEDIATION_X3}')
    resp = ng_send({'command':'subscribe request','call-id':call_id,
                    'from-tag':from_tag,'flags':['all']})
    if not resp or resp.get('result') != 'ok':
        log.error(f'X3: Subscribe request failed: {resp}'); return False
    answer_sdp = build_answer_sdp(resp.get('sdp',''), MEDIATION_IP, MEDIATION_X3)
    resp2 = ng_send({'command':'subscribe answer','call-id':call_id,
                     'from-tag':from_tag,'to-tag':resp.get('to-tag',''),
                     'sdp':answer_sdp,'flags':['allow transcoding']})
    if resp2 and resp2.get('result') == 'ok':
        log.info(f'X3/HI3: Mirror aktif: {call_id} -> {MEDIATION_IP}:{MEDIATION_X3}')
        return True
    log.error(f'X3: Subscribe answer failed: {resp2}'); return False

# ─── HTTP API Handler ─────────────────────────────────────────────────────────
class LIAgentHandler(BaseHTTPRequestHandler):
    def send_json(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        # GET /x1/targets
        if self.path == '/x1/targets':
            targets = db_list_targets()
            self.send_json(200, {'targets': targets, 'count': len(targets)})
        # GET /x1/targets/active
        elif self.path == '/x1/targets/active':
            targets = db_get_targets()
            self.send_json(200, {'targets': targets, 'count': len(targets)})
        # GET /status
        elif self.path == '/status':
            self.send_json(200, {
                'status': 'ok',
                'mediation': f'{MEDIATION_IP}',
                'x2_port': MEDIATION_X2,
                'x3_port': MEDIATION_X3,
                'rtpengine': f'{RTPENGINE_IP}:{RTPENGINE_PORT}',
                'active_targets': len(db_get_targets())
            })
        else:
            self.send_json(404, {'error': 'Not found'})

    def do_POST(self):
        # POST /x1/targets  - hedef ekle
        if self.path == '/x1/targets':
            data = self.read_body()
            phone = data.get('phone_number') or data.get('msisdn')
            imsi  = data.get('imsi')
            notes = data.get('notes', 'Added via X1 API')
            if not phone:
                self.send_json(400, {'error': 'phone_number required'}); return
            db_add_target(phone, imsi, notes)
            self.send_json(201, {'result': 'ok', 'phone_number': phone, 'imsi': imsi})

        # POST /x2/iri  - P-CSCF'ten SIP IRI eventi al
        elif self.path == '/x2/iri':
            data = self.read_body()
            call_id    = data.get('call_id', '')
            event_type = data.get('event', 'UNKNOWN')
            sip_msg    = data.get('sip_message', '')
            caller     = data.get('caller', '')
            callee     = data.get('callee', '')
            threading.Thread(target=send_iri, daemon=True,
                args=(sip_msg, call_id, event_type, caller, callee)).start()
            self.send_json(200, {'result': 'ok'})

        # POST /x3/mirror  - X3 RTP mirror başlat
        elif self.path == '/x3/mirror':
            data = self.read_body()
            call_id  = data.get('call_id', '')
            from_tag = data.get('from_tag', '')
            threading.Thread(target=start_x3_mirror, daemon=True,
                args=(call_id, from_tag)).start()
            self.send_json(200, {'result': 'ok', 'call_id': call_id})

        else:
            self.send_json(404, {'error': 'Not found'})

    def do_DELETE(self):
        # DELETE /x1/targets/{msisdn}
        m = re.match(r'^/x1/targets/(.+)$', self.path)
        if m:
            phone = m.group(1)
            db_delete_target(phone)
            self.send_json(200, {'result': 'ok', 'deactivated': phone})
        else:
            self.send_json(404, {'error': 'Not found'})

    def do_PUT(self):
        # PUT /x1/targets/{msisdn}  - active toggle
        m = re.match(r'^/x1/targets/(.+)$', self.path)
        if m:
            phone = m.group(1)
            data = self.read_body()
            active = data.get('active', 1)
            conn = db_conn()
            cur = conn.cursor()
            cur.execute("UPDATE li_watchlist SET active=%s WHERE phone_number=%s", (active, phone))
            conn.commit(); cur.close(); conn.close()
            self.send_json(200, {'result': 'ok', 'phone_number': phone, 'active': active})
        else:
            self.send_json(404, {'error': 'Not found'})

    def log_message(self, format, *args):
        log.debug(f'HTTP {args[0]} {args[1]}')

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description='LI Agent - X1/X2/X3')
    p.add_argument('--db-host',      default='172.22.0.17')
    p.add_argument('--db-user',      default='pyhss')
    p.add_argument('--db-pass',      default='ims_db_pass')
    p.add_argument('--db-name',      default='ims_hss_db')
    p.add_argument('--mediation-ip', default='172.22.0.1')
    p.add_argument('--x2-port',      default=2048, type=int)
    p.add_argument('--x3-port',      default=2049, type=int)
    p.add_argument('--rtpengine',    default='172.22.0.16:2223')
    p.add_argument('--listen',       default='0.0.0.0:9091')
    a = p.parse_args()

    global DB_HOST, DB_USER, DB_PASS, DB_NAME
    global MEDIATION_IP, MEDIATION_X2, MEDIATION_X3
    global RTPENGINE_IP, RTPENGINE_PORT
    DB_HOST=a.db_host; DB_USER=a.db_user; DB_PASS=a.db_pass; DB_NAME=a.db_name
    MEDIATION_IP=a.mediation_ip; MEDIATION_X2=a.x2_port; MEDIATION_X3=a.x3_port
    rtp_ip, rtp_port = a.rtpengine.rsplit(':',1)
    RTPENGINE_IP=rtp_ip; RTPENGINE_PORT=int(rtp_port)

    listen_ip, listen_port = a.listen.rsplit(':',1)
    log.info(f'LI Agent başlıyor')
    log.info(f'  X1 REST API : http://{listen_ip}:{listen_port}')
    log.info(f'  X2 IRI      : {MEDIATION_IP}:{MEDIATION_X2} (UDP)')
    log.info(f'  X3 CC       : {MEDIATION_IP}:{MEDIATION_X3} (RTP/UDP)')
    log.info(f'  RTPEngine   : {RTPENGINE_IP}:{RTPENGINE_PORT}')
    log.info(f'  DB          : {DB_HOST}/{DB_NAME}')

    # DB bağlantı testi
    try:
        targets = db_get_targets()
        log.info(f'  Aktif hedef : {len(targets)} adet')
        for t in targets:
            log.info(f'    → {t["phone_number"]} / {t["imsi"]}')
    except Exception as e:
        log.error(f'DB bağlantı hatası: {e}')

    HTTPServer((listen_ip, int(listen_port)), LIAgentHandler).serve_forever()

if __name__ == '__main__':
    main()
