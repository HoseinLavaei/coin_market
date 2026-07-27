import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.aban_tether import AbanTetherOTCProvider, AbanTetherP2PProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.aban_tether.get_json")
async def test_aban_tether_otc(mock_get_json):
    mock_get_json.return_value = {
        "data": {
            "markets": {
                "BTC": {
                    "symbol": "BTC",
                    "active": True,
                    "buy_price": "5000000000",
                    "sell_price": "4900000000",
                }
            }
        }
    }
    provider = AbanTetherOTCProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.ABAN_TETHER_OTC, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.ABAN_TETHER_OTC, Quote.RLS, "BTC")
    assert btc.buy_price == Decimal("50000000000")
    assert btc.sell_price == Decimal("49000000000")


@pytest.mark.asyncio
@mock.patch("coin_market.providers.aban_tether.get_json")
async def test_aban_tether_p2p(mock_get_json):
    provider = AbanTetherP2PProvider()
    coins = await provider.fetch(Quote.RLS)
    assert len(coins.coins) == 0
