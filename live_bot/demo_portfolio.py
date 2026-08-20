'''Demo Portfolio Simulation — isolated paper trading environment.

Separate from live state.json. Provides:
- Independent portfolio tracking (demo_state.json, demo_trades.json)
- Portfolio history time series (every run → snapshot)
- Slippage simulation (random 0.01-0.05%)
- Validation report: compares demo trades vs expected strategy behavior
- Pre-flight checklist before going live
- Multi-scenario support (different budgets, exchange configs)

Usage:
    python live_bot/main.py --demo                  # Start/continue demo
    python live_bot/main.py --demo --reset            # Reset demo portfolio
    python live_bot/main.py --demo --scenario aggressive  # Named scenario
    python live_bot/main.py --demo --validate          # Run validation report

Files created:
    demo_state.json    — portfolio state (balances, P&L, history)
    demo_trades.json   — trade log (separate from live trade_log.json)
    demo_report.json   — latest validation report
'''

import json
import os
import math
import random
import tempfile
from datetime import date, datetime, timedelta
from copy import deepcopy


# ── Default demo state template ──
DEMO_STATE_TEMPLATE = {
    'scenario': 'default',
    'initial_cash': 10000.0,
    'currency': 'USDT',
    'exchange': 'binance',
    'created_at': '',
    'last_run_date': '',
    'run_count': 0,
    'cash': 0.0,
    'btc': 0.0,
    # Reserve from BTC sale profits (separate from DCA waiting cash)
    'sell_proceeds_reserve': 0.0,
    'total_invested': 0.0,
    'total_sell_proceeds': 0.0,
    'total_btc_bought': 0.0,
    'total_btc_sold': 0.0,
    'buy_count': 0,
    'sell_count': 0,
    'cumulative_fees': 0.0,
    'cumulative_slippage': 0.0,
    'peak_value': 0.0,
    'max_drawdown': 0.0,
    'cooldown': 0,
    # Currency integrity lock — prevents mixed THB/USDT data
    'currency_locked': False,
    # Portfolio history: list of {date, portfolio_value, btc, cash, price, decision}
    'history': [],
    # Last run details
    'last_decision': None,
    'last_price': 0.0,
    'last_indicators': {},
    # Validation
    'validation': {
        'total_runs': 0,
        'buy_signals': 0,
        'sell_signals': 0,
        'actual_buys': 0,
        'actual_sells': 0,
        'skipped_buys_reason': {},
        'skipped_sells_reason': {},
        'avg_buy_slippage_pct': 0.0,
        'avg_sell_slippage_pct': 0.0,
    },
}


def get_demo_paths(project_root: str, scenario: str = 'default') -> dict:
    """Get file paths for demo portfolio files."""
    base = project_root
    suffix = f'_{scenario}' if scenario != 'default' else ''
    return {
        'state': os.path.join(base, f'demo_state{suffix}.json'),
        'trades': os.path.join(base, f'demo_trades{suffix}.json'),
        'report': os.path.join(base, f'demo_report{suffix}.json'),
    }


def _validate_currency_exchange(exchange: str, currency: str) -> tuple:
    """Validate currency matches exchange. Returns (ok, expected_currency)."""
    expected = {'binance': 'USDT', 'bitkub': 'THB'}.get(exchange, 'USDT')
    if currency != expected:
        return False, expected
    return True, expected


