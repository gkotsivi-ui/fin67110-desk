"""Exercise the actual CrewAI tool loop with a seeded stub, in a child process."""
import os
import json
from pathlib import Path
import socket
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from portable import connect_local_only, connect_ex_local_only
socket.socket.connect = connect_local_only
socket.socket.connect_ex = connect_ex_local_only


with tempfile.TemporaryDirectory() as tmp:
    run=Path(tmp)
    os.environ['CREWAI_STORAGE_DIR']=str(run/'framework')
    from desk_stub_llm import StubLLM,tool_call
    from equity_research_agent_team import Runtime
    from desk_hook import Hook
    from desk_sources import Sources
    from desk_files import AssignedFiles,file_tool

    source=run/'skill.md';source.write_text('Computed amount: $100\n')
    runtime=Runtime.__new__(Runtime)
    runtime.output_dir=run;runtime.set_output_dir(run)
    runtime.role_call_counts={};runtime.skill_files=[source]
    original_instructions=runtime.instructions
    runtime.instructions=lambda name:'Quote assigned files; never recompute.' if name=='legacy.md' else original_instructions(name)
    gate=Hook(run,Sources(run,''))
    runtime.output_hook=lambda name,paths:gate.check(name,paths)
    runtime.llm=StubLLM(emit_events=False,responses=[
        tool_call('read_assigned_file',{'file':'skill.md'}),
        'Final Answer: {"draft":"Amount is $100 [skill.md:L1]."}'])
    packet={'task':'Quote the assigned file.','context':{},'expected_output':'JSON with draft.'}
    result=runtime.role_call('Seeded Reader','legacy.md',packet)
    assert '$100' in result['draft']
    assert (run/'nodes/Seeded_Reader_1/files_read.json').is_file()

    # A role that skips the read cannot publish an output.
    runtime.llm=StubLLM(emit_events=False,responses=['Final Answer: {"draft":"No read."}'])
    try:runtime.role_call('Seeded Reader','legacy.md',packet)
    except ValueError as error:assert 'did not read' in str(error)
    else:raise AssertionError('Unread assigned file was accepted')
    assert not (run/'nodes/Seeded_Reader_2/output.json').exists()
    unread_raw=json.loads((run/'nodes/Seeded_Reader_2/raw_responses.json').read_text())
    assert unread_raw[0]['raw']=='{"draft":"No read."}'

    # Test the real ToolFailure path with strict CrewAI failure policy.
    runtime.llm=StubLLM(emit_events=False,responses=[tool_call('read_assigned_file',{'file':'secret.env'})])
    try:runtime.role_call('Denied Reader','legacy.md',packet)
    except Exception as error:assert 'not assigned' in str(error) or 'failed' in str(error).lower(),str(error)
    else:raise AssertionError('Unassigned file was accepted')
    assert not (run/'nodes/Denied_Reader_1/output.json').exists()

    # Claims role: repair a wrong line and typed amount, preserving every
    # failure and counting this as one role invocation.
    release='earnings_release_Ex99-1.txt'
    (run/release).write_text('Header\nOther text\nNet sales increased 10% to $100.\n')
    claim={'id':'c1','file':release,'line':1,'quote':'Net sales increased 10% to $100.','value':'$100'}
    bad={'claims':[claim],'draft':'Sales were {c1}, up 10%.'}
    good={'claims':[{**claim,'line':3}],'draft':'Sales were {c1}.'}
    runtime.llm=StubLLM(emit_events=False,responses=[
        tool_call('read_assigned_file',{'file':'skill.md'}),
        'Final Answer: '+json.dumps(bad),
        tool_call('read_assigned_file',{'file':'skill.md'}),
        'Final Answer: '+json.dumps(good)])
    output=runtime.role_call('Research Analyst','research_analyst.md',packet)
    assert output['draft']=='Sales were $100 [earnings_release_Ex99-1.txt:L3].'
    assert runtime.role_call_counts['Research Analyst']==1
    attempts=json.loads((run/'nodes/Research_Analyst_1/claim_attempts.json').read_text())
    assert len(attempts)==2
    assert any('appears on line 3' in e for e in attempts[0]['errors'])
    assert any('typed directly' in e for e in attempts[0]['errors'])
    assert not attempts[1]['errors']

    # Exhausted repairs retain their errors and do not exceed three attempts.
    runtime.llm=StubLLM(emit_events=False,responses=[
        tool_call('read_assigned_file',{'file':'skill.md'}),
        'Final Answer: '+json.dumps(bad),
        'Final Answer: '+json.dumps(bad),
        'Final Answer: '+json.dumps(bad)])
    try:runtime.role_call('Research Analyst','research_analyst.md',packet)
    except ValueError as error:assert 'after repairs' in str(error)
    else:raise AssertionError('Bad claims passed after exhausted repairs')
    attempts=json.loads((run/'nodes/Research_Analyst_2/claim_attempts.json').read_text())
    assert len(attempts)==3 and all(a['errors'] for a in attempts)
    assert not (run/'nodes/Research_Analyst_2/output.json').exists()
    assert runtime.role_call_counts['Research Analyst']==2

    # Malformed replies exhaust the same three-attempt budget, and every
    # original reply and parse error remains in the run.
    malformed_reply='{"claims": []}\n{"claims": [], "draft": "another answer"}'
    runtime.llm=StubLLM(emit_events=False,responses=[
        tool_call('read_assigned_file',{'file':'skill.md'}),
        *['Final Answer: '+malformed_reply]*3])
    try:runtime.role_call('Financial Analyst','financial_analyst.md',packet)
    except ValueError as error:assert 'after repairs' in str(error)
    else:raise AssertionError('Malformed replies escaped the repair cap')
    f=run/'nodes/Financial_Analyst_1'
    attempts=json.loads((f/'claim_attempts.json').read_text())
    raw=json.loads((f/'raw_responses.json').read_text())
    assert len(raw)==len(attempts)==3 and all(r['raw']==malformed_reply for r in raw)
    assert all(a['errors'] for a in attempts) and not (f/'output.json').exists()

    # Reading a valid file does not permit changing a quoted amount.
    runtime.llm=StubLLM(emit_events=False,responses=[
        tool_call('read_assigned_file',{'file':'skill.md'}),
        'Final Answer: {"draft":"Amount is $101 [skill.md:L1]."}'])
    try:runtime.role_call('Legacy Financial','legacy.md',packet)
    except ValueError as error:assert '$101' in str(error)
    else:raise AssertionError('Changed financial amount was accepted')

print('SEEDED real file-tool smoke check passed')
