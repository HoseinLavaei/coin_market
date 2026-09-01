from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass
class SubscriptionData:
    id: int
    chat_id: Optional[int]
    provider: Optional[str]
    type_filter: Optional[str]
    volume: Optional[Decimal]
    repeat_interval: Optional[int]
