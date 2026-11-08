#!/usr/bin/env python3
"""Run transfer aggregation RPC checks with upgrades through DF24."""

from feature_transfer_sum_validation import TransferSumValidationTest
from test_framework.util import assert_equal


class TransferSumDF24Test(TransferSumValidationTest):
    def set_test_params(self):
        super().set_test_params()
        forks = self.fork_params_till(24)
        assert_equal(len(forks), 23)
        activation_args = [
            argument.rsplit("=", 1)[0] + "=10" for argument in forks
        ]
        self.extra_args = [
            ["-txnotokens=0", "-transferaggregationheight=10"] + activation_args
            for _ in range(self.num_nodes)
        ]

    def run_test(self):
        super().run_test()

    def snapshot(self, addresses):
        # Verify the intended profile before each rejection check.
        for node in self.nodes:
            info = node.getblockchaininfo()
            assert_equal(info["chain"], "regtest")
            for name, upgrade in info["softforks"].items():
                if upgrade["type"] == "buried":
                    assert_equal(upgrade["height"], 10)
                    assert_equal(upgrade["active"], True)
            assert_equal(info["softforks"]["df24upgrade"]["active"], True)
        return super().snapshot(addresses)


if __name__ == "__main__":
    TransferSumDF24Test().main()
