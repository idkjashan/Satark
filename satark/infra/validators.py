"""Reference validators for Satark entity types (prototype from the 3 Oct 2026 research).

GSTIN mod-36 check, Verhoeff (Aadhaar), Luhn (cards), ISIN, Base58Check (BTC, TRON) and bech32/bech32m.
Run `python3 validators.py` to print the test vectors; every line should show the expected True/False.
See Satark-LLD.md section 8.2 for where each is used."""
import re
A='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
def gstin_check(g14):
    s=0
    for i,ch in enumerate(g14):
        p=A.index(ch)*(2 if i%2 else 1)   # left-to-right: odd pos x1, even pos x2
        s+=p//36+p%36
    return A[(36-s%36)%36]
def gstin_ok(g):
    g=g.upper()
    return bool(re.fullmatch(r'\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]',g)) and gstin_check(g[:14])==g[14]
def verhoeff_ok(num):
    d=[[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]]
    p=[[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]]
    c=0
    for i,ch in enumerate(reversed(num)):
        c=d[c][p[i%8][int(ch)]]
    return c==0
def luhn_ok(num):
    s=0
    for i,ch in enumerate(reversed(num)):
        x=int(ch)*(2 if i%2 else 1)
        s+=x-9 if x>9 else x
    return s%10==0
def isin_ok(isin):
    if not re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}\d',isin): return False
    digits=''.join(str(int(c,36)) for c in isin[:-1])
    return luhn_ok(digits+isin[-1])
if __name__=='__main__':
    for g in ['22AAAAA0000A1Z5','27AAACR5055K1Z7','29AAACI4798L1ZZ']:
        print(g, gstin_ok(g), gstin_check(g[:14]))
    print('luhn 4111111111111111', luhn_ok('4111111111111111'))
    for i in ['INE002A01018','INE009A01021','US0378331005','INE467B01029']:
        print(i, isin_ok(i))
    # Verhoeff test vector from Wikipedia: 236 -> check 3 => 2363 valid
    print('verhoeff 2363', verhoeff_ok('2363'), verhoeff_ok('2364'))

B58='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58check_payload(s):
    import hashlib
    n=0
    for ch in s: n=n*58+B58.index(ch)
    raw=n.to_bytes((n.bit_length()+7)//8,'big')
    raw=b'\x00'*(len(s)-len(s.lstrip('1')))+raw
    body,chk=raw[:-4],raw[-4:]
    ok=hashlib.sha256(hashlib.sha256(body).digest()).digest()[:4]==chk
    return ok, body
def tron_ok(a):
    if not re.fullmatch(r'T[1-9A-HJ-NP-Za-km-z]{33}',a): return False
    ok,body=b58check_payload(a); return ok and len(body)==21 and body[0]==0x41
def btc_base58_ok(a):
    if not re.fullmatch(r'[13][1-9A-HJ-NP-Za-km-z]{25,34}',a): return False
    ok,body=b58check_payload(a); return ok and len(body)==21 and body[0] in (0x00,0x05)
# bech32/bech32m per BIP-173/BIP-350
CH='qpzry9x8gf2tvdw0s3jn54khce6mua7l'
def _polymod(v):
    g=[0x3b6a57b2,0x26508e6d,0x1ea119fa,0x3d4233dd,0x2a1462b3]; c=1
    for x in v:
        b=c>>25; c=(c&0x1ffffff)<<5^x
        for i in range(5): c^=g[i] if (b>>i)&1 else 0
    return c
def bech32_ok(a, hrp='bc'):
    a2=a.lower()
    if a!=a2 and a!=a.upper(): return False
    if not a2.startswith(hrp+'1'): return False
    data=[CH.find(c) for c in a2[len(hrp)+1:]]
    if -1 in data or len(data)<6: return False
    const=_polymod([ord(c)>>5 for c in hrp]+[0]+[ord(c)&31 for c in hrp]+data)
    wit=data[0]
    return (wit==0 and const==1) or (wit>=1 and const==0x2bc830a3)
if __name__=='__main__':
    print('tron USDT contract', tron_ok('TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t'), 'tron doc example', tron_ok('TJRabPrwbZy45sbavfcjinPJC18kjpRTv8'), 'tampered', tron_ok('TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6u'))
    print('btc genesis', btc_base58_ok('1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'), 'p2sh', btc_base58_ok('3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy'))
    print('bech32 v0', bech32_ok('bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4'), 'bech32m v1', bech32_ok('bc1p0xlxvlhemja6c4dqv22uapctqupfhlxm9h8z3k2e72q4k9hcz7vqzk5jj0'), 'bad', bech32_ok('bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t5'))
