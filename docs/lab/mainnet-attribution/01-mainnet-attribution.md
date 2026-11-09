# Mainnet-Zuordnung / Mainnet attribution – SumAllTransfers overflow, 03.11.2026

**Stand / As of**: 09.11.2026 · Daten aus der öffentlichen Ocean-RPC (`getblock`, Stufe 2), dekodiert mit `02-scan/df_tx_decode.py`; Rohausgabe in `02-scan/results/decoded-transactions.json`.
**Erstellt / Prepared**: Community-Beitrag, KI-gestützt (Claude). Nicht unabhängig geprüft. / Community contribution, AI-assisted (Claude). Not independently reviewed.

---

## Deutsch

### Ergebnis

Beide wirksamen Vorfälle vom 03.11.2026 sind `AccountToAccount`-Transaktionen (DfTx-Typ `B`) mit genau zwei Empfängern. Die echte Summe ist jeweils **INT64_MAX + 1 Satoshi**. Der ungepatchte Node bricht bei der Addition des zweiten Empfängers ab. Er bucht beim Absender nur den Betrag des ersten Empfängers ab, schreibt aber beiden den vollen Betrag gut. Ein dritter Versuch blieb wirkungslos.

| Block | Zeit (UTC) | txid | abgebucht | gutgeschrieben (Hauptempfänger) | Wirkung |
|---|---|---|---|---|---|
| 6.564.035 | 03.11.2026 00:13:18 | `c0248c396a0be9fe6122cab0c4f0c1ab4f8160bdde85893a9afd592732cfef0e` | 0,00000001 DFI | 92.233.720.368,54775807 DFI → `df1qel8g4g4f66qxr7cw0t03jkz08cj095vup2jhuy` | wirksam |
| 6.565.374 | 03.11.2026 12:10:36 | `b2518be0b1e17170c2fe6ff59600d740a74b133cef89ebe4761e900c1a76857a` | 0,00000001 DFI | 0,00000001 DFI an sich selbst | **wirkungslos** |
| 6.566.081 | 03.11.2026 19:02:56 | `bc2e5a684592cc2f504268d23a418ca66cbb9900bf4dcb1b5c2eb3ec58b2e8ac` | 8,00000001 DFI | 92.233.720.360,54775807 DFI → `df1qqtlz4uw9w5s4pupwgucv4shl6atqw7xlz2wn07` | wirksam |

Zusammen erzeugt: 92.233.720.368,54775807 + 92.233.720.360,54775807 = **184.467.440.729,09551614 DFI**.

### Warum es funktioniert

- `CAccounts` ist eine `std::map<CScript, CBalances>`; `SumAllTransfers` addiert in der Reihenfolge der Script-Bytes.
- `CBalances::AddBalances` ruft `SafeAdd` auf; bei Überlauf kommt ein Fehler zurück, die Summe bleibt unverändert. `SumAllTransfers` wertet diesen Fehler nicht aus.
- Damit die verkürzte Summe vom Absender gedeckt ist, muss der Empfänger mit dem **kleineren Script** den **kleinen** Betrag tragen. Genau so sind beide Transaktionen gebaut.
- Die Beträge lassen sich über die RPC-Befehle der Wallet nicht eingeben. Die Transaktionen wurden roh gebaut.

### Byte-Zerlegung Block 6.564.035

```
6a                OP_RETURN
4c 65             PUSHDATA1, 101 Byte
44665478          "DfTx"
42                Typ 'B' = AccountToAccount
16 0014 021980eaf85d90d88c0e634baa5ba6d9c7e519c9      from  df1qqgvcp6hctkgd3rqwvd965kaxm8r72xwfzmfs6n
02                2 Empfänger / destinations
16 0014 8b4c9ee6372a3f49fa6307566f2418af96f69617      to[0] df1q3dxfae3h9gl5n7nrqatx7fqc47t0d9sh8r0cue
   01 00000000 0100000000000000                         1 Saldo, Token 0 (DFI), 1 Satoshi
16 0014 cfce8aa2a9d68061fb0e7adf19584f3e24f2d19c      to[1] df1qel8g4g4f66qxr7cw0t03jkz08cj095vup2jhuy
   01 00000000 ffffffffffffff7f                         1 Saldo, Token 0 (DFI), 9.223.372.036.854.775.807 Sat (INT64_MAX)
```
Summe im Node: 1 Sat, dann 1 + INT64_MAX → Überlauf → bleibt **1 Sat**. Abgebucht 1 Sat, gutgeschrieben INT64_MAX.

### Byte-Zerlegung Block 6.566.081

