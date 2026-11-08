#!/usr/bin/env python3
"""Check account-transfer block validation across a lab activation boundary.

Explicit invalidation/restart checks disconnect restoration; this does not
claim automatic competing-chain reorganization or mempool-transition coverage.
"""

from io import BytesIO
from decimal import Decimal
from pathlib import Path
import struct

from test_framework.blocktools import add_witness_commitment
from test_framework.lab_serialization import (
    TokenAwareTransaction,
    TokenAwareOutput,
)
from test_framework.messages import ser_compact_size, ser_string

from feature_transfer_sum_df24 import TransferSumDF24Test
from test_framework.lab_serialization import TokenAwareBlock as CBlock
from test_framework.util import assert_equal, wait_until


class TransferSumActivationTest(TransferSumDF24Test):
    def set_test_params(self):
        super().set_test_params()
        for args in self.extra_args:
            args.remove("-transferaggregationheight=10")
            args.append("-transferaggregationheight=105")

    def run_test(self):
        producer, receiver = self.nodes

        # Prevent P2P propagation; receiver gets blocks via submitblock only.
        producer.setnetworkactive(False)
        receiver.setnetworkactive(False)
        wait_until(lambda: receiver.getconnectioncount() == 0, timeout=30)

        producer.generate(101)

        self.log.info("Submitting initial chain directly to the second node")
        for height in range(1, producer.getblockcount() + 1):
            block_hash = producer.getblockhash(height)
            raw = producer.getblock(block_hash, 0)
            assert_equal(receiver.submitblock(raw), None)

        assert_equal(receiver.getbestblockhash(), producer.getbestblockhash())

        self.log.info("Checking DF24 block serialization round trip")
        producer.generate(1)
        block_hash = producer.getbestblockhash()
        raw = producer.getblock(block_hash, 0)
        stream = BytesIO(bytes.fromhex(raw))
        block = CBlock()
        block.deserialize(stream)

        assert_equal(stream.read(), b"")
        assert_equal(block.serialize().hex(), raw)
        assert_equal(block.calc_merkle_root(), block.hashMerkleRoot)

        self.log.info("Submitting round-tripped control block")
        assert_equal(receiver.submitblock(block.serialize().hex()), None)
        assert_equal(receiver.getbestblockhash(), block_hash)
        assert_equal(
            receiver.getblockchaininfo()["softforks"]["df24upgrade"]["active"],
            True,
        )


        self.log.info("Preparing account balances and authorization UTXO")
        source = producer.getnewaddress("", "legacy")
        recipients = [
            producer.getnewaddress("", "legacy"),
            producer.getnewaddress("", "legacy"),
        ]
        producer.utxostoaccount({source: "10@0"})
        auth_txid = producer.sendtoaddress(source, Decimal("1"))

        previous_height = receiver.getblockcount()
        producer.generate(1)
        for height in range(previous_height + 1, producer.getblockcount() + 1):
            raw = producer.getblock(producer.getblockhash(height), 0)
            assert_equal(receiver.submitblock(raw), None)

        assert_equal(receiver.getaccount(source), ["10.00000000@DFI"])
        auth_coins = [
            coin for coin in producer.listunspent(1)
            if coin["txid"] == auth_txid
            and coin.get("address") == source
            and coin["amount"] == Decimal("1")
        ]
        assert_equal(len(auth_coins), 1)
        auth = auth_coins[0]
        inputs = [{"txid": auth["txid"], "vout": auth["vout"]}]
        addresses = [source] + recipients

        source_script = bytes.fromhex(
            producer.getaddressinfo(source)["scriptPubKey"]
        )
        scripts = sorted(
            bytes.fromhex(producer.getaddressinfo(addr)["scriptPubKey"])
            for addr in recipients
        )

        def make_signed_transfer(amounts):
            payload = b"DfTxB" + ser_string(source_script)
            payload += ser_compact_size(len(scripts))
            for script, amount in zip(scripts, amounts):
                payload += ser_string(script)
                payload += ser_compact_size(1)
                payload += struct.pack("<I", 0)
                payload += struct.pack("<q", amount)
            raw = producer.createrawtransaction(
                inputs,
                [
                    {"data": payload.hex()},
                    {source: Decimal("0.99990000")},
                ],
            )
            signed = producer.signrawtransactionwithwallet(raw)
            assert_equal(signed["complete"], True)
            stream = BytesIO(bytes.fromhex(signed["hex"]))
            tx = TokenAwareTransaction()
            tx.deserialize(stream)
            assert_equal(stream.read(), b"")
            assert_equal(tx.serialize().hex(), signed["hex"])
            tx.rehash()
            assert_equal(
                tx.hash,
                producer.decoderawtransaction(signed["hex"])["txid"],
            )
            return tx

        activation = 105
        assert_equal(producer.getblockcount(), activation - 2)
        maximum = (1 << 63) - 1
        script_addresses = {
            bytes.fromhex(producer.getaddressinfo(addr)["scriptPubKey"]): addr
            for addr in recipients
        }
        small_address, large_address = [script_addresses[s] for s in scripts]

        def candidate(control_raw, tx):
            block = CBlock()
            block.deserialize(BytesIO(bytes.fromhex(control_raw)))
            block.vtx.append(tx)
            coinbase = block.vtx[0]
            prefix = bytes.fromhex("6a24aa21a9ed")
            if any(bytes(out.scriptPubKey).startswith(prefix) for out in coinbase.vout) or any(
                not item.wit.is_null() for item in block.vtx[1:]
            ):
                coinbase.vout = [out for out in coinbase.vout
                                 if not bytes(out.scriptPubKey).startswith(prefix)]
                add_witness_commitment(block)
                out = coinbase.vout[-1]
                if coinbase.nVersion >= 4:
                    coinbase.vout[-1] = TokenAwareOutput(out.nValue, out.scriptPubKey, 0)
                coinbase.rehash()
            block.hashMerkleRoot = block.calc_merkle_root()
            block.rehash()
            return block

        def restore_parent(block, before, auth_before):
            receiver.invalidateblock(block.hash)
            # Disconnecting a block may reinsert transactions into the mempool.
            # Restart without loading a persisted mempool to isolate block tests.
            self.restart_node(1, extra_args=self.extra_args[1] + ["-persistmempool=0"])
            receiver.setnetworkactive(False)
            wait_until(lambda: receiver.getconnectioncount() == 0, timeout=30)
            assert_equal(self.snapshot(addresses), before)
            assert_equal(receiver.gettxout(auth["txid"], auth["vout"]), auth_before)

        for height in [activation - 1, activation, activation + 1]:
            self.log.info("Checking block rules at height %s (activation %s)", height, activation)
            assert_equal(receiver.getblockcount(), height - 1)
            producer.generate(1)
            assert_equal(producer.getblockcount(), height)
            control_hash = producer.getbestblockhash()
            control_raw = producer.getblock(control_hash, 0)
            before = self.snapshot(addresses)
            auth_before = receiver.gettxout(auth["txid"], auth["vout"])
            assert_equal(auth_before is not None, True)

            for amounts in [(1, maximum), (maximum, 1)]:
                tx = make_signed_transfer(amounts)
                block = candidate(control_raw, tx)
                debug_path = Path(receiver.datadir) / "regtest" / "debug.log"
                offset = debug_path.stat().st_size
                result = receiver.submitblock(block.serialize().hex())
                self.log.info("height=%s amounts=%s submitblock=%s", height, amounts, result)
                if height < activation and amounts[0] == 1:
                    assert_equal(result, None)
                    assert_equal(receiver.getbestblockhash(), block.hash)
                    assert_equal(receiver.getaccount(source), ["9.99999999@DFI"])
                    assert_equal(receiver.getaccount(small_address), ["0.00000001@DFI"])
                    assert_equal(receiver.getaccount(large_address), ["92233720368.54775807@DFI"])
                    assert_equal(receiver.gettxout(auth["txid"], auth["vout"]), None)
                    self.log.info("Historical acceptance and exact resulting balances verified")
                    restore_parent(block, before, auth_before)
                else:
                    assert_equal(result, "bad-custom-tx")
                    reason = "less than" if height < activation else "overflow"
                    def has_expected_log():
                        with debug_path.open("rb") as log:
                            log.seek(offset)
                            lines = log.read().decode(errors="replace").splitlines()
                        return any(tx.hash in line and "failed with" in line
                                   and reason in line for line in lines)
                    wait_until(has_expected_log, timeout=10)
                    assert_equal(self.snapshot(addresses), before)
                    assert_equal(receiver.gettxout(auth["txid"], auth["vout"]), auth_before)
                    self.log.info("Rejection reason and unchanged observed state verified: %s", reason)

            # A real valid transfer must succeed under both rule sets.
            valid_tx = make_signed_transfer([100000000, 100000000])
            valid_block = candidate(control_raw, valid_tx)
            assert_equal(receiver.submitblock(valid_block.serialize().hex()), None)
            assert_equal(receiver.getbestblockhash(), valid_block.hash)
            assert_equal(receiver.getaccount(source), ["8.00000000@DFI"])
            for address in recipients:
                assert_equal(receiver.getaccount(address), ["1.00000000@DFI"])
            assert_equal(receiver.gettxout(auth["txid"], auth["vout"]), None)
            self.log.info("Valid transfer accepted at height %s; checking disconnect restoration", height)
            restore_parent(valid_block, before, auth_before)

            assert_equal(receiver.submitblock(control_raw), None)
            assert_equal(receiver.getbestblockhash(), control_hash)
            assert_equal(receiver.getaccount(source), ["10.00000000@DFI"])
            for address in recipients:
                assert_equal(receiver.getaccount(address), [])
            assert_equal(receiver.gettxout(auth["txid"], auth["vout"]) is not None, True)

        self.log.info("Node-level H-1/H/H+1 checks and explicit disconnect controls passed")


if __name__ == "__main__":
    TransferSumActivationTest().main()
