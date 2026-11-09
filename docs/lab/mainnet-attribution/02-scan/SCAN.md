# Scan auf Überlauf-Transaktionen / Overflow scan

**Werkzeug / Tool**: `df_overflow_scan.py` (Scan), `df_tx_decode.py` (Dekodierung einzelner Treffer). Beide nur lesend.
**Geprüfte Typen / Checked types**: `AccountToAccount` (B), `AnyAccountsToAccounts` (a), `UtxosToAccount` (U), `AddPoolLiquidity` (l), also alle Konsens-Pfade, die `SumAllTransfers` nutzen / all consensus paths using `SumAllTransfers`.
**Kriterium / Criterion**: echte Summe je Token > INT64_MAX oder ein Betrag ≤ 0; doppelte Empfänger-Schlüssel wie im Node (erster Eintrag gilt) / true per-token sum > INT64_MAX or any amount ≤ 0; duplicate keys handled like the node (first entry wins).

## Abdeckung / Coverage (Stand / as of 09.11.2026)

| Blöcke / Blocks | Ergebnisdatei / Result file | Treffer / Hits |
|---|---|---|
| 6,560,000 – 6,568,001 | `results/scan-6560000-6568001.json` | siehe unten / see below |
| 6,568,002 – 6,571,635 | `results/scan-6568002-6571635.json` | 0 |
| 6,571,636 – 6,573,023 | `results/scan-6571636-6573023.json` | 0 |
| 6,573,024 – 6,581,452 | `results/scan-6573024-6581452.json` | 0 |
| 6,581,453 – 6,582,461 | `results/scan-6581453-6582461.json` | 0 |

Lückenlos von / continuous from **6,560,000 bis / to 6,582,461** (≈ 31.10.2026 bis / to 09.11.2026). Quelle aller Läufe / source of all runs: public Ocean RPC.
**Nicht gescannt / not scanned**: alles vor Block 6,560,000 / everything before block 6,560,000.

Treffer im Bereich 6,560,000–6,568,001 / hits: Block 6,564,035 (`c0248c39…`) und / and 6,566,081 (`bc2e5a68…`), beide `overflow token 0`. Der Fehlversuch in Block 6,565,374 wird **nicht** gemeldet, weil der Node den doppelten Empfänger verwirft; das ist so gewollt. Details: `../01-mainnet-attribution.md`. / The failed attempt in block 6,565,374 is intentionally **not** reported, because the node drops the duplicate destination.

## Aufruf / Usage

```bash
# Öffentliche Ocean-RPC (Standard) / public Ocean RPC (default)
python df_overflow_scan.py 6560000 6568001 out.json

# Eigener Node / own node (defid with -rpcuser/-rpcpassword or cookie):
export DEFI_RPC_USER=...   DEFI_RPC_PASSWORD=...        # Windows: set DEFI_RPC_USER=...
python df_overflow_scan.py 0 tip out.json --rpc http://127.0.0.1:8554 --workers 4

# Treffer dekodieren / decode hits
python df_tx_decode.py 6564035:c0248c396a0be9fe6122cab0c4f0c1ab4f8160bdde85893a9afd592732cfef0e --rpc http://127.0.0.1:8554
```

Python ≥ 3.8, keine Zusatzpakete / no extra packages. Zugangsdaten nur per Umgebungsvariable, nie in Dateien. / Credentials only via environment variables, never in files.

## Vollscan der ganzen Chain / Full-history scan

- Über Ocean schafft das Skript 15–18 Blöcke/s (gemessen 09.11.2026). Die ganze Chain (≈ 6,58 Mio. Blöcke) bräuchte so rund 4–5 Tage. Ein eigener Node ist schneller und unabhängig davon, ob Ocean nach dem 14.11.2026 noch läuft.
  Via Ocean the script does 15–18 blocks/s (measured 2026-11-09), so the full chain would take roughly 4–5 days. An own node is faster and does not depend on Ocean staying online after 2026-11-14.
- Aufteilen nach Blockbereichen auf mehrere Helfer ist problemlos; die Ergebnisdateien enthalten Start, Ende und Zeitpunkt.
  Splitting by block ranges across helpers works fine; each result file records start, end and scan time.
- Gegenprobe vor jedem Lauf / sanity check before each run: Bereich / range `6564030 6564040` muss / must report `c0248c39…`.

## Grenzen / Limitations

- Erkennt nur die vier genannten Typen und nur das Überlauf-/Nicht-positiv-Muster. EVM-Seite (DMC) nicht geprüft.
  Detects only the four types above and only the overflow / non-positive pattern. EVM side (DMC) not checked.
- Ein Treffer heißt „verdächtig“, nicht automatisch „wirksam“. Mit `df_tx_decode.py` prüfen (echte Summe vs. Node-Summe).
  A hit means "suspicious", not automatically "effective"; check with `df_tx_decode.py` (true sum vs node sum).
