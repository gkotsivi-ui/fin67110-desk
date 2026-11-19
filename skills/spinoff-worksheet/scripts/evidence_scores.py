"""Deterministic evidence completeness, not model-computed numeric ratings."""
def known(ob):return ob and ob.get('value') not in (None,'not applicable','not known') and ob.get('source') not in (None,'not known')
def positive(ob):return known(ob) and isinstance(ob.get('value'),(int,float)) and ob['value']>0
def affirmative(ob):
    if not known(ob):return False
    value=ob['value']
    if isinstance(value,(int,float)):return value>0
    import re
    return not re.search(r'\b(?:no|not|none|false|absent)\b',str(value),re.I)

def score(facts,comparison,ocf):
    def has(key):return known(facts.get(key))
    forced=affirmative(facts.get('forced_seller')) or affirmative(facts.get('index_exclusion'))
    indifferent=affirmative(facts.get('indifferent_seller'))
    insider=facts.get('insider_purchases',{})
    open_market=positive(insider) and insider.get('open_market_confirmed',False) and insider.get('kind') in {'reported after the spin','reported post-spin'}
    stake=affirmative(facts.get('meaningful_insider_stake')) or affirmative(facts.get('own_stock_option_incentive'))
    load_keys=['debt_raised','retained_liabilities','restrictions']
    quantified=all(has(k) for k in load_keys)
    service=facts.get('debt_service',{})
    covered=known(service) and ocf.get('value') is not None and ocf['value']>=service['value']
    price_ok=comparison.get('price') is not None and comparison.get('low_value') is not None and comparison['price']<=comparison['low_value']
    specs=[('Forced seller',2 if forced else 1 if has('index') or has('relative_size') else 0,['forced_seller','index_exclusion','index','relative_size']),
      ('Indifferent seller',2 if indifferent else 1 if has('relative_size') or has('dividend_mismatch') else 0,['indifferent_seller','relative_size','dividend_mismatch']),
      ('Price against value',2 if price_ok else 0,[]),
      ('Load pushed in',2 if quantified and covered else 1 if quantified else 0,load_keys+['debt_service']),
      ('Insiders buying',2 if open_market else 1 if positive(insider) else 0,['insider_purchases']),
      ('Parent motive',2 if positive(facts.get('cash_to_parent',{})) or has('parent_motive') else 1 if has('parent') else 0,['cash_to_parent','parent_motive','parent'])]
    rows=[{'criterion':i,'name':name,'score':value,'source':'; '.join(facts[k]['source'] for k in keys if has(k)) or ('Code price/low comparison; '+str(comparison.get('price_source')) if i==3 else 'not known')} for i,(name,value,keys) in enumerate(specs,1)]
    conditions={'seller_identified':forced or indifferent,'insider_interest':open_market or stake,'at_or_below_low':price_ok,'parent_load_quantified_and_covered':quantified and covered}
    return rows,conditions

def conviction(conditions,liq,facts,ocf,values,comparison):
    if liq.get('buyable') is not True:return 'no conviction','Not buyable at size, or the liquidity evidence is not established'
    required=[facts.get('shares_outstanding'),ocf]
    required += [facts[key] for key in ['debt_raised','cash_to_parent','retained_liabilities','restrictions'] if key in facts and facts[key].get('value')!='not applicable']
    if any(not known(x) for x in required) or values['low'].get('value') is None or comparison.get('price') is None or not comparison.get('price_source'):
        return 'no conviction','A required numerical input or citation is missing'
    return ('high','All five worksheet tests are supported') if all(conditions.values()) else ('low','At least one of seller, insider interest, low-case price or quantified/covered parent load is missing')
