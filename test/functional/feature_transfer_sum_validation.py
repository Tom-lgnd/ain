#!/usr/bin/env python3
"""Test RPC transfer aggregation rejection and account-state preservation."""

from test_framework.test_framework import DefiTestFramework
from test_framework.util import assert_equal, assert_raises_rpc_error


class TransferSumValidationTest(DefiTestFramework):
    def set_test_params(self):
        self.num_nodes = 2
        self.setup_clean_chain = True
        self.extra_args = [
            ["-txnotokens=0", "-amkheight=50", "-eunosheight=101"],
            ["-txnotokens=0", "-amkheight=50", "-eunosheight=101"],
        ]

    def snapshot(self, addresses):
        return [
            {
                "tip": node.getbestblockhash(),
                "mempool": sorted(node.getrawmempool()),
                "accounts": [node.getaccount(addr) for addr in addresses],
            }
            for node in self.nodes
        ]

    def run_test(self):
        node = self.nodes[0]
        node.generate(101)
        self.sync_blocks()

        source = node.getnewaddress("", "legacy")
        destination = node.getnewaddress("", "legacy")
        recipients = [node.getnewaddress("", "legacy") for _ in range(12)]
        addresses = [source, destination] + recipients

        node.utxostoaccount({source: "10@0"})
        node.generate(1)
        self.sync_blocks()
        assert_equal(node.getaccount(source), ["10.00000000@DFI"])
        assert_equal(node.getrawmempool(), [])

        # Each individual amount fits; their combined total exceeds INT64_MAX.
        oversized_total = {
            address: "9000000000.00000000@0" for address in recipients
        }

        self.log.info("Checking overflow rejection in utxostoaccount")
        before = self.snapshot(addresses)
        assert_raises_rpc_error(
            -8, "overflow", node.utxostoaccount, oversized_total
        )
        assert_equal(self.snapshot(addresses), before)

        self.log.info("Checking overflow rejection in accounttoaccount")
        before = self.snapshot(addresses)
        assert_raises_rpc_error(
            -8, "overflow", node.accounttoaccount, source, oversized_total
        )
        assert_equal(self.snapshot(addresses), before)

        # This rejection belongs to the amount parser, not SumAllTransfers.
        self.log.info("Checking parser rejection of a negative amount")
        before = self.snapshot(addresses)
        assert_raises_rpc_error(
            -3,
            "Amount out of range",
            node.accounttoaccount,
            source,
            {destination: "-1@0"},
        )
        assert_equal(self.snapshot(addresses), before)

        # Multiple amounts for one recipient are aggregated by DecodeAmounts.
        self.log.info("Checking overflow rejection within an amount array")
        oversized_array = {
            destination: ["9000000000.00000000@0"] * 12
        }
        before = self.snapshot(addresses)
        assert_raises_rpc_error(
            -8, "overflow", node.utxostoaccount, oversized_array
        )
        assert_equal(self.snapshot(addresses), before)

        self.log.info("Checking a valid transfer still succeeds")
        node.accounttoaccount(source, {destination: "1@0"})
        node.generate(1)
        self.sync_blocks()
        for peer in self.nodes:
            assert_equal(peer.getaccount(source), ["9.00000000@DFI"])
            assert_equal(peer.getaccount(destination), ["1.00000000@DFI"])


if __name__ == "__main__":
    TransferSumValidationTest().main()
