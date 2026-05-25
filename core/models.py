from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, List

from pydantic import BaseModel, Field, PositiveInt, confloat, condecimal, ConfigDict


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LMT = "LMT"
    MKT = "MKT"
    STP = "STP"
    STP_LMT = "STP LMT"
    MIT = "MIT"


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float
    account: Optional[str] = None


class AccountSnapshot(BaseModel):
    net_liquidation: float = 0.0
    total_cash: float = 0.0
    available_funds: float = 0.0
    buying_power: float = 0.0
    settled_cash: float = 0.0
    funds_for_new_buys: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComboLegModel(BaseModel):
    conId: int
    ratio: int
    action: str  # BUY or SELL
    exchange: str = "SMART"


class OrderRequest(BaseModel):
    symbol: str
    action: OrderSide
    quantity: confloat(gt=0)
    order_type: OrderType = OrderType.LMT
    limit_price: Optional[condecimal(gt=0)] = None
    tif: str = "DAY"
    outside_rth: bool = False
    aux_price: Optional[condecimal(gt=0)] = None
    firm_quote_only: bool = False
    e_trade_only: bool = False
    combo_legs: Optional[List[ComboLegModel]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


class OrderStatusModel(BaseModel):
    order_id: int
    status: str
    filled: float = 0.0
    remaining: float = 0.0
    avg_fill_price: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BrokerResponse(BaseModel):
    success: bool
    order_id: Optional[int] = None
    status: Optional[str] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TradeSignal(BaseModel):
    symbol: str
    action: OrderSide
    confidence: float = 0.0
    reason: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
