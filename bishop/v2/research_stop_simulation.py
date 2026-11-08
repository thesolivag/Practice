"""Research-only frozen simulation fork: prove zero-cost M1 limit stop ordering.

Original simulation.py is unchanged; this fork is for the saved-cohort audit.
"""
from bisect import bisect_right
from itertools import islice
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from .types import Clock, Event, utc, stable_id
from .aggregation import expected_slots


@dataclass(frozen=True)
class Costs:
    spread_ticks: Decimal = Decimal('0')
    entry_slippage_ticks: Decimal = Decimal('0')
    stop_slippage_ticks: Decimal = Decimal('0')
    commission_ticks: Decimal = Decimal('0')  # full round trip per unit
    financing_ticks: Decimal = Decimal('0')
    def __post_init__(self):
        for k in self.__dataclass_fields__:
            v=Decimal(str(getattr(self,k)))
            if not v.is_finite() or v<0: raise ValueError('finite nonnegative explicit costs required')
            object.__setattr__(self,k,v)


def simulate(orders,bars,instrument,costs,as_of,actions=(), *, calendar=None, refinement_evidence=None):
    if isinstance(costs,dict): costs=Costs(**costs)
    if not isinstance(costs,Costs): raise ValueError('Costs required')
    if instrument.price_basis!='BID' and not (instrument.price_basis=='MID' and all(getattr(costs,k)==0 for k in costs.__dataclass_fields__)):
        raise ValueError('simulation requires BID bars and declared costs, or MID quotes with explicit zero costs')
    calendar=calendar or instrument.calendar_id
    clock=utc(as_of); bars=tuple(b for b in bars if b.available_at<=clock)
    if any(not b.complete for b in bars): raise ValueError('complete execution bars required')
    if any(b.instrument!=instrument.symbol for b in bars): raise ValueError('mixed instruments')
    if any(a.start>=b.start for a,b in zip(bars,bars[1:])): raise ValueError('bars must be ordered unique')
    ends=[b.end for b in bars]
    policy=stable_id('execution_policy','research_m1_limit_stop_proof_v1',costs,instrument,
                     *((refinement_evidence.id,) if refinement_evidence is not None else ()))
    evidence_at=None; evidence_refs=()
    events=[]; observations=[]; positions=[]
    def emit(o,kind,at,lo=None,price=None,details=None,bar=None):
        known_at=max(utc(at),evidence_at) if evidence_at is not None else utc(at)
        if evidence_refs:
            details={**(details or {}),'refinement_evidence_ids':evidence_refs}
        e=Event(id=stable_id('execution',o.id,kind,at,lo,price,details,policy),kind=kind,instrument=o.instrument,tf=o.tf,clock=Clock(lo or at,at,known_at),side=o.side,reference_id=o.id,price_ticks=price if isinstance(price,int) else None,policy_id=policy,bar_ids=(bar.id,) if bar else (),details=details or {})
        events.append(e); return e
    for o in sorted(orders,key=lambda x:(x.available_at,x.id)):
        if o.available_at>clock: continue
        if o.instrument!=instrument.symbol: raise ValueError('order instrument mismatch')
        evidence_at=o.available_at; evidence_refs=()
        state='PENDING'; outcome='OPEN'; stop=Decimal(o.stop_ticks); target=Decimal(o.target_ticks)
        fill=None; fill_window=None; remaining=o.quantity; realized=Decimal(0); risk=None; censored=None
        management=[]; current=o.available_at
        acts=sorted((dict(a) for a in actions if a.get('order_id')==o.id and utc(a.get('available_at',a.get('at')))<=clock),key=lambda a:utc(a.get('available_at',a.get('at'))))
        for a in acts:
            a['_at']=utc(a.get('available_at',a.get('at')))
            if a.get('kind','').upper() not in ('CANCEL','REPLACE','AMEND','BREAK_EVEN','PARTIAL','MANUAL_CLOSE'):
                raise ValueError('unsupported action kind')
            for field in ('stop_ticks','target_ticks','price_ticks','quantity'):
                if field not in a: continue
                try: value=Decimal(str(a[field]))
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError('invalid action '+field) from exc
                if not value.is_finite() or isinstance(a[field],bool):
                    raise ValueError('finite action '+field+' required')
                if field=='quantity':
                    if value<=0: raise ValueError('positive action quantity required')
                elif value!=value.to_integral_value():
                    raise ValueError('action prices must use whole instrument ticks')
                a[field]=value
            if a['_at']<o.available_at: raise ValueError('action precedes order')
            if a.get('occurred_at') and utc(a['occurred_at'])!=a['_at']: raise ValueError('retroactive actions unsupported')
        ai=0
        emit(o,'ORDER_SUBMITTED',o.available_at,details={'kind':o.kind,'initial_entry_ticks':o.entry_ticks,'initial_stop_ticks':o.stop_ticks,'initial_target_ticks':o.target_ticks,'quantity':str(o.quantity)})
        def censor(reason,at,lo=None,bar=None):
            nonlocal state,outcome,censored
            censored=reason; outcome='CENSORED'; state='CENSORED' if fill is None else 'FILLED'
            emit(o,'EXECUTION_CENSORED',at,lo,details={'reason':reason},bar=bar)
        def close(price,qty,kind,at,lo=None,bar=None):
            nonlocal remaining,realized,state,outcome
            signed=(price-fill)*(1 if o.side=='BUY' else -1)
            realized+=(signed-costs.commission_ticks-costs.financing_ticks)*qty
            remaining-=qty
            emit(o,kind,at,lo,details={'price_ticks':str(price),'quantity':str(qty),'remaining':str(remaining)},bar=bar)
            if remaining==0: state='CLOSED'; outcome='WIN' if realized>0 else 'LOSS' if realized<0 else 'BREAK_EVEN'
        def amend(a,kind,at):
            nonlocal stop,target
            new_stop=a.get('stop_ticks',fill if kind=='BREAK_EVEN' else stop)
            new_target=a.get('target_ticks',target)
            if not (new_stop<new_target if o.side=='BUY' else new_target<new_stop):
                raise ValueError('invalid amended stop/target geometry')
            if new_stop!=new_stop.to_integral_value() or new_target!=new_target.to_integral_value():
                raise ValueError('amended prices must use whole instrument ticks')
            stop,target=new_stop,new_target
            emit(o,'POSITION_AMENDED',at,details={'stop_ticks':str(stop),'target_ticks':str(target)})
            management.append(a)
        def pending_deadline(end):
            if fill is not None:return end
            return min([end]+([o.expires_at] if o.expires_at else [])+
                       [a['_at'] for a in acts[ai:] if a.get('kind','').upper() in ('CANCEL','REPLACE')])
        def gap_is_proven(end,tf):
            nonlocal evidence_at,evidence_refs
            if refinement_evidence is None:return False
            # Old price bounds cannot cover a stop/position change inside an
            # unobserved interval. Keep it censored rather than replaying an
            # amendment after the gap using stale protection geometry.
            if state=='FILLED' and any(current<=a['_at']<end and a.get('kind','').upper() in
                    ('AMEND','BREAK_EVEN','PARTIAL','MANUAL_CLOSE') for a in acts):
                return False
            proof=refinement_evidence.prove_gap(o,state,current,end,stop,target,costs.spread_ticks,clock,calendar,tf)
            if proof is None:return False
            available,identifiers=proof
            evidence_at=max(evidence_at,available)
            evidence_refs=tuple(dict.fromkeys((*evidence_refs,*identifiers)))
            return True
        for b in islice(bars,bisect_right(ends,o.available_at),None):
            if state not in ('PENDING','FILLED') or censored: break
            # A missing active interval must be encountered before later OHLC.
            active_end=pending_deadline(b.start) if refinement_evidence is not None else b.start
            if active_end>current and list(expected_slots(current,active_end,b.tf,calendar)):
                if not gap_is_proven(active_end,b.tf):
                    censor('MISSING_ACTIVE_DATA',active_end); break
            if (refinement_evidence is not None and fill is None and o.expires_at is not None
                    and o.expires_at<=b.start and not any(
                        a['_at']<=o.expires_at and a.get('kind','').upper() in ('CANCEL','REPLACE') for a in acts[ai:])):
                state='MISSED';outcome='EXPIRED';emit(o,'ORDER_EXPIRED',o.expires_at);break
            if b.start<o.available_at<b.end:
                censor('SUBMISSION_INSIDE_BAR',b.available_at,b.start,b); break
            if b.start<current: continue
            # Boundary actions precede the following executable open.
            while ai<len(acts) and acts[ai]['_at']<=b.start:
                a=acts[ai]; ai+=1; kind=a.get('kind','').upper(); at=a['_at']
                if kind in ('CANCEL','REPLACE') and fill is None:
                    state='CANCELLED' if kind=='CANCEL' else 'REPLACED'; outcome=state
                    emit(o,'ORDER_'+state,at,details={k:v for k,v in a.items() if not k.startswith('_')}); break
                if kind in ('AMEND','BREAK_EVEN') and fill is not None:
                    amend(a,kind,at)
                elif kind in ('PARTIAL','MANUAL_CLOSE') and fill is not None:
                    qty=Decimal(str(a.get('quantity',remaining)))
                    if qty<=0 or qty>remaining: raise ValueError('invalid exit quantity')
                    if 'price_ticks' not in a: raise ValueError('manual/partial action needs explicit price_ticks')
                    close(Decimal(str(a['price_ticks'])),qty,'POSITION_'+kind,at); management.append(a)
                elif kind not in ('CANCEL','REPLACE','AMEND','BREAK_EVEN','PARTIAL','MANUAL_CLOSE'): raise ValueError('unsupported action kind')
            if state not in ('PENDING','FILLED'): break
            if fill is None and o.expires_at is not None and o.expires_at<=b.start:
                state='MISSED'; outcome='EXPIRED'; emit(o,'ORDER_EXPIRED',o.expires_at); break
            boundary=min([a['_at'] for a in acts[ai:ai+1]]+([o.expires_at] if fill is None and o.expires_at else []),default=b.end)
            if b.start<boundary<b.end:
                censor('ACTION_OR_EXPIRY_INSIDE_BAR',b.available_at,b.start,b); break
            just=False
            if fill is None:
                touched=o.kind=='MARKET' or (Decimal(b.low_ticks)+costs.spread_ticks<=o.entry_ticks if o.side=='BUY' else b.high_ticks>=o.entry_ticks)
                if not touched: current=b.end; continue
                fill=(Decimal(b.open_ticks)+(costs.spread_ticks+costs.entry_slippage_ticks if o.side=='BUY' else -costs.entry_slippage_ticks)) if o.kind=='MARKET' else Decimal(o.entry_ticks)
                risk=abs(fill-Decimal(o.stop_ticks))
                if risk==0 or (o.side=='BUY' and not stop<fill<target) or (o.side=='SELL' and not target<fill<stop):
                    censor('INVALID_FILL_RISK',b.available_at,b.start,b); break
                state='FILLED'; just=True; fill_window={'start':b.start,'end':b.end,'observed_at':max(b.available_at,evidence_at)}
                emit(o,'ORDER_FILLED',b.available_at,b.start,details={'fill_ticks':str(fill),'quantity':str(o.quantity),'kind':o.kind},bar=b)
            stop_hit=b.low_ticks<=stop if o.side=='BUY' else Decimal(b.high_ticks)+costs.spread_ticks>=stop
            target_hit=b.high_ticks>=target if o.side=='BUY' else Decimal(b.low_ticks)+costs.spread_ticks<=target
            # A terminal close at/beyond target occurs after the entry touch.
            # It proves target ordering only when this bar never hit the stop.
            terminal_target_proof = target_hit and not stop_hit and (
                b.close_ticks>=target if o.side=='BUY'
                else Decimal(b.close_ticks)+costs.spread_ticks<=target)
            tick_proof=None
            if (refinement_evidence is not None and just and o.kind=='LIMIT'
                    and target_hit and not stop_hit and not terminal_target_proof):
                tick_proof=refinement_evidence.resolve_limit_target(o,b,costs)
                if tick_proof is not None:
                    evidence_refs=tuple(dict.fromkeys((*evidence_refs,stable_id('tick_ordering',refinement_evidence.id,b.id))))
                if tick_proof=='FILLED_WITHOUT_EXIT_IN_MINUTE':target_hit=False
            # A valid resting limit must be reached before its adverse stop.
            # Apply only on complete M1 with explicit zero costs. If opening
            # beyond the stop, gap pricing remains unresolved in this audit.
            limit_stop_proof = (just and o.kind=='LIMIT' and b.tf=='M1'
                and stop_hit and not target_hit
                and all(getattr(costs,k)==0 for k in costs.__dataclass_fields__)
                and (Decimal(b.open_ticks)>stop if o.side=='BUY' else Decimal(b.open_ticks)<stop))
            if (stop_hit and target_hit) or (just and o.kind=='LIMIT' and (stop_hit or target_hit) and not terminal_target_proof and not limit_stop_proof and tick_proof!='TARGET_AFTER_ENTRY'):
                censor('UNRESOLVED_INTRABAR_SEQUENCE',b.available_at,b.start,b); break
            if stop_hit:
                px=min(stop,Decimal(b.open_ticks))-costs.stop_slippage_ticks if o.side=='BUY' else max(stop,Decimal(b.open_ticks)+costs.spread_ticks)+costs.stop_slippage_ticks
                close(px,remaining,'POSITION_STOPPED',b.available_at,b.start,b)
            elif target_hit: close(target,remaining,'POSITION_TARGET',b.available_at,b.start,b)
            current=b.end
        if not censored and state in ('PENDING','FILLED'):
            active_end=pending_deadline(clock) if refinement_evidence is not None else clock
            if current<active_end and list(expected_slots(current,active_end,bars[0].tf if bars else 'M1',calendar)):
                # A currently forming final candle is not a missing completed interval.
                duration=bars[-1].end-bars[-1].start if bars else timedelta(minutes=1)
                if current+duration<=active_end and not gap_is_proven(active_end,bars[0].tf if bars else 'M1'):
                    censor('MISSING_ACTIVE_DATA',active_end)
        # Actions at the final observed boundary need no following candle.
        if not censored and state in ('PENDING','FILLED'):
            while ai<len(acts) and acts[ai]['_at']<=clock:
                a=acts[ai]; ai+=1; at=a['_at']; kind=a.get('kind','').upper()
                if refinement_evidence is not None and fill is None and o.expires_at and o.expires_at<at:
                    break
                if at>current and next(expected_slots(current,at,bars[0].tf if bars else 'M1',calendar),None) is not None:
                    if not gap_is_proven(at,bars[0].tf if bars else 'M1'):
                        censor('ACTION_INSIDE_UNOBSERVED_INTERVAL',at,current); break
                if kind in ('CANCEL','REPLACE') and fill is None:
                    state='CANCELLED' if kind=='CANCEL' else 'REPLACED'; outcome=state
                    emit(o,'ORDER_'+state,at,details={k:v for k,v in a.items() if not k.startswith('_')}); break
                if kind in ('AMEND','BREAK_EVEN') and fill is not None:
                    amend(a,kind,at)
                elif kind in ('PARTIAL','MANUAL_CLOSE') and fill is not None:
                    qty=Decimal(str(a.get('quantity',remaining)))
                    if qty<=0 or qty>remaining or 'price_ticks' not in a: raise ValueError('explicit valid manual exit required')
                    close(Decimal(str(a['price_ticks'])),qty,'POSITION_'+kind,at); management.append(a)
                    if state=='CLOSED': break
        if state=='PENDING' and o.expires_at and o.expires_at<=clock and not censored:
            state='MISSED';outcome='EXPIRED';emit(o,'ORDER_EXPIRED',o.expires_at)
        obs={'id':o.id,'setup_id':o.setup_id,'status':state,'outcome':outcome,'fill_ticks':str(fill) if fill is not None else None,'fill_window':fill_window,'remaining_quantity':str(remaining if fill is not None else 0),'realized_ticks_quantity':str(realized),'net_r':str(realized/(risk*o.quantity)) if risk and remaining==0 else None,'censor_reason':censored,'initial_stop_ticks':o.stop_ticks,'initial_target_ticks':o.target_ticks,'costs':costs,'management':[{k:v for k,v in a.items() if not k.startswith('_')} for a in management]}
        observations.append(obs)
        if fill is not None: positions.append({'order_id':o.id,'fill_ticks':str(fill),'remaining_quantity':str(remaining),'stop_ticks':str(stop),'target_ticks':str(target),'state':state,'realized_ticks_quantity':str(realized)})
    events.sort(key=lambda e:e.available_at)
    return {'events':tuple(events),'observations':observations,'positions':positions,'policy_id':policy}
