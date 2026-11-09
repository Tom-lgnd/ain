# SumAllTransfers overflow (DeFiChain, 03.11.2026) – Analyse- und Scan-Paket / analysis and scan package

**Stand / As of**: 09.11.2026
**Art / Type**: Community-Beitrag, KI-gestützt erstellt (Claude), nicht unabhängig geprüft. / Community contribution, prepared with AI assistance (Claude), not independently reviewed.
**Zweck / Purpose**: Ergänzung zu den laufenden Fix-Arbeiten (PR #3135 in DeFiCh/ain, Labor-Fix von M J, Branch von Axel). / Supplement to the ongoing fix work (PR #3135 in DeFiCh/ain, M J's lab fix, Axel's branch).

---

## Deutsch

### Inhalt

| Pfad | Was |
|---|---|
| `01-mainnet-attribution.md` | Byte-Zerlegung der beiden wirksamen Mainnet-Transaktionen und des Fehlversuchs; zeigt, dass es genau dieser Fehler ist. Anregungen für Testfälle. |
| `02-scan/` | Nur lesende Scan- und Dekodier-Skripte (Python, ohne Zusatzpakete) plus Ergebnisse von Block 6.560.000 bis 6.582.461. Beschreibung in `02-scan/SCAN.md`. |
| `03-patch-reference/` | Patch-Entwurf vom 04.11.2026 (Basis v4.2.5) mit Gate `DF25Height` über alle vier Konsens-Pfade. **Nur als Referenz**, der Stand von M J ist weiter getestet. |
| `04-addresses-and-balances.md` | Adressen beider Akteure mit Konto- **und** UTXO-Beständen. Grundlage für den Entwurf eines Clawbacks oder einer Sperre. |
| `SHA256SUMS.txt` | Prüfsummen aller Dateien. |

### Kernaussagen

1. Beide wirksamen Vorfälle (Blöcke 6.564.035 und 6.566.081) sind `AccountToAccount` mit echter Summe INT64_MAX + 1 Sat. Erzeugt wurden zusammen 184.467.440.729,09551614 DFI.
2. Von Block 6.560.000 bis 6.582.461 gibt es **keine weiteren** Überlauf-Transaktionen in den vier Pfaden B, a, U, l. Davor ist nicht gescannt.
3. **Aktivierungshöhe**: 6.566.082 ist der früheste Wert, der keinen bekannten Block ungültig macht. Mit 6.564.035 würden beide Exploit-Blöcke zurückgerollt (Rollback, inzwischen über 18.000 Blöcke). Bei einem Rollback erzeugen Nodes keine Blöcke, solange die Kettenspitze älter als `nMaxTipAge` ist (Standard 10 h, `validation.h`); das lässt sich nur koordiniert mit `-maxtipage` überbrücken.
4. **Ein Clawback muss auch UTXOs erfassen**: Akteur 1 hält neben dem Kontoguthaben 47,0 Mio. DFI als UTXO.
5. Der Fix stoppt nur neue Überläufe. Die ≈ 184 Mrd. DFI bleiben, bis eine Sperre oder ein Clawback in derselben Aktivierung kommt.

### Bewusst nicht enthalten

- Werkzeuge zum **Bauen** von Transaktionen. Die Lücke ist auf dem Mainnet noch offen.
- Vermutungen über die Personen hinter den Adressen.
- Adressen von Dritten, die DFI nachträglich von einer Börse erhalten haben (können unbeteiligte Kunden sein).
- Private oder persönliche Daten jeder Art.

### Hinweis für Masternode-Betreiber

Keine selbst gebaute oder fremde Binärdatei auf Masternodes einspielen, bevor Code und Aktivierungshöhe gemeinsam geprüft und abgestimmt sind. Eine abweichende Konsensregel führt sonst auf eine eigene Kette.

---

## English

### Contents

| Path | What |
|---|---|
| `01-mainnet-attribution.md` | Byte-level breakdown of both effective mainnet transactions and the failed attempt, showing it is exactly this bug; test-case suggestions. |
| `02-scan/` | Read-only scan and decode scripts (Python, standard library only) plus results for blocks 6,560,000–6,582,461. See `02-scan/SCAN.md`. |
| `03-patch-reference/` | Patch draft of 2026-11-04 (base v4.2.5) with a `DF25Height` gate on all four consensus paths. **Reference only**; M J's version is more thoroughly tested. |
| `04-addresses-and-balances.md` | Both actors' addresses with account **and** UTXO balances, as input for a clawback / freeze design. |
| `SHA256SUMS.txt` | Checksums of all files. |

### Key points

1. Both effective incidents (blocks 6,564,035 and 6,566,081) are `AccountToAccount` transactions whose true sum is INT64_MAX + 1 sat; together they created 184,467,440,729.09551614 DFI.
2. Blocks 6,560,000–6,582,461 contain **no further** overflow transactions in the four paths B, a, U, l. Earlier blocks are not scanned.
3. **Activation height**: 6,566,082 is the earliest value that invalidates no known block. 6,564,035 would roll back both exploit blocks (now more than 18,000 blocks). In a rollback, nodes produce no blocks while the tip is older than `nMaxTipAge` (default 10 h, `validation.h`); this can only be bridged in a coordinated way with `-maxtipage`.
4. **A clawback must also cover UTXOs**: actor 1 holds 47.0 M DFI as UTXOs in addition to the account balance.
5. The fix only stops new overflows. The ≈ 184 bn DFI remain until a freeze or clawback ships in the same activation.

### Deliberately not included

- Any tool that **builds** transactions; the hole is still open on mainnet.
- Speculation about the persons behind the addresses.
- Addresses of third parties who later received DFI from an exchange (they may be uninvolved customers).
- Private or personal data of any kind.

### Note for masternode operators

Do not deploy self-built or third-party binaries on masternodes before code and activation height have been reviewed and agreed jointly. A divergent consensus rule puts you on a separate chain.
