from decimal import Decimal

from . import Coins, OrderBooks


def build_prices_output(
        coins: Coins,
        books: OrderBooks,
        type_filter: str | None,
        volume: float | None = None,
) -> str:
    lines = []

    if type_filter == "OTC" or type_filter is None:
        lines.append(f"OTC prices:\n{coins}")

    if type_filter == "P2P":
        lines.append("")

    if type_filter == "P2P" or type_filter is None:
        if volume is not None:
            orderbooks_str = books.to_string(Decimal(str(volume)))
        else:
            orderbooks_str = str(books)
        lines.append(f"Order books (P2P):\n{orderbooks_str}")

    return "\n".join(lines)
