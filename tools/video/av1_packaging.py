"""Import render-owned AV1/AAC assets. All FFmpeg operations use stream copy."""
import json
import math
from pathlib import Path
import re
import subprocess
from fractions import Fraction

SIZES = {'720p': (1280, 720), '480p': (854, 480), '360p': (640, 360)}


def manifest_data(path):
    path = Path(path).resolve()
    manifest = json.loads(path.read_text())
    if manifest.get('version') != 1 or {v['label'] for v in manifest['renditions']} != set(SIZES):
        raise ValueError('Manifest must specify the 720p, 480p and 360p AV1 renditions')
    if len(manifest['renditions']) != 3:
        raise ValueError('Duplicate rendition')
    return manifest


def readiness(path):
    manifest = manifest_data(path)
    pending = []
    for item in manifest['renditions'] + [manifest['fallback']]:
        for field in ('path', 'verification'):
            candidate = Path(item[field])
            if not candidate.is_file():
                pending.append(str(candidate))
        report_path = Path(item['verification'])
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            if report.get('full_decode_passed') is not True:
                pending.append(f'{report_path}: full decode has not passed')
    return dict(ready=not pending, manifest=str(Path(path).resolve()), pending=pending,
                note='Readiness requires subsequent path/hash, codec, timeline and keyframe checks before packaging')


def extradata_bytes(dump):
    chunks = []
    for line in dump.splitlines():
        if ':' in line:
            chunks.append(line.split(':', 1)[1].strip().split('  ', 1)[0].replace(' ', ''))
    return bytes.fromhex(''.join(chunks))


def av1_codec_string(record):
    """AOM AV1 ISOBMFF section 5 mandatory P.LLT.DD, from av1C fields."""
    if len(record) < 4 or record[0] != 0x81:
        raise ValueError('Invalid AV1CodecConfigurationRecord marker/version')
    profile, level = record[1] >> 5, record[1] & 31
    tier = 'H' if record[2] & 0x80 else 'M'
    high, twelve = bool(record[2] & 0x40), bool(record[2] & 0x20)
    if profile > 2 or (twelve and (not high or profile != 2)):
        raise ValueError('Invalid AV1 profile/bit-depth configuration')
    bits = 12 if twelve else 10 if high else 8
    return f'av01.{profile}.{level:02d}{tier}.{bits:02d}'


def media_details(path, workflow):
    info = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-show_data', '-of', 'json', str(path)
    ]))
    video, audio = workflow.stream(info, 'video'), workflow.stream(info, 'audio')
    if not video or not audio or video['codec_name'] != 'av1' or video['codec_tag_string'] != 'av01':
        raise ValueError(f'Expected AV1 video and audio in MP4: {path}')
    if (audio['codec_name'] != 'aac' or audio.get('profile') != 'LC' or
            int(audio['sample_rate']) != 48000 or audio['channels'] != 1):
        raise ValueError(f'Expected AAC-LC 48 kHz mono: {path}')
    # 64 kbps is the encoder setting. VBR headers can report ~65.7 kbps.
    if not 48000 <= int(audio.get('bit_rate', 0)) <= 72000:
        raise ValueError(f'Audio bitrate does not match the 64 kbps policy: {path}')
    if Fraction(video['r_frame_rate']) != 15 or abs(float(Fraction(video['avg_frame_rate'])) - 15) > 0.01:
        raise ValueError(f'Expected 15 fps: {path}')
    codec = av1_codec_string(extradata_bytes(video['extradata']))
    duration = float(info['format']['duration'])
    return dict(path=str(path), sha256=workflow.digest(path), size=path.stat().st_size,
                width=video['width'], height=video['height'], duration=duration, fps=15,
                average_bitrate=round(path.stat().st_size * 8 / duration),
                video_codec=codec, codecs=f'{codec},mp4a.40.2',
                mime=f'video/mp4; codecs="{codec},mp4a.40.2"',
                audio=dict(codec='aac', profile='LC', sample_rate=48000, channels=1, target_kbps=64,
                           measured_bitrate=int(audio['bit_rate'])))


def verified_input(item, manifest, workflow):
    path = Path(item['path']).resolve(strict=True)
    report_path = Path(item['verification']).resolve(strict=True)
    report = json.loads(report_path.read_text())
    for flag in ('full_decode_passed', 'fast_start', 'no_edit_lists', 'normalized_retained_spoken_words_preserved'):
        if report.get(flag) is not True:
            raise ValueError(f'Render verification has not passed {flag}: {report_path}')
    details = media_details(path, workflow)
    if (Path(report['file']).resolve() != path or report['sha256'] != details['sha256'] or
            report['bytes'] != details['size']):
        raise ValueError(f'Render verification does not bind these exact source bytes: {path}')
    for field in ('sha256', 'size'):
        if field in item and item[field] != details[field]:
            raise ValueError(f'Approved input {field} mismatch: {path}')
    expected_size = SIZES[item.get('label', '480p')]
    if (details['width'], details['height']) != expected_size:
        raise ValueError(f'Incorrect rendition dimensions: {path}')
    if abs(details['duration'] - manifest['expected_duration_seconds']) > 0.15:
        raise ValueError(f'Incorrect edited timeline duration: {path}')
    if report.get('max_keyframe_gap_seconds') is not None and report['max_keyframe_gap_seconds'] > 6.1:
        raise ValueError(f'Keyframes do not satisfy six-second intervals: {path}')
    packets = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_packets',
        '-show_entries', 'packet=pts_time,flags', '-of', 'json', str(path)
    ]))['packets']
    keys = [float(p['pts_time']) for p in packets if 'K' in p['flags']]
    if (not keys or abs(keys[0]) > 0.1 or details['duration'] - keys[-1] > 6.1 or
            any(abs((b - a) - 6) > 1 / 15 + 0.001 for a, b in zip(keys, keys[1:]))):
        raise ValueError(f'Expected closed keyframes at six-second boundaries: {path}')
    details['keyframes'] = keys
    details['verification'] = dict(path=str(report_path), sha256=workflow.digest(report_path), full_decode_passed=True)
    details['editorial_identity'] = {key: report[key] for key in (
        'transcript_sha256', 'source_audio_sha256', 'video_edit')}
    return details


