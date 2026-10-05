# Market making: primary-paper evidence and execution requirements

Review date: 2026-10-05. Scope: research and simulation only. This review does not authorize broker connections, subscriptions, orders, or deployment. Journal years and accessible manuscript versions are distinguished below; historical empirical findings are not current profitability estimates.

The literature supports inventory-aware quoting, state-dependent execution models, and measuring adverse selection conditional on execution. It does **not** establish that these strategies earn net profits through a desktop and IBKR Gateway. The missing evidence is the joint distribution of actual fills, subsequent price moves, latency, and costs on the intended access path.

## Ten primary papers

### 1. Avellaneda and Stoikov (2008)

**“High-frequency trading in a limit order book,” Quantitative Finance.** [Author-hosted full text](https://math.nyu.edu/~avellane/HighFrequencyTrading.pdf), sections 2–3.

Theory and simulation: Brownian midprice, exponential utility, and distance-dependent Poisson executions. With cash $X$, inventory $q$, price $S$, and risk aversion $\gamma$, the objective is $\max E[-e^{-\gamma(X_T+q_TS_T)}]$. For intensity $Ae^{-k\delta}$, its approximate reservation price and total spread are

$$
r_t=S_t-q_t\gamma\sigma^2(T-t),\qquad
w_t=\gamma\sigma^2(T-t)+\frac{2}{\gamma}\log(1+\gamma/k).
$$

These are model-dependent approximations, not a universal executable pricing rule. Simulations compare inventory and symmetric quoting; there is no live deployment validation. FIFO priority, message delays, and fill-conditioned informed flow are not established by this basic model. Useful as an inventory-control baseline; fitting $A,k$ cannot repair a misspecified execution mechanism.

### 2. Guéant, Lehalle, and Fernandez-Tapia (2013)

**“Dealing with the inventory risk: a solution to the market making problem,” Mathematics and Financial Economics.** [Full author manuscript, revised 2012](https://arxiv.org/pdf/1105.3115), sections 2–3.

Theory: exponential utility and exponential fill intensities with bounded inventory $q\in[-Q,Q]$. The Hamilton–Jacobi–Bellman system transforms into linear ordinary differential equations; spectral methods yield long-horizon quote approximations. At the positive inventory boundary the modeled agent stops bidding, and conversely for asks at the negative boundary. The core setup uses constant trade size and exogenous Brownian prices; extensions relax some assumptions. This establishes an optimum within a specified model, not measured profitability. Its practical contribution is explicit inventory constraints and a tractable baseline. Real constraints must additionally count outstanding orders and fills arriving while cancellations remain pending.

### 3. Cartea, Jaimungal, and Ricci (2014)

**“Buy Low, Sell High: A High Frequency Trading Perspective,” SIAM Journal on Financial Mathematics.** [Publisher record](https://epubs.siam.org/doi/abs/10.1137/130911196); [author submission](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1964781).

Theory: mutually exciting order flows connect buy/sell activity, book shape, and short-term price drift. The authors report that ignoring short-term predictors exposes market makers to adverse selection by better-informed traders. Their setup explicitly gives the trader superior information-processing and posting speed. Applicability: an inventory-only strategy needs a predictive execution-quality component. **Access limitation:** publisher/author records and abstracts were accessible, but full-text retrieval failed; exact calibration, costs, and experimental execution assumptions were not audited. Accordingly, this review treats it as a mechanism reference, not independently verified tradable evidence or a source of numerical performance targets.

### 4. Cartea, Donnelly, and Jaimungal (2018)

**“Enhancing trading strategies with order book signals,” Applied Mathematical Finance.** [Oxford publication record](https://ora.ox.ac.uk/objects/uuid%3A006addde-3a03-4d75-89c1-04b59026e1c0); [accepted manuscript](https://ora.ox.ac.uk/objects/uuid%3A006addde-3a03-4d75-89c1-04b59026e1c0/files/me4008e0ecca779b45d59231ebca3e69c).

Empirical calibration plus stochastic control: a Markov-modulated jump model optimizes terminal wealth subject to inventory penalties. The accepted version reports eleven Nasdaq equities, January–June 2014 calibration and July–December testing. Volume imbalance predicts next-market-order direction and immediate subsequent price movement; incorporating it improves the reported strategy comparison. This is stronger evidence than an in-sample simulation. **Access limitation:** the archive’s indexed abstract was available, but full-text retrieval failed; FIFO, latency, fee, and fill assumptions remain unverified. The earlier SSRN version lists ten equities, so results across versions must not be mixed. Replication is required before treating reported profit as attainable.

### 5. Cont, Stoikov, and Talreja (2010)

**“A Stochastic Model for Order Book Dynamics,” Operations Research.** [Publisher](https://pubsonline.informs.org/doi/abs/10.1287/opre.1090.0780); [university-hosted author manuscript](https://people.sabanciuniv.edu/atilgan/OrderBook/2008_A%20stochastic%20model%20for%20order%20book%20dynamics%20by%20Rama%20Count%20Sasha%20Stoikov%20and%20Rishi%20Talreja%20%20-%20Columbia%20University.pdf), sections 1–4.

A continuous-time Markov book uses independent arrivals and per-order cancellations; cancellation intensity at level $i$ with $x$ orders is $\theta(i)x$. Tokyo Stock Exchange observations illustrate calibration and conditional probabilities: next price direction, execution before a quote moves, and completing both sides before movement. These are event-horizon predictions. The paper explicitly excludes strategic interaction and long-memory order flow. Useful for interpretable execution benchmarks; a favorable modeled round trip must still survive real queue placement, delay, and costs.

### 6. Huang, Lehalle, and Rosenbaum (2015)

**“Simulating and analyzing order book data: The queue-reactive model,” JASA.** [Full author manuscript](https://arxiv.org/pdf/1312.0563), sections 2–3.

Empirical simulator: arrivals/cancellations depend on current book state while a reference price remains fixed, with stochastic transitions between reference-price regimes. Data cover France Telecom and Alcatel-Lucent on Euronext Paris, January 2010–March 2012, first five levels; first/last trading hours are excluded. The paper examines execution-before-price-move probabilities and book distributions. Purely mechanical queue dynamics understate empirical volatility, motivating additional reference-price dynamics. This is a calibration framework, not proof that a strategy profits. Applicability requires event data and separate validation of queue depletion, cancellation location, price jumps, and opening/closing regimes.

### 7. Lehalle and Mounjid (2018 manuscript)

**“Limit Order Strategic Placement with Adverse Selection Risk and the Role of Latency.”** [Full author manuscript](https://arxiv.org/pdf/1610.00261), sections 2–4; first posted 2016, revised March 2018.

Direct Nasdaq-OMX feed recordings and participant-labelled trades for AstraZeneca, January–September 2013, motivate control of one small limit order. The agent can keep/cancel/reinsert and must execute by the horizon. Value is measured against a conditional future-price benchmark. Latency is modeled as acting only every $\tau$ periods, with cost $V-V_\tau$. Numerical results show slower reactions erode control value. This is not a measured millisecond threshold for another broker. The framework explicitly lacks portfolio inventory risk. It supports including cancel/reinsert timing and adverse selection in simulations, but not assuming immediate cancellation or complete market-making profitability.

### 8. Moallemi and Yuan (2017 manuscript)

**“A Model for Queue Position Valuation in a Limit Order Book.”** [Author-hosted full text, June 2017 revision](https://moallemi.com/ciamac/papers/queue-value-2016.pdf), sections 3–5.

Theory plus Nasdaq ITCH calibration/backtesting for liquid, large-tick US stocks; Bank of America in August 2013 illustrates estimation. Queue value combines execution economics and the option value of retaining priority. Later queue positions have different execution probability and adverse selection. Market-by-order data permit reconstruction of individual order histories; analysis uses the Nasdaq book alone. The historical calibration includes an exchange rebate, which must not be copied into broker economics. Strong justification for queue-aware replay and the opportunity cost of cancelling. Model agreement with historical queue values does not validate a broker-routed strategy or cross-venue execution.

### 9. Menkveld (2013)

**“High frequency trading and the new market makers,” Journal of Financial Markets.** [Author submission](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1722924); [earlier full working paper](https://papers.tinbergen.nl/11076.pdf), sections 2–3.

Empirical case study of a large HFT across Chi-X and Euronext in Dutch stocks. Trading profits decompose into spread earnings and inventory positioning; positive spread earnings coexist with inventory losses. Cross-market access and venue costs matter, and performance depends on capital-cost assumptions. The accessible earlier manuscript examines holding horizons from seconds upward; no numerical estimate from it is presented as a final-publication result. This is evidence about an established participant’s trading, not an implementable retail recipe. Useful for P&L attribution and inventory-horizon diagnostics; a single successful firm does not estimate a new entrant’s probability of success.

### 10. Baron, Brogaard, Hagströmer, and Kirilenko (2019)

**“Risk and Return in High-Frequency Trading,” JFQA.** [Publisher](https://www.cambridge.org/core/product/identifier/S0022109018001096/type/journal_article); [full 2017 university-hosted manuscript](https://www.cb.cityu.edu.hk/ef/doc/GRU/HFT%202017/Brogaard_HFT_risk_return_20170825.pdf), sections II–IV.

Empirical evidence from proprietary Swedish supervisory transactions with participant identities: 25 equities, 2010–2014, across venues. Relative latency and colocation upgrades associate with trading performance through information and risk-management channels. The accessible manuscript explicitly lacks direct trading fees and operating costs; revenues are not fully observed net business profit. Related-instrument activity is also incompletely observed. This supports evaluating competitive access, not buying infrastructure on an assumed return. It does not quantify the expected result of a desktop/IBKR strategy, and historical associations cannot substitute for its own measurements.

## The economic test to implement in research

The following is this review’s proposed accounting diagnostic, not an equation claimed by one paper. For a one-unit fill at time $\tau$, side $d=+1$ for a buy and $-1$ for a sell, price $p$, and midprice $m$, the marked value at horizon $h$ is

$$
d(m_{\tau+h}-p)
=d(m_\tau-p)+d(m_{\tau+h}-m_\tau).
$$

The first term measures spread capture; the second measures subsequent favorable/adverse movement. A posting policy must estimate **fill probability times expected value conditional on that fill**, subtract commissions, exchange/broker fees net of actually received rebates, and include partial-fill quantity, inventory exposure, exit costs, and message charges where applicable. A mark to midprice is not liquidation cash. Fixed data/infrastructure costs belong in business-level P&L. Do not add a separate “adverse selection cost” if the same movement is already counted in markouts.

Research acceptance requirements:

- Reconstruct event ordering and observable information at each decision; record exchange versus receipt timestamps and gaps. Never expose future cancellations to the policy.
- Estimate fills and markouts jointly by queue position, imbalance, volatility, spread, time of day, order age, and latency. Validate on later held-out days and stressed regimes.
- Replay outbound orders, exchange arrival, partial fills, cancel requests, cancel acknowledgements, and rejected amendments. A cancel request leaves exposure until effective; replacement can lose priority or coexist with the original order. Reserve worst-case inventory for outstanding orders.
- Model cancellation-ahead uncertainty when order identity is absent; report conservative bounds. Historical replay must disclose that the hypothetical trader could change subsequent order flow.
- Stress delayed/stale feeds, latency tails, lost acknowledgements, forced inventory exits, and fee assumptions. Compare against a simple inventory-only policy and a no-trade baseline.

## Desktop/Gateway applicability and unresolved gaps

**Engineering inference:** the stated RTX 3070 Ti/32 GB desktop is a plausible research platform for partitioned datasets and modest simulations; no benchmark here establishes throughput. A GPU does not supply exchange queue priority, direct-feed observability, or faster cancellation effectiveness. Without direct feeds and colocation, none of these papers establishes that competing on the next book event is viable through IBKR Gateway.

This paper-only review deliberately makes no current API-rate, fee, timestamp-resolution, or network-latency assertion. Those require current broker/exchange documentation and authorized measurements. A nearby VPS cannot be credited with an execution advantage before the complete observation-to-exchange-action path is measured.

The next decision requires a specified instrument/venue, available event data and rights, broker order-routing behavior, measured latency distributions, observable queue information, actual fee/rebate schedule, capital and loss limits, and out-of-sample joint fill/markout calibration. The two inaccessible Cartea full texts remain verification gaps. Until those gaps close, this literature supports a serious simulator and falsifiable experiments—not an established HFT business case.