def init_demo(initial_cash: float = 10000.0, currency: str = 'USDT',
              exchange: str = 'binance', scenario: str = 'default',
              project_root: str = '.') -> dict:
    """Initialize a fresh demo portfolio."""
    paths = get_demo_paths(project_root, scenario)
    state = deepcopy(DEMO_STATE_TEMPLATE)
    state['scenario'] = scenario
    state['initial_cash'] = initial_cash
    state['cash'] = initial_cash
    state['exchange'] = exchange

    # Currency validation: force correct currency for exchange
    ok, expected = _validate_currency_exchange(exchange, currency)
    if not ok:
        print(f'[DEMO] WARNING: Currency {currency} mismatched with exchange {exchange}. '
              f'Auto-correcting to {expected}.')
        currency = expected
    state['currency'] = currency
    state['currency_locked'] = True  # Lock currency after first init

    state['created_at'] = datetime.now().isoformat()
    _save_json(state, paths['state'])
    _save_json([], paths['trades'])
    print(f'[DEMO] Initialized demo portfolio: "{scenario}"')
    print(f'[DEMO]   Initial cash: {initial_cash:,.2f} {currency}')
    print(f'[DEMO]   Exchange: {exchange}')
    print(f'[DEMO]   Currency locked: {currency}')
    print(f'[DEMO]   Files: {paths["state"]}')
    return state


def load_demo_state(project_root: str, scenario: str = 'default',
                       expected_exchange: str = None) -> dict:
    """Load demo state, or initialize if not exists.

    Validates currency integrity on load. If the loaded state's currency
    doesn't match the expected currency for its exchange, raises ValueError
    to prevent mixed-currency data corruption.

    If expected_exchange is provided and differs from the stored exchange,
    raises ValueError to prevent running with wrong exchange data.
    """
    paths = get_demo_paths(project_root, scenario)
    if os.path.exists(paths['state']):
        with open(paths['state'], 'r') as f:
            state = json.load(f)
        # Currency integrity check
        loaded_exchange = state.get('exchange', 'binance')
        loaded_currency = state.get('currency', 'USDT')
        ok, expected = _validate_currency_exchange(loaded_exchange, loaded_currency)
        if not ok:
            raise ValueError(
                f'CURRENCY INTEGRITY ERROR: demo_state has currency={loaded_currency} '
                f'but exchange={loaded_exchange} expects {expected}. '
                f'This state has mixed THB/USDT data and must be reset. '
                f'Run with --reset to start fresh.'
            )
        # Exchange mismatch check: if caller expects a different exchange,
        # the existing state has wrong-exchange data and must be reset.
        if expected_exchange and loaded_exchange != expected_exchange:
            raise ValueError(
                f'EXCHANGE MISMATCH: demo_state has exchange={loaded_exchange} '
                f'but requested exchange={expected_exchange}. '
                f'The existing portfolio data is for a different exchange. '
                f'Run with --reset to start fresh with {expected_exchange}.'
            )
        return state
    # Auto-init on first load (use expected_exchange if provided)
    init_exchange = expected_exchange or 'binance'
    return init_demo(scenario=scenario, exchange=init_exchange, project_root=project_root)


def save_demo_state(state: dict, project_root: str, scenario: str = 'default'):
    """Save demo state atomically."""
    paths = get_demo_paths(project_root, scenario)
    _save_json(state, paths['state'])


def load_demo_trades(project_root: str, scenario: str = 'default') -> list:
    """Load demo trade log."""
    paths = get_demo_paths(project_root, scenario)
    if os.path.exists(paths['trades']):
        with open(paths['trades'], 'r') as f:
            return json.load(f)
    return []


def reset_demo(project_root: str, scenario: str = 'default',
               initial_cash: float = None) -> dict:
    """Reset demo portfolio to fresh state."""
    paths = get_demo_paths(project_root, scenario)
    # Load old state to get config
    if os.path.exists(paths['state']) and initial_cash is None:
        with open(paths['state'], 'r') as f:
            old = json.load(f)
        initial_cash = old.get('initial_cash', 10000.0)
        currency = old.get('currency', 'USDT')
        exchange = old.get('exchange', 'binance')
    else:
        initial_cash = initial_cash or 10000.0
        currency = 'USDT'
        exchange = 'binance'
    return init_demo(initial_cash, currency, exchange, scenario, project_root)


