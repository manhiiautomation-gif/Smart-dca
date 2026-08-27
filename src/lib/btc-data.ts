import fs from "fs";
import path from "path";

const LIVE_BOT_DIR = "/home/z/my-project/live_bot";
const PROJECT_ROOT = "/home/z/my-project";

// ─── Types ───

export interface BotState {
  cooldown: number;
  total_invested: number;
  adjusted_invested: number;
  total_sell_proceeds: number;
  total_reserve_injected: number;
  peak_value: number;
  max_drawdown: number;
  sell_count: number;
  buy_count: number;
  total_btc_bought: number;
  total_btc_sold: number;
  last_run_date: string;
  last_trade_date: string;
  run_count: number;
  cumulative_fees: number;
  last_indicators: {
    price: number;
    mvrv: number;
    mvrv_source: string;
    mvrv_pct: number;
    mvrv_z: number;
    mvrv_z_source: string;
    rsi: number;
    macd_h: number;
    nupl: number;
    sopr: number;
    sopr_source: string;
    sma_200: number;
    sma_365: number;
    macd_bear: boolean;
    macd_declining: boolean;
    rsi_divergence: boolean;
    ath: number;
    sell_score: number;
    path_taken: string;
    in_bear: boolean;
    cooldown: number;
    realized_price: number;
    lth_realized_price: number;
    lth_source: string;
    rp_source: string;
  };
  last_btc_balance: number;
  last_cash_balance: number;
  last_portfolio_value: number;
  last_price: number;
  last_exchange_currency: string;
  last_dry_run: boolean;
  last_decision: {
    buy_amount: number;
    sell_amount: number;
    multiplier: number;
    base_budget: number;
    reserve_injection: number;
    monday_boost: number;
    in_dca_window: boolean;
  };
}

export interface IndicatorHistory {
  date: string;
  price: number;
  mvrv: number;
  rsi: number;
  sopr: number;
  nupl: number;
  sell_score?: number;
}

export interface Trade {
  date: string;
  type: string;
  amount: number;
  btc: number;
  price: number;
  fee: number;
}

export interface BriefingData {
  price: {
    current: number;
    currency: string;
    change_24h: number | null;
    vs_sma50: number | null;
    vs_sma200: number | null;
    vs_ath: number | null;
  trend: string;
  trendColor: string;
  };
  onchain: {
    mvrv: number;
    mvrv_pct: number;
    mvrv_z: number;
    mvrv_zone: string;
    mvrv_zoneColor: string;
    mvrv_source: string;
    nupl: number;
    nupl_phase: string;
    sopr: number;
    sopr_signal: string;
    sopr_source: string;
  };
  momentum: {
    rsi: number;
    rsi_zone: string;
    rsi_zoneColor: string;
    macd_hist: number;
    macd_signal: string;
    macd_bear_cross: boolean;
    rsi_divergence: boolean;
  };
  bot: {
    status: string;
    last_run: string;
    last_decision: string;
    buy_amount: number;
    sell_amount: number;
    multiplier: number;
    sell_score: number;
    path_taken: string;
    cooldown: number;
    portfolio_value: number;
    btc_balance: number;
    cash_balance: number;
    total_invested: number;
    total_btc_bought: number;
    buy_count: number;
    sell_count: number;
    unrealized_pnl_pct: number;
    avg_cost: number;
    sma_200: number;
    sma_365: number;
    in_bear: boolean;
  };
  keyLevels: {
    ath: number;
    realized_price: number;
    lth_realized_price: number;
    sma_200: number;
    sma_365: number;
    distance_rp: number;
    distance_lth: number;
    distance_sma200: number;
  };
  indicatorHistory: IndicatorHistory[];
  trades: Trade[];
  marketNarrative: string;
  lastRefreshed: string;
}

// ─── Helpers ───

