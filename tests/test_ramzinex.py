import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.ramzinex import RamzinexP2PProvider, RamzinexOTCProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.ramzinex.get_json")
async def test_ramzinex_p2p(mock_get_json):
    # Mock for pairs, then buys, then sells
    mock_get_json.side_effect = [
        {
            "status": 0,
            "data": [
                {
                    "pair_id": 2,
                    "base_currency_symbol": {"en": "btc"},
                    "quote_currency_symbol": {"en": "irr"}
                }
            ]
        },
        {
            "status": 0,
            "data": [[120000000000, 1, 120000000000, False, None, 1, 12345]] # Buy order (bid)
        },
        {
            "status": 0,
            "data": [[121000000000, 1, 121000000000, False, None, 1, 12345]] # Sell order (ask)
        }
    ]
    provider = RamzinexP2PProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.RAMZINEX_P2P, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.RAMZINEX_P2P, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    # Buy price is lowest ask (last in sells data) -> 121000000000 * 10 = 1210000000000
    assert btc.buy_price == Decimal("1210000000000")
    # Sell price is highest bid (first in buys data) -> 120000000000 * 10 = 1200000000000
    assert btc.sell_price == Decimal("1200000000000")


@pytest.mark.asyncio
@mock.patch("coin_market.providers.ramzinex.get_json")
async def test_ramzinex_otc(mock_get_json):
    mock_get_json.return_value = {
        "status": 0,
        "data": [
            {
                "base_currency_symbol": {"en": "BTC"},
                "quote_currency_symbol": {"en": "irr"},
                "buy": "3000000000",
                "sell": "3050000000",
            }
        ]
    }
    provider = RamzinexOTCProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.RAMZINEX_OTC, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.RAMZINEX_OTC, Quote.RLS, "BTC")
    assert btc.buy_price == Decimal("30000000000")
    assert btc.sell_price == Decimal("30500000000")
