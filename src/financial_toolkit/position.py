from dataclasses import dataclass
from math import isfinite

from .transaction import Asset, ALLOWED_TYPES, Transaction


@dataclass
class Position:
    asset: Asset
    quantity: float = 0.0
    average_price: float = 0.0
    current_price: float = 0.0
    realized_pnl: float = 0.0

    def __post_init__(self):
        if not isinstance(self.asset, ALLOWED_TYPES):
            raise TypeError("Invalid asset type")

        for name in (
            "quantity",
            "average_price",
            "current_price",
            "realized_pnl",
        ):
            value = getattr(self, name)

            if isinstance(value, bool):
                raise ValueError(f"{name} must be a finite number")

            try:
                value = float(value)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    f"{name} must be a finite number"
                ) from exc

            if not isfinite(value):
                raise ValueError(f"{name} must be a finite number")

            setattr(self, name, value)

        if self.average_price < 0 or self.current_price < 0:
            raise ValueError("Prices cannot be negative")

        if self.quantity != 0:
            if self.average_price == 0 or self.current_price == 0:
                raise ValueError(
                    "An open position requires positive prices"
                )
        else:
            self.average_price = 0.0

    def update_price(self, price):
        """Actualiza la valoración sin registrar una operación."""
        if isinstance(price, bool):
            raise ValueError("Price must be positive and finite")

        price = float(price)

        if not isfinite(price) or price <= 0:
            raise ValueError("Price must be positive and finite")

        self.current_price = price

    def apply_transaction(self, transaction: Transaction):
        """Actualiza unidades, coste medio y beneficio realizado."""
        if not isinstance(transaction, Transaction):
            raise TypeError("Expected a Transaction")

        asset_id = (
            getattr(self.asset, "ticker", None)
            or self.asset.symbol
        )
        transaction_asset_id = (
            getattr(transaction.asset, "ticker", None)
            or transaction.asset.symbol
        )

        if (
            type(self.asset) is not type(transaction.asset)
            or asset_id != transaction_asset_id
        ):
            raise ValueError(
                "Transaction belongs to a different asset"
            )

        previous_quantity = self.quantity
        change = transaction.signed_quantity
        new_quantity = previous_quantity + change

        if previous_quantity == 0:
            # Apertura de una posición larga o corta.
            self.average_price = transaction.price

        elif (previous_quantity > 0) == (change > 0):
            # Aumento de una posición existente.
            self.average_price = (
                abs(previous_quantity) * self.average_price
                + abs(change) * transaction.price
            ) / abs(new_quantity)

        else:
            # Reducción, cierre o cambio de dirección.
            closed_quantity = min(
                abs(previous_quantity), abs(change)
            )
            direction = 1 if previous_quantity > 0 else -1

            self.realized_pnl += (
                closed_quantity
                * (transaction.price - self.average_price)
                * direction
            )

            if new_quantity == 0:
                self.average_price = 0.0
            elif (new_quantity > 0) != (previous_quantity > 0):
                # Se cerró la posición y se abrió otra contraria.
                self.average_price = transaction.price

        self.quantity = new_quantity
        self.current_price = transaction.price

    @property
    def invested_value(self) -> float:
        """Importe absoluto de entrada de la posición abierta."""
        return abs(self.quantity) * self.average_price

    @property
    def market_value(self) -> float:
        """Valor firmado: negativo para una posición corta."""
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        """Ganancia o pérdida de la posición todavía abierta."""
        return self.quantity * (
            self.current_price - self.average_price
        )

    @property
    def unrealized_return(self) -> float:
        if self.invested_value == 0:
            return 0.0

        return self.unrealized_pnl / self.invested_value

    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl