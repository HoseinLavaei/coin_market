from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import func

from ..database import AsyncSessionLocal
from ..models import Coin, Order, OrderBook, Coins, OrderBooks
from ...domain import Base as AssetBase, Quote, ProviderName
from ...domain import Coin as PydanticCoin, Coins as PydanticCoins
from ...domain import Order as PydanticOrder, OrderBook as PydanticOrderBook, OrderBooks as PydanticOrderBooks


def _coin_key(coin: PydanticCoin) -> tuple[str, str, str, str, str]:
    return (
        coin.provider.name,
        coin.base.name,
        coin.quote.name,
        str(coin.raw_buy_price),
        str(coin.raw_sell_price),
    )


def _to_pydantic_coin(cm: Coin) -> PydanticCoin:
    return PydanticCoin(
        provider=ProviderName[cm.provider],
        base=AssetBase[cm.base],
        quote=Quote[cm.quote],
        raw_buy_price=cm.raw_buy_price,
        raw_sell_price=cm.raw_sell_price,
        buy_fee=cm.buy_fee,
        sell_fee=cm.sell_fee,
        timestamp=cm.timestamp,
    )


def _build_order_map(order_coin_pairs: list[tuple[Order, Coin]]) -> dict[int, PydanticOrder]:
    order_map: dict[int, PydanticOrder] = {}
    for order, coin in order_coin_pairs:
        order_map[order.order_id] = PydanticOrder(
            coin=_to_pydantic_coin(coin),
            quantity=order.quantity,
        )
    return order_map


async def _load_orderbooks(session, order_ids: list[int], order_map: dict[int, PydanticOrder]) -> PydanticOrderBooks:
    ob_rows = await session.execute(
        sa.select(OrderBook).where(
            sa.or_(
                OrderBook.asks_ids.op('&&')(order_ids),
                OrderBook.bids_ids.op('&&')(order_ids)
            )
        )
    )
    orderbooks = PydanticOrderBooks()
    for obm in ob_rows.scalars().all():
        asks = [order_map[oid] for oid in (obm.asks_ids or []) if oid in order_map]
        bids = [order_map[oid] for oid in (obm.bids_ids or []) if oid in order_map]
        if asks or bids:
            first = asks[0] if asks else bids[0]
            key = (first.coin.provider, first.coin.quote, first.coin.base)
            orderbooks.books[key] = PydanticOrderBook(asks=asks, bids=bids)
    return orderbooks


async def _insert_otc_coins(session, coins: PydanticCoins, now: datetime) -> dict:
    coin_id_map = {}
    for key, coin in coins.coins.items():
        coin_model = Coin(
            provider=coin.provider.name,
            base=coin.base.name,
            quote=coin.quote.name,
            raw_buy_price=coin.raw_buy_price,
            raw_sell_price=coin.raw_sell_price,
            buy_fee=coin.buy_fee,
            sell_fee=coin.sell_fee,
            timestamp=now,
        )
        session.add(coin_model)
        await session.flush()
        coin_id_map[_coin_key(coin)] = coin_model.coin_id
    return coin_id_map


async def _insert_orderbook_coins(session, orderbooks: PydanticOrderBooks, coin_id_map: dict, now: datetime) -> None:
    for book in orderbooks.books.values():
        for order in book.asks + book.bids:
            coin = order.coin
            coin_key = _coin_key(coin)
            if coin_key not in coin_id_map:
                coin_model = Coin(
                    provider=coin.provider.name,
                    base=coin.base.name,
                    quote=coin.quote.name,
                    raw_buy_price=coin.raw_buy_price,
                    raw_sell_price=coin.raw_sell_price,
                    buy_fee=coin.buy_fee,
                    sell_fee=coin.sell_fee,
                    timestamp=now,
                )
                session.add(coin_model)
                await session.flush()
                coin_id_map[coin_key] = coin_model.coin_id


async def _insert_orders_and_orderbooks(session, orderbooks: PydanticOrderBooks, coin_id_map: dict) -> dict:
    orderbook_id_map = {}
    for key, book in orderbooks.books.items():
        provider, quote, base = key
        asks_ids = []
        bids_ids = []
        for order in book.asks:
            coin_key = _coin_key(order.coin)
            coin_id = coin_id_map[coin_key]
            order_model = Order(coin_id=coin_id, quantity=order.quantity)
            session.add(order_model)
            await session.flush()
            asks_ids.append(order_model.order_id)
        for order in book.bids:
            coin_key = _coin_key(order.coin)
            coin_id = coin_id_map[coin_key]
            order_model = Order(coin_id=coin_id, quantity=order.quantity)
            session.add(order_model)
            await session.flush()
            bids_ids.append(order_model.order_id)
        ob_model = OrderBook(asks_ids=asks_ids, bids_ids=bids_ids)
        session.add(ob_model)
        await session.flush()
        orderbook_id_map[(provider, quote, base)] = ob_model.orderbook_id
    return orderbook_id_map


async def _insert_collections(session, coin_id_map: dict, orderbook_id_map: dict) -> None:
    group_coin_ids = {}
    for coin_key, coin_id in coin_id_map.items():
        provider, base, quote, _, _ = coin_key
        group_key = (provider, base, quote)
        group_coin_ids.setdefault(group_key, []).append(coin_id)
    for (provider_name, base_name, quote_name), coin_ids in group_coin_ids.items():
        session.add(Coins(provider=provider_name, base=base_name, quote=quote_name, coin_ids=coin_ids))

    orderbook_collection_map = {}
    for (provider, quote, base), ob_id in orderbook_id_map.items():
        key = (provider.name, quote.name, base.name)
        orderbook_collection_map.setdefault(key, []).append(ob_id)
    for (provider_name, quote_name, base_name), ob_ids in orderbook_collection_map.items():
        session.add(OrderBooks(provider=provider_name, base=base_name, quote=quote_name, orderbook_ids=ob_ids))


async def save_snapshot(coins: PydanticCoins, orderbooks: PydanticOrderBooks) -> None:
    async with AsyncSessionLocal() as session:
        now = datetime.now()
        coin_id_map = await _insert_otc_coins(session, coins, now)
        await _insert_orderbook_coins(session, orderbooks, coin_id_map, now)
        orderbook_id_map = await _insert_orders_and_orderbooks(session, orderbooks, coin_id_map)
        await _insert_collections(session, coin_id_map, orderbook_id_map)
        await session.commit()


async def load_latest_snapshot() -> tuple[PydanticCoins, PydanticOrderBooks] | None:
    async with AsyncSessionLocal() as session:
        latest_ts_result = await session.execute(sa.select(func.max(Coin.timestamp)))
        latest_ts = latest_ts_result.scalar_one_or_none()
        if latest_ts is None:
            return None
        coin_rows = await session.execute(sa.select(Coin).where(Coin.timestamp == latest_ts))
        coins = PydanticCoins()
        for cm in coin_rows.scalars().all():
            coins.upsert(_to_pydantic_coin(cm))
        order_coin_rows = await session.execute(
            sa.select(Order, Coin)
            .join(Coin, Order.coin_id == Coin.coin_id)
            .where(Coin.timestamp == latest_ts)
        )
        order_coin_pairs = [(row[0], row[1]) for row in order_coin_rows]
        order_map = _build_order_map(order_coin_pairs)
        if not order_map:
            return coins, PydanticOrderBooks()
        order_ids = list(order_map.keys())
        orderbooks = await _load_orderbooks(session, order_ids, order_map)
        return coins, orderbooks
