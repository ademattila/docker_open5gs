import sys

with open('/tmp/diameter.py', 'r') as f:
    content = f.read()

# ── 1. Routing tablosuna SWx MAR (303) ekle ──────────────────────────────────
old_routing = '{"commandCode": 8388622, "applicationId": 16777291, "responseMethod": self.Answer_16777291_8388622, "failureResultCode": 4100 ,"requestAcronym": "LRR", "responseAcronym": "LRA", "requestName": "LCS Routing Info Request", "responseName": "LCS Routing Info Answer"},'
new_routing = old_routing + '\n                {"commandCode": 303, "applicationId": 16777265, "responseMethod": self.Answer_16777265_303, "failureResultCode": 4100 ,"requestAcronym": "MAR", "responseAcronym": "MAA", "requestName": "Multimedia Authentication Request", "responseName": "Multimedia Authentication Answer"},'

if old_routing not in content:
    print("ERROR: routing table anchor not found!")
    sys.exit(1)

content = content.replace(old_routing, new_routing, 1)
print("Step 1 OK: routing table updated")

# ── 2. Answer_16777265_303 handler ekle (PUA'dan önce) ───────────────────────
swx_handler = '''
    #Multimedia Authentication Answer - SWx (MAA) - 3GPP TS 29.273
    def Answer_16777265_303(self, packet_vars, avps):
        self.logTool.log(service='HSS', level='debug', message=f"[diameter.py] [Answer_16777265_303] [MAA] SWx MAR received", redisClient=self.redisMessaging)

        session_id = self.get_avp_data(avps, 263)[0]                                               #Get Session-ID

        def error_response(result_code, experimental=False, exp_code=None):
            avp = ''
            avp += self.generate_avp(263, 40, session_id)
            avp += self.generate_avp(264, 40, self.OriginHost)
            avp += self.generate_avp(296, 40, self.OriginRealm)
            if experimental and exp_code:
                avp_experimental_result = ''
                avp_experimental_result += self.generate_vendor_avp(266, 40, 10415, '')
                avp_experimental_result += self.generate_avp(298, 40, self.int_to_hex(exp_code, 4))
                avp += self.generate_avp(297, 40, avp_experimental_result)
            else:
                avp += self.generate_avp(268, 40, self.int_to_hex(result_code, 4))
            avp += self.generate_avp(277, 40, "00000001")
            avp += self.generate_avp(1, 40, self.string_to_hex(imsi))
            avp += self.generate_avp(260, 40, "000001024000000c" + format(int(16777265),"x").zfill(8) + "0000010a4000000c000028af")
            return self.generate_diameter_packet("01", "40", 303, 16777265, packet_vars['hop-by-hop-identifier'], packet_vars['end-to-end-identifier'], avp)

        # Get IMSI from User-Name AVP (1)
        try:
            imsi_hex = self.get_avp_data(avps, 1)[0]
            imsi = binascii.unhexlify(imsi_hex).decode('utf-8')
        except Exception:
            self.logTool.log(service='HSS', level='error', message="[diameter.py] [Answer_16777265_303] [MAA] Failed to decode IMSI", redisClient=self.redisMessaging)
            imsi = "unknown"
            avp = ''
            avp += self.generate_avp(263, 40, session_id)
            avp += self.generate_avp(264, 40, self.OriginHost)
            avp += self.generate_avp(296, 40, self.OriginRealm)
            avp += self.generate_avp(268, 40, self.int_to_hex(5012, 4))
            avp += self.generate_avp(277, 40, "00000001")
            avp += self.generate_avp(260, 40, "000001024000000c" + format(int(16777265),"x").zfill(8) + "0000010a4000000c000028af")
            return self.generate_diameter_packet("01", "40", 303, 16777265, packet_vars['hop-by-hop-identifier'], packet_vars['end-to-end-identifier'], avp)

        self.logTool.log(service='HSS', level='debug', message=f"[diameter.py] [Answer_16777265_303] [MAA] IMSI: {imsi}", redisClient=self.redisMessaging)

        # Get subscriber details
        try:
            subscriber_details = self.database.Get_Subscriber(imsi=imsi)
        except ValueError:
            self.logTool.log(service='HSS', level='debug', message=f"[diameter.py] [Answer_16777265_303] [MAA] Unknown subscriber: {imsi}", redisClient=self.redisMessaging)
            return error_response(None, experimental=True, exp_code=5001)
        except Exception:
            self.logTool.log(service='HSS', level='error', message=f"[diameter.py] [Answer_16777265_303] [MAA] DB error: {traceback.format_exc()}", redisClient=self.redisMessaging)
            return error_response(5012)

        if subscriber_details.get('enabled', 1) == 0:
            self.logTool.log(service='HSS', level='debug', message=f"[diameter.py] [Answer_16777265_303] [MAA] Subscriber {imsi} is disabled", redisClient=self.redisMessaging)
            return error_response(None, experimental=True, exp_code=5001)

        # Get PLMN from Visited-Network-Identifier AVP (600) if present, else use home PLMN
        try:
            plmn_raw = self.get_avp_data(avps, 600)
            if plmn_raw:
                plmn = plmn_raw[0]
            else:
                plmn = self.MCC + self.MNC
        except Exception:
            plmn = self.MCC + self.MNC

        # Generate EAP-AKA vectors
        try:
            auc_id = subscriber_details['auc_id']
            vector_dict = self.database.Get_Vectors_AuC(auc_id, "air", plmn=plmn)

            # SIP-Auth-Data-Item (612)
            sip_auth_data = ''
            sip_auth_data += self.generate_vendor_avp(608, "c0", 10415, self.string_to_hex("EAP-AKA"))         #SIP-Authentication-Scheme
            sip_authenticate = vector_dict['rand'] + vector_dict['autn']
            sip_auth_data += self.generate_vendor_avp(609, "c0", 10415, sip_authenticate)                       #SIP-Authenticate (RAND+AUTN)
            sip_auth_data += self.generate_vendor_avp(610, "c0", 10415, vector_dict['xres'])                    #SIP-Authorization (XRES)
            if 'ck' in vector_dict:
                sip_auth_data += self.generate_vendor_avp(625, "c0", 10415, vector_dict['ck'])                  #Confidentiality-Key
            if 'ik' in vector_dict:
                sip_auth_data += self.generate_vendor_avp(626, "c0", 10415, vector_dict['ik'])                  #Integrity-Key

            avp = ''
            avp += self.generate_avp(263, 40, session_id)                                                       #Session-ID
            avp += self.generate_avp(264, 40, self.OriginHost)                                                   #Origin-Host
            avp += self.generate_avp(296, 40, self.OriginRealm)                                                  #Origin-Realm
            avp += self.generate_avp(268, 40, self.int_to_hex(2001, 4))                                         #Result-Code: DIAMETER_SUCCESS
            avp += self.generate_avp(277, 40, "00000001")                                                        #Auth-Session-State
            avp += self.generate_avp(1, 40, self.string_to_hex(imsi))                                           #User-Name
            avp += self.generate_vendor_avp(607, "c0", 10415, self.int_to_hex(1, 4))                            #SIP-Number-Auth-Items
            avp += self.generate_vendor_avp(612, "c0", 10415, sip_auth_data)                                    #SIP-Auth-Data-Item
            avp += self.generate_avp(260, 40, "000001024000000c" + format(int(16777265),"x").zfill(8) + "0000010a4000000c000028af")  #Vendor-Specific-Application-ID (SWx)

            self.logTool.log(service='HSS', level='debug', message=f"[diameter.py] [Answer_16777265_303] [MAA] Successfully built MAA for IMSI: {imsi}", redisClient=self.redisMessaging)
            return self.generate_diameter_packet("01", "40", 303, 16777265, packet_vars['hop-by-hop-identifier'], packet_vars['end-to-end-identifier'], avp)

        except Exception:
            self.logTool.log(service='HSS', level='error', message=f"[diameter.py] [Answer_16777265_303] [MAA] Vector generation error: {traceback.format_exc()}", redisClient=self.redisMessaging)
            return error_response(5012)

'''

anchor = '    #Purge UE Answer (PUA)'
if anchor not in content:
    print("ERROR: PUA anchor not found!")
    sys.exit(1)

content = content.replace(anchor, swx_handler + anchor, 1)
print("Step 2 OK: Answer_16777265_303 handler inserted")

with open('/tmp/diameter_patched.py', 'w') as f:
    f.write(content)

orig_size = len(open('/tmp/diameter.py').read())
patch_size = len(content)
print(f"Original: {orig_size} bytes  →  Patched: {patch_size} bytes  (diff: +{patch_size - orig_size})")
