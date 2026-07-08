from decimal import Decimal
import unittest.mock as mock
from coin_market.providers.ramzinex import RamzinexProvider

@mock.patch("coin_market.providers.provider_base.Provider.get_json")
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
    coins = provider.fetch("irr")
    assert coins.contains("Ramzinex", "irr", "BTC")
    btc = coins.get("Ramzinex", "irr", "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
    assert isinstance(btc.price_change_24h, Decimal)
    assert btc.price_change_24h == Decimal("2.5")
