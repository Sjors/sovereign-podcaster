#!/usr/bin/python3
"""Pinned Marmot v2 local queries and authorized immutable text/media sends."""
import argparse,datetime as dt,fcntl,hashlib,json,os,re,socket,stat,uuid
from pathlib import Path
if not __debug__:raise SystemExit('Run this client without Python optimization; safety checks must stay enabled')
PROTO='marmot.agent-control.v2';MAX_FRAME=1048576;MAX_BYTES=536870896
MARMOT_DIR=Path(os.environ.get('MARMOT_HOME', str(Path.home()/'.marmot-agents/codex')));STAGING=MARMOT_DIR/'media-uploads'
READ_ONLY={'account_list','group_info','timeline_list','timeline_message_get'}
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def atomic(path,data):
 path.parent.mkdir(parents=True,exist_ok=True);path.parent.chmod(0o700)
 tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
 with tmp.open('xb') as f:
  os.chmod(tmp,0o600);f.write(json.dumps(data,ensure_ascii=False,indent=2).encode()+b'\n');f.flush();os.fsync(f.fileno())
 tmp.replace(path)
 fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def owned_regular(path):
 assert not path.is_symlink(),'Symlink file refused';s=path.stat()
 assert stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and s.st_nlink==1 and not stat.S_IMODE(s.st_mode)&0o077,'Expected private owned regular file'
 return s
def rpc(sockpath,payload,timeout,identity=None):
 assert not {'id','marmot_agent_control','auth_token'}&payload.keys(),'Envelope fields are client-owned'
 s=Path(sockpath).lstat();assert stat.S_ISSOCK(s.st_mode) and s.st_uid==os.getuid(),'Unexpected control socket owner/type'
 identity=identity or uuid.uuid4().hex;request={'marmot_agent_control':PROTO,'id':identity,**payload}
 token=os.environ.get('MARMOT_AGENT_AUTH_TOKEN')
 tokenfile=os.environ.get('MARMOT_AGENT_AUTH_TOKEN_FILE')
 if not tokenfile and (MARMOT_DIR/'control.token').exists():tokenfile=str(MARMOT_DIR/'control.token')
 if not token and tokenfile:
  t=Path(tokenfile);owned_regular(t);token=t.read_text().strip()
 if token:request['auth_token']=token
 frame=json.dumps(request,ensure_ascii=False,separators=(',',':')).encode()+b'\n';assert len(frame)<=MAX_FRAME
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
  connection.settimeout(timeout);connection.connect(sockpath);connection.sendall(frame)
  with connection.makefile('rb') as reader:line=reader.readline(MAX_FRAME+1)
 assert len(line)<=MAX_FRAME and line.endswith(b'\n'),'Incomplete/oversized response; inspect outcome before any retry'
 response=json.loads(line);assert response.get('marmot_agent_control')==PROTO and response.get('id')==identity,'Unexpected protocol/correlation'
 return response
def validate_manifest(m):
 assert set(m)=={'account_id_hex','group_id_hex','caption','idempotency_key','attachments'}
 assert re.fullmatch('[0-9a-f]{64}',m['account_id_hex']) and re.fullmatch('[0-9a-f]+',m['group_id_hex']) and len(m['group_id_hex'])%2==0
 assert isinstance(m['caption'],str) or m['caption'] is None
 assert re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',m['idempotency_key'])
 assert 1<=len(m['attachments'])<=10
 total=0;wire=[]
 for a in m['attachments']:
  assert set(a)=={'path','media_type','file_name','sha256','size'}
  p=Path(a['path']);assert p.is_absolute() and '..' not in p.parts and p.is_relative_to(STAGING) and p!=STAGING
  for parent in [p,*p.parents]:
   assert not parent.is_symlink(),'Symlink component refused'
   if parent==STAGING:break
  st=owned_regular(p);assert st.st_size==a['size'] and 0<st.st_size<=MAX_BYTES
  assert re.fullmatch('[0-9a-f]{64}',a['sha256'])
  with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==a['sha256'],'Staged bytes changed'
  assert re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,150}',a['file_name'])
  assert re.fullmatch('[a-z0-9.+-]+/[a-z0-9.+-]+',a['media_type'])
  total+=st.st_size;wire.append({k:a[k] for k in ['path','media_type','file_name']})
 assert total<=MAX_BYTES
 return {'type':'send_media','account_id_hex':m['account_id_hex'],'group_id_hex':m['group_id_hex'],'attachments':wire,'caption':m['caption'],'idempotency_key':m['idempotency_key']}
