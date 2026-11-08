#!/usr/bin/env python3
"""Verify raw account-transfer rejection under the DF24 lab profile."""

import struct
from decimal import Decimal

from feature_transfer_sum_df24 import TransferSumDF24Test
from test_framework.messages import ser_compact_size, ser_string
from test_framework.util import assert_equal, assert_raises_rpc_error


class TransferSumRawDF24Test(TransferSumDF24Test):
    def set_test_params(self):
        super().set_test_params()

    def run_test(self):
        node = self.nodes[0]
        node.generate(101)
        self.sync_blocks()

        source = node.getnewaddress("", "legacy")
        recipients = [
            node.getnewaddress("", "legacy"),
            node.getnewaddress("", "legacy"),
        ]
        addresses = [source] + recipients

        node.utxostoaccount({source: "10@0"})
        auth_txid = node.sendtoaddress(source, Decimal("1"))
        node.generate(1)
        self.sync_all()
        assert_equal(node.getaccount(source), ["10.00000000@DFI"])

        auth_coins = [
            coin for coin in node.listunspent(1)
            if coin["txid"] == auth_txid
            and coin.get("address") == source
            and coin["amount"] == Decimal("1")
        ]
        assert_equal(len(auth_coins), 1)
        auth = auth_coins[0]
        inputs = [{"txid": auth["txid"], "vout": auth["vout"]}]

        source_script = bytes.fromhex(
            node.getaddressinfo(source)["scriptPubKey"]
        )
        recipient_scripts = sorted(
            bytes.fromhex(node.getaddressinfo(addr)["scriptPubKey"])
            for addr in recipients
        )

        def signed_transfer(amounts):
            # AccountToAccount metadata: source script, recipient map.
            payload = b"DfTxB" + ser_string(source_script)
            payload += ser_compact_size(len(recipient_scripts))
            for script, amount in zip(recipient_scripts, amounts):
                payload += ser_string(script)
                payload += ser_compact_size(1)
                payload += struct.pack("<I", 0)  # DFI token identifier.
                payload += struct.pack("<q", amount)

            raw = node.createrawtransaction(
                inputs,
                [
                    {"data": payload.hex()},
                    {source: Decimal("0.99990000")},
                ],
            )
            signed = node.signrawtransactionwithwallet(raw)
            assert_equal(signed["complete"], True)
            return signed["hex"]

        maximum = (1 << 63) - 1
        for amounts in [(1, maximum), (maximum, 1)]:
            self.log.info("Checking raw transfer overflow: %s", amounts)
            signed = signed_transfer(amounts)
            before = self.snapshot(addresses)
            coins_before = [
                peer.gettxout(auth["txid"], auth["vout"])
                for peer in self.nodes
            ]
            for peer in self.nodes:
                assert_raises_rpc_error(
                    -26, "overflow", peer.sendrawtransaction, signed
                )
            assert_equal(self.snapshot(addresses), before)
            assert_equal(
                [
                    peer.gettxout(auth["txid"], auth["vout"])
                    for peer in self.nodes
                ],
                coins_before,
            )

        self.log.info("Checking valid raw transfer control")
        signed = signed_transfer([100000000, 100000000])
        txid = node.sendrawtransaction(signed)
        assert_equal(txid in node.getrawmempool(), True)
        node.generate(1)
        self.sync_all()

        for peer in self.nodes:
            assert_equal(peer.getaccount(source), ["8.00000000@DFI"])
            for recipient in recipients:
                assert_equal(
                    peer.getaccount(recipient), ["1.00000000@DFI"]
                )
            assert_equal(peer.gettxout(auth["txid"], auth["vout"]), None)


if __name__ == "__main__":
    TransferSumRawDF24Test().main()
