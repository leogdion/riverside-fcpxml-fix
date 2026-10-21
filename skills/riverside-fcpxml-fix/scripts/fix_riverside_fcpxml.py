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
  5. Add name-tag lower thirds (--lower-third). Riverside's export drops them.
     Each is a Basic Title (bold name, subtitle at 80% opacity) in its own
     connected storyline with a Cross Dissolve at the head and the tail.
  6. Swap a Riverside video for the participant's local recording
     (--local-video), shifting every cut so the edit is unchanged.
  7. Master the speakers' enhanced tracks (--loudness): FCP plays Riverside's
     mono wavs at -6 dB per channel, so the mix lands around -19 LUFS. Writes
     stereo copies with one gain and one limiter shared by all speakers
     (computed on their sum, so cross-talk can't clip) and repoints the assets.
  8. Turn slow volume fades into 2-frame steps. Riverside mutes with a 0 dB ->
     -96 dB keyframe pair but often omits the hold keyframe before it, so FCP
     fades the voice over seconds, mid-sentence (--keep-volume-ramps to skip).

Usage:
  fix_riverside_fcpxml.py exportedTimeline.fcpxml [-o out.fcpxml]
      [--green NAME ...] [--no-green] [--background NAME]
      [--keep-formats] [--no-align] [--no-validate]
      [--lower-third "Name|subtitle|start|end|left|right" ...]
      [--local-video "ID=PATH@OFFSET"] [--loudness LUFS]
"""
import argparse, glob, os, shutil, subprocess, sys, tempfile, wave
from pathlib import Path
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from urllib.parse import unquote, urlparse


def t(s):
    return Fraction(s[:-1]) if s else Fraction(0)


def ts(x):
    """Fraction of seconds -> FCPXML time."""
    x = Fraction(x)
    return '0s' if x == 0 else f'{x.numerator}s' if x.denominator == 1 else f'{x.numerator}/{x.denominator}s'


def media_path(xml_dir, src):
    if src.startswith('file:'):
        src = unquote(urlparse(src).path)
    return src if os.path.isabs(src) else os.path.join(xml_dir, src)


def probe(path):
    """(width, height, frameDuration) of the first video stream, or None."""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
             'stream=width,height,r_frame_rate,avg_frame_rate', '-of', 'csv=p=0', path],
            capture_output=True, text=True, check=True).stdout.strip()
        w, h, rate, avg = out.split(',')[:4]
        num, den = rate.split('/')
        if int(num) >= 1000 * int(den):   # VFR reports the timebase (e.g. 90000/1); use the average
            num, den = avg.split('/')
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


BASIC_TITLE = '.../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti'
CROSS_DISSOLVE = 'FxPlug:4731E73A-8DAC-4113-9A30-AE85B1761265'


def add_lower_thirds(root, res, seq, formats, new_id, specs, fade='1/2', font='SF Pro Display'):
    """Riverside-style name tags: Basic Title in a connected storyline with
    Cross Dissolves, so the fade is an ordinary FCP transition."""
    fmt = formats[seq.get('format')]
    fd = t(fmt.get('frameDuration', '1/24s'))
    w, h = int(fmt.get('width')), int(fmt.get('height'))
    frames = lambda secs: round(Fraction(secs) / fd)            # snap to the sequence's frames
    ts = lambda n: f'{n * fd.numerator}/{fd.denominator}s' if n else '0s'
    gap = seq.find('spine/gap')
    base = max((int(c.get('lane', 0)) for c in gap), default=0) + 1
    busy = {}   # lane -> [(a, b)], so overlapping tags get their own lane
    title_id, dissolve_id = new_id(), new_id()
    ET.SubElement(res, 'effect', id=title_id, name='Basic Title', uid=BASIC_TITLE)
    ET.SubElement(res, 'effect', id=dissolve_id, name='Cross Dissolve', uid=CROSS_DISSOLVE)
    # Matched to the Riverside render (EAS-214, checked in a 4K FCP render): name
    # 3.2% of frame height, subtitle 2.1%, block centre ~89% down, outer edge 3.4% in.
    # adjust-transform position is in percent of frame height, origin at centre.
    x = 50 * w / h - 3.4 * w / h
    y = -37.8
    fade_n = frames(fade)
    for k, spec in enumerate(specs):
        name, sub, start, end, side = spec.split('|')
        a, b = frames(start), frames(end)
        lane = next(l for l in range(base, base + len(specs))
                    if all(b <= x or a >= y for x, y in busy.get(l, [])))
        busy.setdefault(lane, []).append((a, b))
        local = a - frames(t(gap.get('offset', '0s')) - t(gap.get('start', '0s')))
        # Anchored items must precede the gap's markers (DTD)
        at = next((i for i, c in enumerate(gap) if 'marker' in c.tag or c.tag in ('rating', 'keyword', 'metadata')), len(gap))
        sp = ET.Element('spine', lane=str(lane), offset=ts(local), name=f'Lower Third: {name}')
        gap.insert(at, sp)
        tr = ET.SubElement(sp, 'transition', name='Cross Dissolve', offset='0s', duration=ts(fade_n))
        ET.SubElement(tr, 'filter-video', ref=dissolve_id, name='Cross Dissolve')
        ti = ET.SubElement(sp, 'title', ref=title_id, offset='0s', name=f'{name} - Lower Third',
                           start='3600s', duration=ts(b - a))
        text = ET.SubElement(ti, 'text')
        ET.SubElement(text, 'text-style', ref=f'lt{k}n').text = name
        ET.SubElement(text, 'text-style', ref=f'lt{k}s').text = '\n' + sub
        common = dict(font=font, alignment=side, shadowColor='0 0 0 0.6',
                      shadowOffset='4 315', shadowBlurRadius='6')
        ET.SubElement(ET.SubElement(ti, 'text-style-def', id=f'lt{k}n'), 'text-style',
                      fontSize=str(round(h * 0.032)), fontFace='Bold', fontColor='1 1 1 1', **common)
        ET.SubElement(ET.SubElement(ti, 'text-style-def', id=f'lt{k}s'), 'text-style',
                      fontSize=str(round(h * 0.021)), fontFace='Regular', fontColor='1 1 1 0.8', **common)
        ET.SubElement(ti, 'adjust-transform', position=f'{-x if side == "left" else x:.4f} {y}')
        tr = ET.SubElement(sp, 'transition', name='Cross Dissolve', offset=ts(b - a - fade_n),
                           duration=ts(fade_n))
        ET.SubElement(tr, 'filter-video', ref=dissolve_id, name='Cross Dissolve')
        print(f'lower third: {name} ({side}) {float(a * fd):.3f}-{float(b * fd):.3f}s, lane {lane}')


def auto_lower_thirds(seq, host, guests, delay=Fraction(1, 2), hold=5, min_len=2, merge_gap=Fraction(5, 2),
                      min_tag=Fraction(3, 2)):
    """EAS name-tag rules, from the cuts: the host's first solo shot, each guest's
    first solo shot, the first shot with everyone, and the last shot with everyone
    through to the end. Host bottom-left, guests bottom-right.
    A tag never shows while its person is off screen: it ends 1/4 s before they
    leave the shot, tags are only merged across time they are on screen, and a
    tag cut shorter than min_tag is dropped.
    host / guests: (name, subtitle, recording-id substring)."""
    gap = seq.find('spine/gap')
    people = [host] + guests
    who = lambda sc: next((p for p in people if p[2] in (sc.get('name') or '')), None)
    clips = [(t(sc.get('offset')), t(sc.get('offset')) + t(sc.get('duration')), who(sc))
             for sc in gap.findall('sync-clip')]
    unknown = {sc.get('name') for sc in gap.findall('sync-clip') if who(sc) is None}
    if unknown:
        sys.exit(f'auto lower thirds: no --host/--guest id matches {sorted(unknown)}')
    end = t(gap.get('duration'))
    cuts = sorted({0, end} | {x for a, b, _ in clips for x in (a, b)})
    segs = []                                   # (start, end, frozenset of people on screen)
    for a, b in zip(cuts, cuts[1:]):
        on = frozenset(p for x, y, p in clips if x <= a < y)
        if segs and segs[-1][2] == on:
            segs[-1] = (segs[-1][0], b, on)
        else:
            segs.append((a, b, on))
    everyone = frozenset(people)
    long_enough = [sg for sg in segs if sg[1] - sg[0] >= min_len]
    tags = []                                   # (person, start, end)

    def first(cond, label):
        sg = next((sg for sg in long_enough if cond(sg[2])), None)
        if sg is None:
            print(f'  auto lower thirds: no shot for "{label}"')
        return sg

    def leaves(person, a):
        """When the person is next off screen at or after a (end of the timeline if never)."""
        return next((sg[0] for sg in segs if sg[1] > a and person not in sg[2]), end)

    def tag(person, sg, to_end=False):
        a = sg[0] + delay
        b = min(end if to_end else min(a + hold, sg[1] - Fraction(1, 4)),
                leaves(person, a) - Fraction(1, 4))
        if b - a < min_tag:
            print(f'  auto lower thirds: {person[0]} leaves the shot at {float(b + Fraction(1, 4)):.3f}s; '
                  f'tag at {float(a):.3f}s dropped')
            return
        tags.append((person, a, b))

    for p in people:
        sg = first(lambda on, p=p: on == {p}, f'{p[0]} solo')
        if sg:
            tag(p, sg)
    sg = first(lambda on: on == everyone, 'everyone')
    if sg:
        for p in people:
            tag(p, sg)
    last = next((sg for sg in reversed(long_enough) if sg[2] == everyone), None)
    if last:
        for p in people:
            tag(p, last, to_end=True)
    # Merge a person's tags that (nearly) touch, e.g. host solo straight into the first two-shot
    tags.sort(key=lambda x: (people.index(x[0]), x[1]))
    merged = []
    for p, a, b in tags:
        if (merged and merged[-1][0] == p and a - merged[-1][2] <= merge_gap
                and leaves(p, merged[-1][2]) >= a):
            merged[-1] = (p, merged[-1][1], max(b, merged[-1][2]))
        else:
            merged.append((p, a, b))
    return [f'{p[0]}|{p[1]}|{a}|{b}|{"left" if p is host else "right"}' for p, a, b in merged]


def ffprobe_value(path, stream, entry):
    return subprocess.run(['ffprobe', '-v', 'error', '-select_streams', stream, '-show_entries', entry,
                           '-of', 'csv=p=0', path], capture_output=True, text=True).stdout.strip()


def use_local_video(root, asset, path, shift, format_for):
    """Point a Riverside video asset at the participant's local recording, where
    local time = Riverside time + shift. Every clip of the asset gets shift added
    to its start, its own keyframes and its anchored children (the nested wavs),
    so each cut shows the same moment and the audio stays where it was."""
    info = probe(path)
    if not info:
        sys.exit(f'--local-video: cannot read {path}')
    dur = Fraction(ffprobe_value(path, 'v:0', 'format=duration'))
    used = max((t(c.get('start')) + t(c.get('duration')) for c in root.iter('asset-clip')
                if c.get('ref') == asset.get('id')), default=0)
    if used + shift > dur:
        sys.exit(f'--local-video: the cuts need {float(used + shift):.2f}s of {path} but it is {float(dur):.2f}s')
    old_name = asset.get('name')
    asset.set('name', os.path.basename(path))
    asset.set('duration', ts(dur))
    asset.set('format', format_for(*info))
    channels = ffprobe_value(path, 'a:0', 'stream=channels')
    rate = ffprobe_value(path, 'a:0', 'stream=sample_rate')
    if channels:
        asset.set('hasAudio', '1'); asset.set('audioSources', '1')
        asset.set('audioChannels', channels); asset.set('audioRate', rate)
    else:
        asset.set('hasAudio', '0')
        for k in ('audioSources', 'audioChannels', 'audioRate'):
            asset.attrib.pop(k, None)
    asset.attrib.pop('uid', None)
    asset.find('media-rep').set('src', Path(path).resolve().as_uri())
    # FCP starts the file's time at its latest-starting stream, while ffmpeg (and the
    # frame match that measured shift) uses the video pts. EAS-215's Opal .mov: audio
    # starts at 0.3086s and the export showed the picture 0.32-0.34s early until this.
    starts = [Fraction(s) for s in subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'stream=start_time', '-of', 'csv=p=0', path],
        capture_output=True, text=True).stdout.split() if s not in ('', 'N/A')]
    lead = max(starts, default=0) - Fraction(ffprobe_value(path, 'v:0', 'stream=start_time') or 0)
    if lead:
        print(f'local video: streams start {float(lead):.4f}s after the video; FCP time = video pts - that')
        shift -= lead
    n = 0
    for clip in root.iter('asset-clip'):
        if clip.get('ref') != asset.get('id'):
            continue
        clip.set('start', ts(t(clip.get('start')) + shift))
        if clip.get('name') == old_name:
            clip.set('name', asset.get('name'))
        for child in clip:
            if child.tag.startswith('adjust-'):
                for kf in child.iter('keyframe'):
                    kf.set('time', ts(t(kf.get('time')) + shift))
            elif child.get('offset') is not None:      # anchored items and markers live in the clip's local time
                child.set('offset', ts(t(child.get('offset')) + shift))
            elif 'marker' in child.tag:
                child.set('start', ts(t(child.get('start')) + shift))
        n += 1
    print(f'local video: {path} replaces {asset.get("id")} in {n} clips (shift {float(shift):+.4f}s)')


def master_audio(root, project_seq, assets, xml_dir, src_of, target, ceiling_db=-1.5, block=240, reach=12):
    """Loudness-master the enhanced tracks for FCP. Writes <name>-master.wav
    (stereo, 24-bit) next to each one and repoints the asset.
    All tracks share one gain and one limiter envelope, computed on their sum
    as it plays on the timeline (each speaker's offset to the others is read from
    the overlapping cuts), so no combination of the tracks can pass the ceiling."""
    import numpy as np
    enh = [a for a in assets.values() if (a.get('name') or '').endswith('-enhanced.wav')
           and os.path.exists(src_of(a) or '')]
    if not enh:
        print('loudness: no enhanced tracks found'); return
    gap = project_seq.find('spine/gap')
    # timeline -> source offset of each speaker's enhanced audio, per cut
    spans = []
    for sc in gap.findall('sync-clip'):
        ic = next((c for c in sc if c.tag in ('asset-clip', 'ref-clip')), None)
        au = next((c for c in (ic.iter('asset-clip') if ic is not None else [])
                   if c.get('ref') in {a.get('id') for a in enh}), None)
        if au is None:
            continue
        k = (t(sc.get('start')) - t(sc.get('offset')) + t(ic.get('start')) - t(ic.get('offset'))
             + t(au.get('start')) - t(au.get('offset')))
        a0 = t(sc.get('offset'))
        spans.append((a0, a0 + t(sc.get('duration')), au.get('ref'), k))
    ref = enh[0].get('id')
    delta = {ref: Fraction(0)}
    for a in enh[1:]:
        votes = Counter()
        for x0, x1, r1, k1 in spans:
            if r1 != a.get('id'):
                continue
            for y0, y1, r2, k2 in spans:
                if r2 == ref and y0 < x1 and x0 < y1:
                    votes[k1 - k2] += min(x1, y1) - max(x0, y0)
        if votes:
            d, w = votes.most_common(1)[0]
            share = w / sum(votes.values())
            delta[a.get('id')] = d
            print(f'loudness: {a.get("name")} plays {float(d) * 1000:+.1f} ms vs {enh[0].get("name")} '
                  f'({share:.0%} of overlapping time)')
            if share < 0.9:
                print('  warning: offset not constant; the shared limiter may let some cross-talk peaks through')
        else:
            delta[a.get('id')] = Fraction(0)

    tracks = []
    for a in enh:
        with wave.open(src_of(a)) as w:
            if w.getsampwidth() != 2:
                sys.exit(f'loudness: {a.get("name")} is not 16-bit')
            sr, nch = w.getframerate(), w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
        if nch > 1:
            x = x.reshape(-1, nch).mean(1)
        tracks.append((a, x, round(delta[a.get('id')] * sr)))
    # common domain u: a track's sample s sits at u = s - d
    lo = min(-d for _, _, d in tracks)
    n = max(len(x) - d for _, x, d in tracks) - lo
    nb = -(-n // block)

    def on_u(x, d):
        y = np.zeros(nb * block, np.float32)
        y[-d - lo:-d - lo + len(x)] = x
        return y

    peak = np.zeros(nb, np.float32)            # per block: worst of the sum and each track alone
    total = np.zeros(nb * block, np.float32)
    for _, x, d in tracks:
        y = on_u(x, d)
        total += y
        peak = np.maximum(peak, np.abs(y).reshape(nb, block).max(1))
    peak = np.maximum(peak, np.abs(total).reshape(nb, block).max(1))
    ceiling = 10 ** (ceiling_db / 20)

    def envelope(gain):
        r = np.minimum(1, ceiling / np.maximum(peak * gain, 1e-9))
        m = r.copy()                           # sliding minimum over +-(reach+1) blocks, then a
        for s in range(1, reach + 2):          # moving average over +-reach: never above r
            m[s:] = np.minimum(m[s:], r[:-s]); m[:-s] = np.minimum(m[:-s], r[s:])
        c = np.concatenate([[0], np.cumsum(m, dtype=np.float64)])
        i = np.arange(nb)
        g = (c[np.minimum(i + reach + 1, nb)] - c[np.maximum(i - reach, 0)]) / (
            np.minimum(i + reach + 1, nb) - np.maximum(i - reach, 0))
        return g.astype(np.float32)

    def per_sample(g, a, b):
        centers = np.arange(nb) * block + block / 2
        return np.interp(np.arange(a, b), centers, g).astype(np.float32)

    def loudness(gain):
        g = envelope(gain)
        proc = subprocess.Popen(['ffmpeg', '-hide_banner', '-nostats', '-f', 'f32le', '-ar', str(sr), '-ac', '1',
                                 '-i', '-', '-af', 'ebur128=framelog=verbose', '-f', 'null', '-'],
                                stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        step = sr * 600
        for a in range(0, len(total), step):
            b = min(a + step, len(total))
            proc.stdin.write((total[a:b] * gain * per_sample(g, a, b)).tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors='replace')
        proc.wait()
        vals = [l.split()[1] for l in err.splitlines() if l.strip().startswith('I:')]
        return float(vals[-1]) + 3.01           # mono sum -> dual-mono stereo

    gain = 10 ** ((target - loudness(1.0)) / 20)
    for _ in range(2):                          # the limiter takes a little back; settle on the target
        gain *= 10 ** ((target - loudness(gain)) / 20)
    g = envelope(gain)
    print(f'loudness: gain {20 * np.log10(gain):+.1f} dB, limiter on {np.mean(g < 0.999):.1%} of the time '
          f'(max {-20 * np.log10(g.min()):.1f} dB), ceiling {ceiling_db} dBFS')
    for a, x, d in tracks:
        out = os.path.splitext(src_of(a))[0] + '-master.wav'
        with wave.open(out, 'wb') as w:
            w.setnchannels(2); w.setsampwidth(3); w.setframerate(sr)
            step = sr * 600
            for s0 in range(0, len(x), step):
                s1 = min(s0 + step, len(x))
                y = x[s0:s1] * gain * per_sample(g, s0 - d - lo, s1 - d - lo)
                q = np.clip(np.round(y * 8388607), -8388608, 8388607).astype('<i4')
                b = q.view(np.uint8).reshape(-1, 4)[:, :3]
                w.writeframes(np.repeat(b, 2, axis=0).tobytes())
        a.set('name', os.path.basename(out))
        a.set('audioChannels', '2')
        rep = a.find('media-rep')
        rep.set('src', os.path.relpath(out, xml_dir) if not os.path.isabs(rep.get('src')) and
                not rep.get('src').startswith('file:') else Path(out).as_uri())
        print(f'loudness: wrote {out}')
    print(f'loudness: expected mix {loudness(gain):.1f} LUFS (verify on the export)')


def hold_volume_steps(root, ramp=Fraction(2, 24), min_step=40):
    """Riverside mutes with a 2-frame 0 dB -> -96 dB ramp, but often leaves out the hold
    keyframe before it, so FCP interpolates across the whole gap and the voice fades out
    (or in) over seconds, mid-sentence. Hold the earlier value until `ramp` before the
    later keyframe. Returns (steps fixed, total seconds that were fading)."""
    fixed, fading = 0, Fraction(0)
    for av in root.iter('adjust-volume'):
        for anim in av.iter('keyframeAnimation'):
            kfs = list(anim)
            for i in range(len(kfs) - 1, 0, -1):
                a, b = kfs[i - 1], kfs[i]
                ta, tb = t(a.get('time')), t(b.get('time'))
                va, vb = (float(k.get('value').replace('dB', '')) for k in (a, b))
                if abs(vb - va) >= min_step and tb - ta > ramp:
                    hold = ET.Element('keyframe', time=ts(tb - ramp), value=a.get('value'))
                    anim.insert(i, hold)
                    fixed += 1
                    fading += tb - ta
    return fixed, fading


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
    ap.add_argument('--keep-volume-ramps', action='store_true',
                    help="don't turn Riverside's slow 0/-96 dB volume fades into 2-frame steps")
    ap.add_argument('--lower-third', action='append', default=[], metavar='SPEC',
                    help='"Name|subtitle|start|end|left|right": a name tag from start to end '
                         '(seconds on the timeline), bottom-left or bottom-right (repeatable)')
    ap.add_argument('--host', metavar='"Name|subtitle|ID"',
                    help='with --guest: add name tags by the EAS rules (see auto_lower_thirds); '
                         'ID is a substring of the recording id (check a frame to know who is who)')
    ap.add_argument('--guest', action='append', default=[], metavar='"Name|subtitle[|ID]"',
                    help='guest name tag; ID optional with one guest (the other recording)')
    ap.add_argument('--local-video', action='append', default=[], metavar='"ID=PATH@OFFSET"',
                    help='use a local recording for the video asset whose name contains ID; '
                         'OFFSET (seconds, e.g. 11.6 or 280/24) = local time - Riverside time, '
                         'measured by matching frames (see SKILL.md)')
    ap.add_argument('--loudness', type=float, metavar='LUFS',
                    help='master the enhanced tracks to this integrated loudness (e.g. -14); '
                         'writes <name>-master.wav files next to them')
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

    # 6. Local recordings in place of Riverside's video
    for spec in args.local_video:
        key, rest = spec.split('=', 1)
        path, shift = rest.rsplit('@', 1)
        match = [a for a in assets.values() if key in (a.get('name') or '') and a.get('hasVideo') == '1'
                 and a.get('duration') not in (None, '0s')]
        if len(match) != 1:
            sys.exit(f'--local-video: "{key}" matches {len(match)} video assets')
        use_local_video(root, match[0], path, Fraction(shift), format_for)

    videos = [a for a in assets.values()
              if a.get('hasVideo') == '1' and a.get('duration') not in (None, '0s')
              and os.path.exists(src_of(a))]
    real = {a.get('id'): probe(src_of(a)) for a in videos}

    # 2. Real resolutions + project format
    if not args.keep_formats:
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

    # 8. Volume mutes as 2-frame steps, not slow fades
    if not args.keep_volume_ramps:
        n, secs = hold_volume_steps(root)
        print(f'volume: {n} slow mute fades turned into 2-frame steps ({float(secs):.0f} s of fading)')

    # 7. Loudness (after alignment: it reads each speaker's offset from the final cuts)
    if args.loudness is not None:
        master_audio(root, project_seq, assets, xml_dir, src_of, args.loudness)

    # 5. Lower thirds
    specs = list(args.lower_third)
    if args.host:
        host = tuple(args.host.split('|'))
        guests = [tuple(g.split('|')) for g in args.guest]
        if len(guests) == 1 and len(guests[0]) == 2:
            ids = {sc.get('name') for sc in root.iter('sync-clip')} - {n for n in
                   (sc.get('name') for sc in root.iter('sync-clip')) if host[2] in (n or '')}
            if len(ids) != 1:
                sys.exit(f'--guest needs an ID; recordings: {sorted(ids)}')
            guests = [guests[0] + (ids.pop(),)]
        specs += auto_lower_thirds(project_seq, host, guests)
    if specs:
        add_lower_thirds(root, res, project_seq, formats, new_id, specs)

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
