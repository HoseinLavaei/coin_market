import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.bitpin import BitpinOTCProvider, BitpinP2PProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.bitpin.get_json")
async def test_bitpin_otc(mock_get_json):
    mock_get_json.return_value = {
        "results": [
            {
                "currency1": {"title": "Bitcoin", "code": "BTC"},
                "currency2": {"title": "Toman", "code": "IRT"},
                "otc_buy_percent": "0.01",
                "otc_sell_percent": "0.01",
                "price": "3000000000",
                "price_info": {
                    "change": "2.1",
                    "max": "3100000000",
                    "min": "2900000000",
                    "value": "500"
                }
            }
        ]
    }
    provider = BitpinOTCProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.BITPIN_OTC, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.BITPIN_OTC, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    assert isinstance(btc.buy_price, Decimal)
    assert btc.buy_price > 0
    assert isinstance(btc.sell_price, Decimal)
    assert btc.sell_price > 0


@pytest.mark.asyncio
@mock.patch("coin_market.providers.bitpin.get_json")
async def test_bitpin_p2p(mock_get_json):
    def side_effect(url, **kwargs):
        if "markets" in url:
            return {
                "results": [
                    {
                        "id": 1,
                        "currency1": {"code": "BTC"},
                        "currency2": {"code": "IRT"}
                    }
                ]
            }
        elif "orderbook" in url:
            return {
                "asks": [["3000000000", "1"]],
                "bids": [["2900000000", "1"]]
            }
        return {}

    mock_get_json.side_effect = side_effect
    provider = BitpinP2PProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.BITPIN_P2P, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.BITPIN_P2P, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    assert btc.buy_price == Decimal("3000000000") * 10
    assert btc.sell_price == Decimal("2900000000") * 10