def simulate_slippage(amount: float, side: str,
                       base_pct: float = 0.03) -> tuple:
    """Simulate order slippage.

    Returns (adjusted_amount, slippage_cost).
    Slippage is random 0.01-0.05% by default, always against the trader.
    - Buy: you pay MORE (slippage adds to cost)
    - Sell: you receive LESS (slippage reduces proceeds)
    """
    slippage_pct = random.uniform(base_pct * 0.3, base_pct * 1.7) / 100
    slippage_cost = amount * slippage_pct
    if side == 'buy':
        return amount + slippage_cost, slippage_cost
    else:
        return amount - slippage_cost, slippage_cost


def process_demo_trade(state: dict, decision: dict, price: float,
                       currency: str, fee_pct: float = 0.0015,
                       use_slippage: bool = True,
                       project_root: str = '.',
                       scenario: str = 'default') -> dict:
    """Process a trading decision in the demo portfolio.

    This replaces the trade execution logic in engine.py for demo mode.
    Returns updated state dict.
    """
    today = date.today().isoformat()
    state['last_run_date'] = today
    state['run_count'] += 1
    state['last_price'] = price
    state['last_decision'] = {
        'buy_amount': round(decision.get('buy_amount', 0), 2),
        'sell_amount': round(decision.get('sell_amount', 0), 2),
        'sell_score': decision.get('sell_score', 0),
        'path_taken': decision.get('path_taken', 'none'),
        'reserve_injection': round(decision.get('reserve_injection', 0), 2),
        'in_bear': decision.get('in_bear', False),
    }

    # Decrement cooldown
    if state['cooldown'] > 0:
        state['cooldown'] -= 1
    state['cooldown'] = decision.get('new_cooldown', state['cooldown'])

    # Update validation counters
    val = state['validation']
    val['total_runs'] += 1

    buy_signal = decision.get('buy_amount', 0) > 0
    sell_signal = decision.get('sell_amount', 0) > 0
    if buy_signal:
        val['buy_signals'] += 1
    if sell_signal:
        val['sell_signals'] += 1

    # ── BUY ──
    buy_status = 'none'
    if buy_signal:
        buy_amount = decision['buy_amount']
        buy_attempted = buy_amount  # Track original for status reporting
        min_buy = 10.0 if currency == 'USDT' else 10.0

        if buy_amount < min_buy:
            reason = f'below_min ({buy_amount:.2f} < {min_buy})'
            val['skipped_buys_reason'][reason] = val['skipped_buys_reason'].get(reason, 0) + 1
            buy_status = 'skipped'
            print(f'[DEMO] BUY SKIPPED: {reason}')
        elif state['cash'] < buy_amount:
            # Buy with what we have
            if state['cash'] >= min_buy:
                buy_amount = state['cash']
                print(f'[DEMO] BUY ADJUSTED: insufficient cash, using {buy_amount:.2f}')
            else:
                reason = f'no_cash ({state["cash"]:.2f})'
                val['skipped_buys_reason'][reason] = val['skipped_buys_reason'].get(reason, 0) + 1
                buy_status = 'skipped'
                print(f'[DEMO] BUY SKIPPED: {reason}')
                buy_amount = 0

        if buy_amount > 0:
            # Apply slippage
            if use_slippage:
                cost_with_slippage, slip_cost = simulate_slippage(buy_amount, 'buy')
            else:
                cost_with_slippage = buy_amount
                slip_cost = 0.0

            fee = cost_with_slippage * fee_pct
            total_cost = cost_with_slippage + fee
            btc_got = cost_with_slippage / price

            if total_cost > state['cash']:
                # Re-adjust if slippage pushed us over
                cost_with_slippage = state['cash'] / (1 + fee_pct)
                fee = cost_with_slippage * fee_pct
                total_cost = cost_with_slippage + fee
                btc_got = cost_with_slippage / price
                slip_cost = cost_with_slippage - buy_amount

            state['cash'] -= total_cost
            state['btc'] += btc_got
            state['total_invested'] += cost_with_slippage
            state['total_btc_bought'] += btc_got
            state['buy_count'] += 1
            state['cumulative_fees'] += fee
            state['cumulative_slippage'] += max(0, slip_cost)
            val['actual_buys'] += 1
            buy_status = 'success'

            # Deduct reserve injection from sell_proceeds_reserve
            reserve_inj = decision.get('reserve_injection', 0)
            if reserve_inj > 0:
                state['sell_proceeds_reserve'] = max(0, state.get('sell_proceeds_reserve', 0) - reserve_inj)

            print(f'[DEMO] BUY: {cost_with_slippage:.2f} {currency} -> {btc_got:.8f} BTC @ {price:,.2f}')
            print(f'[DEMO]   Fee: {fee:.2f}  Slippage: {max(0, slip_cost):.4f}  Status: {buy_status}')
            if reserve_inj > 0:
                print(f'[DEMO]   Reserve used: {reserve_inj:.2f} (remaining: {state["sell_proceeds_reserve"]:,.2f} {currency})')

            # Record trade
            _append_demo_trade(project_root, scenario, 'buy',
                              cost_with_slippage, btc_got, price, fee,
                              extra={
                                  'slippage': round(max(0, slip_cost), 4),
                                  'reserve': round(decision.get('reserve_injection', 0), 2),
                              })

    # ── SELL ──

    if sell_signal and not buy_signal:
        sell_amount = decision['sell_amount']
        btc_to_sell = sell_amount / price

        # Never sell 100%
        if btc_to_sell >= state['btc'] * 0.99:
            btc_to_sell = state['btc'] * 0.99

        min_sell = 10.0 if currency == 'USDT' else 10.0
        if btc_to_sell * price < min_sell:
            reason = f'below_min ({btc_to_sell * price:.2f} < {min_sell})'
            val['skipped_sells_reason'][reason] = val['skipped_sells_reason'].get(reason, 0) + 1
            print(f'[DEMO] SELL SKIPPED: {reason}')
        else:
            # Apply slippage
            if use_slippage:
                proceeds_with_slippage, slip_cost = simulate_slippage(sell_amount, 'sell')
            else:
                proceeds_with_slippage = sell_amount
                slip_cost = 0.0

            fee = proceeds_with_slippage * fee_pct
            net_proceeds = proceeds_with_slippage - fee
            btc_sold = proceeds_with_slippage / price

            state['btc'] -= btc_sold
            # Separate: sell proceeds go to reserve (for buy-the-dip), not general cash
            state['sell_proceeds_reserve'] = state.get('sell_proceeds_reserve', 0.0) + net_proceeds
            # Also add to cash for portfolio value calculation
            state['cash'] += net_proceeds
            state['total_sell_proceeds'] += proceeds_with_slippage
            state['total_btc_sold'] += btc_sold
            state['sell_count'] += 1
            state['cumulative_fees'] += fee
            state['cumulative_slippage'] += max(0, slip_cost)
            val['actual_sells'] += 1

            print(f'[DEMO] SELL: {btc_sold:.8f} BTC -> {proceeds_with_slippage:.2f} {currency} @ {price:,.2f}')
            print(f'[DEMO]   Fee: {fee:.2f}  Slippage: {max(0, slip_cost):.4f}')
            print(f'[DEMO]   Proceeds -> reserve (total reserve: {state["sell_proceeds_reserve"]:,.2f} {currency})')

            _append_demo_trade(project_root, scenario, 'sell',
                              proceeds_with_slippage, btc_sold, price, fee,
                              extra={
                                  'slippage': round(max(0, slip_cost), 4),
                                  'path': decision.get('path_taken', ''),
                                  'score': decision.get('sell_score', 0),
                              })

    # ── Portfolio snapshot ──
    portfolio = state['btc'] * price + state['cash']
    if portfolio > state['peak_value']:
        state['peak_value'] = portfolio
    if state['peak_value'] > 0:
        dd = (state['peak_value'] - portfolio) / state['peak_value']
        if dd > state['max_drawdown']:
            state['max_drawdown'] = dd

    # Append to history
    state['history'].append({
        'date': today,
        'portfolio_value': round(portfolio, 2),
        'btc': round(state['btc'], 8),
        'cash': round(state['cash'], 2),
        'price': round(price, 2),
        'decision': 'buy' if buy_status == 'success' else ('sell' if sell_signal and not buy_signal else ('buy_skipped' if buy_status == 'skipped' else 'hold')),
        'buy_status': buy_status,
    })
    # Keep last 365 history entries
    if len(state['history']) > 365:
        state['history'] = state['history'][-365:]

    # Save
    save_demo_state(state, project_root, scenario)

    # Print summary
    roi = ((portfolio - state['initial_cash']) / state['initial_cash'] * 100) if state['initial_cash'] > 0 else 0
    print(f'[DEMO] Portfolio: {portfolio:,.2f} {currency} (ROI: {roi:+.2f}%)')
    print(f'[DEMO] BTC: {state["btc"]:.8f}  Cash: {state["cash"]:,.2f}')
    print(f'[DEMO] Peak: {state["peak_value"]:,.2f}  MaxDD: {state["max_drawdown"]*100:.2f}%')
    print(f'[DEMO] Buy status: {buy_status}')
    reserve = state.get('sell_proceeds_reserve', 0.0)
    print(f'[DEMO] Sell proceeds reserve: {reserve:,.2f} {currency}')

    # Low balance warning
    from . import config as cfg
    daily_budget = cfg.get_daily_budget()
    if state['cash'] > 0 and daily_budget > 0:
        days_remaining = state['cash'] / daily_budget
        if days_remaining <= cfg.LOW_BALANCE_DAYS:
            print(f'[DEMO] ⚠ LOW BALANCE WARNING: {state["cash"]:,.2f} {currency} remaining')
            print(f'[DEMO] ⚠ At {daily_budget:,.2f} {currency}/run, only ~{days_remaining:.1f} runs left')

    return state


