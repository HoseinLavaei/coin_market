import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote
from coin_market.coin import ProviderName
from coin_market.providers.ramzinex import RamzinexProvider


@mock.patch("coin_market.providers.ramzinex.get_json")
def test_ramzinex(mock_get_json):
    mock_get_json.return_value = {
        "status": 0,
        "data": [
            {
                "base_currency_symbol": {"en": "BTC"},
                "quote_currency_symbol": {"en": "irr"},
                "sell": "3000000000",
                "financial": {
                    "last24h": {
                        "change_percent": "2.5",
                        "highest": "3100000000",
                        "lowest": "2900000000",
                        "quote_volume": "15"
                    }
                }
            }
        ]
    }
    provider = RamzinexProvider()
    coins = provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.RAMZINEX, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.RAMZINEX, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
