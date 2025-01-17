from typing import Tuple, Union

from eth_typing import HexAddress, HexStr

from rotkehlchen.accounting.structures import ActionType, LedgerActionType
from rotkehlchen.assets.asset import Asset, EthereumToken
from rotkehlchen.assets.unknown_asset import UnknownEthereumToken
from rotkehlchen.constants.misc import ZERO
from rotkehlchen.errors import (
    ConversionError,
    DeserializationError,
    UnknownAsset,
    UnprocessableTradePair,
)
from rotkehlchen.fval import AcceptableFValInitInput, FVal
from rotkehlchen.typing import (
    AssetAmount,
    AssetMovementCategory,
    ChecksumEthAddress,
    Fee,
    HexColorCode,
    Location,
    Optional,
    Price,
    Timestamp,
    TradePair,
    TradeType,
)
from rotkehlchen.utils.misc import convert_to_int, create_timestamp, iso8601ts_to_timestamp


def deserialize_fee(fee: Optional[str]) -> Fee:
    """Deserializes a fee from a json entry. Fee in the JSON entry can also be null
    in which case a ZERO fee is returned.

    Can throw DeserializationError if the fee is not as expected
    """
    if fee is None:
        return Fee(ZERO)

    try:
        result = Fee(FVal(fee))
    except ValueError as e:
        raise DeserializationError(f'Failed to deserialize a fee entry due to: {str(e)}') from e

    return result


def deserialize_timestamp(timestamp: Union[int, str, FVal]) -> Timestamp:
    """Deserializes a timestamp from a json entry. Given entry can either be a
    string or an int.

    Can throw DeserializationError if the data is not as expected
    """
    if timestamp is None:
        raise DeserializationError('Failed to deserialize a timestamp entry from a null entry')

    if isinstance(timestamp, int):
        processed_timestamp = Timestamp(timestamp)
    elif isinstance(timestamp, FVal):
        try:
            processed_timestamp = Timestamp(timestamp.to_int(exact=True))
        except ConversionError as e:
            # An fval was not representing an exact int
            raise DeserializationError(
                'Tried to deserialize a timestamp fron a non-exact int FVal entry',
            ) from e
    elif isinstance(timestamp, str):
        try:
            processed_timestamp = Timestamp(int(timestamp))
        except ValueError as e:
            # String could not be turned to an int
            raise DeserializationError(
                f'Failed to deserialize a timestamp entry from string {timestamp}',
            ) from e
    else:
        raise DeserializationError(
            f'Failed to deserialize a timestamp entry. Unexpected type {type(timestamp)} given',
        )

    if processed_timestamp < 0:
        raise DeserializationError(
            f'Failed to deserialize a timestamp entry. Timestamps can not have'
            f' negative values. Given value was {processed_timestamp}',
        )

    return processed_timestamp


def deserialize_timestamp_from_date(
        date: Optional[str],
        formatstr: str,
        location: str,
        skip_milliseconds: bool = False,
) -> Timestamp:
    """Deserializes a timestamp from a date entry depending on the format str

    formatstr can also have a special value of 'iso8601' in which case the iso8601
    function will be used.

    Can throw DeserializationError if the data is not as expected
    """
    if not date:
        raise DeserializationError(
            f'Failed to deserialize a timestamp from a null entry in {location}',
        )

    if not isinstance(date, str):
        raise DeserializationError(
            f'Failed to deserialize a timestamp from a {type(date)} entry in {location}',
        )

    if skip_milliseconds:
        # Seems that poloniex added milliseconds in their timestamps.
        # https://github.com/rotki/rotki/issues/1631
        # We don't deal with milliseconds in Rotki times so we can safely remove it
        splits = date.split('.', 1)
        if len(splits) == 2:
            date = splits[0]

    if formatstr == 'iso8601':
        return iso8601ts_to_timestamp(date)

    try:
        return Timestamp(create_timestamp(datestr=date, formatstr=formatstr))
    except ValueError as e:
        raise DeserializationError(
            f'Failed to deserialize {date} {location} timestamp entry',
        ) from e


def deserialize_timestamp_from_poloniex_date(date: str) -> Timestamp:
    """Deserializes a timestamp from a poloniex api query result date entry

    The poloniex dates follow the %Y-%m-%d %H:%M:%S format but are in UTC time
    and not local time so can't use iso8601ts_to_timestamp() directly since that
    would interpet them as local time.

    Can throw DeserializationError if the data is not as expected
    """
    return deserialize_timestamp_from_date(
        date,
        '%Y-%m-%d %H:%M:%S',
        'poloniex',
        skip_milliseconds=True,
    )


