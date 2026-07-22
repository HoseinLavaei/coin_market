import unittest.mock as mock
from decimal import Decimal

from coin_market.providers.exir import ExirProvider


@mock.patch("coin_market.providers.exir.get_json")
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
    from coin_market.coin import Currency
    coins = provider.fetch(Currency.RLS)
    from coin_market.coin import ProviderName
    assert coins.contains(ProviderName.EXIR, Currency.RLS, "BTC")
    btc = coins.get(ProviderName.EXIR, Currency.RLS, "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
