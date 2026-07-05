"""
qrp.broker — Broker abstraction for paper trading.

One interface, two implementations:

- AlpacaBroker    : real paper trading against Alpaca Markets (paper=True).
                    Activates automatically when ALPACA_API_KEY and
                    ALPACA_SECRET_KEY are set in the environment.
- SimulatedBroker : a local broker that mimics the same API — account,
                    positions, market orders with fill prices — persisted to
                    a JSON file. Lets you test the entire live loop with zero
                    credentials and zero risk.

The live loop (qrp.live) does not know or care which one it is talking to.
That separation — strategy code never imports a vendor SDK directly — is a
core piece of production trading architecture.
"""
import json
import os
from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    qty: float
    avg_price: float


class SimulatedBroker:
    """File-backed paper broker mimicking Alpaca's essential API."""

    def __init__(self, state_file: str = "output/sim_broker_state.json",
                 starting_cash: float = 100_000.0):
        self.state_file = state_file
        if os.path.exists(state_file):
            with open(state_file) as f:
                self.state = json.load(f)
        else:
            self.state = {"cash": starting_cash, "positions": {}, "orders": []}

    # --- Alpaca-shaped interface ---
    def get_account(self) -> dict:
        return {"cash": self.state["cash"],
                "equity": self.state["cash"] + sum(
                    p["qty"] * p["last_price"] for p in self.state["positions"].values())}

    def get_positions(self) -> dict:
        return {s: Position(s, p["qty"], p["avg_price"])
                for s, p in self.state["positions"].items()}

    def submit_order(self, symbol: str, qty: float, side: str, price: float) -> dict:
        """Market order with immediate fill at the provided reference price
        plus 5 bps of simulated slippage against you."""
        slip = price * 0.0005 * (1 if side == "buy" else -1)
        fill = price + slip
        pos = self.state["positions"].get(symbol, {"qty": 0.0, "avg_price": 0.0, "last_price": price})
        if side == "buy":
            cost = qty * fill
            if cost > self.state["cash"] + 1e-6:
                qty = self.state["cash"] / fill                     # partial fill on cash limit
                cost = qty * fill
            new_qty = pos["qty"] + qty
            pos["avg_price"] = (pos["qty"] * pos["avg_price"] + qty * fill) / max(new_qty, 1e-12)
            pos["qty"] = new_qty
            self.state["cash"] -= cost
        else:
            qty = min(qty, pos["qty"])                              # no shorting in sim
            pos["qty"] -= qty
            self.state["cash"] += qty * fill
        pos["last_price"] = price
        if pos["qty"] > 1e-9:
            self.state["positions"][symbol] = pos
        else:
            self.state["positions"].pop(symbol, None)
        order = {"symbol": symbol, "qty": round(qty, 4), "side": side,
                 "fill_price": round(fill, 4)}
        self.state["orders"].append(order)
        return order

    def mark_prices(self, prices: dict):
        for s, p in self.state["positions"].items():
            if s in prices:
                p["last_price"] = float(prices[s])

    def save(self):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)


class AlpacaBroker:
    """Thin wrapper over alpaca-py, paper endpoint only.
    Requires: pip install alpaca-py ; env vars ALPACA_API_KEY, ALPACA_SECRET_KEY."""

    def __init__(self):
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        self._MarketOrderRequest = MarketOrderRequest
        self._OrderSide, self._TIF = OrderSide, TimeInForce
        self.client = TradingClient(os.environ["ALPACA_API_KEY"],
                                    os.environ["ALPACA_SECRET_KEY"], paper=True)

    def get_account(self) -> dict:
        a = self.client.get_account()
        return {"cash": float(a.cash), "equity": float(a.equity)}

    def get_positions(self) -> dict:
        return {p.symbol: Position(p.symbol, float(p.qty), float(p.avg_entry_price))
                for p in self.client.get_all_positions()}

    def submit_order(self, symbol: str, qty: float, side: str, price: float) -> dict:
        req = self._MarketOrderRequest(
            symbol=symbol, qty=round(qty, 4),
            side=self._OrderSide.BUY if side == "buy" else self._OrderSide.SELL,
            time_in_force=self._TIF.DAY)
        o = self.client.submit_order(req)
        return {"symbol": symbol, "qty": qty, "side": side, "order_id": str(o.id)}

    def mark_prices(self, prices: dict):  # live broker marks itself
        pass

    def save(self):
        pass


def get_broker():
    """Alpaca paper account if credentials exist, else the simulator."""
    if os.environ.get("ALPACA_API_KEY") and os.environ.get("ALPACA_SECRET_KEY"):
        try:
            b = AlpacaBroker()
            print("[broker] connected to Alpaca paper trading")
            return b
        except Exception as e:
            print(f"[broker] Alpaca unavailable ({type(e).__name__}); using simulator")
    else:
        print("[broker] no Alpaca credentials found; using local simulator")
    return SimulatedBroker()