def deserialize_timestamp_from_bitstamp_date(date: str) -> Timestamp:
    """Deserializes a timestamp from a bitstamp api query result date entry

    The bitstamp dates follow the %Y-%m-%d %H:%M:%S format but are in UTC time
    and not local time so can't use iso8601ts_to_timestamp() directly since that
    would interpet them as local time.

    Can throw DeserializationError if the data is not as expected
    """
    return deserialize_timestamp_from_date(
        date,
        '%Y-%m-%d %H:%M:%S',
        'bitstamp',
        skip_milliseconds=True,
    )


def deserialize_timestamp_from_kraken(time: Union[str, FVal, int]) -> Timestamp:
    """Deserializes a timestamp from a kraken api query result entry
    Kraken has timestamps in floating point strings. Example: '1561161486.3056'.

    If the dictionary has passed through rlk_jsonloads the entry can also be an Fval

    Can throw DeserializationError if the data is not as expected
    """
    if not time:
        raise DeserializationError(
            'Failed to deserialize a timestamp entry from a null entry in kraken',
        )

    if isinstance(time, int):
        return Timestamp(time)
    if isinstance(time, str):
        try:
            return Timestamp(convert_to_int(time, accept_only_exact=False))
        except ConversionError as e:
            raise DeserializationError(
                f'Failed to deserialize {time} kraken timestamp entry',
            ) from e
    if isinstance(time, FVal):
        try:
            return Timestamp(time.to_int(exact=False))
        except ConversionError as e:
            raise DeserializationError(
                f'Failed to deserialize {time} kraken timestamp entry from an FVal',
            ) from e

    # else
    raise DeserializationError(
        f'Failed to deserialize a timestamp entry from a {type(time)} entry in kraken',
    )


def deserialize_timestamp_from_binance(time: int) -> Timestamp:
    """Deserializes a timestamp from a binance api query result entry
    Kraken has timestamps in integer but also including milliseconds


    Can throw DeserializationError if the data is not as expected
    """
    if not isinstance(time, int):
        raise DeserializationError(
            f'Failed to deserialize a timestamp entry from a {type(time)} entry in binance',
        )

    return Timestamp(int(time / 1000))


def deserialize_optional_fval(
        value: Optional[AcceptableFValInitInput],
        name: str,
        location: str,
) -> FVal:
    """
    Deserializes an FVal from a field that was optional and if None raises DeserializationError
    """
    if value is None:
        raise DeserializationError(
            f'Failed to deserialize value entry for {name} during {location} since null was given',
        )

    try:
        result = FVal(value)
    except ValueError as e:
        raise DeserializationError(f'Failed to deserialize value entry: {str(e)}') from e

    return result


def deserialize_asset_amount(amount: AcceptableFValInitInput) -> AssetAmount:
    try:
        result = AssetAmount(FVal(amount))
    except ValueError as e:
        raise DeserializationError(f'Failed to deserialize an amount entry: {str(e)}') from e

    return result


def deserialize_asset_amount_force_positive(amount: AcceptableFValInitInput) -> AssetAmount:
    """Acts exactly like deserialize_asset_amount but also forces the number to be positive

    Is needed for some places like some exchanges that list the withdrawal amounts as
    negative numbers because it's a withdrawal"""
    result = deserialize_asset_amount(amount)
    if result < ZERO:
        result = AssetAmount(abs(result))
    return result


def deserialize_price(amount: AcceptableFValInitInput) -> Price:
    try:
        result = Price(FVal(amount))
    except ValueError as e:
        raise DeserializationError(f'Failed to deserialize a price/rate entry: {str(e)}') from e

    return result


def deserialize_trade_type(symbol: str) -> TradeType:
    """Takes a string and attempts to turn it into a TradeType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize trade type symbol from {type(symbol)} entry',
        )

    if symbol in ('buy', 'LIMIT_BUY', 'BUY', 'Buy'):
        return TradeType.BUY
    if symbol in ('sell', 'LIMIT_SELL', 'SELL', 'Sell'):
        return TradeType.SELL
    if symbol == 'settlement_buy':
        return TradeType.SETTLEMENT_BUY
    if symbol == 'settlement_sell':
        return TradeType.SETTLEMENT_SELL

    # else
    raise DeserializationError(
        f'Failed to deserialize trade type symbol. Unknown symbol {symbol} for trade type',
    )


def deserialize_trade_type_from_db(symbol: str) -> TradeType:
    """Takes a string from the DB and attempts to turn it into a TradeType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize trade type symbol from {type(symbol)} entry',
        )

    if symbol == 'A':
        return TradeType.BUY
    if symbol == 'B':
        return TradeType.SELL
    if symbol == 'C':
        return TradeType.SETTLEMENT_BUY
    if symbol == 'D':
        return TradeType.SETTLEMENT_SELL
    # else
    raise DeserializationError(
        f'Failed to deserialize trade type symbol. Unknown DB symbol {symbol} for trade type',
    )


