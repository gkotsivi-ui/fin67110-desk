"""Seeded real CrewAI role chain, including verbatim manager and verifier."""
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
def denied(*a,**k):raise RuntimeError('Seeded all-role test cannot fetch')
socket.socket.connect=denied

with tempfile.TemporaryDirectory() as tmp:
    run=Path(tmp);os.environ['CREWAI_STORAGE_DIR']=str(run/'framework')
    from desk_stub_llm import StubLLM,tool_call
    from equity_research_agent_team import Runtime,EquityResearchFlow
    from desk_sources import Sources,write_json
    from desk_hook import Hook,HookFailure
    from desk_role_contracts import report_catalog
    (run/'10-K.txt').write_text('Income was $100.\nDebt was $20.\n')
    (run/'earnings_release_Ex99-1.txt').write_text('A seeded release.\n')
    calc=run/'calculated_facts.json'
    write_json(calc,{'metrics':{'free_cash_flow':{'value':80,'formula':'100 - 20','unit':'USD','sources':['10-K.txt:L1','10-K.txt:L2']}},
                    'quarter_results':{'latest_10q_capital_spending':{'value':80,'formula':'100 - 20','unit':'USD','sources':['10-K.txt:L1','10-K.txt:L2']}}})
    runtime=Runtime.__new__(Runtime);runtime.output_dir=run;runtime.set_output_dir(run)
    runtime.role_call_counts={};runtime.skill_files=[calc]
    runtime.desk=SimpleNamespace(filings={form:SimpleNamespace(accession='seeded-accession') for form in ('10-K','10-Q','8-K')},run_timestamp='2026-11-17T12:00:00-05:00')
    runtime.research_context=lambda:{'saved_filing':'10-K.txt'}
    runtime.financial_context=lambda:{'saved_values':'calculated_facts.json'}
    gate=Hook(run,Sources(run,''))
    runtime.output_hook=lambda name,paths:gate.check(name,paths)
    flow=EquityResearchFlow('ZZZZ',[]);flow.runtime=runtime

    def answer(files,output):
        runtime.llm=StubLLM(emit_events=False,responses=[*[tool_call('read_assigned_file',{'file':f}) for f in files],
                          'Final Answer: '+json.dumps(output)])

    research={'claims':[{'id':'c1','file':'10-K.txt','line':1,'quote':'Income was $100.','value':'$100'}],
              'draft':'== 1. OVERVIEW ==\nIncome {c1}.\nGrowth supported by {c1}.\nInsight: Income supports resilience at {c1}.'}
    answer(['calculated_facts.json'],research);flow.research_analyst({})
    financial={'claims':[{'id':'c1','computed':'free_cash_flow'}],
               'draft':'== 2. CASH ==\nCash generation {c1}.\nInsight: Spending leaves cash of {c1}.'}
    answer(['calculated_facts.json'],financial);flow.financial_analyst('')
    author_files=lambda roles:[f'nodes/{role.replace(" ","_")}_1/{name}' for role in roles for name in ('output.json','draft.md')]
    advisor={'claims':[{'id':'c1','from':'Financial Analyst','claim':'c1'}],
             'draft':'== 3. RATING ==\nHold. Cash {c1} supports caution.\nInsight: Protection remains from {c1}.'}
    answer(author_files(['Research Analyst','Financial Analyst']),advisor);flow.investment_advisor('')
    research_file='nodes/Research_Analyst_1/draft.md'
    sections={'Overview':{'file':research_file,'start':2,'end':2},
              'Market Positioning and Growth Outlook':{'file':research_file,'start':3,'end':3},
              'Future Developments and Strategic Recommendations':{'file':research_file,'start':4,'end':4},
              'Valuation Insights':{'file':'nodes/Financial_Analyst_1/draft.md','start':2,'end':3},
              'Investment Recommendation':{'file':'nodes/Investment_Advisor_1/draft.md','start':2,'end':3}}
    all_authors=['Research Analyst','Financial Analyst','Investment Advisor']
    def replies(files,output):
        return [*[tool_call('read_assigned_file',{'file':f}) for f in files],'Final Answer: '+json.dumps(output)]
    corrected_files=[p.replace('Financial_Analyst_1','Financial_Analyst_2') for p in author_files(all_authors)]
    corrected_sections=json.loads(json.dumps(sections))
    corrected_sections['Valuation Insights']['file']='nodes/Financial_Analyst_2/draft.md'
    corrected_financial={**financial,'draft':financial['draft'].replace('Cash generation','Reported cash generation')}
    manager_review={'claims':[],'failures':[{'role':'Financial Analyst','part':'Valuation Insights','feedback':'Clarify the reported cash generation definition.'}],'sections':sections}
    malformed=json.dumps(manager_review)+'\n'+json.dumps({'failures':[]})
    runtime.llm=StubLLM(emit_events=False,responses=[
        *[tool_call('read_assigned_file',{'file':f}) for f in author_files(all_authors)],
        'Final Answer: '+malformed,
        *replies(author_files(all_authors),manager_review),
        *replies(['calculated_facts.json'],corrected_financial),
        *replies(corrected_files,{'claims':[],'failures':[],'sections':corrected_sections})])
    report=Path(flow.strategy_manager(''))
    manager_node=run/'nodes/Strategy_Manager_1'
    raws=json.loads((manager_node/'raw_responses.json').read_text())
    attempts=json.loads((manager_node/'claim_attempts.json').read_text())
    assert len(raws)==2 and raws[0]['raw']==malformed
    assert len(attempts)==2 and attempts[0]['output']['unparsed_response']==malformed
    assert attempts[0]['errors'] and not attempts[1]['errors']
    catalog=report_catalog(run)
    checks=[{'target':c['target'],'status':'correct','reason':'The saved evidence and latest_10q_capital_spending support the meaning and period.','correction':''} for c in catalog]
    answer(['calculated_facts.json',*corrected_files,'report.md','verifier_input.json'],{'claims':[],'checks':checks})
    verified=Path(flow.verifier(str(report)))
    gate.check('seeded checked reports',[report,verified])
    assert runtime.role_call_counts=={'Research Analyst':1,'Financial Analyst':2,'Investment Advisor':1,'Strategy Manager':2,'Verifier':1}
    assert '$80' in verified.read_text()
    assert '== 1.' not in report.read_text() # Manager selected body lines only.
    verified.write_text(verified.read_text().replace('$80','$81'))
    try:gate.check('seeded changed report',[verified])
    except HookFailure:pass
    else:raise AssertionError('Changed report was accepted')
print('SEEDED all-role CrewAI chain passed')
