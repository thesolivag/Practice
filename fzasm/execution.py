"""Limit-order accounting with explicit intrabar ambiguity and per-target status."""
from datetime import timedelta
from .types import BiasDirection


class TradeOutcome:
    attrs = ('fz_result_r','r1_result_r','r2_result_r','r3_result_r','r4_result_r')

    def __init__(self, setup, entry_bar_idx):
        self.setup = setup
        self.entry_bar_idx = entry_bar_idx
        self.symbol, self.direction = setup.symbol, setup.bias
        self.entry_price, self.stop_loss = setup.entry_price, setup.stop_loss
        self.unit_risk = abs(self.entry_price-self.stop_loss)
        if self.unit_risk <= 0:
            raise ValueError('Nonpositive risk')
        self.sign = 1 if self.direction == BiasDirection.BULLISH else -1
        self.fz_tp1, self.fz_tp2 = setup.take_profit_1, setup.take_profit_2
        self.tp_1r, self.tp_2r, self.tp_3r, self.tp_4r = [self.entry_price+self.sign*self.unit_risk*r for r in (1,2,3,4)]
        self.status = {a:'PENDING' for a in self.attrs}
        self.exit_times = {}
        self.reasons = {}
        for a in self.attrs:
            setattr(self,a,None)
        self.filled_at = None
        self.exit_time = None
        self.closed = False
        self.bars_held = 0
        self.fz_tp1_hit = False
        self.fz_tp1_banked = 0.
        self.last_bar = None

    def is_fully_evaluated(self):
        return all(s not in ('PENDING','OPEN') for s in self.status.values())

    def finish(self, attr, status, at, result=None, reason=''):
        self.status[attr] = status
        setattr(self,attr,result)
        self.exit_times[attr] = at
        self.reasons[attr] = reason
        self.closed = self.is_fully_evaluated()
        if self.closed:
            self.exit_time = at

    def r(self, price):
        return self.sign*(price-self.entry_price)/self.unit_risk

    def _path(self, points, attr, filled, partial):
        """Simulate one continuous OHLC traversal; return result and state.

        Opposite traversals are compared, not selected for their profit.
        """
        target = self.r(self.fz_tp2) if attr == 'fz_result_r' else int(attr[1])
        tp1 = self.r(self.fz_tp1)
        start = self.r(points[0])
        if not filled and start <= 0:
            # Adverse gap beyond stop cannot establish a normal entry/stop fill.
            if start <= -1:
                return None, filled, partial, 'GAP_THROUGH_ENTRY_STOP'
            filled = True
        if filled:
            stop = 0 if partial and attr == 'fz_result_r' else -1
            if start <= stop:
                return ((.5*tp1 + .5*start) if partial else start), filled, partial, ''
            if start >= target:
                return ((.5*tp1+.5*target) if attr == 'fz_result_r' else target), filled, True, ''
            if attr == 'fz_result_r' and start >= tp1:
                partial = True
        for endprice in points[1:]:
            end = self.r(endprice)
            if not filled and min(start,end) <= 0 <= max(start,end):
                filled = True
                start = 0
            if filled:
                if end < start:
                    stop = 0 if partial and attr == 'fz_result_r' else -1
                    if end <= stop <= start:
                        return (.5*tp1 if partial else -1.), filled, partial, ''
                elif end > start:
                    if attr == 'fz_result_r' and not partial and start <= tp1 <= end:
                        partial = True
                    if start <= target <= end:
                        result = .5*tp1+.5*target if attr == 'fz_result_r' else target
                        return result, filled, partial, ''
            start = end
        return None, filled, partial, ''

    def evaluate_bar(self, bar, bar_idx, max_bars=120):
        if self.closed or bar.timestamp < self.setup.timestamp or bar.timestamp == self.last_bar:
            return
        # Missing intervals could hide either fill or exit: never jump over them.
        if bar.timestamp > (self.last_close if self.last_bar is not None else self.setup.timestamp):
            for a in self.attrs:
                if self.status[a] in ('PENDING','OPEN'):
                    self.finish(a,'UNKNOWN',bar.timestamp,reason='DATA_GAP')
            return
        self.last_bar, self.last_close = bar.timestamp, bar.available_at
        self.bars_held += 1
        # Pending orders expire at the configured Asian session end (UTC research default).
        expiry = self.setup.timestamp.replace(hour=6,minute=0,second=0,microsecond=0)
        for attr in self.attrs:
            status = self.status[attr]
            if status not in ('PENDING','OPEN'):
                continue
            if status == 'PENDING' and bar.timestamp >= expiry:
                self.finish(attr,'UNFILLED',bar.timestamp,reason='SESSION_EXPIRED')
                continue
            partial = self.fz_tp1_hit if attr == 'fz_result_r' else False
            # With partials, arbitrary extra turns inside OHLC can hit the new
            # break-even stop between TP1 and TP2. Two canonical paths alone
            # cannot prove that did not happen.
            lo_r, hi_r = sorted((self.r(bar.low),self.r(bar.high)))
            if attr == 'fz_result_r' and not partial and lo_r <= 0 and hi_r >= self.r(self.fz_tp1):
                self.finish(attr,'UNKNOWN',bar.available_at,reason='TP1_BREAK_EVEN_ORDER')
                continue
            outcomes = [self._path(path,attr,status=='OPEN',partial) for path in
                        ((bar.open,bar.high,bar.low,bar.close),(bar.open,bar.low,bar.high,bar.close))]
            first, second = outcomes
            if first != second or first[3]:
                self.finish(attr,'UNKNOWN',bar.available_at,reason=first[3] or 'INTRABAR_ORDER')
                continue
            result, filled, partial, _ = first
            if filled:
                if self.filled_at is None:
                    self.filled_at = bar.timestamp
                self.status[attr] = 'OPEN'
            if attr == 'fz_result_r':
                self.fz_tp1_hit = partial
                self.fz_tp1_banked = .5*self.r(self.fz_tp1) if partial else 0.
            if result is not None:
                self.finish(attr,'CLOSED',bar.available_at,result)
            elif filled and bar.available_at >= self.filled_at + timedelta(hours=max_bars):
                result = self.r(bar.close)
                if attr == 'fz_result_r' and partial:
                    result = self.fz_tp1_banked+.5*result
                self.finish(attr,'CLOSED',bar.available_at,result,reason='TIME_EXIT')

    def end_of_data(self, at):
        for attr in self.attrs:
            if self.status[attr] in ('PENDING','OPEN'):
                self.finish(attr,'UNKNOWN',at,reason='END_OF_DATA')
