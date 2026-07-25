import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote
from coin_market.coin import ProviderName
from coin_market.providers.bitpin import BitpinProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.bitpin.get_json")
async def test_bitpin(mock_get_json):
    mock_get_json.return_value = {
        "results": [
            {
                "currency1": {"title": "Bitcoin", "code": "BTC"},
                "currency2": {"title": "Toman", "code": "IRT"},
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
    provider = BitpinProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.BITPIN, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.BITPIN, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
