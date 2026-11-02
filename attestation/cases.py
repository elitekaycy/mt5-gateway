"""The MT5 attestation catalog. A promotion needs every case passing on both images."""

from __future__ import annotations

BOOT_CASES = (
    "boot_fresh_three_vars_no_servers_dat",
    "boot_resolver_service_only",
    "boot_table_only_no_resolver_service",
    "boot_restart_soon_after_login",
    "boot_with_baked_servers_dat",
    "boot_name_only_login",
    "boot_network_cut_during_login",
    "boot_algo_trading_off",
    "boot_wrong_password_never_logs_in",
)

SECURITY_CASES = (
    "security_api_key",
    "security_kill_switch",
    "security_no_secret_left_behind",
)

SESSION_CASES = (
    "surface_processes",
    "api_every_read_route",
    "api_calculators_and_order_check",
    "api_market_buy_and_sell",
    "api_fill_reply_reports_the_real_price",
    "api_sl_tp_set_and_modified",
    "api_partial_close",
    "api_close_all_only_touches_its_magic",
    "api_pending_lifecycle",
    "api_idempotency_replays_and_refuses",
    "api_invalid_orders_open_nothing",
    "api_closing_a_missing_position_fails_cleanly",
    "api_concurrent_orders_each_open_one",
    "api_concurrent_reads_all_answer",
    "api_history_finds_the_trade",
)

RECOVERY_CASES = (
    "recovery_restart",
    "recovery_terminal_crash",
    "recovery_api_crash",
    "recovery_network_loss",
    "recovery_stop_is_graceful",
)

FINAL_CASES = ("surface_terminal_did_not_change", "final_account_is_flat")

# Every route, and the case that drives it against a real broker. A route added to the
# app without an entry here fails tests/test_attestation.py.
ROUTE_COVERAGE = {
    "GET /health": "api_every_read_route",
    "GET /health/live": "api_every_read_route",
    "GET /health/ready": "api_every_read_route",
    "GET /metrics": "api_every_read_route",
    "GET /reconcile": "api_every_read_route",
    "GET /account": "api_every_read_route",
    "GET /last_error": "api_every_read_route",
    "GET /last_error_str": "api_every_read_route",
    "GET /symbols": "api_every_read_route",
    "GET /symbol_info/<symbol>": "api_every_read_route",
    "GET /symbol_info_tick/<symbol>": "api_every_read_route",
    "GET /fetch_data_pos": "api_every_read_route",
    "GET /fetch_data_range": "api_every_read_route",
    "GET /copy_ticks_range": "api_every_read_route",
    "GET /get_positions": "api_every_read_route",
    "GET /positions_total": "api_every_read_route",
    "GET /orders": "api_every_read_route",
    "GET /history_deals_range": "api_history_finds_the_trade",
    "GET /history_deals_get": "api_history_finds_the_trade",
    "GET /history_orders_get": "api_history_finds_the_trade",
    "GET /get_deal_from_ticket": "api_history_finds_the_trade",
    "GET /get_order_from_ticket": "api_history_finds_the_trade",
    "POST /order": "api_market_buy_and_sell",
    "POST /order_check": "api_calculators_and_order_check",
    "POST /order_calc_margin": "api_calculators_and_order_check",
    "POST /order_calc_profit": "api_calculators_and_order_check",
    "POST /close_position": "api_market_buy_and_sell",
    "POST /position_close_partial": "api_partial_close",
    "POST /close_all_positions": "api_close_all_only_touches_its_magic",
    "POST /modify_sl_tp": "api_sl_tp_set_and_modified",
    "PUT /orders/<int:ticket>": "api_pending_lifecycle",
    "DELETE /orders/<int:ticket>": "api_pending_lifecycle",
    "POST /kill": "security_kill_switch",
    "POST /kill/release": "security_kill_switch",
}


def required_cases(variant: str) -> tuple[str, ...]:
    """Both images run the same catalog; only what the image can do differs inside a case."""
    if variant not in ("vnc", "headless"):
        raise ValueError(f"unknown variant: {variant}")
    return BOOT_CASES + SECURITY_CASES + SESSION_CASES + RECOVERY_CASES + FINAL_CASES
