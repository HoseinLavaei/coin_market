import unittest.mock as mock
from decimal import Decimal

from coin_market.providers.exir import ExirProvider


@mock.patch("coin_market.providers.provider_base.Provider.get_json")
def test_exir(mock_get_json):
    mock_get_json.return_value = {
        "BTC-IRT": {
            "last": "3000000000",
            "open": "2900000000",
            "high": "3100000000",
            "low": "2850000000",
            "volume": "10"
        }
    }
    provider = ExirProvider()
    coins = provider.fetch("IRT")
    assert coins.contains("Exir", "IRT", "BTC")
    btc = coins.get("Exir", "IRT", "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
    # (3000000000 - 2900000000) / 2900000000 * 100 = 3.448...
    assert isinstance(btc.price_change_24h, Decimal)
    assert btc.price_change_24h > 0
