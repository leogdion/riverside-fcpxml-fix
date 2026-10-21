---
name: riverside-fcpxml-fix
description: Fix a Riverside.fm "export timeline" FCPXML (exportedTimeline.fcpxml) for Final Cut Pro — key out a green-screen speaker with the background placed inside their clip so it follows Riverside's crop/position, remove blank/empty frames at layout switches, correct 4K media mislabeled as 1080p, and find missing media (the "-enhanced.wav" tracks). Also covers fixes after editing — lip-sync offsets inside the green-screen compounds, chapter markers that don't export, and using the FCPXML to map the final timeline back to each speaker's source recording. Use whenever the user has a Riverside timeline export for FCP and mentions green screen, chroma key, background replacement, blank/black/empty frames, flashes of background, 4K, missing media, lip sync / audio out of sync, missing chapters, or asks to "fix the Riverside timeline".
---

# Fix a Riverside FCPXML timeline export

Riverside's "Export timeline → Final Cut Pro" folder contains `exportedTimeline.fcpxml`
plus `<id>-video.mp4`, `<id>-audio.wav`, a background `<id>-image-converted.png` and
LUT pngs. It imports cleanly, but has these problems:

| Problem | Symptom in FCP | Cause | Fix |
|---|---|---|---|
| Blank frames | For a frame at some cuts, only the background shows (no speakers) | Each speaker cut is a `sync-clip` wrapping one `asset-clip`. Riverside computes the sync-clip `start` in the source's own timebase; for media at an odd rate (e.g. `frameDuration="799847/19194800s"` ≈ 23.998fps) it doesn't equal the inner clip's `offset`, so the sync-clip's window hangs off one end of its content | Set every `sync-clip@start` = inner clip `@offset` |
| 4K labeled as 1080p | Media/project treated as 1080p | Assets reference `FFVideoFormat1080p24` although the mp4 is 3840×2160 | New 2160p format for those assets; project sequence to the largest source size. Safe: FCPXML crop (`trim-rect`) and `position` are percentages of frame height, so Riverside's layout doesn't move |
| Green-screen background | Want the speaker keyed with the background **in their clip**, cropped/positioned with them — not the full-frame background on the main timeline | — | One compound clip (`<media>`) per green-screen recording: background still on the spine, full recording connected above it. Every timeline `asset-clip` of that recording becomes a `ref-clip` to the compound (keeping its crop/transform keyframes and nested audio). Result: one place to key, 840 cuts follow |
| Missing media | "Missing media" in FCP; speakers silent | XML references `<name>-<id>-enhanced.wav` (the audible tracks) but Riverside doesn't include them; the included `-audio.wav` clips are set to -96 dB | Download each participant's enhanced/Magic Audio track from Riverside, name it as listed, File → Relink Files |
| Lip sync off (one speaker) | A speaker's mouth lags their voice by a few frames | That participant's webcam video lags their own audio in the Riverside recording (Leo's video: 9 frames late on EAS-212, 12 on EAS-213; guests were fine). **The amount changes every episode — measure it each time** | **Not done by the script.** Edit by hand: see "After editing: lip-sync offset" below |
| Chapters missing from the export | Riverside's AI chapter markers show in FCP but the shared .mov has no chapters | Riverside attaches all chapter markers to the single top-level `<gap>`. Blading that gap in FCP copies **every** marker onto **each** piece (only the in-range ones are visible), and the markers never made it into the export (likely because they sit on gap clips; unconfirmed) | **Not done by the script.** Compute `MM:SS - Title` from the XML (marker `start` → timeline time, see below) and add chapters downstream |
| Choppy video (one speaker) | Motion stutters | Webcam delivered ~15 fps; Riverside padded to 24 fps with duplicate frames (~35 % of frames in EAS-212) | Source problem; can't be fixed in the edit. Check with `ffmpeg -vf mpdecimate` on a short window before chasing an XML bug |
| Missing name tags | Riverside's lower thirds ("Name / url" bottom-left/right) aren't in FCP | The FCPXML export has **no `<title>` elements** at all | `--host "Leo Dion|brightdigit.com|<id>" --guest "Guest Name|url"` places them by Leo's rules (below); `--lower-third "Name|subtitle|start|end|left|right"` places one by hand. Each is a Basic Title (bold name, subtitle at 80 % opacity, SF Pro Display) in its own connected storyline with 0.5 s Cross Dissolves. Measure the times on Riverside's rendered mp4 (white-pixel count in the bottom band, per frame) |
| Voices fade out mid-sentence | A speaker fades out over 1–9 s while still talking (listener complaint on EAS-214 ~38:00) | Riverside mutes with `0 dB` → `−96 dB` volume keyframes 2 frames apart, but often omits the hold keyframe before the ramp; FCP interpolates across the whole gap. Riverside's own render holds full level until the −96 key (verified on the Graham Lee episode, 63 ramps) | Script inserts the hold keyframe 2 frames before the far keyframe (`--keep-volume-ramps` to skip). 185 enhanced-track fades on the Graham Lee episode, 99 over speech |
| Quiet export | Export ~−19 LUFS, ~5 dB under YouTube | FCP plays the mono enhanced wavs at −6 dB per channel | `--loudness -14` (see below) |
| VFR 4K speaker | Black or wrong-layout frame at the first frame of that speaker's cuts | Riverside labels the VFR file e.g. `FFVideoFormat2160p26` (EAS-214: Leo's 4K webcam, avg 26.22 fps); sync-clip `start` ≠ inner `offset` | Same alignment fix. Verify by diffing a FCP render against Riverside's mp4 frame by frame (64×36 gray, mean abs diff > 25) |

