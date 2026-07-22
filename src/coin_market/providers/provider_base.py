from typing import Protocol
import requests
from requests import Session

from ..coin import Coins, Currency

def get_json(url:str, params:dict[str,str]|None=None) -> dict:
    try:
        session: Session = requests.Session()
        response = session.get(url, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise RuntimeError(f"API error: {e}") from e


class Provider(Protocol):
    @staticmethod
    def fetch(currency: Currency) -> Coins:
        raise NotImplementedError