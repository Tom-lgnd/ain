#!/usr/bin/env python3
"""
df_tx_decode.py - read-only decoder for transfer transactions found by df_overflow_scan.py.

EN: Prints the OP_RETURN payload, message type, source and destination addresses with amounts,
    the true per-token sum (arbitrary precision) and what the unpatched node computes
    (SumAllTransfers stops at the first failing addition and keeps the old value).
DE: Gibt OP_RETURN-Inhalt, Typ, Absender/Empfänger mit Beträgen, die echte Summe je Token und die
    Summe aus, die der ungepatchte Node berechnet (Abbruch bei der ersten fehlschlagenden Addition).

Usage / Aufruf:
    python df_tx_decode.py <height>:<txid> [<height>:<txid> ...] [--rpc URL]
    Credentials for an own node only via DEFI_RPC_USER / DEFI_RPC_PASSWORD.

Only decodes. It cannot build or send transactions. / Nur Dekodierung, kann nichts bauen oder senden.
"""
import argparse, datetime, hashlib, json, struct
import df_overflow_scan as S

CH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def polymod(v):
    g = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]; c = 1
    for x in v:
        b = c >> 25; c = (c & 0x1ffffff) << 5 ^ x
        for i in range(5): c ^= g[i] if (b >> i) & 1 else 0
    return c


def bech32(hrp, ver, prog):
    acc = bits = 0; d = [ver]
    for x in prog:
        acc = (acc << 8) | x; bits += 8
        while bits >= 5: bits -= 5; d.append((acc >> bits) & 31)
    if bits: d.append((acc << (5 - bits)) & 31)
    hv = [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    pm = polymod(hv + d + [0] * 6) ^ 1
    return hrp + "1" + "".join(CH[x] for x in d + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])


def b58check(ver, h):
    p = bytes([ver]) + h; p += hashlib.sha256(hashlib.sha256(p).digest()).digest()[:4]
    n = int.from_bytes(p, "big"); a = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"; s = ""
    while n: n, r = divmod(n, 58); s = a[r] + s
    return "1" * (len(p) - len(p.lstrip(b"\0"))) + s


def addr(sh):
    b = bytes.fromhex(sh)
    if len(b) == 22 and b[:2] == b"\x00\x14": return bech32("df", 0, b[2:])
    if len(b) == 25 and b[:3] == b"\x76\xa9\x14": return b58check(0x12, b[3:23])
    if len(b) == 23 and b[0] == 0xa9: return b58check(0x5a, b[2:22])
    return "script:" + sh


def fmt(sat):
    sign = "-" if sat < 0 else ""; sat = abs(sat)
    return f"{sign}{sat // 10**8:,}.{sat % 10**8:08d}".replace(",", "'")


def node_sum(accs):
    """What unpatched SumAllTransfers returns: std::map order (by script bytes), stop on first failing add."""
    total = {}
    for _sc, bals in sorted(accs, key=lambda kv: bytes.fromhex(kv[0])):
        for tok, amt in bals:
            new = total.get(tok, 0) + amt
            if new > S.INT64_MAX or new < -S.INT64_MAX - 1:
                break                      # CBalances::AddBalances returns on first error -> rest of this entry lost
            total[tok] = new
    return total


def decode(h, txid):
    blk = S.rpc("getblock", [S.rpc("getblockhash", [h]), 2])
    tx = next(t for t in blk["tx"] if t["txid"] == txid)
    for vo in tx["vout"]:
        d = S.push_data(vo["scriptPubKey"].get("hex", ""))
        if d and d[:4] == b"DfTx": break
    else:
        return {"height": h, "txid": txid, "error": "no DfTx payload"}
    t = chr(d[4]); r = S.R(d[5:]); rec = {"height": h, "txid": txid,
        "block_time_utc": datetime.datetime.fromtimestamp(blk["time"], datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "type": S.TYPES.get(t, t), "op_return_hex": vo["scriptPubKey"]["hex"]}
    groups = {}
    if t == "B": rec["from"] = addr(r.script()); groups["to"] = r.accounts()
    elif t == "a": groups["from"] = r.accounts(); groups["to"] = r.accounts()
    elif t == "U": groups["to"] = r.accounts()
    elif t == "l": groups["from"] = r.accounts(); rec["share_address"] = addr(r.script())
    for name, accs in groups.items():
        rec[name + "_accounts"] = [{"address": addr(sc), "amounts": [f"{fmt(v)} @token{tok}" for tok, v in bals]} for sc, bals in accs]
        true = {}
        for _sc, bals in accs:
            for tok, v in bals: true[tok] = true.get(tok, 0) + v
        rec[name + "_true_sum"] = {f"token{k}": fmt(v) for k, v in true.items()}
        rec[name + "_unpatched_node_sum"] = {f"token{k}": fmt(v) for k, v in node_sum(accs).items()}
        rec[name + "_overflow"] = any(v > S.INT64_MAX for v in true.values())
    return rec


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("items", nargs="+"); ap.add_argument("--rpc", default=S.DEFAULT_RPC)
    a = ap.parse_args(); S.RPC_URL = a.rpc
    print(json.dumps([decode(int(x.split(":")[0]), x.split(":")[1]) for x in a.items], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