## Run the script

```bash
~/.claude/skills/riverside-fcpxml-fix/scripts/fix_riverside_fcpxml.py <folder>/exportedTimeline.fcpxml
# -> <folder>/exportedTimeline-fixed.fcpxml  (never overwrites the original)
```

It prints missing media, format changes, detected green-screen recordings and background,
number of clips repointed, sync-clips aligned (and how many were actually showing a blank
frame), then validates against Final Cut Pro's own DTD
(`/Applications/Final Cut Pro*.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources/FCPXMLv1_xx.dtd`).

Options: `--lower-third SPEC` (repeatable; see table), `--green NAME` (asset-name substring; repeatable) to override green-screen
auto-detection (samples a frame at 25% and checks the frame border is mostly green),
`--background NAME`, `--no-green`, `--keep-formats`, `--no-align`, `--no-validate`,
`--local-video "ID=PATH@OFFSET"` and `--loudness LUFS` (below; `--loudness` needs numpy).
Needs `ffmpeg`/`ffprobe` (Homebrew) for resolution and green detection.

**Name tags (Leo's standard, added in FCP, not Riverside: Riverside's titles are unreliable
and never reach the XML).** `--host`/`--guest` places them from the cuts:
1. Host's first solo shot.  2. Guest's first solo shot.  3. First shot with everyone.
4. Last shot with everyone, through to the end of the video.
Shots under 2 s don't count. Each tag starts 0.5 s after the cut and holds 5 s or until the
next layout change (rule 4 runs to the end). A person's tags less than 2.5 s apart merge into
one. Host bottom-left, guest bottom-right. Pass the host's recording-id substring; the guest
is the other recording.
**A tag never shows while its person is off screen** (Leo, EAS-215: Georg's rule-4 tag ran
over the final solo shots of Leo). Every tag ends 0.25 s before its person leaves the shot,
tags merge only across time the person stays on screen, and a tag cut below 1.5 s is dropped.

**Loudness (`--loudness -14`).** FCP plays Riverside's mono `-enhanced.wav` at −6 dB per
channel in the stereo project (measured EAS-215: tracks −16.6 LUFS, mix −19.4, every clip
exactly −6.0 dB vs its source), so every export comes out ~5 dB under YouTube's −14. The
script writes `<id>-enhanced-master.wav` (stereo, 24-bit) for each speaker and repoints the
assets. All speakers share one gain and one limiter envelope computed on their sum *as it
plays on the timeline*: each speaker's offset to the others comes from the overlapping cuts
(EAS-215: Leo +41.7 ms vs Georg, 100 % constant after alignment), so cross-talk can't pass the
−1.5 dBFS ceiling, with any mute/ramp combination. Don't add a Limiter via XML: FCP's audio
effect IDs (`AudioUnit: 0x…`) aren't confirmed as FCPXML uids, and there is no mix bus.

