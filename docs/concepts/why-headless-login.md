# Why this exists

MetaTrader 5 is a Windows GUI application with a closed protocol. Running it
as a service normally means a Windows box and a human clicking "Login." This
project runs the real MT5 terminal under Wine and exposes its Python API as
a REST service, so any language or system can drive an MT5 account
programmatically.

The hard part is logging in **headless, for any broker**. MT5 can't
discover a broker by name on a fresh install without its encrypted broker
directory (`servers.dat`), and that file can't be generated. This gateway
solves it: it **resolves the broker's server name to a connectable
address** and connects directly, so you supply only the account credentials
and the server *name* — never an IP, a directory file, or a VNC session.

See [How headless login works](../headless-login.md) for the mechanism, or
[Install MT5 + mt5-gateway on a terminal](../get-started/install-mt5-terminal.md)
for a step-by-step walkthrough of a real boot.