def validate_text(m):
 assert set(m)=={'account_id_hex','group_id_hex','text','idempotency_key'}
 assert re.fullmatch('[0-9a-f]{64}',m['account_id_hex']) and re.fullmatch('[0-9a-f]+',m['group_id_hex']) and len(m['group_id_hex'])%2==0
 assert isinstance(m['text'],str) and 0<len(m['text'].encode())<=30000
 assert re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',m['idempotency_key'])
 return dict(type='send_final',**m)
def main():
 global MARMOT_DIR,STAGING
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--home',type=Path,default=MARMOT_DIR);ap.add_argument('--socket');ap.add_argument('--timeout',type=float,default=600)
 choice=ap.add_mutually_exclusive_group(required=True);choice.add_argument('--query',type=Path,help='JSON file containing one allowed read-only operation');choice.add_argument('--check-media',type=Path,help='Validate a private media manifest without sending');choice.add_argument('--send-text',type=Path,help='Send one explicitly authorized private text manifest');choice.add_argument('--send-media',type=Path,help='Send only the explicit user-authorized immutable manifest')
 args=ap.parse_args();MARMOT_DIR=args.home.expanduser().absolute();STAGING=MARMOT_DIR/'media-uploads'
 s=MARMOT_DIR.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700,'Expected private owned Marmot home'
 if args.socket is None:args.socket=str(MARMOT_DIR/'dev/wn-agent.sock')
 if args.query:
  payload=json.loads(args.query.read_text());assert payload.get('type') in READ_ONLY,'Query mode permits read-only operations only';print(json.dumps(rpc(args.socket,payload,args.timeout),ensure_ascii=False));return
 path=args.check_media or args.send_media or args.send_text;owned_regular(path);m=json.loads(path.read_text());payload=validate_text(m) if args.send_text else validate_manifest(m);fingerprint=hashlib.sha256(canonical(m)).hexdigest()
 if args.check_media:print(json.dumps({'valid':True,'manifest_sha256':fingerprint,'attachments':len(m['attachments']),'total_bytes':sum(a['size'] for a in m['attachments']),'messages_sent':False}));return
 ledger=MARMOT_DIR/'dev/client-sends'/(hashlib.sha256(m['idempotency_key'].encode()).hexdigest()+'.json');ledger.parent.mkdir(parents=True,exist_ok=True);ledger.parent.chmod(0o700)
 with ledger.with_suffix('.lock').open('a') as lock:
  os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX)
  if ledger.exists():
   old=json.loads(ledger.read_text());assert old['manifest_sha256']==fingerprint and old['manifest']==m,'Idempotency key is bound to different bytes/metadata/routing; refusing resend'
   if old['state']=='confirmed':print(json.dumps({'already_confirmed':True,'ledger':str(ledger),'response':old['response']},ensure_ascii=False));return
   raise SystemExit('Prior send is pending/uncertain. Inspect its timeline and receipt before retrying; no request sent.')
  record={'state':'pending','attempted_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'correlation_id':uuid.uuid4().hex,'manifest_sha256':fingerprint,'manifest':m,'socket':args.socket,'recovery':'Do not blindly retry after timeout/restart. Changed request under same server key can send again.'};atomic(ledger,record)
  try:
   response=rpc(args.socket,payload,args.timeout,record['correlation_id']);record['response']=response
   assert response.get('type')=='final_sent' and response.get('message_ids_hex'),'No nonempty successful send receipt; outcome requires inspection'
   for identifier in response['message_ids_hex']:assert isinstance(identifier,str) and identifier and len(identifier)%2==0 and re.fullmatch('[0-9a-fA-F]+',identifier)
  except BaseException as error:
   record['state']='uncertain';record['error_type']=type(error).__name__;atomic(ledger,record);raise
  record['state']='confirmed';atomic(ledger,record);print(json.dumps({'sent':True,'ledger':str(ledger),'response':response,'phone_display_verified':False},ensure_ascii=False))
if __name__=='__main__':main()
