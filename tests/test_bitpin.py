from decimal import Decimal
import unittest.mock as mock
from coin_market.providers.bitpin import BitpinProvider

@mock.patch("coin_market.providers.provider_base.Provider.get_json")
def test_bitpin(mock_get_json):
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
    coins = provider.fetch("IRT")
    assert coins.contains("Bitpin", "IRT", "BTC")
    btc = coins.get("Bitpin", "IRT", "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
    assert isinstance(btc.price_change_24h, Decimal)
    assert btc.price_change_24h == Decimal("2.1")
