import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.nobitex import NobitexP2PProvider, NobitexOTCProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.nobitex.get_json")
async def test_nobitex_p2p(mock_get_json):
    mock_get_json.return_value = {
        "status": "ok",
        "bids": [["1896010", "10"]],
        "asks": [["1897190", "1674.6"]]
    }
    provider = NobitexP2PProvider()
    coins = await provider.fetch(Quote.RLS)
    
    # Check USDT since it's one of the fetched pairs
    assert coins.contains(ProviderName.NOBITEX_P2P, Quote.RLS, "USDT")
    usdt = coins.get(ProviderName.NOBITEX_P2P, Quote.RLS, "USDT")
    assert usdt.base == "USDT"
    # Buy price is lowest ask: 1,897,190 IRT * 10 = 18,971,900 RLS
    assert usdt.buy_price == Decimal("18971900")
    # Sell price is highest bid: 1,896,010 IRT * 10 = 18,960,100 RLS
    assert usdt.sell_price == Decimal("18960100")


@pytest.mark.asyncio
@mock.patch("coin_market.providers.nobitex.get_json")
async def test_nobitex_otc(mock_get_json):
    mock_get_json.return_value = {
        "status": "ok",
        "stats": {
            "BTC-RLS": {
                "bestBuy": "30000000000",
                "bestSell": "29000000000"
            }
        }
    }
    provider = NobitexOTCProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.NOBITEX_OTC, Quote.RLS, "BTC")
    btc = coins.get(ProviderName.NOBITEX_OTC, Quote.RLS, "BTC")
    assert btc.buy_price == Decimal("30000000000")
    assert btc.sell_price == Decimal("29000000000")
