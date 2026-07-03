#!/usr/bin/env python3
"""Harvest the baked broker directory (app/broker_servers.json).

Queries a broker-directory search (the same /Search the gateway falls back to) for
a set of broker keywords and writes a name -> access-point map, so the gateway can
resolve those brokers to an address fully offline, with no runtime network call.

This is a maintenance tool, run occasionally to refresh the table — not part of a
build or a request. Broker access points change rarely, and MT5 self-seeds the live
directory on first connect, so a slightly stale table still bootstraps a login.

    python3 scripts/harvest-broker-servers.py            # default resolver + broker list
    python3 scripts/harvest-broker-servers.py --resolver https://mt5.mtapi.io

The broker keyword list is seeded from the public TradeVPS broker dataset plus a
curated set of popular brokers; the resolver is fuzzy, so a keyword pulls every
matching company. Coverage is a convenience cache — brokers not listed still resolve
at runtime via the network fallback.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

DEFAULT_RESOLVER = "https://mt5.mtapi.io"
TRADEVPS_DATASET = "https://broker-servers.apis.tradevps.net/"

# Popular brokers to guarantee coverage beyond the TradeVPS list. Keywords are
# fuzzy-matched against company + server names, so one entry pulls all a broker's
# entities (e.g. "Exness" -> Exness CY/KE/MU/SC/VG/…).
CURATED = [
    "Exness", "ICMarkets", "Pepperstone", "FTMO", "Deriv", "XM", "OANDA",
    "Tickmill", "Equiti", "Vantage", "FxPro", "IG", "Admirals", "AdmiralMarkets",
    "Alpari", "AMarkets", "Axi", "BlackBull", "CMC", "Dukascopy", "EightcapPU",
    "Eightcap", "FBS", "Fusion", "GoMarkets", "HFM", "HotForex", "HYCM", "IronFX",
    "JustMarkets", "LiteFinance", "MultiBank", "OctaFX", "Octa", "Pepperstone",
    "RoboForex", "Swissquote", "ThinkMarkets", "TMGM", "Tradeview", "Windsor",
    "FivePercent", "FundedNext", "TheFundedTrader", "MyForexFunds", "E8",
    "Purple", "Errante", "Scope", "Skilling", "Zero", "CapitalCom", "Plus500",
    "Coinexx", "Weltrade", "InstaForex", "NordFX", "FxOpen", "Grand", "Darwinex",
    "Trading212", "MetaQuotes",
]


def fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "mt5-gateway-harvest"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def tradevps_keywords():
    """Broker keywords derived from the public TradeVPS server-name dataset."""
    try:
        data = fetch_json(TRADEVPS_DATASET)
    except Exception as exc:  # dataset optional; curated list still runs
        print(f"  (TradeVPS dataset unavailable: {exc})", file=sys.stderr)
        return []
    brokers = data.get("brokers", data) if isinstance(data, dict) else data
    keywords = set()
    for broker in brokers:
        for server in broker.get("servers", []):
            name = str(server.get("name", ""))
            if name:
                keywords.add(name.split("-", 1)[0])
    return sorted(keywords)


def search(resolver, keyword):
    url = f"{resolver.rstrip('/')}/Search?company={urllib.parse.quote(keyword)}"
    try:
        return fetch_json(url)
    except Exception as exc:
        print(f"  {keyword}: {exc}", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolver", default=DEFAULT_RESOLVER)
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "..", "app", "broker_servers.json"),
    )
    args = parser.parse_args()

    keywords = sorted(set(CURATED) | set(tradevps_keywords()))
    print(f"Harvesting {len(keywords)} broker keywords from {args.resolver}", file=sys.stderr)

    servers = {}
    for keyword in keywords:
        results = search(args.resolver, keyword)
        if not isinstance(results, list):
            continue  # error payloads come back as a dict, not a company list
        for company in results:
            if not isinstance(company, dict):
                continue
            for record in company.get("results", []) or []:
                name = str(record.get("name", "")).strip()
                access = [str(a).strip() for a in record.get("access", []) or [] if str(a).strip()]
                if name and access:
                    servers[name] = sorted(set(access), key=access.index)

    table = {"servers": dict(sorted(servers.items()))}
    out = os.path.abspath(args.out)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(table, handle, indent=1, sort_keys=True)
        handle.write("\n")
    print(f"Wrote {len(servers)} servers to {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
