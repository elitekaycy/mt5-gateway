import os
import sys
import types

# MetaTrader5 is a Windows-only binary package, so app modules that import it can't
# be imported on Linux CI. Inject a stub exposing just the constants the code under
# test references, before any app import. setdefault keeps a real install if present.
_mt5 = types.ModuleType("MetaTrader5")
_mt5.ORDER_TIME_GTC = 0
_mt5.ORDER_TIME_DAY = 1
_mt5.ORDER_TIME_SPECIFIED = 2
_mt5.ORDER_TIME_SPECIFIED_DAY = 3
sys.modules.setdefault("MetaTrader5", _mt5)

# App modules import their siblings by bare name (e.g. `from order_time import ...`),
# so the app dir must be on the path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))
