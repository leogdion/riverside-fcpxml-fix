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
| Lip sync off (one speaker) | A speaker's mouth lags their voice by a few frames | That participant's webcam video lags their own audio in the Riverside recording (EAS-212: Leo's video was 9 frames / 375 ms late; the guest was fine) | **Not done by the script.** Edit by hand: see "After editing: lip-sync offset" below |
| Chapters missing from the export | Riverside's AI chapter markers show in FCP but the shared .mov has no chapters | Riverside attaches all chapter markers to the single top-level `<gap>`. Blading that gap in FCP copies **every** marker onto **each** piece (only the in-range ones are visible), and the markers never made it into the export (likely because they sit on gap clips; unconfirmed) | **Not done by the script.** Compute `MM:SS - Title` from the XML (marker `start` → timeline time, see below) and add chapters downstream |
| Choppy video (one speaker) | Motion stutters | Webcam delivered ~15 fps; Riverside padded to 24 fps with duplicate frames (~35 % of frames in EAS-212) | Source problem; can't be fixed in the edit. Check with `ffmpeg -vf mpdecimate` on a short window before chasing an XML bug |

## Run the script

```bash
~/.claude/skills/riverside-fcpxml-fix/scripts/fix_riverside_fcpxml.py <folder>/exportedTimeline.fcpxml
# -> <folder>/exportedTimeline-fixed.fcpxml  (never overwrites the original)
```

It prints missing media, format changes, detected green-screen recordings and background,
number of clips repointed, sync-clips aligned (and how many were actually showing a blank
frame), then validates against Final Cut Pro's own DTD
(`/Applications/Final Cut Pro*.app/Contents/Frameworks/Interchange.framework/Versions/A/Resources/FCPXMLv1_xx.dtd`).

Options: `--green NAME` (asset-name substring; repeatable) to override green-screen
auto-detection (samples a frame at 25% and checks the frame border is mostly green),
`--background NAME`, `--no-green`, `--keep-formats`, `--no-align`, `--no-validate`.
Needs `ffmpeg`/`ffprobe` (Homebrew) for resolution and green detection.

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
- Measure the lag first (short windows only, e.g. compare mouth motion with the waveform
  around a plosive), and verify in the export afterwards (EAS-212: +333 to +375 ms → fixed).

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
