"""Pure arithmetic. Every price/duration supplied here is fixture data."""
from decimal import Decimal

def cost(data):
    unknown={'uncached':None,'estimated_usd':None,'actual_billed_usd':None}
    if data.get('semantics')!='cache_subset_reasoning_in_output' or data.get('rates') is None:
        return unknown
    values=[data.get(x) for x in ['input','cached','output','reasoning']]
    if any(type(v) is not int or v<0 for v in values): raise ValueError('invalid usage')
    inp,cached,out,reasoning=values
    if cached>inp or reasoning>out: raise ValueError('invalid subset usage')
    rates=list(map(lambda n:Decimal(str(n)),data['rates']))
    if len(rates)!=3 or any(not n.is_finite() or n<0 for n in rates): raise ValueError('invalid rates')
    uncached=inp-cached
    total=(uncached*rates[0]+cached*rates[1]+out*rates[2])/Decimal(1000000)
    return {'uncached':uncached,'estimated_usd':float(total),'actual_billed_usd':None}

def cumulative(data):
    values=data['snapshots']; resets=set(data['reset_indices'])
    if any(type(x) is not int or x<0 for x in values): raise ValueError('invalid snapshot')
    total=0
    for i in range(1,len(values)):
        if i in resets: total+=values[i]
        elif values[i]<values[i-1]: return {'total':None,'complete':False}
        else: total+=values[i]-values[i-1]
    return {'total':total,'complete':True}

def union(intervals):
    total=0; end=None
    for a,b in sorted(intervals):
        if b<a: raise ValueError('negative interval')
        total += b-a if end is None else max(0,b-max(end,a))
        end=b if end is None else max(end,b)
    return total

def intervals(data):
    if data['end']<data['start']: raise ValueError('negative elapsed')
    return {'active':union(data['active']),'work':sum(b-a for a,b in data['active']),
            'wait':union(data['wait']),'elapsed':data['end']-data['start']}
