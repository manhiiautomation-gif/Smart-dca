'use client';

import { useEffect, useState, useCallback } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Activity,
  TrendingDown,
  Bot,
  BarChart3,
  Newspaper,
  RefreshCw,
  ArrowDownRight,
  ArrowUpRight,
  AlertTriangle,
  Zap,
  Target,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// ─── Types ───

interface BriefingData {
  price: {
    current: number;
    currency: string;
    change_24h: number | null;
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
  trades: Array<{
    date: string;
    type: string;
    amount: number;
    btc: number;
    price: number;
    fee: number;
  }>;
  marketNarrative: string;
  lastRefreshed: string;
}

// ─── Mini Chart Component (SVG sparkline) ───

function Sparkline({
  data,
  color = "#f59e0b",
  height = 40,
}: {
  data: number[];
  color?: string;
  height?: number;
}) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 100;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${w} ${height}`}
      className="w-full"
      style={{ height }}
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ─── Format helpers ───

function fmt(n: number, decimals = 2): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(decimals)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(decimals)}K`;
  return n.toFixed(decimals);
}

function fmtCurrency(n: number, currency: string): string {
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 0 })} ${currency}`;
}

function ChangeBadge({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground text-xs">N/A</span>;
  const isUp = value >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 text-sm font-semibold ${isUp ? "text-emerald-500" : "text-red-500"}`}
    >
      {isUp ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
      {Math.abs(value).toFixed(2)}%
    </span>
  );
}

// ─── Main Dashboard ───

