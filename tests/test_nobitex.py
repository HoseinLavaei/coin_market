import unittest.mock as mock
from decimal import Decimal

from coin_market.providers.nobitex import NobitexProvider


@mock.patch("coin_market.providers.provider_base.Provider.get_json")
def test_nobitex(mock_get_json):
    mock_get_json.return_value = {
        "status": "ok",
        "stats": {
            "BTC-RLS": {
                "latest": "30000000000",
                "dayChange": "1.5",
                "dayHigh": "31000000000",
                "dayLow": "29000000000",
                "volumeDst": "100"
            }
        }
    }
    provider = NobitexProvider()
    coins = provider.fetch("RLS")
    assert coins.contains("Nobitex", "RLS", "BTC")
    btc = coins.get("Nobitex", "RLS", "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
    assert isinstance(btc.price_change_24h, Decimal)
    assert btc.price_change_24h == Decimal("1.5")