LEDGER_ACTION_TYPE_MAPPING = {str(x): x for x in LedgerActionType}


def deserialize_ledger_action_type(symbol: str) -> LedgerActionType:
    """Takes a string and attempts to turn it into a LedgerActionType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize ledger action type symbol from {type(symbol)} entry',
        )

    value = LEDGER_ACTION_TYPE_MAPPING.get(symbol, None)
    if value is None:
        raise DeserializationError(
            f'Failed to deserialize ledger action symbol. Unknown symbol '
            f'{symbol} for ledger action',
        )

    return value


def deserialize_ledger_action_type_from_db(symbol: str) -> LedgerActionType:
    """Takes a string from the DB and attempts to turn it into a LedgerActionType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize ledger action type symbol from {type(symbol)} entry',
        )

    if symbol == 'A':
        return LedgerActionType.INCOME
    if symbol == 'B':
        return LedgerActionType.EXPENSE
    if symbol == 'C':
        return LedgerActionType.LOSS
    if symbol == 'D':
        return LedgerActionType.DIVIDENDS_INCOME
    if symbol == 'E':
        return LedgerActionType.DONATION_RECEIVED
    if symbol == 'F':
        return LedgerActionType.AIRDROP
    if symbol == 'G':
        return LedgerActionType.GIFT
    if symbol == 'H':
        return LedgerActionType.GRANT
    # else
    raise DeserializationError(
        f'Failed to deserialize ledger action type symbol. Unknown DB '
        f'symbol {symbol} for trade type',
    )


ACTION_TYPE_MAPPING = {str(x): x for x in ActionType}


def deserialize_action_type(symbol: str) -> ActionType:
    """Takes a string and attempts to turn it into an ActionType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize action type symbol from {type(symbol)} entry',
        )

    value = ACTION_TYPE_MAPPING.get(symbol, None)
    if value is None:
        raise DeserializationError(
            f'Failed to deserialize action symbol. Unknown symbol '
            f'{symbol} for ledger action',
        )

    return value


def deserialize_action_type_from_db(symbol: str) -> ActionType:
    """Takes a string from the DB and attempts to turn it into an ActionType

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize action type symbol from {type(symbol)} entry',
        )

    if symbol == 'A':
        return ActionType.TRADE
    if symbol == 'B':
        return ActionType.ASSET_MOVEMENT
    if symbol == 'C':
        return ActionType.ETHEREUM_TX
    if symbol == 'D':
        return ActionType.LEDGER_ACTION

    # else
    raise DeserializationError(
        f'Failed to deserialize action type symbol. Unknown DB '
        f'symbol {symbol} for trade type',
    )


def deserialize_location(symbol: str) -> Location:
    """Takes a string and attempts to turn it into a Location enum class

    Can throw DeserializationError if the symbol is not as expected
    """

    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize location symbol from {type(symbol)} entry',
        )

    if symbol == 'external':
        return Location.EXTERNAL
    if symbol == 'kraken':
        return Location.KRAKEN
    if symbol == 'poloniex':
        return Location.POLONIEX
    if symbol == 'bittrex':
        return Location.BITTREX
    if symbol == 'binance':
        return Location.BINANCE
    if symbol == 'bitmex':
        return Location.BITMEX
    if symbol == 'coinbase':
        return Location.COINBASE
    if symbol == 'total':
        return Location.TOTAL
    if symbol == 'banks':
        return Location.BANKS
    if symbol == 'blockchain':
        return Location.BLOCKCHAIN
    if symbol == 'coinbasepro':
        return Location.COINBASEPRO
    if symbol == 'gemini':
        return Location.GEMINI
    if symbol == 'equities':
        return Location.EQUITIES
    if symbol == 'realestate':
        return Location.REALESTATE
    if symbol == 'commodities':
        return Location.COMMODITIES
    if symbol == 'crypto.com':
        return Location.CRYPTOCOM
    if symbol == 'uniswap':
        return Location.UNISWAP
    if symbol == 'bitstamp':
        return Location.BITSTAMP
    if symbol == 'binance_us':
        return Location.BINANCE_US
    if symbol == 'bitfinex':
        return Location.BITFINEX
    if symbol == 'bitcoinde':
        return Location.BITCOINDE
    if symbol == 'iconomi':
        return Location.ICONOMI
    if symbol == 'kucoin':
        return Location.KUCOIN
    if symbol == 'balancer':
        return Location.BALANCER
    if symbol == 'loopring':
        return Location.LOOPRING
    # else
    raise DeserializationError(
        f'Failed to deserialize location symbol. Unknown symbol {symbol} for location',
    )


