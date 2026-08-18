---
title: mt5-gateway
hide:
  - navigation
  - toc
---

<section class="mtg-hero" markdown="1">

<div class="mtg-hero__pills" markdown="0">
  <span class="pill pill--accent">MIT licensed</span>
  <span class="pill">Docker Hub</span>
  <span class="pill">any MetaQuotes broker</span>
</div>

# Trade MetaTrader 5 over plain HTTP — <em>headless, any broker.</em> { .mtg-hero__lede }

<p class="mtg-hero__sub" markdown="0">
mt5-gateway runs the real MT5 terminal under Wine in Docker and exposes it as a
REST API. Point it at any MetaQuotes broker with three env vars and it logs
itself in on boot — no Windows, no VNC, no manual clicking.
</p>

<div class="mtg-hero__ctas" markdown="0">
  <a class="mtg-btn mtg-btn--primary" href="get-started/quickstart/">
    <span>Run it in 5 minutes</span><span>&rarr;</span>
  </a>
  <a class="mtg-btn" href="#see-it-boot">Watch the terminal demo</a>
  <a class="mtg-btn" href="reference/configuration/">Every config var</a>
</div>

<div class="mtg-ticker" markdown="0">
  <span class="tick">EURUSD <span class="up">1.08501 &#9650;</span></span><span class="sep">&middot;</span>
  <span class="tick">XAUUSD <span class="down">2412.30 &#9660;</span></span><span class="sep">&middot;</span>
  <span class="tick">GBPUSD <span class="up">1.27180 &#9650;</span></span><span class="sep">&middot;</span>
  <span class="tick">USDJPY <span class="down">148.220 &#9660;</span></span><span class="sep">&middot;</span>
  <span class="tick">XAUUSD <span class="down">2412.30 &#9660;</span></span><span class="sep">&middot;</span>
  <span class="tick">EURUSD <span class="up">1.08501 &#9650;</span></span><span class="sep">&middot;</span>
  <span class="tick">GBPUSD <span class="up">1.27180 &#9650;</span></span>
</div>

</section>

<a id="see-it-boot"></a>

<div class="mtg-demo" markdown="0">
  <img src="assets/mt5-gateway-demo.gif"
       alt="Pull the image, run it headless against a broker account, and confirm it's alive, logged in, and trading-ready — all from the terminal">
  <div class="mtg-demo__caption">
    Pull the image, run it headless, confirm it's alive and trading-ready — the
    exact commands from <a href="get-started/quickstart/">Quickstart</a>.
    Recorded with <a href="https://github.com/charmbracelet/vhs">VHS</a>; the
    tape is <a href="https://github.com/elitekaycy/mt5-gateway/blob/main/docs/assets/mt5-gateway-demo.tape">committed and regenerable</a>.
  </div>
</div>

<section class="mtg-section" markdown="1">
<div class="mtg-section__head" markdown="0">
  <span class="mtg-section__num">&sect; 01</span>
  <h2>How it works, in three steps</h2>
</div>

<div class="mtg-steps" markdown="0">

<div class="mtg-step">
<div class="mtg-step__num">1</div>
<h3>Give it a server name</h3>
<p>Not an IP, not a broker directory file — just the broker's server name
(e.g. <code>Exness-MT5Trial9</code>), your login, and your password.</p>
</div>

<div class="mtg-step">
<div class="mtg-step__num">2</div>
<h3>It resolves and logs in</h3>
<p>The gateway turns that name into a connectable address, launches the
real MT5 terminal under Wine, and authorizes — headless, no VNC.</p>
</div>

<div class="mtg-step">
<div class="mtg-step__num">3</div>
<h3>Trade over REST</h3>
<p>Orders, positions, ticks, and history — all plain HTTP, with
idempotency keys, a kill switch, and broker-truth reconciliation.</p>
</div>

</div>
</section>

<section class="mtg-section" markdown="1">
<div class="mtg-section__head" markdown="0">
  <span class="mtg-section__num">&sect; 02</span>
  <h2>What you get</h2>
</div>

<div class="grid cards" markdown>

- **Headless login, any broker**

    ---

    No `servers.dat`, no manual click-through. Give it a server name and it
    resolves and connects on its own. See
    [why this exists](concepts/why-headless-login.md).

- **REST API + Swagger**

    ---

    Every endpoint documented and callable from `/apidocs` the moment the
    container is up. See the [API reference](reference/api.md).

- **Idempotent orders**

    ---

    A stable `Idempotency-Key` makes retries safe — replay the same response
    instead of a duplicate order. Full detail in the
    [API reference](reference/api.md).

- **Kill switch + audit log**

    ---

    `POST /kill` halts trading instantly; every order is append-only logged.
    See [health, kill switch, and metrics](operations/health-and-safety.md).

- **Broker-truth reconciliation**

    ---

    `GET /reconcile` returns real positions, orders, and deals — recover
    strategy state after a restart or an ambiguous response.

- **Drop-in broker for qkt**

    ---

    [qkt](https://github.com/elitekaycy/qkt) — an event-driven trading
    engine — talks to this gateway out of the box. See
    [Using with qkt](connect/qkt.md).

</div>
</section>

<section class="mtg-section" markdown="1">
<div class="mtg-section__head" markdown="0">
  <span class="mtg-section__num">&sect; 03</span>
  <h2>Get started</h2>
</div>

- [Quickstart](get-started/quickstart.md) — pull the image, run it, confirm it's alive.
- [Install MT5 + mt5-gateway on a terminal](get-started/install-mt5-terminal.md) — the boot sequence, step by step.
- [Production deploy](get-started/production-deploy.md) — a hardened Compose example.
- [Configuration](reference/configuration.md) — every env var, core vs optional.

</section>

<p markdown="0" style="color: var(--mtg-fg-mute); font-size: 0.85rem; margin-top: 3rem;">
Built on the foundation laid by
<a href="https://github.com/slowfound">slowfound</a> in
<a href="https://github.com/slowfound/metatrader5-quant-server-python">metatrader5-quant-server-python</a>.
</p>
