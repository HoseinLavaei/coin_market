import unittest.mock as mock
from decimal import Decimal

from coin_market.providers.nobitex import NobitexProvider


@mock.patch("coin_market.providers.nobitex.get_json")
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
    from coin_market.coin import Currency
    coins = provider.fetch(Currency.RLS)
    from coin_market.coin import ProviderName
    assert coins.contains(ProviderName.NOBITEX, Currency.RLS, "BTC")
    btc = coins.get(ProviderName.NOBITEX, Currency.RLS, "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
