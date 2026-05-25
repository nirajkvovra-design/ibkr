"""
Tax lot management and FIFO matching engine.
Keeps persistent records of buy lots and calculates tax implications for automated trades.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import config
from utils import get_logger

logger = get_logger(__name__)


class TaxLot:
    """Represents a specific purchase/buy lot for a symbol."""

    def __init__(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: str,
        order_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.symbol = symbol.upper()
        self.quantity = float(quantity)
        self.price = float(price)
        self.timestamp = timestamp  # ISO format string
        self.order_id = order_id
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": self.timestamp,
            "order_id": self.order_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaxLot":
        return cls(
            symbol=data["symbol"],
            quantity=data["quantity"],
            price=data["price"],
            timestamp=data["timestamp"],
            order_id=data.get("order_id"),
            metadata=data.get("metadata", {}),
        )


class TaxManager:
    """Manages active tax lots and computes realized/unrealized tax implications using the FIFO method."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path or config.TAX_LOTS_FILE)
        self.lock = threading.Lock()
        self.active_lots: Dict[str, List[TaxLot]] = {}
        self.realized_trades: List[Dict[str, Any]] = []
        self._load_data()

    def _load_data(self) -> None:
        """Load persistent tax lot state from storage file."""
        with self.lock:
            if not self.storage_path.exists():
                self.active_lots = {}
                self.realized_trades = []
                return

            try:
                content = self.storage_path.read_text(encoding="utf-8")
                if not content.strip():
                    self.active_lots = {}
                    self.realized_trades = []
                    return
                
                data = json.loads(content)
                lots_data = data.get("active_lots", {})
                self.active_lots = {
                    symbol: [TaxLot.from_dict(lot) for lot in lots_list]
                    for symbol, lots_list in lots_data.items()
                }
                self.realized_trades = data.get("realized_trades", [])
                logger.info(
                    "Loaded tax lots from %s. Active symbols: %d. Realized trade count: %d",
                    self.storage_path.name,
                    len(self.active_lots),
                    len(self.realized_trades),
                )
            except Exception as e:
                logger.error("Failed to load tax lots from %s: %s", self.storage_path, e)
                self.active_lots = {}
                self.realized_trades = []

    def _save_data(self) -> None:
        """Persist current tax lot state to storage file."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "active_lots": {
                    symbol: [lot.to_dict() for lot in lots_list]
                    for symbol, lots_list in self.active_lots.items()
                },
                "realized_trades": self.realized_trades,
            }
            self.storage_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save tax lots to %s: %s", self.storage_path, e)

    def add_buy_lot(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: Optional[str] = None,
        order_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaxLot:
        """Record a new buy transaction as a tax lot."""
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

        lot = TaxLot(
            symbol=symbol,
            quantity=quantity,
            price=price,
            timestamp=timestamp,
            order_id=order_id,
            metadata=metadata,
        )

        with self.lock:
            symbol_upper = symbol.upper()
            if symbol_upper not in self.active_lots:
                self.active_lots[symbol_upper] = []
            self.active_lots[symbol_upper].append(lot)
            self._save_data()

        logger.info(
            "Registered BUY Tax Lot: %s | Qty: %.4f | Price: $%.2f | OrderID: %s",
            symbol.upper(),
            quantity,
            price,
            order_id,
        )
        return lot

    def _determine_holding_period(self, buy_time_str: str, sell_time_str: str) -> str:
        """Compare buy and sell timestamps to determine if gain/loss is Short-Term or Long-Term."""
        try:
            # Parse datetime (handling optional timezones safely)
            buy_dt = datetime.fromisoformat(buy_time_str.replace("Z", "+00:00"))
            sell_dt = datetime.fromisoformat(sell_time_str.replace("Z", "+00:00"))
            
            # If dates are timezone-naive, make them UTC to prevent comparisons crash
            if buy_dt.tzinfo is None:
                buy_dt = buy_dt.replace(tzinfo=timezone.utc)
            if sell_dt.tzinfo is None:
                sell_dt = sell_dt.replace(tzinfo=timezone.utc)

            holding_days = (sell_dt - buy_dt).days
            return "LONG_TERM" if holding_days > 365 else "SHORT_TERM"
        except Exception as e:
            logger.warning("Failed parsing timestamps for holding period: %s", e)
            return "SHORT_TERM"

    def estimate_tax_implication(
        self,
        symbol: str,
        quantity: float,
        sell_price: float,
        sell_timestamp: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Simulate a FIFO sale of target quantity at sell_price to evaluate potential tax implications.
        Does NOT alter active tax lots.
        """
        symbol_upper = symbol.upper()
        quantity_to_match = float(quantity)
        
        with self.lock:
            lots = self.active_lots.get(symbol_upper, [])
            # Deep copy active lots so we can simulate match safely
            temp_lots = [TaxLot.from_dict(lot.to_dict()) for lot in lots]

        if not sell_timestamp:
            sell_timestamp = datetime.now(timezone.utc).isoformat()

        matched_lots = []
        realized_pnl = 0.0
        stcg = 0.0
        ltcg = 0.0
        remaining_qty_to_match = quantity_to_match

        for lot in temp_lots:
            if remaining_qty_to_match <= 0:
                break

            match_qty = min(lot.quantity, remaining_qty_to_match)
            gain_per_share = sell_price - lot.price
            match_gain = match_qty * gain_per_share
            holding_type = self._determine_holding_period(lot.timestamp, sell_timestamp)

            if holding_type == "LONG_TERM":
                ltcg += match_gain
            else:
                stcg += match_gain

            realized_pnl += match_gain
            matched_lots.append({
                "buy_price": lot.price,
                "buy_timestamp": lot.timestamp,
                "matched_quantity": match_qty,
                "holding_type": holding_type,
                "pnl": match_gain,
            })

            lot.quantity -= match_qty
            remaining_qty_to_match -= match_qty

        # Apply tax rates
        # Losses offset gains; at a single-trade level we show direct impact
        est_st_tax = max(0.0, stcg * config.SHORT_TERM_TAX_RATE)
        est_lt_tax = max(0.0, ltcg * config.LONG_TERM_TAX_RATE)
        total_estimated_tax = est_st_tax + est_lt_tax

        unmatched_quantity = remaining_qty_to_match

        return {
            "symbol": symbol_upper,
            "quantity_requested": quantity_to_match,
            "quantity_matched": quantity_to_match - unmatched_quantity,
            "unmatched_quantity": unmatched_quantity,
            "average_buy_price": (
                sum(m["buy_price"] * m["matched_quantity"] for m in matched_lots)
                / (quantity_to_match - unmatched_quantity)
                if (quantity_to_match - unmatched_quantity) > 0
                else 0.0
            ),
            "sell_price": sell_price,
            "realized_pnl": realized_pnl,
            "short_term_gain_loss": stcg,
            "long_term_gain_loss": ltcg,
            "estimated_tax": total_estimated_tax,
            "tax_lots_matched": matched_lots,
        }

    def process_sell(
        self,
        symbol: str,
        quantity: float,
        sell_price: float,
        sell_timestamp: Optional[str] = None,
        order_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process an actual sell execution by matching against active buy lots (FIFO method).
        This updates active lots, saves results, and records realized trades.
        """
        symbol_upper = symbol.upper()
        quantity_to_match = float(quantity)

        if not sell_timestamp:
            sell_timestamp = datetime.now(timezone.utc).isoformat()

        # Step 1: Run simulation/estimation first
        implication = self.estimate_tax_implication(
            symbol_upper, quantity_to_match, sell_price, sell_timestamp
        )

        # Step 2: Actually remove/reduce lots under write lock
        with self.lock:
            lots = self.active_lots.get(symbol_upper, [])
            remaining_qty_to_match = quantity_to_match
            new_lots_list = []

            for lot in lots:
                if remaining_qty_to_match <= 0:
                    new_lots_list.append(lot)
                    continue

                match_qty = min(lot.quantity, remaining_qty_to_match)
                lot.quantity -= match_qty
                remaining_qty_to_match -= match_qty

                if lot.quantity > 0:
                    new_lots_list.append(lot)

            self.active_lots[symbol_upper] = new_lots_list
            
            # Clean up if symbol has no active lots
            if not self.active_lots[symbol_upper]:
                del self.active_lots[symbol_upper]

            # Record this realized trade in history
            realized_trade = {
                "timestamp": sell_timestamp,
                "symbol": symbol_upper,
                "quantity": quantity_to_match - implication["unmatched_quantity"],
                "sell_price": sell_price,
                "average_buy_price": implication["average_buy_price"],
                "realized_pnl": implication["realized_pnl"],
                "short_term_gain_loss": implication["short_term_gain_loss"],
                "long_term_gain_loss": implication["long_term_gain_loss"],
                "estimated_tax": implication["estimated_tax"],
                "order_id": order_id,
                "unmatched_quantity": implication["unmatched_quantity"],
            }
            self.realized_trades.append(realized_trade)
            self._save_data()

        logger.info(
            "Processed SELL Execution: %s | Qty: %.4f | Price: $%.2f | P&L: $%.2f | Est Tax: $%.2f | OrderID: %s",
            symbol_upper,
            quantity_to_match,
            sell_price,
            implication["realized_pnl"],
            implication["estimated_tax"],
            order_id,
        )

        return implication

    def generate_tax_report(self) -> Dict[str, Any]:
        """Generate a complete breakdown of current year/historical realized capital gains and active lot valuations."""
        with self.lock:
            total_realized_pnl = sum(t["realized_pnl"] for t in self.realized_trades)
            total_stcg = sum(t["short_term_gain_loss"] for t in self.realized_trades)
            total_ltcg = sum(t["long_term_gain_loss"] for t in self.realized_trades)
            total_tax_paid = sum(t["estimated_tax"] for t in self.realized_trades)

            active_position_cost = 0.0
            active_lot_count = 0
            for symbol, lots in self.active_lots.items():
                active_lot_count += len(lots)
                active_position_cost += sum(lot.quantity * lot.price for lot in lots)

        return {
            "total_realized_pnl": total_realized_pnl,
            "realized_short_term_gains": total_stcg,
            "realized_long_term_gains": total_ltcg,
            "total_estimated_tax_paid": total_tax_paid,
            "active_unrealized_lots_count": active_lot_count,
            "active_positions_total_cost_basis": active_position_cost,
        }

    def reset_lots(self) -> None:
        """Clear all active lots and realized histories (primarily for testing/resets)."""
        with self.lock:
            self.active_lots = {}
            self.realized_trades = []
            self._save_data()
        logger.info("Cleared all active tax lots and realized histories.")
