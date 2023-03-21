import logging
import os
from typing import TYPE_CHECKING, Optional
from rotkehlchen.errors.asset import WrongAssetType

from ypricemagic import magic
from web3.types import BlockIdentifier

from rotkehlchen.assets.asset import AssetWithOracles
from rotkehlchen.constants.assets import A_ALETH, A_ETH, A_WETH
from rotkehlchen.constants.misc import EXP18
from rotkehlchen.errors.price import PriceQueryUnsupportedAsset
from rotkehlchen.inquirer import Inquirer
from rotkehlchen.interfaces import CurrentPriceOracleInterface
from rotkehlchen.logging import RotkehlchenLogsAdapter
from rotkehlchen.types import Price
from ypricemagic import magic

if TYPE_CHECKING:
    from rotkehlchen.chain.ethereum.node_inquirer import EthereumInquirer


logger = logging.getLogger(__name__)
log = RotkehlchenLogsAdapter(logger)


class YPriceMagicOracle(CurrentPriceOracleInterface):
    """
    Provides logic to use ypricemagic api as oracle for certain assets
    """

    def __init__(self, ethereum_inquirer: "EthereumInquirer"):
        super().__init__(oracle_name="saddle")
        self.ethereum = ethereum_inquirer

        # this oracle is only used with ETH. If we ever open more chains
        # TODO: figure out how to make ypricemagic use rotki's ethereum_inquirer
        os.environ("BROWNIE_NETWORK_ID", "1")

    def rate_limited_in_last(
        self,
        seconds: Optional[int] = None,  # pylint: disable=unused-argument
    ) -> bool:
        return False

    def get_price(
        self,
        from_asset: AssetWithOracles,
        to_asset: AssetWithOracles,
        block_identifier: BlockIdentifier,
    ) -> Price:
        log.debug(
            f"Querying ypricemagic for price of {from_asset} to USD and USD to {to_asset}"
        )

        try:
            from_token = from_asset.resolve_to_evm_token()
            to_token = to_asset.resolve_to_evm_token()
            # TODO: we might need to do some more type changes than just resolve_to_evm_token
        except WrongAssetType as e:
            raise PriceQueryUnsupportedAsset(e.identifier) from e

        from_token_usd = magic.get_price(from_token.evm_address, block_identifier)

        to_token_usd = magic.get_price(to_token.evm_address, block_identifier)

        return from_token_usd / to_token_usd

    def query_current_price(
        self,
        from_asset: AssetWithOracles,
        to_asset: AssetWithOracles,
        match_main_currency: bool,
    ) -> tuple[Price, bool]:
        """
        May raise:
        - PriceQueryUnsupportedAsset: If an asset not supported by saddle is used in the oracle
        Returns:
        1. The price of from_asset at the current timestamp
        for the current oracle
        2. False value, since it never tries to match main currency
        """
        price = self.get_price(
            from_asset=from_asset,
            to_asset=to_asset,
            block_identifier="latest",
        )
        return price, False
