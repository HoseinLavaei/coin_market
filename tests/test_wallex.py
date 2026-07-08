import unittest.mock as mock
from decimal import Decimal

from coin_market.providers.wallex import WallexProvider


@mock.patch("coin_market.providers.provider_base.Provider.get_json")
def test_wallex(mock_get_json):
    mock_get_json.return_value = {
        "result": {
            "symbols": {
                "BTCUSDT": {
                    "baseAsset": "BTC",
                    "quoteAsset": "USDT",
                    "enName": "Bitcoin",
                    "stats": {
                        "lastPrice": "50000",
                        "24h_ch": "1.2",
                        "24h_highPrice": "51000",
                        "24h_lowPrice": "49000",
                        "24h_quoteVolume": "1000000"
                    }
                }
            }
        }
    }
    provider = WallexProvider()
    coins = provider.fetch("USDT")
    assert coins.contains("Wallex", "USDT", "BTC")
    btc = coins.get("Wallex", "USDT", "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
    assert isinstance(btc.price_change_24h, Decimal)
    assert btc.price_change_24h == Decimal("1.2")