def _split_pair(pair: TradePair) -> Tuple[str, str]:
    assets = pair.split('_')
    if len(assets) != 2:
        # Could not split the pair
        raise UnprocessableTradePair(pair)

    if len(assets[0]) == 0 or len(assets[1]) == 0:
        # no base or no quote asset
        raise UnprocessableTradePair(pair)

    return assets[0], assets[1]


def pair_get_assets(pair: TradePair) -> Tuple[Asset, Asset]:
    """Returns a tuple with the (base, quote) assets

    May raise:
    - UnprocessableTradePair
    - UnknownAsset
    """
    base_str, quote_str = _split_pair(pair)

    base_asset = Asset(base_str)
    quote_asset = Asset(quote_str)
    return base_asset, quote_asset


def get_pair_position_str(pair: TradePair, position: str) -> str:
    """Get the string representation of an asset of a trade pair"""
    assert position in ('first', 'second')
    base_str, quote_str = _split_pair(pair)
    return base_str if position == 'first' else quote_str


def deserialize_trade_pair(pair: str) -> TradePair:
    """Takes a trade pair string, makes sure it's valid, wraps it in proper type and returns it"""
    try:
        pair_get_assets(TradePair(pair))
    except UnprocessableTradePair as e:
        raise DeserializationError(str(e)) from e
    except UnknownAsset as e:
        raise DeserializationError(
            f'Unknown asset {e.asset_name} found while processing trade pair',
        ) from e

    return TradePair(pair)


def deserialize_location_from_db(symbol: str) -> Location:
    """Takes a DB enum string and attempts to turn it into a Location enum class

    Can throw DeserializationError if the symbol is not as expected
    """

    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize location symbol from {type(symbol)} entry',
        )

    if symbol == 'A':
        return Location.EXTERNAL
    if symbol == 'B':
        return Location.KRAKEN
    if symbol == 'C':
        return Location.POLONIEX
    if symbol == 'D':
        return Location.BITTREX
    if symbol == 'E':
        return Location.BINANCE
    if symbol == 'F':
        return Location.BITMEX
    if symbol == 'G':
        return Location.COINBASE
    if symbol == 'H':
        return Location.TOTAL
    if symbol == 'I':
        return Location.BANKS
    if symbol == 'J':
        return Location.BLOCKCHAIN
    if symbol == 'K':
        return Location.COINBASEPRO
    if symbol == 'L':
        return Location.GEMINI
    if symbol == 'M':
        return Location.EQUITIES
    if symbol == 'N':
        return Location.REALESTATE
    if symbol == 'O':
        return Location.COMMODITIES
    if symbol == 'P':
        return Location.CRYPTOCOM
    if symbol == 'Q':
        return Location.UNISWAP
    if symbol == 'R':
        return Location.BITSTAMP
    if symbol == 'S':
        return Location.BINANCE_US
    if symbol == 'T':
        return Location.BITFINEX
    if symbol == 'U':
        return Location.BITCOINDE
    if symbol == 'V':
        return Location.ICONOMI
    if symbol == 'W':
        return Location.KUCOIN
    if symbol == 'X':
        return Location.BALANCER
    if symbol == 'Y':
        return Location.LOOPRING
    # else
    raise DeserializationError(
        f'Failed to deserialize location symbol. Unknown symbol {symbol} for location',
    )


def deserialize_asset_movement_category(symbol: str) -> AssetMovementCategory:
    """Takes a string and determines whether to accept it as an asset movement category

    Can throw DeserializationError if symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize asset movement category symbol from {type(symbol)} entry',
        )

    if symbol.lower() == 'deposit':
        return AssetMovementCategory.DEPOSIT
    if symbol.lower() == 'withdrawal':
        return AssetMovementCategory.WITHDRAWAL

    # else
    raise DeserializationError(
        f'Failed to deserialize asset movement category symbol. Unknown symbol {symbol}',
    )


def deserialize_asset_movement_category_from_db(symbol: str) -> AssetMovementCategory:
    """Takes a DB enum string and turns it into an asset movement category

    Can throw DeserializationError if symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize asset movement category symbol from '
            f'{type(symbol)} DB enum entry',
        )

    if symbol == 'A':
        return AssetMovementCategory.DEPOSIT
    if symbol == 'B':
        return AssetMovementCategory.WITHDRAWAL

    # else
    raise DeserializationError(
        f'Failed to deserialize asset movement category symbol from DB enum entry.'
        f'Unknown symbol {symbol}',
    )