def bandwidth(segments, durations, target=6):
    """RFC 8216 peak: contiguous windows of 0.5..1.5 target durations."""
    peaks = []
    for start in range(len(durations)):
        size, duration = 0, 0
        for index in range(start, len(durations)):
            size += segments[index].stat().st_size
            duration += durations[index]
            if duration > target * 1.5:
                break
            if duration >= target * 0.5:
                peaks.append(size * 8 / duration)
    if not peaks:
        peaks = [sum(p.stat().st_size for p in segments) * 8 / sum(durations)]
    return dict(peak_bandwidth=math.ceil(max(peaks)),
                average_bandwidth=math.ceil(sum(p.stat().st_size for p in segments) * 8 / sum(durations)))


def prepare(args, workflow):
    manifest = manifest_data(args.manifest)
    status = readiness(args.manifest)
    if not status['ready']:
        raise ValueError('Render inputs are not ready: ' + '; '.join(status['pending']))
    # Check everything before creating an output directory or touching any input.
    variants = [dict(label=item['label'], **verified_input(item, manifest, workflow))
                for item in sorted(manifest['renditions'], key=lambda x: SIZES[x['label']][1], reverse=True)]
    fallback = verified_input(manifest['fallback'], manifest, workflow)
    reference = variants[0]
    for item in variants + [fallback]:
        if item['editorial_identity'] != reference['editorial_identity']:
            raise ValueError('Renditions do not share the same edited content/audio timeline')
        if len(item['keyframes']) != len(reference['keyframes']) or any(
                abs(a - b) > 0.002 for a, b in zip(item['keyframes'], reference['keyframes'])):
            raise ValueError('Rendition keyframes are not aligned')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / 'hls').mkdir()
    commands = []
    master = ['#EXTM3U', '#EXT-X-VERSION:7', '#EXT-X-INDEPENDENT-SEGMENTS']
    for variant in variants:
        relative = Path('hls') / variant['label']
        (output / relative).mkdir()
        command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'warning', '-n', '-i', variant['path'],
                   '-map', '0:v:0', '-map', '0:a:0', '-map_metadata', '-1', '-map_chapters', '-1', '-c', 'copy',
                   '-f', 'hls', '-hls_time', '6', '-hls_playlist_type', 'vod', '-hls_list_size', '0',
                   '-hls_segment_type', 'fmp4', '-hls_flags', 'independent_segments',
                   '-hls_fmp4_init_filename', 'init.mp4', '-hls_segment_filename',
                   str(relative / 'segment-%06d.m4s'), str(relative / 'index.m3u8')]
        print(f"Remuxing verified {variant['label']} AV1/AAC (stream copy)", flush=True)
        commands.append(command)
        subprocess.run(command, cwd=output, check=True)
        playlist = output / relative / 'index.m3u8'
        text = playlist.read_text()
        durations = [float(x) for x in re.findall(r'^#EXTINF:([\d.]+),', text, re.M)]
        segments = [playlist.parent / line for line in text.splitlines() if line and not line.startswith('#')]
        if len(segments) != len(durations) or not durations or any(abs(d - 6) > 0.1 for d in durations[:-1]):
            raise ValueError('Remuxing did not produce six-second aligned segments')
        variant.update(bandwidth(segments, durations), segment_count=len(segments), hls_duration=sum(durations))
        master.extend([f'#EXT-X-STREAM-INF:BANDWIDTH={variant["peak_bandwidth"]},'
                       f'AVERAGE-BANDWIDTH={variant["average_bandwidth"]},'
                       f'RESOLUTION={variant["width"]}x{variant["height"]},FRAME-RATE=15.000,'
                       f'CODECS="{variant["codecs"]}"', f'{variant["label"]}/index.m3u8'])
    (output / 'hls' / 'master.m3u8').write_text('\n'.join(master) + '\n')
    assets, master_sha, fallback_sha = workflow.package_hls(output, Path(fallback['path']))
    if fallback_sha != fallback['sha256']:
        raise ValueError('Packaging changed the approved fallback bytes')
    for asset in assets:
        if asset['role'] == 'fallback':
            asset['mime'] = fallback['mime']
    # Re-hash all render inputs after packaging to catch a replaced/running source.
    for item in variants + [fallback]:
        if workflow.digest(item['path']) != item['sha256']:
            raise ValueError('A render input changed during packaging')
    bundle = dict(version=2, created_at=workflow.utc_now(), policy='av1-15fps-aac64-mono-6s',
                  input_manifest=dict(path=str(args.manifest.resolve()), sha256=workflow.digest(args.manifest)),
                  settings=dict(max_height=720, fps=15, video_codec='av1', audio_kbps=64, audio_channels=1,
                                sample_rate=48000, segment_seconds=6, stream_copy_only=True),
                  variants=variants, fallback=fallback, master_sha256=master_sha, fallback_sha256=fallback_sha,
                  assets=assets, commands=commands, real_episode_uploaded=False, video_event_published=False)
    workflow.save_json(output / 'bundle.json', bundle)
    workflow.validate_bundle(output)
    print(json.dumps(dict(bundle=str(output), assets=len(assets), upload_bytes=sum(a['size'] for a in assets),
                          fallback_sha256=fallback_sha, real_episode_uploaded=False), indent=2))