export default function Home() {
  const [data, setData] = useState<BriefingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBriefing = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/briefing");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setData(json);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBriefing();
    const interval = setInterval(fetchBriefing, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [fetchBriefing]);

  const getTimeString = () => {
    if (!data?.lastRefreshed) return "";
    return new Date(data.lastRefreshed).toLocaleTimeString("th-TH", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  if (loading && !data) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-zinc-400 flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span>Loading BTC Briefing...</span>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <Card className="bg-zinc-900 border-zinc-800 max-w-md">
          <CardContent className="pt-6 text-center">
            <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-zinc-100 mb-1">Failed to Load Data</h2>
            <p className="text-zinc-400 text-sm mb-4">{error}</p>
            <Button variant="outline" onClick={fetchBriefing} className="border-zinc-700 text-zinc-300 hover:bg-zinc-800">
              <RefreshCw className="w-4 h-4 mr-2" />Retry
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data) return null;

  const { price: p, onchain: oc, momentum: mom, bot, keyLevels: kl } = data;
  const isDark = true;

  const priceHistory = data.trades.length > 0 ? [p.current] : [];

  return (
    <div className={`min-h-screen ${isDark ? "bg-zinc-950 text-zinc-100" : "bg-white"}`}>
      {/* ─── Header ─── */}
      <header className={`border-b ${isDark ? "border-zinc-800 bg-zinc-900/80" : "border-zinc-200 bg-white/80"} backdrop-blur-sm sticky top-0 z-50`}>
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-amber-500/20 flex items-center justify-center">
              <Zap className="w-5 h-5 text-amber-500" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">BTC Daily Briefing</h1>
              <p className="text-xs text-zinc-500">Manual trading intelligence + Phoenix bot status</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Badge
              variant="outline"
              className={`${isDark ? "border-zinc-700 text-zinc-400" : "border-zinc-300 text-zinc-600"} text-xs`}
            >
              {getTimeString()}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchBriefing}
              disabled={loading}
              className={`${isDark ? "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800" : ""}`}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* ─── Row 1: Price Hero + Trend ─── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Price Hero Card */}
          <Card className={`lg:col-span-2 ${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardContent className="pt-6">
              <div className="flex flex-col sm:flex-row sm:items-end gap-3 mb-4">
                <div>
                  <p className={`text-sm font-medium ${isDark ? "text-zinc-400" : "text-zinc-500"} mb-1`}>
                    BTC / {p.currency}
                  </p>
                  <div className="flex items-baseline gap-3">
                    <span className="text-4xl font-bold tracking-tight">
                      {p.current.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <ChangeBadge value={p.change_24h} />
                  </div>
                </div>
                <Badge
                  className="self-start sm:self-end"
                  style={{
                    backgroundColor: `${p.trendColor}20`,
                    color: p.trendColor,
                    borderColor: `${p.trendColor}40`,
                  }}
                >
                  {p.trend}
                </Badge>
              </div>
              {/* Price vs Key MAs */}
              <div className={`grid grid-cols-3 gap-3 ${isDark ? "text-zinc-400" : "text-zinc-600"}`}>
                <div className="text-center">
                  <p className="text-xs mb-0.5">vs SMA200</p>
                  <p className="text-sm font-semibold">
                    {p.vs_sma200 !== null ? (
                      <span className={p.vs_sma200 >= 0 ? "text-emerald-400" : "text-red-400"}>
                        {p.vs_sma200 >= 0 ? "+" : ""}
                        {p.vs_sma200.toFixed(1)}%
                      </span>
                    ) : (
                      "N/A"
                    )}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs mb-0.5">vs ATH</p>
                  <p className="text-sm font-semibold">
                    {p.vs_ath !== null ? (
                      <span className={p.vs_ath >= 0 ? "text-emerald-400" : "text-red-400"}>
                        {p.vs_ath >= 0 ? "+" : ""}
                        {p.vs_ath.toFixed(1)}%
                      </span>
                    ) : (
                      "N/A"
                    )}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-xs mb-0.5">SMA200</p>
                  <p className="text-sm font-semibold">
                    {bot.sma_200 > 0
                      ? bot.sma_200.toLocaleString(undefined, { maximumFractionDigits: 0 })
                      : "N/A"}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Phoenix Bot Status Card */}
          <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Bot className="w-4 h-4 text-amber-500" />
                Phoenix v5.1
                <Badge
                  variant="outline"
                  className={`ml-auto text-xs ${bot.status === "active" ? "border-emerald-700 text-emerald-400" : "border-red-700 text-red-400"}`}
                >
                  {bot.status === "active" ? "ACTIVE" : "OFFLINE"}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div>
                  <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>Portfolio</p>
                  <p className="font-semibold">{fmtCurrency(bot.portfolio_value, p.currency)}</p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>P&L</p>
                  <p
                    className={`font-semibold ${bot.unrealized_pnl_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {bot.unrealized_pnl_pct >= 0 ? "+" : ""}
                    {bot.unrealized_pnl_pct.toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>BTC</p>
                  <p className="font-mono text-xs">{bot.btc_balance.toFixed(6)}</p>
                </div>
                <div>
                  <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>Cash</p>
                  <p className="font-mono text-xs">{fmtCurrency(bot.cash_balance, p.currency)}</p>
                </div>
              </div>
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2`}>
                <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"} mb-1`}>Last Decision</p>
                <p className="text-sm font-medium">{bot.last_decision}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>
                    Multiplier: {bot.multiplier}x | Score: {bot.sell_score}
                  </span>
                  {bot.path_taken !== "none" && (
                    <Badge variant="outline" className="text-xs border-amber-700 text-amber-400">
                      {bot.path_taken}
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ─── Row 2: On-Chain + Momentum + Key Levels ─── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* On-Chain Pulse */}
          <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Layers className="w-4 h-4 text-orange-400" />
                On-Chain Pulse
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* MVRV */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>MVRV Ratio</span>
                  <Badge
                    className="text-xs"
                    style={{
                      backgroundColor: `${oc.mvrv_zoneColor}20`,
                      color: oc.mvrv_zoneColor,
                      borderColor: `${oc.mvrv_zoneColor}40`,
                    }}
                  >
                    {oc.mvrv_zone}
                  </Badge>
                </div>
                <p className="text-2xl font-bold">{oc.mvrv.toFixed(3)}</p>
                <div className={`flex gap-4 text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>
                  <span>Pct: {(oc.mvrv_pct * 100).toFixed(1)}%</span>
                  <span>Z: {oc.mvrv_z.toFixed(2)}</span>
                </div>
              </div>
              {/* NUPL */}
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2`}>
                <div className="flex items-center justify-between">
                  <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>NUPL</span>
                  <span className="text-xs font-medium">{oc.nupl_phase}</span>
                </div>
                <p className="text-lg font-semibold">{oc.nupl.toFixed(3)}</p>
              </div>
              {/* SOPR */}
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2`}>
                <div className="flex items-center justify-between">
                  <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>SOPR</span>
                  <span className={`text-xs font-medium ${oc.sopr < 1 ? "text-emerald-400" : "text-zinc-400"}`}>
                    {oc.sopr_signal}
                  </span>
                </div>
                <p className={`text-lg font-semibold ${oc.sopr < 1 ? "text-emerald-400" : ""}`}>{oc.sopr.toFixed(3)}</p>
                <p className={`text-xs ${isDark ? "text-zinc-600" : "text-zinc-400"}`}>
                  Source: {oc.sopr_source}
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Technical Momentum */}
          <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Activity className="w-4 h-4 text-blue-400" />
                Technical Momentum
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* RSI */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>RSI (14)</span>
                  <Badge
                    className="text-xs"
                    style={{
                      backgroundColor: `${mom.rsi_zoneColor}20`,
                      color: mom.rsi_zoneColor,
                      borderColor: `${mom.rsi_zoneColor}40`,
                    }}
                  >
                    {mom.rsi_zone}
                  </Badge>
                </div>
                {/* RSI bar */}
                <div className={`w-full h-2 rounded-full ${isDark ? "bg-zinc-800" : "bg-zinc-200"} mb-1`}>
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(mom.rsi, 100)}%`,
                      backgroundColor: mom.rsi_zoneColor,
                    }}
                  />
                </div>
                <p className="text-2xl font-bold">{mom.rsi.toFixed(1)}</p>
              </div>
              {/* MACD */}
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2`}>
                <div className="flex items-center justify-between">
                  <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>MACD Histogram</span>
                  <span
                    className={`text-sm font-semibold ${mom.macd_hist >= 0 ? "text-emerald-400" : "text-red-400"}`}
                  >
                    {mom.macd_hist >= 0 ? "+" : ""}
                    {mom.macd_hist.toFixed(0)}
                  </span>
                </div>
                <p className="text-sm mt-1">{mom.macd_signal}</p>
              </div>
              {/* Signals */}
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2 space-y-1`}>
                {mom.macd_bear_cross && (
                  <div className="flex items-center gap-2 text-xs text-red-400">
                    <TrendingDown className="w-3.5 h-3.5" />
                    MACD Bearish Crossover
                  </div>
                )}
                {mom.rsi_divergence && (
                  <div className="flex items-center gap-2 text-xs text-amber-400">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    RSI Divergence Detected
                  </div>
                )}
                {!mom.macd_bear_cross && !mom.rsi_divergence && (
                  <p className={`text-xs ${isDark ? "text-zinc-600" : "text-zinc-400"}`}>
                    No divergence signals
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Key On-Chain Levels */}
          <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <Target className="w-4 h-4 text-emerald-400" />
                Key On-Chain Levels
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <LevelRow
                label="Realized Price"
                value={kl.realized_price}
                distance={kl.distance_rp}
                isDark={isDark}
              />
              <LevelRow
                label="LTH Realized Price"
                value={kl.lth_realized_price}
                distance={kl.distance_lth}
                isDark={isDark}
              />
              <LevelRow
                label="SMA 200"
                value={kl.sma_200}
                distance={kl.distance_sma200}
                isDark={isDark}
              />
              <LevelRow
                label="ATH"
                value={kl.ath}
                distance={p.vs_ath}
                isDark={isDark}
              />
              <div className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-200"} pt-2`}>
                <p className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"}`}>
                  Below Realized Price = historically profitable accumulation zone.
                  Above LTH-RP = long-term holders in profit (sell pressure zone).
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ─── Row 3: Market Narrative ─── */}
        <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold">
              <Newspaper className="w-4 h-4 text-cyan-400" />
              Market Briefing
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className={`text-sm leading-relaxed ${isDark ? "text-zinc-300" : "text-zinc-600"}`}>
              {data.marketNarrative}
            </p>
          </CardContent>
        </Card>

        {/* ─── Row 4: Recent Trades ─── */}
        {data.trades.length > 0 && (
          <Card className={`${isDark ? "bg-zinc-900 border-zinc-800" : ""}`}>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                <BarChart3 className="w-4 h-4 text-violet-400" />
                Recent Trades
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={`text-xs ${isDark ? "text-zinc-500" : "text-zinc-400"} text-left`}>
                      <th className="pb-2 pr-4">Date</th>
                      <th className="pb-2 pr-4">Type</th>
                      <th className="pb-2 pr-4 text-right">Amount</th>
                      <th className="pb-2 pr-4 text-right">BTC</th>
                      <th className="pb-2 text-right">Price</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.map((t, i) => (
                      <tr
                        key={i}
                        className={`border-t ${isDark ? "border-zinc-800" : "border-zinc-100"}`}
                      >
                        <td className={`py-2 pr-4 text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>
                          {t.date}
                        </td>
                        <td className="py-2 pr-4">
                          <Badge
                            variant="outline"
                            className={`text-xs ${t.type === "BUY" || t.type === "buy" ? "border-emerald-700 text-emerald-400" : "border-red-700 text-red-400"}`}
                          >
                            {t.type.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {t.amount.toLocaleString()} {p.currency}
                        </td>
                        <td className="py-2 pr-4 text-right font-mono text-xs">
                          {t.btc.toFixed(8)}
                        </td>
                        <td className="py-2 text-right font-mono text-xs">
                          {t.price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )}

        {/* ─── Footer ─── */}
        <footer className={`text-center py-4 text-xs ${isDark ? "text-zinc-600" : "text-zinc-400"}`}>
          Phoenix v5.1 Briefing Dashboard | Auto-refreshes every 5 min | For manual trading decisions only
        </footer>
      </main>
    </div>
  );
}

// ─── Sub-components ───

function LevelRow({
  label,
  value,
  distance,
  isDark,
}: {
  label: string;
  value: number;
  distance: number | null;
  isDark: boolean;
}) {
  if (value <= 0) return null;
  return (
    <div className="flex items-center justify-between">
      <span className={`text-xs ${isDark ? "text-zinc-400" : "text-zinc-500"}`}>
        {label}
      </span>
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono">
          {value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        </span>
        {distance !== null && (
          <span
            className={`text-xs font-semibold ${distance >= 0 ? "text-emerald-400" : "text-red-400"}`}
          >
            {distance >= 0 ? "+" : ""}
            {distance.toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}
