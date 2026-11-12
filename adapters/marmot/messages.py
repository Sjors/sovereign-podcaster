"""Authenticate a turn against the connector's MLS-verified private timeline."""
import importlib.util
import os
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('wn_control',ROOT/'skills/marmot-whitenoise/scripts/wn_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def authenticated(config,environ,prompt,rpc=None):
    names=('MARMOT_ACCOUNT_ID_HEX','MARMOT_GROUP_ID_HEX','MARMOT_MESSAGE_ID_HEX','MARMOT_SENDER_ACCOUNT_ID_HEX')
    account,group,message,sender=(environ.get(n,'') for n in names)
    if any(not re.fullmatch('[0-9a-f]{64}',x) for x in (account,message,sender)) or not re.fullmatch('(?:[0-9a-f]{2})+',group):raise RuntimeError('Authenticated incoming message context is missing; install the pinned Marmot bridge patch')
    if account!=config['account_id_hex'] or sender!=config['trusted_hex']:raise RuntimeError('Incoming sender is outside the trusted contact allowlist')
    control.MARMOT_DIR=Path(config['marmot_home'])
    response=(rpc or control.rpc)(environ.get('MARMOT_AGENT_SOCKET',str(control.MARMOT_DIR/'dev/wn-agent.sock')),
        dict(type='timeline_message_get',account_id_hex=account,group_id_hex=group,message_id_hex=message),30)
    msg=response.get('message') or {}
    if response.get('type')!='timeline_message' or any(response.get(k)!=v for k,v in [('account_id_hex',account),('group_id_hex',group),('message_id_hex',message)]) or msg.get('message_id_hex')!=message or msg.get('sender',{}).get('account_id_hex')!=sender or msg.get('direction')!='received' or msg.get('availability')!='available' or msg.get('text_truncated') or not isinstance(msg.get('text'),str):raise RuntimeError('Incoming message cannot be verified from the connector timeline')
    # The harness may append trusted control instructions; approvals always use
    # the original, authenticated text below, never a model-expanded prompt.
    if msg['text'] not in prompt:raise RuntimeError('Harness prompt does not contain the authenticated incoming message')
    return dict(account=account,group=group,message_id=message,sender=sender,text=msg['text'],recorded_at=msg['recorded_at'],reply_to=msg.get('reply_to_message_id_hex'))
