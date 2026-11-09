#!/usr/bin/env python3
"""
df_overflow_scan.py - read-only scan of DeFiChain mainnet blocks for the SumAllTransfers overflow.

EN: Scans every block in a height range for custom transactions that use SumAllTransfers
    (AccountToAccount 'B', AnyAccountsToAccounts 'a', UtxosToAccount 'U', AddPoolLiquidity 'l')
    and reports any whose true per-token sum exceeds INT64_MAX or that carry an amount <= 0.
    Read-only: only getblockcount / getblockhash / getblock. Moves nothing, needs no wallet.
DE: Durchsucht einen Blockbereich nach Custom-Transaktionen, die SumAllTransfers nutzen, und meldet
    jede, deren echte Summe je Token INT64_MAX übersteigt oder die einen Betrag <= 0 enthält.
    Nur lesend, braucht keine Wallet.

Usage / Aufruf:
    python df_overflow_scan.py <start_height> <end_height|tip> <out.json> [--rpc URL] [--workers N]

    --rpc      JSON-RPC endpoint. Default: public Ocean RPC (https://ocean.defichain.com/v0/mainnet/rpc).
               Own node / eigener Node: --rpc http://127.0.0.1:8554
               Credentials (own node only) via environment variables / Zugangsdaten nur per Umgebungsvariable:
               DEFI_RPC_USER, DEFI_RPC_PASSWORD   (never put them on the command line or in files)
    --workers  parallel requests (default 6; use 2-4 against a small own node)

Duplicate destination keys are handled like the node does (std::map deserialisation keeps the FIRST entry,
serialize.h m.insert), so a "two times the same address" transaction is not reported as an overflow.
"""
import argparse, base64, json, os, struct, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

DEFAULT_RPC = "https://ocean.defichain.com/v0/mainnet/rpc"
INT64_MAX = 2**63 - 1
TYPES = {"B": "AccountToAccount", "a": "AnyAccountsToAccounts", "U": "UtxosToAccount", "l": "AddPoolLiquidity"}
RPC_URL = DEFAULT_RPC


def rpc(method, params):
    body = json.dumps({"jsonrpc": "1.0", "id": "scan", "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "df-overflow-scan"}
    user, pw = os.environ.get("DEFI_RPC_USER"), os.environ.get("DEFI_RPC_PASSWORD")
    if user and pw:
        headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
    last = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(RPC_URL, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.load(r)
            if res.get("error"):
                raise RuntimeError(res["error"])
            return res["result"]
        except Exception as e:
            last = e
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"rpc failed: {method} {params}: {last}")


class R:
    def __init__(self, b): self.b, self.i = b, 0
    def take(self, n):
        v = self.b[self.i:self.i + n]
        if len(v) != n: raise ValueError("eof")
        self.i += n; return v
    def cs(self):
        f = self.take(1)[0]
        if f < 253: return f
        return int.from_bytes(self.take({253: 2, 254: 4, 255: 8}[f]), "little")
    def script(self): return self.take(self.cs()).hex()
    def balances(self):
        out = {}
        for _ in range(self.cs()):
            tok = struct.unpack("<I", self.take(4))[0]; amt = struct.unpack("<q", self.take(8))[0]
            out.setdefault(tok, amt)          # first entry wins, like the node
        return list(out.items())
    def accounts(self):
        out = {}
        for _ in range(self.cs()):
            sc = self.script(); bal = self.balances()
            out.setdefault(sc, bal)           # first entry wins, like the node
        return list(out.items())


def push_data(script_hex):
    b = bytes.fromhex(script_hex)
    if len(b) < 2 or b[0] != 0x6a: return None
    op, i = b[1], 2
    if op < 0x4c: n = op
    elif op == 0x4c: n, i = b[2], 3
    elif op == 0x4d: n, i = int.from_bytes(b[2:4], "little"), 4
    elif op == 0x4e: n, i = int.from_bytes(b[2:6], "little"), 6
    else: return None
    return b[i:i + n]


def check_accounts(accs):
    """Problems: per-token true sum > INT64_MAX, or non-positive amounts."""
    sums, probs = {}, []
    for _owner, bals in accs:
        for tok, amt in bals:
            if amt <= 0: probs.append(f"non-positive {amt}@{tok}")
            sums[tok] = sums.get(tok, 0) + amt
    for tok, s in sums.items():
        if s > INT64_MAX: probs.append(f"overflow token {tok}: true sum {s}")
    return probs


def scan_height(h):
    blk = rpc("getblock", [rpc("getblockhash", [h]), 2])
    hits = []
    for tx in blk["tx"]:
        for vo in tx["vout"]:
            d = push_data(vo["scriptPubKey"].get("hex", ""))
            if not d or d[:4] != b"DfTx" or len(d) < 5: continue
            t = chr(d[4])
            if t not in TYPES: continue
            try:
                r = R(d[5:])
                if t == "B": r.script(); parts = [r.accounts()]          # from, to
                elif t == "a": parts = [r.accounts(), r.accounts()]      # from, to
                else: parts = [r.accounts()]                             # 'U': to / 'l': from
            except Exception as e:
                hits.append({"height": h, "txid": tx["txid"], "type": TYPES[t], "problem": f"parse error {e}"}); continue
            probs = [p for acc in parts for p in check_accounts(acc)]
            if probs:
                hits.append({"height": h, "txid": tx["txid"], "type": TYPES[t], "problem": "; ".join(probs)})
    return h, blk["time"], hits


def main():
    global RPC_URL
    ap = argparse.ArgumentParser(description="Read-only SumAllTransfers overflow scan")
    ap.add_argument("start", type=int); ap.add_argument("end"); ap.add_argument("out")
    ap.add_argument("--rpc", default=DEFAULT_RPC); ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    RPC_URL = a.rpc
    end = rpc("getblockcount", []) if a.end == "tip" else int(a.end)
    hits, done, t0, last = [], 0, time.time(), None
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for h, bt, hh in ex.map(scan_height, range(a.start, end + 1)):
            hits += hh; done += 1; last = (h, bt)
            if done % 250 == 0:
                print(f"{done}/{end - a.start + 1} blocks, hits={len(hits)}, {time.time() - t0:.0f}s", flush=True)
    res = {"start": a.start, "end": end, "blocks_scanned": done, "end_block_time_unix": last[1] if last else None,
           "rpc": "ocean-public" if a.rpc == DEFAULT_RPC else "own-node",
           "scanned_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "hits": hits}
    with open(a.out, "w") as f:
        json.dump(res, f, indent=1)
    print("DONE", json.dumps(res)[:2000], flush=True)


if __name__ == "__main__":
    main()