def snapshot_indicators(state: dict, indicators: dict):
    """Store indicator snapshot in demo state."""
    state['last_indicators'] = indicators


def generate_validation_report(state: dict, project_root: str,
                               scenario: str = 'default') -> dict:
    """Generate a pre-flight validation report for the demo portfolio.

    Checks:
    1. Strategy signal consistency (buy/sell signals fired as expected)
    2. Slippage impact analysis
    3. P&L confidence interval
    4. Risk metrics (max DD, Sharpe-like ratio)
    5. Go-live readiness checklist
    """
    trades = load_demo_trades(project_root, scenario)
    history = state.get('history', [])
    val = state.get('validation', {})

    # ── 1. Signal consistency ──
    signal_exec_ratio_buy = (val.get('actual_buys', 0) / val.get('buy_signals', 1)) * 100 if val.get('buy_signals', 0) > 0 else 100
    signal_exec_ratio_sell = (val.get('actual_sells', 0) / val.get('sell_signals', 1)) * 100 if val.get('sell_signals', 0) > 0 else 100

    # ── 2. Slippage analysis ──
    total_slip = state.get('cumulative_slippage', 0)
    total_traded = state.get('total_invested', 0) + state.get('total_sell_proceeds', 0)
    avg_slip_pct = (total_slip / total_traded * 100) if total_traded > 0 else 0

    # ── 3. P&L metrics ──
    portfolio = state.get('btc', 0) * state.get('last_price', 0) + state.get('cash', 0)
    invested = state.get('total_invested', 0)
    initial = state.get('initial_cash', 10000)
    total_fees = state.get('cumulative_fees', 0)
    net_pnl = portfolio - initial
    roi_pct = (net_pnl / initial * 100) if initial > 0 else 0

    # ── 4. Risk metrics from history ──
    returns = []
    for i in range(1, len(history)):
        prev_val = history[i-1]['portfolio_value']
        curr_val = history[i]['portfolio_value']
        if prev_val > 0:
            returns.append((curr_val - prev_val) / prev_val)

    avg_return = sum(returns) / len(returns) if returns else 0
    std_return = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5 if returns else 0
    sharpe_like = (avg_return / std_return * (365**0.5)) if std_return > 0 else 0

    # ── 5. Go-live checklist ──
    checks = []
    min_runs = 14  # At least 2 weeks of daily runs

    def check(name, passed, detail):
        checks.append({'name': name, 'passed': passed, 'detail': detail})

    check('Minimum runs',
          val.get('total_runs', 0) >= min_runs,
          f'{val.get("total_runs", 0)}/{min_runs} runs')

    check('Buy signals executed',
          signal_exec_ratio_buy >= 80,
          f'{signal_exec_ratio_buy:.0f}% of buy signals executed')

    check('No excessive skipped buys',
          val.get('buy_signals', 0) - val.get('actual_buys', 0) <= 2,
          f'{val.get("buy_signals", 0) - val.get("actual_buys", 0)} skipped')

    check('Fees reasonable',
          total_fees < initial * 0.02,
          f'Total fees: {total_fees:.2f} ({total_fees/initial*100:.2f}% of capital)')

    check('Slippage acceptable',
          avg_slip_pct < 0.1,
          f'Avg slippage: {avg_slip_pct:.4f}%')

    check('Max drawdown known',
          state.get('max_drawdown', 0) > 0 or val.get('total_runs', 0) >= min_runs,
          f'Max DD: {state.get("max_drawdown", 0)*100:.2f}%')

    check('Portfolio positive or acceptable',
          net_pnl > -initial * 0.15,
          f'P&L: {net_pnl:+.2f} ({roi_pct:+.2f}%)')

    check('At least 1 buy executed',
          val.get('actual_buys', 0) >= 1,
          f'{val.get("actual_buys", 0)} buys')

    all_passed = all(c['passed'] for c in checks)
    go_live_ready = all_passed and val.get('total_runs', 0) >= min_runs

    report = {
        'generated_at': datetime.now().isoformat(),
        'scenario': scenario,
        'summary': {
            'total_runs': val.get('total_runs', 0),
            'buy_signals': val.get('buy_signals', 0),
            'sell_signals': val.get('sell_signals', 0),
            'actual_buys': val.get('actual_buys', 0),
            'actual_sells': val.get('actual_sells', 0),
            'signal_exec_ratio_buy': round(signal_exec_ratio_buy, 1),
            'signal_exec_ratio_sell': round(signal_exec_ratio_sell, 1),
        },
        'performance': {
            'initial_cash': initial,
            'current_portfolio': round(portfolio, 2),
            'net_pnl': round(net_pnl, 2),
            'roi_pct': round(roi_pct, 2),
            'total_invested': round(invested, 2),
            'total_fees': round(total_fees, 2),
            'total_slippage': round(total_slip, 4),
            'avg_slippage_pct': round(avg_slip_pct, 4),
            'peak_value': round(state.get('peak_value', 0), 2),
            'max_drawdown_pct': round(state.get('max_drawdown', 0) * 100, 2),
            'sharpe_like': round(sharpe_like, 2),
            'avg_daily_return_pct': round(avg_return * 100, 4),
        },
        'skipped_trades': {
            'buys': val.get('skipped_buys_reason', {}),
            'sells': val.get('skipped_sells_reason', {}),
        },
        'go_live_checklist': checks,
        'go_live_ready': go_live_ready,
        'recommendation': _get_recommendation(val, state, checks),
    }

    # Save report
    paths = get_demo_paths(project_root, scenario)
    _save_json(report, paths['report'])

    return report


