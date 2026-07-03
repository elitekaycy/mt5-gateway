"""Operational safety and reconciliation endpoints."""

from flask import Blueprint, jsonify, request
from kill_switch import kill_switch
from lib import close_all_positions
from metrics import metrics
from mt5_connection import mt5
from reconciliation import reconcile

control_bp = Blueprint("control", __name__)


@control_bp.get("/reconcile")
def reconcile_endpoint():
    magic = request.args.get("magic", type=int)
    try:
        snapshot = reconcile(magic)
    except RuntimeError as error:
        return jsonify({"error": str(error), "error_type": "connection_error"}), 503
    return jsonify(snapshot)


@control_bp.post("/kill")
def engage_kill_switch():
    kill_switch.engage()
    metrics.set("kill_switch_active", 1)
    result = None
    if request.args.get("flatten", "false").lower() == "true":
        for order in mt5.orders_get() or ():
            mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": order.ticket})
        result = close_all_positions()
    return jsonify({"kill_switch_active": True, "flatten": result})


@control_bp.post("/kill/release")
def release_kill_switch():
    kill_switch.release()
    metrics.set("kill_switch_active", 0)
    return jsonify({"kill_switch_active": False})
