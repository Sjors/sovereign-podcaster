"""Deterministic private-first YouTube uploads; resumable URLs remain private."""
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlsplit
import episodes as e

CHUNK=8*1024*1024

def sdk():
    path=Path(__file__).resolve().parents[2]/'skills/youtube-publishing/scripts/youtube_access.py'
    spec=importlib.util.spec_from_file_location('youtube_access',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def metadata(value):
    required={'title','description','category_id','language','tags','made_for_kids','contains_synthetic_media'}
    if set(value)!=required:raise ValueError('YouTube metadata requires exactly '+', '.join(sorted(required)))
    if not isinstance(value['title'],str) or not 1<=len(value['title'])<=100 or any(x in value['title'] for x in '<>'):raise ValueError('Invalid YouTube title')
    if not isinstance(value['description'],str) or len(value['description'].encode())>5000 or any(x in value['description'] for x in '<>'):raise ValueError('Invalid YouTube description')
    if not re.fullmatch('[0-9]+',value['category_id']) or not re.fullmatch('[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*',value['language']):raise ValueError('Invalid category/language')
    if not isinstance(value['tags'],list) or any(not isinstance(t,str) or not t or ',' in t for t in value['tags']) or sum(len(t)+1 for t in value['tags'])>500:raise ValueError('Invalid tags')
    if any(type(value[k]) is not bool for k in ('made_for_kids','contains_synthetic_media')):raise ValueError('Explicit audience and synthetic-media flags are required')
    return dict(snippet=dict(title=value['title'],description=value['description'],categoryId=value['category_id'],defaultLanguage=value['language'],defaultAudioLanguage=value['language'],tags=value['tags']),
                status=dict(privacyStatus='private',selfDeclaredMadeForKids=value['made_for_kids'],containsSyntheticMedia=value['contains_synthetic_media']))

def valid_uri(uri):
    p=urlsplit(uri)
    if p.scheme!='https' or p.hostname not in ('www.googleapis.com','youtube.googleapis.com','upload.youtube.com') or p.username or p.fragment:raise ValueError('Unexpected resumable upload destination')
    return uri

def response_json(response,body):
    code=int(response.status)
    if code in (200,201):return json.loads(body)
    if code==308:return None
    # Never expose headers, resumable URI, request body or OAuth details.
    raise RuntimeError('YouTube upload HTTP '+str(code)+'; inspect private stage state before retrying')

def progress(response,total):
    value=response.get('range','')
    if not value:return 0
    m=re.fullmatch('bytes=0-([0-9]+)',value)
    if not m or not 0<=int(m[1])<total:raise ValueError('Unexpected upload progress acknowledgement')
    return int(m[1])+1

def resumable(service,packet,folder,state,check):
    from googleapiclient.http import MediaFileUpload
    path=folder/'upload.private.json';video=Path(packet['files']['video']['path']);size=video.stat().st_size
    binding=dict(video=packet['files']['video'],metadata=packet['metadata'],channel=packet['channel_id'],manifest_sha256=packet['manifest_sha256'])
    saved=e.read(path) if path.exists() else dict(binding=binding,phase='new',offset=0)
    if saved['binding']!=binding:raise ValueError('Upload session belongs to different bytes/metadata/channel')
    if saved.get('video_id'):return saved['video_id']
    http=service._http
    def put(body,headers):
        check()
        try:return http.request(valid_uri(saved['uri']),method='PUT',body=body,headers=headers)
        except Exception:raise RuntimeError('Upload outcome is uncertain; resume this saved session to query progress') from None
    if not saved.get('uri'):
        if saved['phase']!='new':raise RuntimeError('Upload initiation outcome is unresolved; do not create a second upload')
        request=service.videos().insert(part='snippet,status',body=metadata(packet['metadata']),notifySubscribers=False,
            media_body=MediaFileUpload(str(video),mimetype='video/mp4',chunksize=CHUNK,resumable=True))
        saved['phase']='initiating';e.save(path,saved);check()
        headers=dict(request.headers);headers.update({'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(size)})
        try:response,body=http.request(request.uri,method='POST',body=request.body,headers=headers)
        except Exception:raise RuntimeError('Upload initiation response was lost; inspect before creating another session') from None
        if int(response.status) not in (200,201) or not response.get('location'):raise RuntimeError('YouTube did not return a resumable upload session; inspect private state')
        saved.update(uri=valid_uri(response['location']),phase='uploading');e.save(path,saved)
    else:
        response,body=put(b'',{'Content-Length':'0','Content-Range':f'bytes */{size}'})
        done=response_json(response,body)
        if done:
            saved.update(video_id=done['id'],phase='uploaded');e.save(path,saved);return saved['video_id']
        saved['offset']=progress(response,size);e.save(path,saved)
    with video.open('rb') as source:
        while saved['offset']<size:
            offset=saved['offset'];source.seek(offset);chunk=source.read(min(CHUNK,size-offset))
            response,body=put(chunk,{'Content-Length':str(len(chunk)),'Content-Type':'video/mp4','Content-Range':f'bytes {offset}-{offset+len(chunk)-1}/{size}'})
            done=response_json(response,body)
            if done:
                saved.update(video_id=done['id'],phase='uploaded');e.save(path,saved);return saved['video_id']
            next_offset=progress(response,size)
            if next_offset<=offset or next_offset>offset+len(chunk):raise ValueError('Upload acknowledgement made no valid progress')
            saved['offset']=next_offset;e.save(path,saved)
    raise RuntimeError('All bytes acknowledged without final video ID; query the same saved session on resume')

def validate_readback(video,packet,privacy):
    desired=metadata(packet['metadata']);snippet=video.get('snippet',{});status=video.get('status',{})
    if snippet.get('channelId')!=packet['channel_id'] or status.get('privacyStatus')!=privacy:raise ValueError('YouTube channel/visibility readback mismatch')
    for k in ('title','description','categoryId','defaultLanguage','defaultAudioLanguage'):
        if snippet.get(k)!=desired['snippet'][k]:raise ValueError('YouTube metadata readback mismatch: '+k)
    if sorted(snippet.get('tags',[]))!=sorted(desired['snippet']['tags']):raise ValueError('YouTube tags readback mismatch')
    for k in ('selfDeclaredMadeForKids','containsSyntheticMedia'):
        if status.get(k,False)!=desired['status'][k]:raise ValueError('YouTube status readback mismatch: '+k)
    return video

def caption_entries(raw):
    if isinstance(raw,bytes):raw=raw.decode('utf-8-sig')
    result=[]
    def seconds(text):
        parts=text.replace(',','.').split(':');return sum(float(p)*60**i for i,p in enumerate(reversed(parts)))
    for block in re.split(r'\n\s*\n',raw.replace('\r\n','\n').strip()):
        lines=block.splitlines()
        for i,line in enumerate(lines):
            match=re.fullmatch(r'([0-9:.]+) --> ([0-9:.]+)(?: .*)?',line.strip())
            if match:
                text=html.unescape(re.sub(r'<[^>]*>','',' '.join(lines[i+1:])))
                result.append(dict(start=round(seconds(match[1]),2),end=round(seconds(match[2]),2),text=' '.join(text.split())))
                break
    if not result:raise ValueError('Caption download contains no timed cues')
    return result

def thumbnail_bytes(video):
    thumbnails=video['snippet'].get('thumbnails',{})
    selected=thumbnails.get('maxres') or thumbnails.get('standard') or thumbnails.get('high')
    if not selected:raise ValueError('YouTube has no reviewable thumbnail')
    uri=selected['url'];p=urlsplit(uri)
    if p.scheme!='https' or not p.hostname or not p.hostname.endswith('.ytimg.com') or p.username:raise ValueError('Unexpected thumbnail destination')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect)
    with opener.open(uri,timeout=30) as response:
        raw=response.read(8*1024*1024+1)
        if len(raw)>8*1024*1024 or response.headers.get_content_type() not in ('image/jpeg','image/png','image/webp'):raise ValueError('Invalid thumbnail response')
    return hashlib.sha256(raw).hexdigest()

def thumbnail_readback(response,video):
    actual=video.get('snippet',{}).get('thumbnails',{})
    for variant in ('maxres','standard','high'):
        if not actual.get(variant):continue
        returned=next((item[variant] for item in response.get('items',[]) if isinstance(item.get(variant),dict)),None)
        if not returned or (returned.get('width'),returned.get('height'))!=(actual[variant].get('width'),actual[variant].get('height')):return None
        # YouTube can give the upload and video APIs different signed URLs for
        # identical transformed images. Verify the preferred image, not its URL.
        expected=thumbnail_bytes(dict(snippet=dict(thumbnails={'high':returned})))
        observed=thumbnail_bytes(video)
        return observed if expected==observed else None
    return None

def wait_processed(service,video_id,packet,check):
    access=sdk();deadline=time.monotonic()+packet.get('processing_timeout_seconds',1800)
    while True:
        check();video=access.owned_video(service,video_id,packet['channel_id'],part='snippet,status,processingDetails')
        status=video.get('processingDetails',{}).get('processingStatus')
        if status=='succeeded':return video
        if status in ('failed','terminated'):raise RuntimeError('YouTube video processing failed; inspect the existing video ID')
        if time.monotonic()>=deadline:raise RuntimeError('YouTube processing deadline reached; resume the existing upload later')
        time.sleep(10)

def caption_ready(service,video_id,packet,folder,check,allow_update=False):
    from googleapiclient.http import MediaFileUpload
    expected=caption_entries(Path(packet['files']['captions']['path']).read_bytes())
    name='sovereign-podcaster-'+packet['files']['captions']['sha256'][:20];language=packet['metadata']['language'];path=folder/'caption.json'
    items=service.captions().list(part='snippet',videoId=video_id).execute(num_retries=2).get('items',[])
    matches=[x for x in items if (x['id']==packet['reuse_caption_id'] if packet.get('reuse_caption_id') else x['snippet'].get('name')==name and x['snippet'].get('language')==language)]
    if packet.get('reuse_caption_id') and not matches:raise ValueError('Previously reviewed caption track is missing')
    if len(matches)>1:raise ValueError('Duplicate caption tracks require inspection')
    if not matches:
        if path.exists():raise RuntimeError('Caption creation outcome is unresolved; inspect tracks before retrying')
        e.save(path,dict(phase='inserting',name=name,video_id=video_id,source=packet['files']['captions']));check()
        try:track=service.captions().insert(part='snippet',body={'snippet':{'videoId':video_id,'language':language,'name':name,'isDraft':False}},media_body=MediaFileUpload(packet['files']['captions']['path'],mimetype='text/vtt',resumable=False)).execute(num_retries=0)
        except Exception:raise RuntimeError('Caption insertion outcome is unresolved; inspect saved state/tracks before resuming') from None
        e.save(path,dict(phase='inserted',id=track['id'],name=name,source=packet['files']['captions']))
        matches=[track]
    track=matches[0]
    if allow_update and packet.get('reuse_caption_id'):
        current=service.captions().download(id=track['id'],tfmt='vtt').execute(num_retries=2)
        if caption_entries(current)!=caption_entries(Path(packet['files']['captions']['path']).read_bytes()):
            check();e.save(path,dict(phase='updating',id=track['id'],source=packet['files']['captions']))
            try:service.captions().update(part='id',body={'id':track['id']},media_body=MediaFileUpload(packet['files']['captions']['path'],mimetype='text/vtt',resumable=False)).execute(num_retries=0)
            except Exception:raise RuntimeError('Caption replacement outcome uncertain; resume the same track ID') from None
            found=service.captions().list(part='snippet',videoId=video_id,id=track['id']).execute(num_retries=2).get('items',[])
            if len(found)!=1:raise ValueError('Updated caption track missing')
            track=found[0]
    if track['snippet'].get('status')=='failed':raise RuntimeError('YouTube caption processing failed')
    deadline=time.monotonic()+packet.get('processing_timeout_seconds',1800)
    while track['snippet'].get('status')!='serving':
        if track['snippet'].get('status')=='failed':raise RuntimeError('YouTube caption processing failed')
        if time.monotonic()>=deadline:raise RuntimeError('YouTube captions processing deadline reached; resume later')
        check();time.sleep(10)
        listed=service.captions().list(part='snippet',videoId=video_id,id=track['id']).execute(num_retries=2).get('items',[])
        if len(listed)!=1:raise ValueError('Caption track disappeared during processing')
        track=listed[0]
    for attempt in range(4):
        check()
        downloaded=service.captions().download(id=track['id'],tfmt='vtt').execute(num_retries=2)
        try:actual=caption_entries(downloaded);break
        except ValueError:
            if attempt==3:raise RuntimeError('YouTube caption download is not ready; preserve the same video and caption IDs') from None
            time.sleep(5)
    if len(expected)!=len(actual) or any(a['text']!=b['text'] or abs(a['start']-b['start'])>.05 or abs(a['end']-b['end'])>.05 for a,b in zip(expected,actual)):raise ValueError('Caption download differs from the reviewed words/timing')
    track=dict(track,verified_cues_sha256=e.digest(actual))
    e.save(path,dict(phase='verified',id=track['id'],name=name,source=packet['files']['captions'],readback=track))
    return track

def private(service,packet,folder,check):
    from googleapiclient.http import MediaFileUpload
    access=sdk();video_id=packet.get('reuse_video_id') or resumable(service,packet,folder,{},check)
    video=wait_processed(service,video_id,packet,check)
    if packet.get('reuse_video_id'):
        if video['status'].get('privacyStatus')!='private':raise ValueError('Only an existing private video can be revised in place')
        desired=metadata(packet['metadata'])
        try:validate_readback(video,packet,'private')
        except ValueError:
            status={k:v for k,v in video['status'].items() if k in ('embeddable','license','publicStatsViewable')};status.update(desired['status'])
            check();e.save(folder/'metadata-update.json',dict(video_id=video_id,manifest_sha256=packet['manifest_sha256'],state='updating'))
            try:service.videos().update(part='snippet,status',body={'id':video_id,'snippet':desired['snippet'],'status':status}).execute(num_retries=0)
            except Exception:raise RuntimeError('Metadata update outcome uncertain; resume the same private video ID') from None
    validate_readback(access.owned_video(service,video_id,packet['channel_id']),packet,'private')
    state_path=folder/'thumbnail.json'
    if not state_path.exists() or e.read(state_path).get('state')!='set':
        check();e.save(state_path,dict(state='setting',source=packet['files']['thumbnail']))
        try:result=service.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(packet['files']['thumbnail']['path'],mimetype='image/jpeg',resumable=False)).execute(num_retries=0)
        except Exception:raise RuntimeError('Thumbnail update uncertain; the same exact thumbnail may be safely reapplied to this video ID') from None
        e.save(state_path,dict(state='set',source=packet['files']['thumbnail'],response=result))
    elif e.read(state_path)['source']!=packet['files']['thumbnail']:raise ValueError('Thumbnail source changed')
    track=caption_ready(service,video_id,packet,folder,check,allow_update=True)
    video=validate_readback(access.owned_video(service,video_id,packet['channel_id'],part='snippet,status,processingDetails'),packet,'private')
    thumb=e.read(state_path)
    thumbnail_sha=thumbnail_readback(thumb['response'],video)
    if not thumbnail_sha:raise RuntimeError('Thumbnail readback is not available yet; resume this stage later')
    return dict(video_id=video_id,channel_id=packet['channel_id'],privacy_status='private',verified=True,caption_id=track['id'],thumbnail_source=packet['files']['thumbnail'],metadata=packet['metadata'],video_source=packet['files']['video'],readback=video,thumbnail_readback_sha256=thumbnail_sha,caption_readback_sha256=track['verified_cues_sha256'],
                limitation='YouTube transforms uploaded media and thumbnails. API resource/processing readback does not prove phone playback or byte-identical transcoding.')

def public(service,packet,private_receipt,folder,check):
    access=sdk();video_id=private_receipt['video_id']
    video=access.owned_video(service,video_id,packet['channel_id'],part='snippet,status,processingDetails')
    current=video['status']['privacyStatus']
    if current not in ('private','public'):raise ValueError('Unexpected visibility; inspect before publication')
    validate_readback(video,packet,current)
    if video.get('processingDetails',{}).get('processingStatus')!='succeeded':raise RuntimeError('YouTube is not processed')
    # Re-check captions and thumbnail before the only visibility mutation.
    track=caption_ready(service,video_id,dict(packet,reuse_caption_id=private_receipt['caption_id']),folder.parent/'youtube-private',check)
    if track['id']!=private_receipt['caption_id']:raise ValueError('Reviewed caption ID changed')
    old_urls={x.get('url') for x in private_receipt['readback']['snippet']['thumbnails'].values()}
    new_urls={x.get('url') for x in video['snippet'].get('thumbnails',{}).values()}
    if thumbnail_bytes(video)!=private_receipt['thumbnail_readback_sha256']:raise ValueError('Reviewed thumbnail bytes changed')
    if track['verified_cues_sha256']!=private_receipt['caption_readback_sha256']:raise ValueError('Reviewed captions changed')
    if current=='private':
        check();e.save(folder/'visibility.json',dict(state='updating',video_id=video_id,manifest_sha256=packet['manifest_sha256']))
        status={k:v for k,v in video['status'].items() if k in ('embeddable','license','publicStatsViewable','selfDeclaredMadeForKids','containsSyntheticMedia')}
        status['privacyStatus']='public'
        try:service.videos().update(part='status',body={'id':video_id,'status':status}).execute(num_retries=0)
        except Exception:raise RuntimeError('Visibility update outcome uncertain; resume this same video ID for readback') from None
    check();video=validate_readback(access.owned_video(service,video_id,packet['channel_id'],part='snippet,status,processingDetails'),packet,'public')
    return dict(video_id=video_id,channel_id=packet['channel_id'],privacy_status='public',verified=True,readback=video)