def _get_recommendation(val: dict, state: dict, checks: list) -> str:
    """Generate human-readable recommendation."""
    total_runs = val.get('total_runs', 0)
    if total_runs < 7:
        return (f'TOO EARLY: Only {total_runs} runs. '
                f'Need at least 14 runs (2 weeks daily) for meaningful validation. '
                f'Keep the demo running.')
    if total_runs < 14:
        signal_word = 'good' if all(c["passed"] for c in checks[:3]) else 'concerning'
        return (f'GETTING THERE: {total_runs}/14 minimum runs. '
                f'Strategy signals look {signal_word}. '
                f'Wait for 14+ runs before considering go-live.')

    failed = [c for c in checks if not c['passed']]
    if not failed:
        return ('GO-LIVE READY: All checks passed. The demo portfolio shows consistent strategy execution. '
                'Consider starting with a small live amount (10-20% of intended capital) and monitor for 1-2 weeks.')
    return (f'NOT YET: {len(failed)} check(s) failed: '
            + ', '.join(f["name"] for f in failed) + '. '
            + 'Address these issues before going live.')


def print_validation_report(report: dict):
    """Pretty-print the validation report."""
    print()
    print('=' * 60)
    print('  DEMO PORTFOLIO VALIDATION REPORT')
    print('=' * 60)
    s = report['summary']
    p = report['performance']
    print(f'  Scenario:        {report["scenario"]}')
    print(f'  Generated:       {report["generated_at"]}')
    print(f'  Total runs:      {s["total_runs"]}')
    print()
    print('  ── Signal Execution ──')
    print(f'  Buy signals:     {s["buy_signals"]} (executed: {s["actual_buys"]}, ratio: {s["signal_exec_ratio_buy"]}%)')
    print(f'  Sell signals:    {s["sell_signals"]} (executed: {s["actual_sells"]}, ratio: {s["signal_exec_ratio_sell"]}%)')
    print()
    print('  ── Performance ──')
    print(f'  Initial cash:    {p["initial_cash"]:,.2f}')
    print(f'  Portfolio now:   {p["current_portfolio"]:,.2f}')
    print(f'  Net P&L:         {p["net_pnl"]:+,.2f} ({p["roi_pct"]:+.2f}%)')
    print(f'  Total invested:  {p["total_invested"]:,.2f}')
    print(f'  Total fees:      {p["total_fees"]:,.2f}')
    print(f'  Total slippage:  {p["total_slippage"]:,.4f} (avg: {p["avg_slippage_pct"]:.4f}%)')
    print(f'  Peak value:      {p["peak_value"]:,.2f}')
    print(f'  Max drawdown:    {p["max_drawdown_pct"]:.2f}%')
    print(f'  Sharpe-like:     {p["sharpe_like"]:.2f}')
    print()
    print('  ── Skipped Trades ──')
    skipped = report['skipped_trades']
    if skipped['buys']:
        for reason, count in skipped['buys'].items():
            print(f'  Buy skipped:     {count}x — {reason}')
    else:
        print('  Buy skipped:     none')
    if skipped['sells']:
        for reason, count in skipped['sells'].items():
            print(f'  Sell skipped:    {count}x — {reason}')
    else:
        print('  Sell skipped:    none')
    print()
    print('  ── Go-Live Checklist ──')
    for c in report['go_live_checklist']:
        icon = 'PASS' if c['passed'] else 'FAIL'
        print(f'  [{icon}] {c["name"]}: {c["detail"]}')
    print()
    status = 'READY' if report['go_live_ready'] else 'NOT READY'
    print(f'  >>> GO-LIVE STATUS: {status} <<<')
    print()
    print(f'  Recommendation: {report["recommendation"]}')
    print('=' * 60)
    print()


def _append_demo_trade(project_root: str, scenario: str,
                       trade_type: str, amount: float, btc_amount: float,
                       price: float, fee: float, extra: dict = None):
    """Append a trade to demo trade log."""
    paths = get_demo_paths(project_root, scenario)
    trades = load_demo_trades(project_root, scenario)
    record = {
        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'type': trade_type,
        'amount': round(amount, 2),
        'btc': round(btc_amount, 8),
        'price': round(price, 2),
        'fee': round(fee, 2),
    }
    if extra:
        record.update(extra)
    trades.append(record)
    if len(trades) > 500:
        trades = trades[-500:]
    _save_json(trades, paths['trades'])


def _save_json(data, path: str):
    """Atomic JSON save."""
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
