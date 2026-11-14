"""Opt-in, complete mechanical ASM research path (not a teacher-certified replica)."""
from collections import Counter
from dataclasses import replace
from .types import BiasDirection as B
from .sessions import AsianSessionManager, HourlySweepDetector
from .entry import EntryModelEvaluator
from .full_context import active_levels, map_candidates, choose_map, _alive
from .instruments import pip


class FullASMEngine:
    VERSION='asm-full-research-v1'

    def __init__(self, extra_pairs=None, entry_policy='auto', confirmation_tf='M5'):
        if entry_policy not in ('auto','h1_av','h1_av_m5','swing_ob','swing_fvg'):
            raise ValueError('Unknown full-model entry policy')
        self.entry_policy=entry_policy
        self.session_mgr=AsianSessionManager(extra_pairs=extra_pairs)
        self.diagnostics=Counter()
        self.contexts={}
        self.used=set()
        self.last_review={}
        self._clock=None
        self._daily_key=None
        self._daily_candidates=[]

    def scan_asset(self,symbol,candles_by_tf,current_time=None,**kwargs):
        if current_time is None or current_time.utcoffset() is None or current_time.utcoffset().total_seconds()!=0:
            raise ValueError('An explicit UTC decision clock is required')
        now=current_time
        if self._clock is not None and now<self._clock:
            raise ValueError('Replay clock cannot move backwards')
        self._clock=now
        self.last_review={'version':self.VERSION,'clock':now.isoformat(),'rejection':''}
        closed={tf:[c for c in bars if c.available_at<=now] for tf,bars in candles_by_tf.items()}
        for tf,bars in closed.items():
            if any(c.timeframe!=tf or c.timestamp.utcoffset() is None or c.timestamp.utcoffset().total_seconds()!=0 for c in bars) or any(a.timestamp>=b.timestamp for a,b in zip(bars,bars[1:])):
                raise ValueError('Candles must be unique, ordered and match their timeframe')
        if not self.session_mgr.is_supported_symbol(symbol):return None
        if not self.session_mgr.is_in_asian_session(now):
            self.contexts={k:v for k,v in self.contexts.items() if k[0]!=symbol}
            return None
        self.contexts={k:v for k,v in self.contexts.items() if k[0]!=symbol or k[1].date()==now.date()}
        minute=closed.get('M5',[])
        h1=closed.get('H1',[])
        if not h1:return self._reject('NO_H1')
        price=minute[-1].close if minute else h1[-1].close
        daily_key=(tuple(closed.get('D1',[])),pip(symbol))
        if daily_key!=self._daily_key:
            self._daily_candidates=map_candidates(closed.get('D1',[]),pip(symbol))
            self._daily_key=daily_key
        maps=self._daily_candidates
        intraday=closed.get('H1',[])+closed.get('M5',[])
        maps=[m for m in maps if _alive(m,[c for c in intraday if c.timestamp>=m.timestamp])]
        daily,reason=choose_map(maps,price)
        self.last_review={'version':self.VERSION,'clock':now.isoformat(),'map_candidates':[
            {'map':m.map_type.value,'bias':m.bias.value,'from':m.origin_level,'to':m.target_level,
             'known_at':m.timestamp.isoformat(),'rule':m.notes} for m in maps],'rejection':reason}
        if daily is None:
            # A rejected/reversed context must not reappear after its entry clock.
            self.contexts={k:v for k,v in self.contexts.items() if k[0]!=symbol}
            return self._reject(reason)
        # Discover at sweep CLOSE only. H2 is a fallback when no H1 sweep is
        # available at the same decision clock. Older valid contexts coexist.
        sweeps=[]
        for tf in ('H1','H2'):
            bars=closed.get(tf,[])
            if bars and bars[-1].available_at==now:
                sweep=HourlySweepDetector.detect_h1_sweep(bars)
                if sweep and self.session_mgr.is_in_asian_session(sweep.sweep_candle.timestamp):
                    sweeps.append(sweep)
                    break
        for sweep in sweeps:
            key=(symbol,sweep.sweep_candle.timestamp,sweep.sweep_candle.timeframe)
            if key in self.used or key in self.contexts:continue
            if sweep.direction!=daily.bias:
                self._reject('SWEEP_MAP_CONFLICT');continue
            # Freeze levels as they were known before the sweep OPEN. No level
            # created by the sweep can retroactively justify its location.
            pois=[]
            for tf in ('H4','H2'):
                prior=[c for c in closed.get(tf,[]) if c.available_at<=sweep.sweep_candle.timestamp]
                for p in active_levels(prior,pip(symbol)):
                    if p.direction==sweep.direction and p.is_tested_by(sweep.sweep_candle):
                        in_zone=(daily.origin_level<=p.mid_price<=daily.equilibrium_50) if daily.bias==B.BULLISH else (daily.equilibrium_50<=p.mid_price<=daily.origin_level)
                        respected=(sweep.sweep_candle.close>=p.price_bottom if daily.bias==B.BULLISH else sweep.sweep_candle.close<=p.price_top)
                        if in_zone and respected:pois.append(p)
            if not pois:
                self._reject('NO_PREEXISTING_LEVEL_IN_RANGE_HALF');continue
            # Recency is an explicit research choice, not a teacher ranking.
            poi=max(pois,key=lambda p:(p.timestamp,p.timeframe,p.level_type.value))
            self.contexts[key]=(sweep,replace(daily),poi)
            self.diagnostics['qualified_context']+=1
        # Do not pick a context by its eventual result. Earlier sweep first.
        for key,(sweep,frozen,poi) in sorted(list(self.contexts.items()),key=lambda x:(x[0][1],x[0][2])):
            if key[0]!=symbol:continue
            long=frozen.bias==B.BULLISH
            after=[c for c in closed.get('M1',minute) if c.timestamp>=sweep.sweep_candle.available_at]
            invalid=frozen.bias!=daily.bias or any(
                (c.low<sweep.sweep_price or c.high>=frozen.target_level) if long else
                (c.high>sweep.sweep_price or c.low<=frozen.target_level) for c in after)
            if invalid:
                del self.contexts[key];self.used.add(key);self._reject('CONTEXT_INVALIDATED');continue
            # Recognition is separated from map-equilibrium partial management.
            # Fixed dummy fields are replaced with the genuine frozen target.
            recognition_map=replace(frozen,entry_only=True)
            plan=self._entry(symbol,closed,sweep,recognition_map,now)
            if plan is None:continue
            target=frozen.target_level
            if not (plan.entry_price<target if long else plan.entry_price>target):
                self._reject('TARGET_NOT_FAVORABLE');continue
            setup=replace(plan,daily_map=frozen,take_profit_1=target,take_profit_2=target,
                risk_reward=abs(target-plan.entry_price)/abs(plan.entry_price-plan.stop_loss),
                stop_variant='sweep_plus_3p',notes='Full ASM research v1; source-faithfulness not certified.',
                entry_evidence=dict(plan.entry_evidence,model_version=self.VERSION,
                    context_map=frozen.map_type.value,context_rule=frozen.notes,
                    context_available_at=frozen.timestamp.isoformat(),context_from=frozen.origin_level,
                    context_to=target,context_equilibrium=frozen.equilibrium_50,
                    poi_type=poi.level_type.value,poi_bottom=poi.price_bottom,poi_top=poi.price_top,
                    poi_available_at=poi.timestamp.isoformat(),poi_rule=poi.metadata['rule'],
                    target_rule='nearest_unreached_aligned_daily_map_destination_frozen_at_sweep',
                    map_conflict_rule='abstain',poi_selection_rule='latest_preexisting_in_range_half',
                    entry_policy=self.entry_policy,order_available_at=now.isoformat(),
                    execution_rule='pending_limit_after_decision_close',
                    stop_rule='sweep_extreme_plus_three_pips',teacher_validated=False))
            self.last_review['rejection']=''
            del self.contexts[key];self.used.add(key);self.diagnostics['signals']+=1
            return setup
        return None

    def _entry(self,symbol,closed,sweep,daily,now):
        hourly=closed.get('H1',[])
        if self.entry_policy=='h1_av':
            if hourly and hourly[-1].available_at==now:
                return EntryModelEvaluator.evaluate_h1_av(symbol,hourly,sweep,daily)
            return None
        for tf in ('M5','M10','M15'):
            bars=closed.get(tf,[])
            if not bars or bars[-1].available_at!=now:continue
            if self.entry_policy in ('auto','swing_fvg'):
                plan=EntryModelEvaluator.evaluate_swing_retest(symbol,bars,sweep,daily,'fvg_av_overlap',junction_tolerance=pip(symbol))
                if plan:return plan
            if self.entry_policy in ('auto','swing_ob'):
                plan=EntryModelEvaluator.evaluate_swing_retest(symbol,bars,sweep,daily,'order_block',junction_tolerance=pip(symbol))
                if plan:return plan
            if tf=='M5' and self.entry_policy in ('auto','h1_av_m5'):
                plan=EntryModelEvaluator.evaluate_h1_av_m5(symbol,hourly,bars,sweep,daily)
                if plan:return plan
        return None

    def _reject(self,reason):
        self.diagnostics[reason]+=1
        self.last_review['rejection']=reason
        return None
