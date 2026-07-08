from abc import ABC, abstractmethod

import requests
from requests import Session

from ..coin import Coins


class Provider(ABC):
    """Abstract base class for cryptocurrency data providers."""

    NAME: str
    URL: str
    SUPPORTED_CURRENCIES: set[str]
    SESSION: Session = requests.Session()

    def __init__(self):
        """Initialize a reusable HTTP session."""
        self.SESSION.headers.update({
            "User-Agent": "tether-monitor"
        })

    def get_json(self, currency) -> dict:
        """Perform a GET request and return the parsed JSON.

        Returns:
            The parsed JSON response.

        Raises:
            RuntimeError: If the request fails.
        """
        try:
            params = self.get_params(currency)
            response = self.SESSION.get(self.URL, params=(params if params is not None else None), timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise RuntimeError(f"{self.NAME} API error: {e}") from e

    @abstractmethod
    def get_params(self, currency: str) -> dict[str, str] | None:
        return None

    def fetch(self, currency: str) -> Coins:
        """Fetch coin data for the given currency."""
        if currency not in self.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"{self.NAME} does not support '{currency}'. "
                f"Supported currencies: {sorted(self.SUPPORTED_CURRENCIES)}"
            )

        return self._fetch(currency, self.get_json(currency))

    @abstractmethod
    def _fetch(self, currency: str, json: dict) -> Coins:
        """Fetch coin data for the given currency.

        Each provider is responsible for:
        - validating the currency against SUPPORTED_CURRENCIES,
        - converting it to the API's expected format (upper/lower/etc.),
        - mapping the provider's response into Coin objects.
        """
        raise NotImplementedError
