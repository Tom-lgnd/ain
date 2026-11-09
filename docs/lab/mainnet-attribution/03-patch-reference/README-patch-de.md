> **Hinweis (09.11.2026)**: Referenzstand vom 04.11.2026. Inzwischen weiter: Labor-Fix von M J (mit Aktivierungshöhe, getestet) und PR #3135. Der Scan reicht jetzt bis Block 6.582.461, siehe `../02-scan/SCAN.md`.

# Patch: Überlauf in `SumAllTransfers` (Exploit vom 03.11.2026)

**Stand**: 04.11.2026 · **Basis**: DeFiCh/ain v4.2.5 (wendet auch sauber auf `master` bd09486 an)
**Datei**: `0001-consensus-reject-overflowing-transfer-sums-SumAllTra.patch` (git format-patch)
**Erstellt**: Community-Beitrag, KI-gestützt (Claude) – *Entwurf, nicht von der Development SIG geprüft*

---

## 1. Ursache

`src/dfi/balances.h`, Zeile 265 (v4.2.5):

```cpp
inline CBalances SumAllTransfers(const CAccounts &to) {
    CBalances sum;
    for (const auto &kv : to) {
        sum.AddBalances(kv.second.balances);   // Rückgabewert (Res) wird verworfen
    }
    return sum;
}
```

`CBalances::Add` → `CTokenAmount::Add` → `SafeAdd` erkennt den int64-Überlauf korrekt und liefert einen Fehler –
lässt die Summe dabei aber **unverändert**. Weil `SumAllTransfers` den Fehler ignoriert, fällt der überlaufende
Betrag einfach aus der Summe heraus. Gutgeschrieben wird anschließend jeder Empfänger einzeln und in voller Höhe.

Zusätzlich bricht `AddBalances` beim ersten Fehler ab: Hat derselbe Empfänger noch weitere Token, fallen auch
diese aus der Summe. Die Lücke betrifft also **nicht nur DFI**, sondern jedes Token (DUSD, dToken …).

Auf dem Mainnet zweimal wirksam ausgenutzt (Scan bis Block 6.568.001, siehe `../02-scan/SCAN.md`):

| Block | Zeit (UTC) | tx | abgebucht | erzeugt |
|---|---|---|---|---|
| 6.564.035 | 03.11. 00:13 | `c0248c39…cfef0e` | 0,00000001 DFI | 92.233.720.368,54775807 DFI → `df1qel8g…` |
| 6.566.081 | 03.11. 19:02 | `bc2e5a68…b2e8ac` | 8,00000001 DFI | 92.233.720.360,54775807 DFI → `df1qqtlz…` |

Zusammen ≈ **184,47 Mrd. DFI** – fast genau die Menge des Bitcoin-Überlaufs von 2010 (184.467.440.737 BTC),
weil beide Male dieselbe int64-Grenze ausgereizt wurde.

Ein Versuch in Block 6.565.374 (`b2518be0…`) blieb **wirkungslos**: Er nannte zweimal dieselbe Empfängeradresse,
und beim Einlesen behält der Node von doppelten Schlüsseln nur den ersten (`serialize.h`, `m.insert`).

## 2. Betroffene Konsens-Pfade

| Transaktion | Stelle | Wirkung |
|---|---|---|
| `AccountToAccount` (B) | `consensus/accounts.cpp` | Abbuchung = verkürzte Summe → Inflation (**ausgenutzt**) |
| `AnyAccountsToAccounts` (a) | `consensus/accounts.cpp` | Vergleich Eingänge = Ausgänge mit verkürzten Summen → Inflation möglich |
| `UtxosToAccount` (U) | `consensus/accounts.cpp` | Vergleich mit verbrannten UTXO-Beträgen über verkürzte Summe → Inflation möglich, **ohne Kontoguthaben** |
| `AddPoolLiquidity` (l) | `consensus/poolpairs.cpp` | Pool bekommt weniger als abgebucht wird → keine Inflation, aber falsch |

Nicht konsensrelevant (nur RPC/Anzeige, nicht geändert): `rpc_accounts.cpp`, `mn_rpc.cpp`, `rpc_customtx.cpp`.

## 3. Was der Patch macht

1. **Neue Funktion** `SumAllTransfersChecked()` in `balances.h`: lehnt Beträge ≤ 0 ab und gibt bei Überlauf
   einen Fehler zurück statt einer verkürzten Summe.
2. **Neuer Hardfork-Parameter** `DF25Height` (`consensus/params.h`, `chainparams.cpp`, `-df25height` für regtest,
   `getblockchaininfo` → `df25upgrade`).
3. **Weiche** `CCustomTxVisitor::SumTransfers()`: ab `DF25Height` geprüfte Summe, darunter das alte Verhalten –
   damit alte Blöcke bei einer Neusynchronisation weiter gültig bleiben.
4. Die vier Pfade aus Abschnitt 2 verwenden die Weiche und lehnen die Transaktion bei Fehler ab.
   Ab DF6 ist eine fehlgeschlagene Custom-Transaktion „fatal“ → der ganze Block ist ungültig.
