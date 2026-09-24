---
name: riverside-fcpxml-fix
description: Fix a Riverside.fm "export timeline" FCPXML (exportedTimeline.fcpxml) for Final Cut Pro — key out a green-screen speaker with the background placed inside their clip so it follows Riverside's crop/position, remove blank/empty frames at layout switches, correct 4K media mislabeled as 1080p, and find missing media (the "-enhanced.wav" tracks). Use whenever the user has a Riverside timeline export for FCP and mentions green screen, chroma key, background replacement, blank/black/empty frames, flashes of background, 4K, missing media, or asks to "fix the Riverside timeline".
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
