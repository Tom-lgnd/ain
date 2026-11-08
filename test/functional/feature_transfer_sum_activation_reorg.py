#!/usr/bin/env python3
"""Test automatic competing-chain reorganization across lab activation H=105."""

from io import BytesIO
from decimal import Decimal
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


class TransferSumActivationReorgTest(TransferSumDF24Test):
    def set_test_params(self):
        super().set_test_params()
        self.num_nodes = 3
        self.extra_args.append(list(self.extra_args[0]))
        for args in self.extra_args:
            args.remove("-transferaggregationheight=10")
            args.append("-transferaggregationheight=105")

    def run_test(self):
        producer, alternate, receiver = self.nodes

        # Isolate all nodes; blocks are exchanged explicitly via submitblock.
        alternate.setnetworkactive(False)
        producer.setnetworkactive(False)
        receiver.setnetworkactive(False)
        wait_until(lambda: all(node.getconnectioncount() == 0 for node in self.nodes), timeout=30)

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
        parent_height = activation - 2
        assert_equal(producer.getblockcount(), parent_height)
        # The third node starts from exactly the same funded parent.
        for height in range(1, parent_height + 1):
            raw = producer.getblock(producer.getblockhash(height), 0)
            assert_equal(alternate.submitblock(raw), None)
        parent_hash = producer.getbestblockhash()
        for node in self.nodes:
            assert_equal(node.getbestblockhash(), parent_hash)
            assert_equal(node.getaccount(source), ["10.00000000@DFI"])

        script_addresses = {
            bytes.fromhex(producer.getaddressinfo(addr)["scriptPubKey"]): addr
            for addr in recipients
        }
        small_address, large_address = [script_addresses[s] for s in scripts]
        # Sign both transactions while the common authorization coin is unspent.
        legacy_tx = make_signed_transfer([1, (1 << 63) - 1])
        valid_tx = make_signed_transfer([100000000, 100000000])

        # Build fork A's historical block at H-1 using an empty valid template.
        producer.generate(1)
        template_hash = producer.getbestblockhash()
        historical_block = CBlock()
        historical_block.deserialize(BytesIO(bytes.fromhex(producer.getblock(template_hash, 0))))
        historical_block.vtx.append(legacy_tx)
        prefix = bytes.fromhex("6a24aa21a9ed")
        coinbase = historical_block.vtx[0]
        if any(bytes(out.scriptPubKey).startswith(prefix) for out in coinbase.vout) or any(
            not tx.wit.is_null() for tx in historical_block.vtx[1:]
        ):
            coinbase.vout = [out for out in coinbase.vout
                             if not bytes(out.scriptPubKey).startswith(prefix)]
            add_witness_commitment(historical_block)
            out = coinbase.vout[-1]
            if coinbase.nVersion >= 4:
                coinbase.vout[-1] = TokenAwareOutput(out.nValue, out.scriptPubKey, 0)
            coinbase.rehash()
        historical_block.hashMerkleRoot = historical_block.calc_merkle_root()
        historical_block.rehash()

        # Only the producer discards a template. Receiver reorganizations below
        # are driven solely by submitblock and strictly greater chainwork.
        producer.invalidateblock(template_hash)
        assert_equal(producer.getbestblockhash(), parent_hash)
        assert_equal(producer.submitblock(historical_block.serialize().hex()), None)
        assert_equal(producer.getbestblockhash(), historical_block.hash)
        producer.generate(2)
        assert_equal(producer.getblockcount(), activation + 1)

        def feed_fork(node, first_height):
            for height in range(first_height, node.getblockcount() + 1):
                raw = node.getblock(node.getblockhash(height), 0)
                result = receiver.submitblock(raw)
                self.log.info("Fork block height=%s submitblock=%s", height, result)
                assert_equal(result in (None, "inconclusive"), True)
            assert_equal(receiver.getbestblockhash(), node.getbestblockhash())

        def check_state(historical):
            assert_equal(receiver.getaccount(source),
                         ["9.99999999@DFI"] if historical else ["8.00000000@DFI"])
            assert_equal(receiver.getaccount(small_address),
                         ["0.00000001@DFI"] if historical else ["1.00000000@DFI"])
            assert_equal(receiver.getaccount(large_address),
                         ["92233720368.54775807@DFI"] if historical else ["1.00000000@DFI"])
            assert_equal(receiver.gettxout(auth["txid"], auth["vout"]), None)
            assert_equal(receiver.gettxout(legacy_tx.hash, 1) is not None, historical)
            assert_equal(receiver.gettxout(valid_tx.hash, 1) is not None, not historical)
            assert_equal(receiver.getrawmempool(), [])

        def require_stronger(node):
            assert_equal(
                int(node.getblockchaininfo()["chainwork"], 16)
                > int(receiver.getblockchaininfo()["chainwork"], 16), True)

        self.log.info("Adopting fork A through H+1, including the historical H-1 transfer")
        feed_fork(producer, parent_height + 1)
        check_state(True)

        self.log.info("Building fork B with a valid H-1 transfer and greater chainwork")
        alternate.sendrawtransaction(valid_tx.serialize().hex())
        alternate.generate(4)
        assert_equal(alternate.getblockcount(), activation + 2)
        require_stronger(alternate)
        feed_fork(alternate, parent_height + 1)
        check_state(False)
        self.log.info("Automatic A-to-B reorganization restored balances and selected UTXOs")

        self.log.info("Extending fork A to force historical H-1 replay while tip is above H")
        producer.generate(2)
        assert_equal(producer.getblockcount(), activation + 3)
        require_stronger(producer)
        feed_fork(producer, activation + 2)
        check_state(True)
        self.log.info("Automatic B-to-A reorganization replayed the historical rule correctly")

        def replay_snapshot():
            return {
                "tip": receiver.getbestblockhash(),
                "height": receiver.getblockcount(),
                "chainwork": receiver.getblockchaininfo()["chainwork"],
                "accounts": [receiver.getaccount(addr) for addr in addresses],
                "auth": receiver.gettxout(auth["txid"], auth["vout"]),
                "legacy_change": receiver.gettxout(legacy_tx.hash, 1),
                "valid_change": receiver.gettxout(valid_tx.hash, 1),
                "mempool": sorted(receiver.getrawmempool()),
            }

        # Fork A is active at H+3 and contains the historical transfer at H-1.
        # Replay must use each block's height rather than the current tip height.
        expected_replay = replay_snapshot()
        assert_equal(expected_replay["height"], activation + 3)
        for mode in ["-reindex-chainstate", "-reindex"]:
            self.log.info("Rebuilding historical branch with %s", mode)
            self.restart_node(
                2, extra_args=self.extra_args[2] + [mode, "-persistmempool=0"])
            receiver.setnetworkactive(False)
            wait_until(lambda: receiver.getconnectioncount() == 0, timeout=30)
            wait_until(lambda: receiver.getbestblockhash() == expected_replay["tip"], timeout=120)
            check_state(True)
            assert_equal(replay_snapshot(), expected_replay)
            self.log.info("%s preserved the tip and all checked balances/UTXOs", mode)

        alternate.generate(2)
        assert_equal(alternate.getblockcount(), activation + 4)
        require_stronger(alternate)
        feed_fork(alternate, activation + 3)
        check_state(False)
        self.log.info("Second automatic A-to-B switch restored the valid branch state")

        # Receiver must now match the independently maintained fork B reference.
        for address in addresses:
            assert_equal(receiver.getaccount(address), alternate.getaccount(address))
        assert_equal(receiver.getblockchaininfo()["chainwork"],
                     alternate.getblockchaininfo()["chainwork"])
        self.log.info("Competing-chain activation reorganization checks passed")


if __name__ == "__main__":
    TransferSumActivationReorgTest().main()
