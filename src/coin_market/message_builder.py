from decimal import Decimal

from coin_market import Coins, OrderBooks


def build_prices_output(
        coins: Coins,
        books: OrderBooks,
        type_filter: str | None,
        volume: Decimal | None = None,
) -> str:
    lines = []
    if type_filter == "OTC" or type_filter is None:
        lines.append(str(coins))
    if type_filter == "P2P" or type_filter is None:
        if volume is not None:
            lines.append(books.to_string(volume))
        else:
            lines.append(str(books))
    return "\n\n".join(lines)