**Local recording (`--local-video "ID=PATH@OFFSET"`).** Shows a participant's local file
instead of their Riverside video. Riverside's clip stays as the parent of the nested wavs
(`srcEnable="audio"`, crop/transform kept); the local file is anchored above it on lane 1 with
a shifted copy of the crop/transform and its audio off (`srcEnable="video"`, −96 dB, every
channel inactive), so the edit and the audio are unchanged. All three guards are needed: FCP
ignores `srcEnable` inside these sync-clips (EAS-216: Riverside's uncropped video covered the
guest in grids; the Opal camera mic played 0.9 s early as an echo). Don't re-point the parent
at the local file instead: FCP reads anchored offsets in the parent's timebase, the VFR local
file put the wavs off grid, and the speaker's voice was silently dropped in every on-screen cut. OFFSET = local time − Riverside time. Measure by **matching frames**,
not audio: decode both at `fps=100,scale=64:36,format=gray` over 60 s windows at 3–4 points
and take the shift with the lowest mean abs diff (EAS-215: 11.59–11.63 s, no drift). The
local file's own audio said 11.24 s; its A/V pairing is ~0.39 s worse than Riverside's, so
audio alignment would put the picture 9 frames late. Add any lip-sync correction on top
(EAS-215: 280/24 s = video-match + ~1.6 frames). OFFSET is in ffmpeg video-pts time; the
script converts to FCP's media time, which **starts at the latest-starting stream**: the Opal
.mov's audio starts at 0.3086 s and FCP skipped that much video, so the first export's
picture ran 0.32–0.34 s (~8 frames) ahead of the sound until the script subtracted it.
That rule isn't universal: EAS-216's Opal file has a video edit list and pre-roll frames, and
FCP showed the picture a further 0.34 s ahead; fixed by passing OFFSET 0.34 s lower (−243.84
instead of −243.50). After a swap, always check the export: motion-correlate the speaker's
solo shots against the local file in 3–4 long clips (expect +0.00 s vs the intended OFFSET),
and correct OFFSET by what you measure. Check the local file's frame rate first.
On EAS-215 the Opal C1 was itself ~15 fps (VFR, 50–75 ms frame gaps), so the swap only
improved quality (10-bit 4:2:2 HEVC vs 8-bit H.264), not choppiness.

**Identify speakers by looking at a frame from each `*-video.mp4`** before attributing any
finding to a person; IDs, clip counts and resolutions don't tell you who is who.

Before running, confirm detection with the user if unsure: extract a frame from each
`*-video.mp4` (`ffmpeg -ss 120 -i X -frames:v 1 -vf scale=640:-1 out.jpg`) and look.

## Manual steps in Final Cut Pro afterwards (tell the user)

1. If a previous import exists, delete it (or use a new library), then File → Import → XML.
2. **Add the Keyer once per compound.** Select a timeline clip of the speaker → Reveal in
   Browser (⇧F) → open the "*Name* + Background (id)" compound → drag Effects → Keying →
   Keyer onto the video (upper layer). Tune Strength / Fill Holes / Edge Distance / Spill
   Level; check with View → Matte. All cuts update.
   - Do **not** add the Keyer via XML. `<filter-video>` with uid
     `FxPlug:41122549-B8A6-470E-94DA-211294D20B62` imports, but without FCP's on-apply
     auto-sample it keys the wrong colour (it removed the black pop filter, not the green).
   - To change the background later, replace the image inside the compound.
3. Relink the missing `-enhanced.wav` files (File → Relink Files → Missing).
4. The full-frame background still sits on lane 1 of the main timeline behind the other
   speakers; delete it if not wanted.
5. When sharing, check **Share → Roles → Burn in captions = None**. FCP remembers this
   per destination, and an EAS-212 export went out with captions burnt in.

## After editing: lip-sync offset

If one speaker's picture lags their audio, shift the video *inside* their compound so every
cut follows (EAS-212 diff, `EAS-212.fcpxmld` → `EAS-212-sync.fcpxmld`):

