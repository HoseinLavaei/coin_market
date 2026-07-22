import unittest.mock as mock
from decimal import Decimal

from coin_market import AbanTetherProvider
from coin_market.coin import Quote
from coin_market.coin import ProviderName


@mock.patch("coin_market.providers.aban_tether.get_json")
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
    aban_tether_coins = aban_tether.fetch(Quote.RLS)
    assert aban_tether_coins.contains(ProviderName.ABAN_TETHER, Quote.RLS, "BTC")
    btc_aban_tether = aban_tether_coins.get(ProviderName.ABAN_TETHER, Quote.RLS, "BTC")
    assert btc_aban_tether.base == "BTC"
    assert isinstance(btc_aban_tether.current_price, Decimal)
    assert btc_aban_tether.current_price > 0
