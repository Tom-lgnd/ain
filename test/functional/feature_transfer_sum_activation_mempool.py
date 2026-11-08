#!/usr/bin/env python3
"""Check prospective-height admission and pending entries at lab activation."""

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
from test_framework.util import assert_equal, assert_raises_rpc_error, wait_until


class TransferSumActivationMempoolTest(TransferSumDF24Test):
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
        def lock_auth_output(txid):
            script = producer.getaddressinfo(source)["scriptPubKey"]
            raw = producer.gettransaction(txid)["hex"]
            outputs = producer.decoderawtransaction(raw)["vout"]
            matches = [
                {"txid": txid, "vout": out["n"]}
                for out in outputs
                if out["scriptPubKey"]["hex"] == script
                and out["value"] == Decimal("1")
            ]
            assert_equal(len(matches), 1)
            assert_equal(producer.lockunspent(False, matches), True)
            return matches[0]

        auth_txid = producer.sendtoaddress(source, Decimal("1"))
        locked_auth = lock_auth_output(auth_txid)
        second_auth_txid = producer.sendtoaddress(source, Decimal("1"))
        locked_second = lock_auth_output(second_auth_txid)
        independent_auth_txid = producer.sendtoaddress(source, Decimal("1"))
        assert_equal(producer.lockunspent(True, [locked_auth, locked_second]), True)

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

        def make_signed_transfer(amounts, selected_inputs=None):
            payload = b"DfTxB" + ser_string(source_script)
            payload += ser_compact_size(len(scripts))
            for script, amount in zip(scripts, amounts):
                payload += ser_string(script)
                payload += ser_compact_size(1)
                payload += struct.pack("<I", 0)
                payload += struct.pack("<q", amount)
            raw = producer.createrawtransaction(
                inputs if selected_inputs is None else selected_inputs,
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
        assert_equal(receiver.getblockcount(), activation - 2)
        second_coins = [
            coin for coin in producer.listunspent(1)
            if coin["txid"] == second_auth_txid
            and coin.get("address") == source
            and coin["amount"] == Decimal("1")
        ]
        assert_equal(len(second_coins), 1)
        second_auth = second_coins[0]
        second_inputs = [{"txid": second_auth["txid"], "vout": second_auth["vout"]}]
        maximum = (1 << 63) - 1
        pending = make_signed_transfer([1, maximum])
        probe = make_signed_transfer([1, maximum], second_inputs)
        valid = make_signed_transfer([100000000, 100000000])
        independent_coins = [coin for coin in producer.listunspent(1)
                             if coin["txid"] == independent_auth_txid
                             and coin.get("address") == source]
        assert_equal(len(independent_coins), 1)
        independent_auth = independent_coins[0]

        def sign_payment(txid, vout, input_amount, output_amount):
            raw = producer.createrawtransaction(
                [{"txid": txid, "vout": vout}], [{source: output_amount}])
            signed = producer.signrawtransactionwithwallet(raw, [{
                "txid": txid, "vout": vout,
                "scriptPubKey": source_script.hex(), "amount": input_amount,
            }])
            assert_equal(signed["complete"], True)
            return signed["hex"], producer.decoderawtransaction(signed["hex"])["txid"]

        child_hex, child_hash = sign_payment(
            pending.hash, 1, Decimal("0.99990000"), Decimal("0.99980000"))
        independent_hex, independent_hash = sign_payment(
            independent_auth["txid"], independent_auth["vout"],
            Decimal("1"), Decimal("0.99990000"))

        # Producer builds an empty H-1 block while the isolated receiver is at H-2.
        # Both authorization coins remain unspent in this control block.
        producer.generate(1)
        assert_equal(producer.getblockcount(), activation - 1)
        control_hash = producer.getbestblockhash()
        control_raw = producer.getblock(control_hash, 0)
        chain_balances = [receiver.getaccount(addr) for addr in addresses]
        def chain_coin(coin):
            value = receiver.gettxout(coin["txid"], coin["vout"], False)
            if value is None:
                return None
            # Confirmations and bestblock legitimately change when the tip advances.
            return {key: val for key, val in value.items()
                    if key not in ("confirmations", "bestblock")}

        original_auth = chain_coin(auth)
        original_second_auth = chain_coin(second_auth)

        self.log.info("Checking legacy admission at tip H-2 for prospective block H-1")
        assert_equal(receiver.sendrawtransaction(pending.serialize().hex()), pending.hash)
        assert_equal(pending.hash in receiver.getrawmempool(), True)
        assert_equal(receiver.sendrawtransaction(child_hex), child_hash)
        assert_equal(receiver.sendrawtransaction(independent_hex), independent_hash)
        assert_equal(sorted(receiver.getrawmempool()),
                     sorted([pending.hash, child_hash, independent_hash]))
        assert_equal([receiver.getaccount(addr) for addr in addresses], chain_balances)
        assert_equal(chain_coin(auth), original_auth)

        self.log.info("Advancing to tip H-1 without mining the pending transaction")
        assert_equal(receiver.submitblock(control_raw), None)
        assert_equal(receiver.getbestblockhash(), control_hash)
        immediately_after = receiver.getrawmempool()
        self.log.info("Pending legacy transaction present immediately after tip change: %s",
                      pending.hash in immediately_after)
        assert_equal([receiver.getaccount(addr) for addr in addresses], chain_balances)
        assert_equal(chain_coin(auth), original_auth)

        # A separate auth input avoids confusing an overflow rejection with a
        # mempool double-spend conflict involving the old pending transaction.
        self.log.info("Checking strict admission at tip H-1 for prospective block H")
        assert_raises_rpc_error(-26, "overflow", receiver.sendrawtransaction, probe.serialize().hex())
        after_probe = receiver.getrawmempool()
        self.log.info("Pending legacy transaction present after account-view rebuild: %s",
                      pending.hash in after_probe)
        assert_equal(probe.hash in after_probe, False)
        assert_equal([receiver.getaccount(addr) for addr in addresses], chain_balances)
        assert_equal(chain_coin(second_auth),
                     original_second_auth)
        assert_equal(pending.hash in after_probe, False)
        assert_equal(child_hash in after_probe, False)
        assert_equal(independent_hash in after_probe, True)
        self.log.info("Invalid parent and descendant removed; independent entry retained")

        self.log.info("Checking valid replacement transfer and block generation at H")
        assert_equal(receiver.sendrawtransaction(valid.serialize().hex()), valid.hash)
        assert_equal(valid.hash in receiver.getrawmempool(), True)
        receiver.generate(1)
        assert_equal(receiver.getblockcount(), activation)
        block_hash = receiver.getbestblockhash()
        block = receiver.getblock(block_hash)
        assert_equal(valid.hash in block["tx"], True)
        assert_equal(pending.hash in block["tx"], False)
        assert_equal(probe.hash in block["tx"], False)
        assert_equal(child_hash in block["tx"], False)
        assert_equal(independent_hash in block["tx"], True)
        assert_equal(receiver.getrawmempool(), [])
        assert_equal(receiver.getaccount(source), ["8.00000000@DFI"])
        for address in recipients:
            assert_equal(receiver.getaccount(address), ["1.00000000@DFI"])
        assert_equal(chain_coin(auth), None)
        assert_equal(chain_coin(second_auth) is not None, True)

        assert_equal(producer.submitblock(receiver.getblock(block_hash, 0)), None)
        assert_equal(producer.getbestblockhash(), block_hash)
        for address in addresses:
            assert_equal(producer.getaccount(address), receiver.getaccount(address))
        self.log.info("Prospective-height admission, pending-entry cleanup and valid mining checks passed")

        self.log.info("Disconnecting back to H-2; checking valid mempool resurrection")
        receiver.invalidateblock(control_hash)
        assert_equal(receiver.getblockcount(), activation - 2)
        resurrected = receiver.getrawmempool()
        assert_equal(valid.hash in resurrected, True)
        assert_equal(independent_hash in resurrected, True)
        assert_equal(receiver.getaccount(source), ["10.00000000@DFI"])
        for address in recipients:
            assert_equal(receiver.getaccount(address), [])

        # Fresh destinations prevent the valid resurrected account transfer
        # from causing an unrelated recipient-balance overflow in this probe.
        reverse_recipients = [producer.getnewaddress("", "legacy") for _ in range(2)]
        scripts = sorted(bytes.fromhex(producer.getaddressinfo(addr)["scriptPubKey"])
                         for addr in reverse_recipients)
        reverse_pending = make_signed_transfer([1, maximum], second_inputs)
        reverse_child_hex, reverse_child_hash = sign_payment(
            reverse_pending.hash, 1, Decimal("0.99990000"), Decimal("0.99980000"))
        self.log.info("Checking restored historical admission below activation")
        assert_equal(receiver.sendrawtransaction(reverse_pending.serialize().hex()), reverse_pending.hash)
        assert_equal(receiver.sendrawtransaction(reverse_child_hex), reverse_child_hash)
        restored_pool = receiver.getrawmempool()
        for txid in [valid.hash, independent_hash, reverse_pending.hash, reverse_child_hash]:
            assert_equal(txid in restored_pool, True)
        assert_equal(receiver.getaccount(source), ["10.00000000@DFI"])
        for address in recipients + reverse_recipients:
            assert_equal(receiver.getaccount(address), [])
        assert_equal(chain_coin(second_auth), original_second_auth)

        self.log.info("Reconnecting the valid branch across H; checking renewed eviction")
        receiver.reconsiderblock(control_hash)
        assert_equal(receiver.getbestblockhash(), block_hash)
        assert_equal(receiver.getblockcount(), activation)
        assert_equal(receiver.getrawmempool(), [])
        assert_equal(receiver.getaccount(source), ["8.00000000@DFI"])
        for address in recipients:
            assert_equal(receiver.getaccount(address), ["1.00000000@DFI"])
        for address in reverse_recipients:
            assert_equal(receiver.getaccount(address), [])
        assert_equal(chain_coin(second_auth), original_second_auth)
        assert_equal(chain_coin(auth), None)
        assert_raises_rpc_error(-26, "overflow", receiver.sendrawtransaction,
                                reverse_pending.serialize().hex())
        assert_equal(receiver.getrawmempool(), [])
        for address in addresses + reverse_recipients:
            assert_equal(receiver.getaccount(address), producer.getaccount(address))
        self.log.info("Reverse-transition resurrection and renewed forward cleanup checks passed")


if __name__ == "__main__":
    TransferSumActivationMempoolTest().main()
