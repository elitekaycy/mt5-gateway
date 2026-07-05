from enum import Enum

from mt5_connection import mt5


class MT5Timeframe(Enum):
    M1 = mt5.TIMEFRAME_M1  # 1-minute
    M5 = mt5.TIMEFRAME_M5  # 5-minute
    M15 = mt5.TIMEFRAME_M15  # 15-minute
    M30 = mt5.TIMEFRAME_M30  # 30-minute
    H1 = mt5.TIMEFRAME_H1  # 1-hour
    H4 = mt5.TIMEFRAME_H4  # 4-hour
    D1 = mt5.TIMEFRAME_D1  # daily
    W1 = mt5.TIMEFRAME_W1  # weekly
    MN1 = mt5.TIMEFRAME_MN1  # monthly


ORDER_TYPE_TO_STRING = {
    mt5.ORDER_TYPE_BUY: "BUY",
    mt5.ORDER_TYPE_SELL: "SELL",
    mt5.ORDER_TYPE_BUY_LIMIT: "BUY_LIMIT",
    mt5.ORDER_TYPE_SELL_LIMIT: "SELL_LIMIT",
    mt5.ORDER_TYPE_BUY_STOP: "BUY_STOP",
    mt5.ORDER_TYPE_SELL_STOP: "SELL_STOP",
    mt5.ORDER_TYPE_BUY_STOP_LIMIT: "BUY_STOP_LIMIT",
    mt5.ORDER_TYPE_SELL_STOP_LIMIT: "SELL_STOP_LIMIT",
}

TRADE_ACTION_DEAL = mt5.TRADE_ACTION_DEAL
TRADE_ACTION_PENDING = mt5.TRADE_ACTION_PENDING