```xml
<!-- before -->
<media id="r15" name="Leo + Background (6aad51e7)" uid="7upIruInQ6iMqxP+M0dVMg" ...>
  ... <asset-clip ref="r16" lane="1" offset="0s" name="…-video.mp4" duration="359932500/90000s" .../>
<!-- after: video starts 9 frames in, duration shortened by 9 frames -->
<media id="r15" name="Leo + Background (6aad51e7) sync" ...>          <!-- renamed, uid removed -->
  ... <asset-clip ref="r16" lane="1" offset="0s" name="…-video.mp4" start="9/24s" duration="95973/24s" .../>
```

- Export the project from FCP first (File → Export XML → `.fcpxmld`), edit `Info.fcpxml`, re-import.
- **Rename every changed `<media>` and the `<project>`, and delete their `uid` attributes.**
  Otherwise FCP matches them by UID to what's already in the library and silently keeps
  the old versions.
- Only the video `asset-clip` inside the compound changes; the audio is untouched.
- Measure the lag on every episode; don't reuse the last value (EAS-212: 9 frames, EAS-213: 12).
  What works: find speech onsets after ≥0.5 s of silence in the speaker's `-audio.wav`, then
  tile 24 mouth-cropped frames from the source video starting 6 frames before each onset
  (`ffmpeg -ss <t-6/24> -i <id>-video.mp4 -vf "crop=…,scale=240:-2,tile=8x3"`). Tile 7 is the
  onset; count tiles until the mouth opens. What doesn't: correlating mouth-area motion with
  the audio envelope. The pop filter hides the mouth, r ≈ 0.1, and the curve is too flat to trust.
- Verify in the export afterwards: map a few export times to source time by audio (FFT
  cross-correlation against the speaker's `-enhanced.wav`) and by video (frame-difference
  motion against the source video). Their difference should equal the shift you applied, and
  onset filmstrips from the export should show the mouth opening ~1–2 frames *before* the
  sound (natural). EAS-212: +333…+375 ms; EAS-213: +500 ms, mouth leads by ~2 frames → fixed.

## After editing: chapters and timeline → source mapping

- Chapter marker time on the timeline = `gap.offset + marker.start − gap.start`. After the
  gap is bladed, de-duplicate: keep each marker only from the piece whose range contains it.
- To find what source moment is at timeline time `t`: for any connected `sync-clip`/`audio`
  in a gap, `t_local = t − gap.offset + gap.start`; if `child.offset ≤ t_local < child.offset + child.duration`
  then `source = child.start + (t_local − child.offset)`. The clips inside the compounds and
  sync-clips use offset = start (identity), and every Riverside participant shares one
  recording clock, so the same source time indexes each speaker's `-audio.wav`.
- This mapping is how EAS-212 got per-word speaker labels (RMS of each speaker's raw wav in
  0.25 s windows; ~50–100× separation) and how a transcript from a different edit was
  re-timed onto the final cut. Details: [references/lessons-learned.md](references/lessons-learned.md).

## FCPXML notes (if editing by hand)

- Layout: top-level `<gap>` holds the background stills (`<video>` lane 1) and one
  `sync-clip` per cut, one lane per speaker (lane 2, 3, 4 …). Inside: the video
  `asset-clip` with `adjust-crop`/`adjust-transform` keyframes, nested audio
  `asset-clip`s (lane -1 raw at -96 dB, lane -2 enhanced) and `audio-channel-source active="0"`.
- `ref-clip` child order per DTD: timing/intrinsic params (`adjust-*`), anchored clips,
  markers, `audio-role-source`, `filter-video`, `filter-audio`, `metadata`. It cannot hold
  `audio-channel-source` — drop it and use `srcEnable="video"`.
- Anchored clip `offset` is in the parent's local time (the parent's `start`), not 0.
- Compounds referenced only inside a project don't show up in the Browser. Add an event-level
  `<ref-clip ref="<media id>"/>`, or use Reveal in Browser.
- Build the `<media>` compounds *after* repointing the timeline clips, or the compound's own
  inner clip gets repointed to itself.
- Check coverage: every frame of the gap should be covered by at least one `sync-clip`. A gap
  in coverage is a different bug from the start/offset mismatch.
