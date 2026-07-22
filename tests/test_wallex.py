import unittest.mock as mock
from decimal import Decimal
from coin_market.coin import Currency
from coin_market.coin import ProviderName
from coin_market.providers.wallex import WallexProvider


@mock.patch("coin_market.providers.wallex.get_json")
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
    coins = provider.fetch(Currency.USD)
    assert coins.contains(ProviderName.WALLEX, Currency.USD, "BTC")
    btc = coins.get(ProviderName.WALLEX, Currency.USD, "BTC")
    assert btc.symbol == "BTC"
    assert isinstance(btc.current_price, Decimal)
    assert btc.current_price > 0
