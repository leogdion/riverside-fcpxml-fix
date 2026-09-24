#!/usr/bin/env python3
"""Fix a Riverside "Export timeline" FCPXML for Final Cut Pro.

Fixes applied (each can be disabled):
  1. Report media files referenced by the XML that are missing on disk.
  2. Declare each video asset at its real resolution (Riverside labels 4K
     media as 1080p) and set the project to the largest source resolution.
  3. Align every sync-clip's start with its inner clip. Riverside rounds it in
     the source's timebase, and for odd-rate media (e.g. ~23.998fps) this
     leaves a blank frame at the head or tail of the clip.
  4. Wrap each green-screen recording in a compound clip (background image
     under the video) and point every timeline cut at it, so Riverside's
     per-cut crop/position moves the background together with the person.
     The Keyer is NOT added: applied via XML it doesn't auto-sample the screen
     colour, so add it by hand once per compound in FCP.

Usage:
  fix_riverside_fcpxml.py exportedTimeline.fcpxml [-o out.fcpxml]
      [--green NAME ...] [--no-green] [--background NAME]
      [--keep-formats] [--no-align] [--no-validate]
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from urllib.parse import unquote, urlparse


def t(s):
    return Fraction(s[:-1]) if s else Fraction(0)


def media_path(xml_dir, src):
    if src.startswith('file:'):
        src = unquote(urlparse(src).path)
    return src if os.path.isabs(src) else os.path.join(xml_dir, src)


def probe(path):
    """(width, height, frameDuration) of the first video stream, or None."""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
             'stream=width,height,r_frame_rate', '-of', 'csv=p=0', path],
            capture_output=True, text=True, check=True).stdout.strip()
        w, h, rate = out.split(',')[:3]
        num, den = rate.split('/')
        return int(w), int(h), f'{den}/{num}s' if den != '1' else f'1/{num}s'
    except Exception:
        return None


def is_green_screen(path, duration):
    """Sample a frame and check whether the frame border is mostly green."""
    W, H = 64, 36
    ss = float(duration) * 0.25 if duration else 10
    try:
        raw = subprocess.run(
            ['ffmpeg', '-v', 'error', '-ss', f'{ss:.2f}', '-i', path, '-frames:v', '1',
             '-vf', f'scale={W}:{H}', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
            capture_output=True, check=True).stdout
    except Exception:
        return False
    if len(raw) < W * H * 3:
        return False
    border = [(x, y) for y in range(H) for x in range(W)
              if y < H // 4 or x < W // 8 or x >= W - W // 8]
    green = 0
    for x, y in border:
        r, g, b = raw[(y * W + x) * 3:(y * W + x) * 3 + 3]
        if g > 60 and g > r * 1.25 and g > b * 1.25:
            green += 1
    return green / len(border) > 0.6


def format_name(h, frame_duration):
    fps = 1 / t(frame_duration)
    tag = {Fraction(24000, 1001): '2398', Fraction(30000, 1001): '2997',
           Fraction(60000, 1001): '5994'}.get(fps, str(round(float(fps))))
    return f'FFVideoFormat{h}p{tag}'


def find_dtd(version):
    for app in glob.glob('/Applications/Final Cut Pro*.app'):
        p = os.path.join(app, 'Contents/Frameworks/Interchange.framework/Versions/A/'
                              f'Resources/FCPXMLv{version.replace(".", "_")}.dtd')
        if os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('input')
    ap.add_argument('-o', '--output', help='default: <input>-fixed.fcpxml')
    ap.add_argument('--green', action='append', metavar='NAME',
                    help='asset name substring of a green-screen video (repeatable; default: auto-detect)')
    ap.add_argument('--no-green', action='store_true', help='skip the background compounds')
    ap.add_argument('--background', metavar='NAME', help='asset name substring of the background image')
    ap.add_argument('--keep-formats', action='store_true', help="don't correct resolutions / project format")
    ap.add_argument('--no-align', action='store_true', help="don't align sync-clip starts")
    ap.add_argument('--no-validate', action='store_true', help="don't validate against FCP's DTD")
    args = ap.parse_args()

    src = args.input
    dst = args.output or os.path.splitext(src)[0] + '-fixed.fcpxml'
    xml_dir = os.path.dirname(os.path.abspath(src))
    tree = ET.parse(src)
    root = tree.getroot()
    res = root.find('resources')
    assets = {a.get('id'): a for a in res.iter('asset')}
    formats = {f.get('id'): f for f in res.iter('format')}
    used = {e.get('id') for e in res}
    project_seq = root.find('.//project/sequence')

    def new_id():
        i = next(i for i in range(len(used), 100000) if f'r{i}' not in used)
        used.add(f'r{i}')
        return f'r{i}'

    def src_of(a):
        rep = a.find('media-rep')
        return media_path(xml_dir, rep.get('src')) if rep is not None else None

    # 1. Missing media
    missing = [a.get('name') for a in assets.values() if not os.path.exists(src_of(a) or '')]
    print(f'missing media: {len(missing)}')
    for name in missing:
        print(f'  MISSING  {name}')

    videos = [a for a in assets.values()
              if a.get('hasVideo') == '1' and a.get('duration') not in (None, '0s')
              and os.path.exists(src_of(a))]
    real = {a.get('id'): probe(src_of(a)) for a in videos}

    # 2. Real resolutions + project format
    if not args.keep_formats:
        def format_for(w, h, fd):
            for f in formats.values():
                if (f.get('width'), f.get('height'), f.get('frameDuration')) == (str(w), str(h), fd):
                    return f.get('id')
            fid = new_id()
            f = ET.Element('format', id=fid, name=format_name(h, fd), frameDuration=fd,
                           width=str(w), height=str(h))
            res.insert(0, f)
            formats[fid] = f
            return fid

        for a in videos:
            info = real[a.get('id')]
            if not info:
                continue
            w, h, fd = info
            cur = formats.get(a.get('format'))
            if cur is not None and (cur.get('width'), cur.get('height')) == (str(w), str(h)):
                continue
            a.set('format', format_for(w, h, fd))
            print(f'format: {a.get("name")} declared {cur.get("width") if cur is not None else "?"}'
                  f'x{cur.get("height") if cur is not None else "?"} -> actual {w}x{h}')
        biggest = max((i for i in real.values() if i), key=lambda i: i[0] * i[1], default=None)
        pf = formats.get(project_seq.get('format'))
        if biggest and pf is not None and int(pf.get('width', 0)) < biggest[0]:
            project_seq.set('format', format_for(biggest[0], biggest[1], pf.get('frameDuration')))
            print(f'project: {pf.get("width")}x{pf.get("height")} -> {biggest[0]}x{biggest[1]}')

    # 4. Green-screen compounds
    if not args.no_green:
        if args.green:
            sources = [a.get('id') for a in videos if any(g in a.get('name') for g in args.green)]
        else:
            sources = [a.get('id') for a in videos
                       if is_green_screen(src_of(a), float(t(a.get('duration'))))]
        stills = Counter(v.get('ref') for v in root.iter('video')
                         if assets.get(v.get('ref')) is not None
                         and assets[v.get('ref')].get('duration') == '0s')
        if args.background:
            bg_ref = next((i for i, a in assets.items() if args.background in a.get('name')), None)
        else:
            bg_ref = stills.most_common(1)[0][0] if stills else None
        print('green-screen videos: ' + (', '.join(assets[s].get('name') for s in sources) or 'none'))
        if sources and not bg_ref:
            print('  no background image found; skipping compounds (use --background)')
            sources = []
        if sources:
            print(f'background: {assets[bg_ref].get("name")}')

        # A person's name comes from the enhanced audio Riverside nests in their clips
        person = {}
        for clip in root.iter('asset-clip'):
            if clip.get('ref') in sources and clip.get('ref') not in person:
                for child in clip.iter('asset-clip'):
                    n = child.get('name', '')
                    if n.endswith('-enhanced.wav'):
                        person[clip.get('ref')] = n.split('-')[0].replace('_', ' ').title()

        media_for = {ref: new_id() for ref in sources}
        n = kept_audio = 0
        for parent in root.iter():
            for i, clip in enumerate(list(parent)):
                if clip.tag != 'asset-clip' or clip.get('ref') not in media_for:
                    continue
                # ref-clip can't carry audio-channel-source; Riverside mutes the video's
                # own audio (active="0") and uses the nested wavs, so video-only is right.
                if any(c.get('active', '1') != '0' for c in clip.findall('audio-channel-source')):
                    kept_audio += 1
                rc = ET.Element('ref-clip', ref=media_for[clip.get('ref')], srcEnable='video',
                                **{k: clip.get(k) for k in ('offset', 'name', 'start', 'duration')
                                   if clip.get(k) is not None})
                for child in clip:
                    if child.tag != 'audio-channel-source':
                        rc.append(child)
                parent.remove(clip)
                parent.insert(i, rc)
                n += 1
        if kept_audio:
            print(f'  warning: {kept_audio} clips had the video file audio enabled; it is now dropped')

        event = root.find('library/event')
        for k, ref in enumerate(sources):
            a = assets[ref]
            dur = a.get('duration')
            name = f'{person.get(ref, "Speaker")} + Background ({a.get("name")[:8]})'
            m = ET.SubElement(res, 'media', id=media_for[ref], name=name)
            seq = ET.SubElement(m, 'sequence', format=a.get('format'), duration=dur, tcStart='0s',
                                tcFormat='NDF', audioLayout='stereo', audioRate='48k')
            bg = ET.SubElement(ET.SubElement(seq, 'spine'), 'video', ref=bg_ref, offset='0s',
                               name='Background', duration=dur)
            ET.SubElement(bg, 'asset-clip', ref=ref, lane='1', offset='0s', name=a.get('name'),
                          start='0s', duration=dur, srcEnable='video')
            # Browser entry so the compound shows up in the event
            event.insert(k, ET.Element('ref-clip', ref=media_for[ref], name=name, duration=dur))
        if sources:
            print(f'compounds: {len(sources)}; timeline clips repointed: {n}')

    # 3. Sync-clip alignment
    if not args.no_align:
        fixed = off = 0
        for sc in root.iter('sync-clip'):
            inner = next((c for c in sc if c.tag in ('asset-clip', 'ref-clip')), None)
            if inner is not None and sc.get('start') != inner.get('offset'):
                if abs(t(sc.get('start')) - t(inner.get('offset'))) * 24 >= Fraction(1, 2):
                    off += 1
                sc.set('start', inner.get('offset'))
                fixed += 1
        print(f'sync-clips aligned: {fixed} ({off} were showing a blank frame)')

    ET.indent(tree, space='  ')
    tree.write(dst, encoding='UTF-8', xml_declaration=True)
    print(f'wrote {dst}')

    if not args.no_validate:
        dtd = find_dtd(root.get('version', '1.10'))
        if not dtd or not shutil.which('xmllint'):
            print('validation skipped (Final Cut Pro DTD or xmllint not found)')
        else:
            with tempfile.TemporaryDirectory() as tmp:   # xmllint chokes on spaces in the app path
                local = os.path.join(tmp, 'fcpxml.dtd')
                shutil.copy(dtd, local)
                r = subprocess.run(['xmllint', '--noout', '--dtdvalid', local, dst],
                                   capture_output=True, text=True)
            print('DTD validation: ' + ('OK' if r.returncode == 0 else 'FAILED\n' + r.stderr[-2000:]))
            if r.returncode:
                sys.exit(1)


if __name__ == '__main__':
    main()
