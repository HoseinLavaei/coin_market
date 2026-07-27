import pytest
import unittest.mock as mock
from decimal import Decimal

from coin_market.coin import Quote, ProviderName
from coin_market.providers.wallex import WallexP2PProvider, WallexOTCProvider


@pytest.mark.asyncio
@mock.patch("coin_market.providers.wallex.get_json")
async def test_wallex_p2p(mock_get_json):
    mock_get_json.return_value = {
        "result": {
            "symbols": {
                "BTCUSDT": {
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "enName": "Bitcoin",
                    "stats": {
                        "lastPrice": "50000",
                        "bidPrice": "49900",
                        "askPrice": "50100",
                        "24h_ch": "1.2",
                        "24h_highPrice": "51000",
                        "24h_lowPrice": "49000",
                        "24h_quoteVolume": "1000000"
                    }
                }
            }
        }
    }
    provider = WallexP2PProvider()
    coins = await provider.fetch(Quote.USD)
    assert coins.contains(ProviderName.WALLEX_P2P, Quote.USD, "BTC")
    btc = coins.get(ProviderName.WALLEX_P2P, Quote.USD, "BTC")
    assert btc.base == "BTC"
    # Buy price is askPrice (50100)
    assert btc.buy_price == Decimal("50100")
    # Sell price is bidPrice (49900)
    assert btc.sell_price == Decimal("49900")


@pytest.mark.asyncio
@mock.patch("coin_market.providers.wallex.get_json")
async def test_wallex_otc(mock_get_json):
    mock_get_json.side_effect = [
        {
            "result": {
                "USDTTMN": {
                    "symbol": "USDTTMN",
                    "baseAsset": "USDT",
                    "quoteAsset": "TMN"
                }
            }
        },
        {"success": True, "result": {"price": "192000"}}, # Buy
        {"success": True, "result": {"price": "189000"}}  # Sell
    ]
    provider = WallexOTCProvider()
    coins = await provider.fetch(Quote.RLS)
    assert coins.contains(ProviderName.WALLEX_OTC, Quote.RLS, "USDT")
    usdt = coins.get(ProviderName.WALLEX_OTC, Quote.RLS, "USDT")
    assert usdt.buy_price == Decimal("1920000") # 192000 * 10
    assert usdt.sell_price == Decimal("1890000") # 189000 * 10