def deserialize_hex_color_code(symbol: str) -> HexColorCode:
    """Takes a string either from the API or the DB and deserializes it into
    a hexadecimal color code.

    Can throw DeserializationError if the symbol is not as expected
    """
    if not isinstance(symbol, str):
        raise DeserializationError(
            f'Failed to deserialize color code from {type(symbol).__name__} entry',
        )

    try:
        color_value = int(symbol, 16)
    except ValueError as e:
        raise DeserializationError(
            f'The given color code value "{symbol}" could not be processed as a hex color value',
        ) from e

    if color_value < 0 or color_value > 16777215:
        raise DeserializationError(
            f'The given color code value "{symbol}" is out of range for a normal color field',
        )

    if len(symbol) != 6:
        raise DeserializationError(
            f'The given color code value "{symbol}" does not have 6 hexadecimal digits',
        )

    return HexColorCode(symbol)


def deserialize_ethereum_address(symbol: str) -> ChecksumEthAddress:
    """This is identical to string_to_ethereum_address()

    TODO:
    But it's wrong. We should differentiate between those two functions.
    That one should only be used for typing purposes while this one here
    should be used to properly deserialize and check that symbol is indeed
    an ethereum address and is always checksummed. So also external input sanitization.
    https://github.com/rotki/rotki/issues/2334
    """
    return ChecksumEthAddress(HexAddress(HexStr(symbol)))


def deserialize_int_from_str(symbol: str, location: str) -> int:
    if not isinstance(symbol, str):
        raise DeserializationError(f'Expected a string but got {type(symbol)} at {location}')

    try:
        result = int(symbol)
    except ValueError as e:
        raise DeserializationError(
            f'Could not turn string "{symbol}" into an integer at {location}',
        ) from e

    return result


def deserialize_int_from_hex(symbol: str, location: str) -> int:
    """Takes a hex string and turns it into an integer. Some apis returns 0x as
    a hex int and this may be an error. So we handle this as return 0 here.

    May Raise:
    - DeserializationError if the given data are in an unexpected format.
    """
    if not isinstance(symbol, str):
        raise DeserializationError(f'Expected hex string but got {type(symbol)} at {location}')

    if symbol == '0x':
        return 0

    try:
        result = int(symbol, 16)
    except ValueError as e:
        raise DeserializationError(
            f'Could not turn string "{symbol}" into an integer at {location}',
        ) from e

    return result


def deserialize_int_from_hex_or_int(symbol: Union[str, int], location: str) -> int:
    """Takes a symbol which can either be an int or a hex string and
    turns it into an integer

    May Raise:
    - DeserializationError if the given data are in an unexpected format.
    """
    if isinstance(symbol, int):
        result = symbol
    elif isinstance(symbol, str):
        if symbol == '0x':
            return 0

        try:
            result = int(symbol, 16)
        except ValueError as e:
            raise DeserializationError(
                f'Could not turn string "{symbol}" into an integer {location}',
            ) from e
    else:
        raise DeserializationError(
            f'Unexpected type {type(symbol)} given to '
            f'deserialize_int_from_hex_or_int() for {location}',
        )

    return result


def deserialize_ethereum_token_from_db(identifier: str) -> EthereumToken:
    """Takes an identifier and returns the <EthereumToken>"""
    try:
        ethereum_token = EthereumToken(identifier=identifier)
    except UnknownAsset as e:
        raise DeserializationError(
            f'Unknown ethereum token {e.asset_name} found',
        ) from e

    return ethereum_token


def deserialize_unknown_ethereum_token_from_db(
        ethereum_address: str,
        symbol: str,
        name: Optional[str],
        decimals: Optional[int],
) -> UnknownEthereumToken:
    """Takes at least an ethereum address and a symbol, and returns an
    <UnknownEthereumToken>
    """
    try:
        unknown_ethereum_token = UnknownEthereumToken(
            ethereum_address=deserialize_ethereum_address(ethereum_address),
            symbol=symbol,
            name=name,
            decimals=decimals,
        )
    except Exception as e:
        raise DeserializationError(
            f'Failed deserializing an unknown ethereum token with '
            f'address {ethereum_address}, symbol {symbol}, name {name}, '
            f'decimals {decimals}.',
        ) from e

    return unknown_ethereum_token