```
6a 4c 65 44665478 42
16 0014 c973c878aee9b6ee1e6b9221292e01616f02db63      from  df1qe9eus79waxmwu8ntjgsjjtspv9hs9kmr8y44x2
02
16 0014 0167258a996cc1d9b53094be06c01df467acc0f7      to[0] df1qq9njtz5ednqandfsjjlqdsqa73n6es8h6gapdz
   01 00000000 0108af2f00000000                         Token 0, 800.000.001 Sat = 8,00000001 DFI
16 0014 02fe2af1c5752150f02e4730cac2ffd7560778df      to[1] df1qqtlz4uw9w5s4pupwgucv4shl6atqw7xlz2wn07
   01 00000000 fff750d0ffffff7f                         Token 0, INT64_MAX − 800.000.000 Sat = 92.233.720.360,54775807 DFI
```
Summe im Node: 8,00000001 DFI, dann Überlauf → bleibt **8,00000001 DFI**. Echte Summe: INT64_MAX + 1 Sat.

### Fehlversuch Block 6.565.374

```
6a 4c 65 44665478 42
16 0014 02fe2af1c5752150f02e4730cac2ffd7560778df      from  df1qqtlz4uw9w5s4pupwgucv4shl6atqw7xlz2wn07
02                                                      Zähler 2, aber zweimal DASSELBE Script:
16 0014 02fe2af1c5752150f02e4730cac2ffd7560778df   01 00000000 0100000000000000   1 Sat
16 0014 02fe2af1c5752150f02e4730cac2ffd7560778df   01 00000000 ffffffffffffff7f   INT64_MAX
```
Beim Einlesen der Map behält der Node von doppelten Schlüsseln nur den **ersten** Eintrag (`serialize.h`, `m.insert`). Übrig bleibt eine Überweisung von 1 Sat an sich selbst. Das wäre ein sinnvoller zusätzlicher Regressionstest.

### Weitere Testfall-Anregung

Mehrere Token beim selben Empfänger: `AddBalances` bricht beim ersten fehlschlagenden Token ab, weitere Token dieses Empfängers fallen ebenfalls aus der Summe. So ließen sich mit dem alten Code auch DUSD oder dToken erzeugen. Der Fix (Fehler weiterreichen) deckt das ab, ein eigener Test macht es sichtbar.

---

## English

### Result

Both effective incidents of 03 Nov 2026 are `AccountToAccount` transactions (DfTx type `B`) with exactly two destinations. In each case the true sum is **INT64_MAX + 1 satoshi**. The unpatched node aborts when adding the second destination. It debits the source by the first destination's amount only, but credits both destinations in full. A third attempt had no effect.

| Block | Time (UTC) | txid | debited | credited (main recipient) | effect |
|---|---|---|---|---|---|
| 6,564,035 | 2026-11-03 00:13:18 | `c0248c39…cfef0e` | 0.00000001 DFI | 92,233,720,368.54775807 DFI → `df1qel8g…` | effective |
| 6,565,374 | 2026-11-03 12:10:36 | `b2518be0…76857a` | 0.00000001 DFI | 0.00000001 DFI to itself | **no effect** |
| 6,566,081 | 2026-11-03 19:02:56 | `bc2e5a68…b2e8ac` | 8.00000001 DFI | 92,233,720,360.54775807 DFI → `df1qqtlz…` | effective |

Full txids and addresses: see the German table above. Total created: **184,467,440,729.09551614 DFI**.

### Why it works

- `CAccounts` is a `std::map<CScript, CBalances>`; `SumAllTransfers` adds in script-byte order.
- `CBalances::AddBalances` uses `SafeAdd`; on overflow it returns an error and leaves the sum unchanged. `SumAllTransfers` ignores that error.
- For the truncated sum to be covered by the source balance, the destination with the **smaller script** must carry the **small** amount. Both transactions are built exactly like that.
- Such amounts cannot be entered through the wallet RPC; the transactions were built raw.

### Byte layout

See the two annotated hex dumps above (identical for both languages). Block 6,564,035: node sum stays at **1 sat**. Block 6,566,081: node sum stays at **8.00000001 DFI**.

### Failed attempt, block 6,565,374

Count byte says 2, but both entries use the **same** script. On deserialisation the node keeps only the **first** entry of a duplicate key (`serialize.h`, `m.insert`). What remains is a 1-sat transfer to itself. Worth a regression test.

### Additional test suggestion

Multiple tokens for the same destination: `AddBalances` stops at the first failing token, so further tokens of that destination also drop out of the sum. With the old code this would also allow creating DUSD or dTokens. The fix (propagating the error) covers it; a dedicated test makes it explicit.
