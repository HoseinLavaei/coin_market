import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.exir import ExirP2PProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.exir.get_json")
async def test_exir_p2p(mock_get_json):
    mock_get_json.return_value = {
        "btc-irt": {
            "bids": [[299000000, 1]],
            "asks": [[301000000, 1]],
            "timestamp": "2026-07-26T11:45:07.725Z"
        }
    }
    provider = ExirP2PProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.EXIR_P2P, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.EXIR_P2P, Quote.RLS, "BTC")
    assert btc.base == "BTC"
    # Buy price is lowest ask: 301,000,000 IRT * 10 = 3,010,000,000 RLS
    # Sell price is highest bid: 299,000,000 IRT * 10 = 2,990,000,000 RLS
    assert btc.buy_price == Decimal("3010000000")
    assert btc.sell_price == Decimal("2990000000")