5. **Unit-Test** `src/test/balances_tests.cpp`: normaler Fall, Exploit-Fall (1 Sat + INT64_MAX),
   Mehr-Token-Fall, negativer Betrag.

Keine legitime Transaktion wird durch die Prüfung abgelehnt: negative Beträge scheitern schon heute bei der
Gutschrift/Abbuchung, Nullbeträge schon beim Einlesen, und eine echte Summe über INT64_MAX kann niemand decken.

## 4. Die Aktivierungshöhe – Entscheidung der SIG

Im Patch steht für Mainnet `DF25Height = 6566082` (markiert mit `TODO(SIG)`).

| Wert | Wirkung | Voraussetzung |
|---|---|---|
| **6.566.082** | Frühestmögliche Höhe, bei der alle bekannten Blöcke gültig bleiben. Jede **weitere** Überlauf-Transaktion ist ab sofort ungültig – auch eine, die bis zur Verteilung noch passiert (gepatchte Nodes verwerfen dann genau diesen Block). Die ≈ 184 Mrd. DFI beider Akteure bleiben bestehen → zusätzlich Entscheidung über Sperre/Burn nötig (Weg B). | Vor der Freigabe Scan bis zur aktuellen Spitze wiederholen (`df_overflow_scan.py`) |
| **6.564.035** | Beide Exploit-Blöcke werden ungültig (Weg A / „Bitcoin-Weg“). | Bereits synchronisierte Nodes werten alte Blöcke nicht neu aus → jeder Betreiber muss `invalidateblock 9561186a1ca841ee2bd56e6acab7c2f5082b23d8b43bd3a6a7ac4bae775bc5fc` (Hash von Block 6.564.035) ausführen; Koordination der Masternodes; siehe Abschnitt 5 |
| dazwischen (z. B. 6.564.036) | ergibt keinen Sinn: der zweite Exploit-Block würde trotzdem ungültig, der erste bliebe | – |

## 5. Hürden bei Weg A (aus dem Code, nicht getestet)

- **Kettenspitze zu alt**: Ein Masternode erzeugt keine Blöcke, solange der Node „im Aufholen“ ist
  (`IsInitialBlockDownload`, `miner.cpp`). Das gilt, wenn der letzte Block älter als `nMaxTipAge` ist –
  Standard **10 Stunden** (`DEFAULT_MAX_TIP_AGE = 10 * 60 * 60`, `validation.h`), nicht 24 h.
  Nach dem Zurücksetzen auf Block 6.564.034 (03.11. 00:13 UTC) braucht es daher z. B. `-maxtipage=604800`.
- **Anker / Checkpoints**: Trifft ein Node beim Verbinden auf „bad-custom-tx“, setzt `ActivateBestChainStep`
  auf den letzten Bitcoin-Anker bzw. Checkpoint unterhalb dieser Höhe zurück. Ob das bei einem bereits
  verbundenen Block greift und wie Anker nach Block 6.564.035 behandelt werden, muss die SIG auf regtest prüfen.
- **Mempool**: Normale Transaktionen aus den verworfenen Blöcken kommen über `UpdateMempoolForReorg` zurück;
  alles, was auf den erzeugten DFI aufbaut, wird ungültig.

## 6. Prüfung

- **Kompiliert gegen die echten Header** (`balances.h`, `amount.h`, `script.h`): Exploit-Fall ergibt mit der alten
  Funktion 1 Satoshi (Fehler nachgestellt), mit der neuen einen Fehler; Mehr-Token- und Negativ-Fall ebenso.
- **Syntaxprüfung** (`g++ -fsyntax-only`, C++17, Boost 1.83, aus `ain-rs-exports` erzeugter Rust-Header):
  `accounts.cpp`, `txvisitor.cpp`, `poolpairs.cpp`, `chainparams.cpp`, `rpc/blockchain.cpp`, `balances_tests.cpp` fehlerfrei.
- **Nicht gemacht**: kompletter Build von `defid` (C++ + Rust/EVM), Lauf der Unit-Tests im Test-Framework,
  Funktionstest auf regtest, Neusynchronisation des Mainnets mit dem Patch. Das muss die SIG vor einer Freigabe tun.
- **Scan der Chain** auf weitere Überlauf-Transaktionen: siehe `../02-scan/SCAN.md` (Skript `../02-scan/df_overflow_scan.py`,
  rein lesend über die öffentliche Ocean-RPC; gegen die Exploit-Transaktion geprüft).

## 7. Anwenden (für Entwickler)

```bash
git clone https://github.com/DeFiCh/ain.git && cd ain
git checkout v4.2.5
git am /pfad/0001-consensus-reject-overflowing-transfer-sums-SumAllTra.patch
./make.sh build          # bzw. der übliche Build der SIG
./build/src/test/test_defi --run_test=balances_tests
```

**Wichtig**: Keine selbst gebaute Binärdatei auf Masternodes einspielen, bevor die SIG Patch und Aktivierungshöhe
freigegeben hat – eine abweichende Konsensregel führt sonst zu einer eigenen Kette.
