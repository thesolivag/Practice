import os,json,base64,zlib
from pathlib import Path
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from slk import db,tenancy
try:
    uid=tenancy.owner_id()
    conn=db.connect()
    with conn.cursor() as cur:
        cur.execute('SET TRANSACTION READ ONLY');conn.begin()
        cur.execute("SELECT status,created_at,updated_at,payload FROM bishop_app_entries WHERE user_id=%s AND pair='USDCAD' AND status='WIN' ORDER BY updated_at DESC LIMIT 6",(uid,))
        rows=list(cur.fetchall())
        cur.execute("SELECT status,created_at,updated_at,payload FROM bishop_app_entries WHERE user_id=%s AND pair='USDCAD' ORDER BY updated_at DESC LIMIT 6",(uid,))
        rows+=list(cur.fetchall())
        output={}
        for row in rows:
            payload=json.loads(row.pop('payload'));output[payload['order']['id']]={**row,**payload}
        table='bias' if uid==tenancy.owner_id() else 'tenant_bias'
        cur.execute("SELECT id,pair,story,side,status,confirm_time,target,invalidation,no_trade FROM bias WHERE pair='USDCAD' ORDER BY COALESCE(confirm_time,tap_time) DESC LIMIT 12")
        biases=list(cur.fetchall())
        conn.rollback()
    conn.close()
    data=zlib.compress(json.dumps({'entries':list(output.values()),'web_biases':biases},default=str).encode())
    key=AESGCM.generate_key(bit_length=256);nonce=os.urandom(12)
    pub=serialization.load_pem_public_key(Path('audit-public.pem').read_bytes())
    sealed=pub.encrypt(key,padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    envelope={k:base64.b64encode(v).decode() for k,v in {'key':sealed,'nonce':nonce,'data':AESGCM(key).encrypt(nonce,data,None)}.items()}
    print('BISHOP_PRIVATE_AUDIT='+json.dumps(envelope,separators=(',',':')))
except Exception as exc:
    print('Private read-only audit failed: '+type(exc).__name__)
    raise SystemExit(1)
