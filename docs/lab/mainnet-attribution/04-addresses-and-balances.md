# Adressen und Bestände / Addresses and balances (für Clawback / Sperre – for clawback / freeze design)

**Stand / As of**: 09.11.2026 12:53 UTC, Kettenspitze / chain tip 6,582,480. Quelle / source: public Ocean API (`/address/<a>/balance`, `/address/<a>/tokens`).
Nur öffentliche On-Chain-Daten. Keine Aussagen über Personen. / Public on-chain data only. No statements about persons.

---

## Deutsch

### Wichtig für einen Clawback

Die erzeugten DFI liegen **nicht nur im Kontoguthaben** (Account-Modell), sondern teilweise schon als **UTXO** (Coins). Ein Clawback, der nur die Kontoguthaben entfernt, ließe die Coins übrig. 47 Mio. DFI als UTXO reichen für rund 2.350 Masternodes (20.000 DFI je Masternode). Ein Entwurf muss daher entweder

- auch die UTXOs dieser Scripts erfassen (z. B. Ausgaben dieser Scripts ab der Aktivierungshöhe ungültig) **oder**
- als Ausgabesperre statt Löschung gebaut sein,

und er muss `AccountToUtxos`, Pool-, Vault- und Masternode-Wege dieser Scripts mit abdecken.

### Akteur 1 (Block 6.564.035)

| Rolle | Adresse | Konto (DFI) | UTXO (DFI) |
|---|---|---|---|
| Empfänger der erzeugten DFI | `df1qel8g4g4f66qxr7cw0t03jkz08cj095vup2jhuy` | 92.123.620.368,54776001 | **47.000.009,99998350** |
| Absender | `df1qqgvcp6hctkgd3rqwvd965kaxm8r72xwfzmfs6n` | 0 | 215.938,99997660 |
| Empfänger 1 Satoshi | `df1q3dxfae3h9gl5n7nrqatx7fqc47t0d9sh8r0cue` | 0,00000001 | 0 |

Von den erzeugten 92.233.720.368,54775807 DFI wurden ≈ 110,1 Mio. in UTXO umgewandelt. Davon gingen rund 62,9 Mio. an eine Einzahlungsadresse, die nach den Zahlungsmustern einer Börse zuzuordnen ist (siehe unten). 47,0 Mio. liegen noch beim Empfänger.

### Akteur 2 (Block 6.566.081)

| Rolle | Adresse | Konto | UTXO (DFI) |
|---|---|---|---|
| Empfänger der erzeugten DFI | `df1qqtlz4uw9w5s4pupwgucv4shl6atqw7xlz2wn07` | 92.233.720.364,08003235 DFI; 0,0969845 DUSD; 0,0001956 MSTR | 0,99643569 |
| Absender (−8,00000001 DFI) | `df1qe9eus79waxmwu8ntjgsjjtspv9hs9kmr8y44x2` | 14,99499437 DFI; 131,93915207 DUSD; 0,1 COIN | 363,25721976 |
| Empfänger 8,00000001 DFI | `df1qq9njtz5ednqandfsjjlqdsqa73n6es8h6gapdz` | 8,00000001 DFI; 30.000 DUSD | 85,26746424 |

Die erzeugten DFI von Akteur 2 sind seit Block 6.566.081 **unbewegt**. Absender- und Kleinbetrag-Adresse halten auch Altbestände, die nicht aus dem Überlauf stammen. Eine Sperre sollte daher nur das erzeugte Guthaben betreffen, nicht pauschal ganze Adressen.

### Bereits weitergeflossene DFI (Börse)

| Adresse | Einordnung | UTXO (DFI) |
|---|---|---|
| `8FoE9hStpZWCiptybVKsvXMq2SKEaUgRf2` | Einzahlungsadresse, Empfänger von ≈ 62,9 Mio. DFI aus Akteur 1 (*aus Zahlungsmustern abgeleitet: Börse*) | 0 |
| `8SYMR5DF2nyRy9PwhcdmHcmvP3gh6swopD` | Sammeladresse derselben Börse (*abgeleitet*), dort mit Kundengeldern **vermischt** | 65.912.953,87555347 |

- Am 04.11.2026 wurden von der Sammeladresse 6,77 Mio. DFI an Dritte ausgezahlt. Die Empfängeradressen sind hier **bewusst nicht aufgeführt**: Die Empfänger sind unbekannt und können unbeteiligte Kunden sein.
- Per Konsensregel lassen sich vermischte Börsenbestände kaum sauber trennen. Wie damit umgegangen wird, ist eine eigene Entscheidung, die die Börse einbeziehen muss.

---

## English

### Key point for a clawback

The created DFI are **not only held as account balances**; part has already been converted to **UTXOs** (coins). A clawback that only removes account balances leaves the coins in place. 47 M DFI in UTXOs are enough for about 2,350 masternodes (20,000 DFI each). A design should therefore either

- also cover the UTXOs of these scripts (e.g. spends from these scripts invalid from the activation height) **or**
- be built as a spend freeze instead of a deletion,

and it must cover `AccountToUtxos`, pool, vault and masternode paths of these scripts.

### Actor 1 (block 6,564,035)

| Role | Address | Account (DFI) | UTXO (DFI) |
|---|---|---|---|
| Recipient of created DFI | `df1qel8g…2jhuy` | 92,123,620,368.54776001 | **47,000,009.99998350** |
| Source | `df1qqgvcp…zmfs6n` | 0 | 215,938.99997660 |
| 1-satoshi recipient | `df1q3dxfae…r0cue` | 0.00000001 | 0 |

Of the 92,233,720,368.54775807 DFI created, ≈ 110.1 M were converted to UTXOs; about 62.9 M went to a deposit address that payment patterns attribute to an exchange; 47.0 M remain with the recipient.

### Actor 2 (block 6,566,081)

| Role | Address | Account | UTXO (DFI) |
|---|---|---|---|
| Recipient of created DFI | `df1qqtlz…z2wn07` | 92,233,720,364.08003235 DFI (+ dust DUSD, MSTR) | 0.99643569 |
| Source (−8.00000001 DFI) | `df1qe9eus…r8y44x2` | 14.99499437 DFI; 131.93915207 DUSD; 0.1 COIN | 363.25721976 |
| 8.00000001-DFI recipient | `df1qq9njtz…h6gapdz` | 8.00000001 DFI; 30,000 DUSD | 85.26746424 |

Actor 2's created DFI have **not moved** since block 6,566,081. The source and small-amount addresses also hold pre-existing funds that do not stem from the overflow; a freeze should target the created balance, not whole addresses indiscriminately.

### DFI that already moved on (exchange)

| Address | Assessment | UTXO (DFI) |
|---|---|---|
| `8FoE9h…Rf2` | deposit address, received ≈ 62.9 M DFI from actor 1 (*inferred from payment patterns: exchange*) | 0 |
| `8SYMR5…opD` | collection address of the same exchange (*inferred*), **mixed** with customer funds | 65,912,953.87555347 |

- On 2026-11-04, 6.77 M DFI were withdrawn from the collection address to third parties. Those recipient addresses are **deliberately not listed**: the recipients are unknown and may be uninvolved customers.
- Mixed exchange holdings can hardly be separated cleanly by a consensus rule. How to handle them is a separate decision that has to involve the exchange.
