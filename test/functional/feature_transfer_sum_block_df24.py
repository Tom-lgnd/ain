#!/usr/bin/env python3
"""Validate DF24 block serialization and direct block submission."""

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


class TransferSumBlockDF24Test(TransferSumDF24Test):
    def set_test_params(self):
        super().set_test_params()

    def run_test(self):
        producer, receiver = self.nodes

        # Prevent P2P propagation; receiver gets blocks via submitblock only.
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

        # Producer builds a valid next block; receiver stays at its parent.
        producer.generate(1)
        control_hash = producer.getbestblockhash()
        control_raw = producer.getblock(control_hash, 0)

        maximum = (1 << 63) - 1
        for amounts in [(1, maximum), (maximum, 1)]:
            self.log.info("Checking full-block overflow rejection: %s", amounts)
            tx = make_signed_transfer(amounts)
            bad_block = CBlock()
            bad_block.deserialize(BytesIO(bytes.fromhex(control_raw)))
            bad_block.vtx.append(tx)

            # Refresh any witness commitment after changing transactions.
            prefix = bytes.fromhex("6a24aa21a9ed")
            coinbase = bad_block.vtx[0]
            has_commitment = any(
                bytes(out.scriptPubKey).startswith(prefix)
                for out in coinbase.vout
            )
            if has_commitment or any(
                not item.wit.is_null() for item in bad_block.vtx[1:]
            ):
                coinbase.vout = [
                    out for out in coinbase.vout
                    if not bytes(out.scriptPubKey).startswith(prefix)
                ]
                add_witness_commitment(bad_block)
                output = coinbase.vout[-1]
                if coinbase.nVersion >= 4:
                    coinbase.vout[-1] = TokenAwareOutput(
                        output.nValue, output.scriptPubKey, 0
                    )
                coinbase.rehash()

            bad_block.hashMerkleRoot = bad_block.calc_merkle_root()
            bad_block.rehash()

            before = self.snapshot(addresses)
            auth_before = receiver.gettxout(auth["txid"], auth["vout"])
            assert_equal(auth_before is not None, True)

            result = receiver.submitblock(bad_block.serialize().hex())
            self.log.info(
                "Block submission observation: %s",
                {
                    "rpc_result": result,
                    "candidate_hash": bad_block.hash,
                    "receiver_tip": receiver.getbestblockhash(),
                    "candidate_is_tip":
                        receiver.getbestblockhash() == bad_block.hash,
                    "receiver_accounts_before": before[1]["accounts"],
                    "receiver_accounts_after": [
                        receiver.getaccount(address) for address in addresses
                    ],
                    "authorization_utxo_unspent":
                        receiver.gettxout(auth["txid"], auth["vout"]) is not None,
                },
            )
            assert_equal(result, "bad-custom-tx")

            debug_log = (
                Path(receiver.datadir) / "regtest" / "debug.log"
            ).read_text(errors="replace")
            matching = [
                line for line in debug_log.splitlines()
                if tx.hash in line
                and "failed with" in line
                and "overflow" in line
            ]
            assert_equal(bool(matching), True)
            self.log.info("Verified rejection reason: %s", matching[-1])

            assert_equal(self.snapshot(addresses), before)
            assert_equal(
                receiver.gettxout(auth["txid"], auth["vout"]), auth_before
            )

        self.log.info("Accepting unchanged control block after rejection")
        assert_equal(receiver.submitblock(control_raw), None)
        assert_equal(receiver.getbestblockhash(), control_hash)
        assert_equal(receiver.getaccount(source), ["10.00000000@DFI"])

        self.log.info("Checking valid raw transfer after block rejection")
        valid = make_signed_transfer([100000000, 100000000])
        producer.sendrawtransaction(valid.serialize().hex())
        previous_height = receiver.getblockcount()
        producer.generate(1)
        for height in range(previous_height + 1, producer.getblockcount() + 1):
            raw = producer.getblock(producer.getblockhash(height), 0)
            assert_equal(receiver.submitblock(raw), None)

        for peer in self.nodes:
            assert_equal(peer.getaccount(source), ["8.00000000@DFI"])
            for address in recipients:
                assert_equal(peer.getaccount(address), ["1.00000000@DFI"])
            assert_equal(peer.gettxout(auth["txid"], auth["vout"]), None)


if __name__ == "__main__":
    TransferSumBlockDF24Test().main()
