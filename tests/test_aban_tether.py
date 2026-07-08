import unittest.mock as mock
from decimal import Decimal

from coin_market import AbanTetherProvider


@mock.patch("coin_market.providers.aban_tether.AbanTetherProvider.get_json")
def test_aban_tether(mock_get_json):
    mock_get_json.return_value = {
        "data": {
            "markets": {
                "BTC": {
                    "symbol": "BTC",
                    "active": True,
                    "buy_price": "5000000000",
                }
            }
        }
    }
    aban_tether = AbanTetherProvider()
    aban_tether_coins = aban_tether.fetch("IRT")
    assert aban_tether_coins.contains("AbanTether", "IRT", "BTC")
    btc_aban_tether = aban_tether_coins.get("AbanTether", "IRT", "BTC")
    assert btc_aban_tether.symbol == "BTC"
    assert isinstance(btc_aban_tether.current_price, Decimal)
    assert btc_aban_tether.current_price > 0