function readJson<T>(filePath: string): T | null {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

function getMvrvZone(mvrv: number): { zone: string; color: string } {
  if (mvrv < 1.0) return { zone: "Deep Accumulation", color: "#22c55e" };
  if (mvrv < 1.5) return { zone: "Accumulation", color: "#86efac" };
  if (mvrv < 2.0) return { zone: "Neutral", color: "#facc15" };
  if (mvrv < 2.5) return { zone: "Euphoria", color: "#f97316" };
  if (mvrv < 3.5) return { zone: "Overvalued", color: "#ef4444" };
  return { zone: "Extreme Euphoria", color: "#dc2626" };
}

function getNuplPhase(nupl: number): string {
  if (nupl < 0) return "Capitulation";
  if (nupl < 0.25) return "Fear";
  if (nupl < 0.5) return "Optimism";
  if (nupl < 0.75) return "Belief";
  return "Euphoria";
}

function getRsiZone(rsi: number): { zone: string; color: string } {
  if (rsi < 30) return { zone: "Oversold", color: "#22c55e" };
  if (rsi < 45) return { zone: "Neutral-Low", color: "#86efac" };
  if (rsi < 55) return { zone: "Neutral", color: "#facc15" };
  if (rsi < 70) return { zone: "Neutral-High", color: "#f97316" };
  return { zone: "Overbought", color: "#ef4444" };
}

function getSoprSignal(sopr: number): string {
  if (sopr < 0.9) return "Heavy Loss Selling";
  if (sopr < 1.0) return "Selling at Loss";
  if (sopr < 1.1) return "Normal";
  if (sopr < 1.3) return "Profit Taking";
  return "Strong Profit Taking";
}

function getTrend(
  price: number,
  sma200: number,
  inBear: boolean
): { trend: string; color: string } {
  if (inBear) return { trend: "Bear Market", color: "#ef4444" };
  if (sma200 <= 0) return { trend: "N/A", color: "#6b7280" };
  const dist = ((price - sma200) / sma200) * 100;
  if (dist > 20) return { trend: "Strong Bull", color: "#22c55e" };
  if (dist > 5) return { trend: "Bull Trend", color: "#86efac" };
  if (dist > -5) return { trend: "Sideways", color: "#facc15" };
  if (dist > -15) return { trend: "Bear Trend", color: "#f97316" };
  return { trend: "Deep Bear", color: "#ef4444" };
}

function buildNarrative(
  mvrv: number,
  mvrvZone: string,
  nupl: number,
  rsi: number,
  sopr: number,
  price: number,
  sma200: number,
  inBear: boolean,
  sellScore: number,
  pathTaken: string,
  botStatus: string
): string {
  const parts: string[] = [];

  // MVRV situation
  if (mvrv < 1.0) {
    parts.push(
      `MVRV at ${mvrv.toFixed(2)} is in deep accumulation zone — historically strong buy signals.`
    );
  } else if (mvrv < 1.5) {
    parts.push(
      `MVRV at ${mvrv.toFixed(2)} — still in accumulation territory, good for DCA.`
    );
  } else if (mvrv < 2.0) {
    parts.push(
      `MVRV at ${mvrv.toFixed(2)} — neutral zone, normal DCA pace recommended.`
    );
  } else if (mvrv < 2.5) {
    parts.push(
      `MVRV at ${mvrv.toFixed(2)} — entering euphoria, consider reducing buy size.`
    );
  } else {
    parts.push(
      `MVRV at ${mvrv.toFixed(2)} — overvalued territory, selling signals active.`
    );
  }

  // Price vs MA200
  if (!inBear && sma200 > 0) {
    const above = ((price - sma200) / sma200) * 100;
    if (above > 10) {
      parts.push(
        `Price is ${above.toFixed(1)}% above SMA200 — strong structural uptrend.`
      );
    } else {
      parts.push(`Price near SMA200 — watch for trend confirmation.`);
    }
  } else if (inBear) {
    parts.push(`Price below SMA200 — bear market structure, cautious buying.`);
  }

  // SOPR
  if (sopr < 1.0) {
    parts.push(
      `SOPR at ${sopr.toFixed(3)} — holders selling at loss, possible bottom signal.`
    );
  }

  // Bot status
  if (sellScore > 0 && pathTaken !== "none") {
    parts.push(
      `Phoenix bot has active sell signal (score ${sellScore}, path ${pathTaken}).`
    );
  } else if (botStatus === "active") {
    const mult = mvrv < 1.5 ? "enhanced" : mvrv < 2.0 ? "normal" : "reduced";
    parts.push(`Phoenix bot is buying with ${mult} multiplier.`);
  }

  return parts.join(" ");
}

// ─── Main Data Builder ───

export function getBriefingData(): BriefingData {
  const state = readJson<BotState>(
    path.join(LIVE_BOT_DIR, "state.json")
  );
  const historyRaw = readJson<IndicatorHistory[]>(
    path.join(LIVE_BOT_DIR, "indicator_history.json")
  );
  const tradesRaw = readJson<Trade[]>(
    path.join(PROJECT_ROOT, "trade_log.json")
  );

  // Defaults if no data
  const indicators = state?.last_indicators;
  const price = indicators?.price ?? 0;
  const currency = state?.last_exchange_currency ?? "THB";
  const sma200 = indicators?.sma_200 ?? 0;
  const sma365 = indicators?.sma_365 ?? 0;
  const inBear = indicators?.in_bear ?? false;

  const mvrv = indicators?.mvrv ?? 0;
  const mvrvZone = getMvrvZone(mvrv);
  const nupl = indicators?.nupl ?? 0;
  const sopr = indicators?.sopr ?? 0;
  const rsi = indicators?.rsi ?? 50;
  const rsiZone = getRsiZone(rsi);
  const macdH = indicators?.macd_h ?? 0;

  // Calculate change from history (if available)
  let change24h: number | null = null;
  let vsSma200: number | null = null;
  const history = (historyRaw ?? []).slice(-90);
  if (history.length >= 2) {
    const prev = history[history.length - 2];
    change24h =
      prev.price > 0
        ? ((price - prev.price) / prev.price) * 100
        : null;
  }
  if (sma200 > 0) {
    vsSma200 = ((price - sma200) / sma200) * 100;
  }

  const trend = getTrend(price, sma200, inBear);

  // Bot data
  const lastDecision = state?.last_decision;
  const portfolioValue = state?.last_portfolio_value ?? 0;
  const btcBalance = state?.last_btc_balance ?? 0;
  const cashBalance = state?.last_cash_balance ?? 0;
  const totalInvested = state?.total_invested ?? 0;
  const totalBtcBought = state?.total_btc_bought ?? 0;
  const avgCost =
    btcBalance > 0
      ? (state?.adjusted_invested ?? totalInvested) / btcBalance
      : 0;
  const unrealizedPnl =
    avgCost > 0
      ? ((price - avgCost) / avgCost) * 100
      : 0;

  // Key levels
  const ath = indicators?.ath ?? 0;
  const realizedPrice = indicators?.realized_price ?? 0;
  const lthRp = indicators?.lth_realized_price ?? 0;

  // Narrative
  const narrative = buildNarrative(
    mvrv,
    mvrvZone.zone,
    nupl,
    rsi,
    sopr,
    price,
    sma200,
    inBear,
    indicators?.sell_score ?? 0,
    indicators?.path_taken ?? "none",
    "active"
  );

  // Trades
  const trades = (tradesRaw ?? []).slice(-10).reverse();

  return {
    price: {
      current: price,
      currency,
      change_24h: change24h,
      vs_sma200: vsSma200,
      vs_ath: ath > 0 ? ((price - ath) / ath) * 100 : null,
      trend: trend.trend,
      trendColor: trend.color,
    },
    onchain: {
      mvrv,
      mvrv_pct: indicators?.mvrv_pct ?? 0,
      mvrv_z: indicators?.mvrv_z ?? 0,
      mvrv_zone: mvrvZone.zone,
      mvrv_zoneColor: mvrvZone.color,
      mvrv_source: indicators?.mvrv_source ?? "unknown",
      nupl,
      nupl_phase: getNuplPhase(nupl),
      sopr,
      sopr_signal: getSoprSignal(sopr),
      sopr_source: indicators?.sopr_source ?? "unknown",
    },
    momentum: {
      rsi,
      rsi_zone: rsiZone.zone,
      rsi_zoneColor: rsiZone.color,
      macd_hist: macdH,
      macd_signal:
        macdH < -5000
          ? "Strong Bearish"
          : macdH < -1000
            ? "Bearish"
            : macdH < 0
              ? "Weak Bearish"
              : macdH < 1000
                ? "Weak Bullish"
                : macdH < 5000
                  ? "Bullish"
                  : "Strong Bullish",
      macd_bear_cross: indicators?.macd_bear ?? false,
      rsi_divergence: indicators?.rsi_divergence ?? false,
    },
    bot: {
      status: state ? "active" : "no data",
      last_run: state?.last_run_date ?? "N/A",
      last_decision:
        lastDecision?.buy_amount > 0
          ? `BUY ${(lastDecision.buy_amount).toLocaleString()} ${currency}`
          : lastDecision?.sell_amount > 0
            ? `SELL ${(lastDecision.sell_amount).toLocaleString()} ${currency}`
            : "No trade",
      buy_amount: lastDecision?.buy_amount ?? 0,
      sell_amount: lastDecision?.sell_amount ?? 0,
      multiplier: lastDecision?.multiplier ?? 0,
      sell_score: indicators?.sell_score ?? 0,
      path_taken: indicators?.path_taken ?? "none",
      cooldown: indicators?.cooldown ?? 0,
      portfolio_value: portfolioValue,
      btc_balance: btcBalance,
      cash_balance: cashBalance,
      total_invested: totalInvested,
      total_btc_bought: totalBtcBought,
      buy_count: state?.buy_count ?? 0,
      sell_count: state?.sell_count ?? 0,
      unrealized_pnl_pct: unrealizedPnl,
      avg_cost: avgCost,
      sma_200: sma200,
      sma_365: sma365,
      in_bear: inBear,
    },
    keyLevels: {
      ath,
      realized_price: realizedPrice,
      lth_realized_price: lthRp,
      sma_200: sma200,
      sma_365: sma365,
      distance_rp:
        realizedPrice > 0
          ? ((price - realizedPrice) / realizedPrice) * 100
          : 0,
      distance_lth:
        lthRp > 0 ? ((price - lthRp) / lthRp) * 100 : 0,
      distance_sma200:
        sma200 > 0 ? ((price - sma200) / sma200) * 100 : 0,
    },
    indicatorHistory: history.map((h) => ({
      date: h.date,
      price: h.price ?? 0,
      mvrv: h.mvrv ?? 0,
      rsi: h.rsi ?? 50,
      sopr: h.sopr ?? 1,
      nupl: h.nupl ?? 0,
      sell_score: h.sell_score ?? 0,
    })),
    trades: trades,
    marketNarrative: narrative,
    lastRefreshed: new Date().toISOString(),
  };
}
