import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote
from coin_market.coin import ProviderName
from coin_market.providers.exir import ExirProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.exir.get_json")
async def test_exir(mock_get_json):
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
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.EXIR, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.EXIR, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
