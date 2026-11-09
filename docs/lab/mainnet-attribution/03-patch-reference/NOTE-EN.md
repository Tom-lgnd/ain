# Patch reference (draft of 2026-11-04) – English note

**Status**: reference only. Prepared with AI assistance (Claude), never built as a full `defid`, never run on regtest. The work by M J (lab-tested, activation height, reorg tests) and PR #3135 (12 call sites, functional test) are further along. The German `README-patch-de.md` has the full explanation.

## What it does

- New `SumAllTransfersChecked()` in `balances.h`: rejects amounts ≤ 0 and returns an error on overflow instead of a truncated sum.
- New hardfork parameter `DF25Height` (`consensus/params.h`, `chainparams.cpp`, `-df25height` for regtest, `df25upgrade` in `getblockchaininfo`).
- Switch `CCustomTxVisitor::SumTransfers()`: checked sum from `DF25Height`, old behaviour below, so historic blocks stay valid on resync.
- Used in all four consensus paths: `AccountToAccount`, `AnyAccountsToAccounts`, `UtxosToAccount` (inflation possible **without** any account balance) and `AddPoolLiquidity` (no inflation, but the pool receives less than is debited).
- Unit test `src/test/balances_tests.cpp`: normal case, exploit case (1 sat + INT64_MAX), multi-token case, negative amount.
- RPC/display call sites (`rpc_accounts.cpp`, `mn_rpc.cpp`, `rpc_customtx.cpp`) are **not** changed; PR #3135 covers them.

## Activation height

Mainnet value in the patch: `DF25Height = 6566082` (marked `TODO(SIG)`), the earliest height that invalidates no known block. `6564035` would invalidate both exploit blocks (rollback); already-synced nodes would then also need `invalidateblock` on block 6,564,035 and a coordinated `-maxtipage`.

## Apply

```bash
git clone https://github.com/DeFiCh/ain.git && cd ain
git checkout v4.2.5
git am 0001-consensus-reject-overflowing-transfer-sums-SumAllTra.patch
```
