# Lessons learned — EAS-212 (Riverside → Final Cut Pro → YouTube / Transistor)

Case study from EmpowerApps Show episode 212 (Leo Dion with Jared Sorge, September 2026,
54:12). Riverside "export timeline" → this script → edit in Final Cut Pro → 4K master for
YouTube + 1080p HEVC for Transistor. Everything below was verified on that episode unless
marked otherwise.

## Files and where they live

| Path | What |
|---|---|
| `/Volumes/Media/timeline/` | Riverside export: `exportedTimeline.fcpxml` (original), `exportedTimeline-keyed.fcpxml` (this script's output), `<id>-video.mp4`, `<id>-audio.wav`, background png, LUTs |
| `/Volumes/Media/EAS-212.fcpxmld` | Project as exported from FCP after editing (v1.14) |
| `/Volumes/Media/EAS-212-sync.fcpxmld` | Hand-fixed copy (lip sync), imported as project "EAS-212 (sync fixed)" |
| `/Volumes/Media/EAS-212/` | Riverside raw 4K recordings, Magic Clips, masters, transcripts, show notes, guest stills |

Riverside media ids for this episode: `6aad51e7…` = Leo (main), `6aad620d…` = Leo (intro
re-record), `6aad51e85f…` = Jared. The raw `riverside_<name>_raw-video-cfr_*.mp4` downloads
have the same duration/timing as the timeline `<id>-video.mp4`.

## FCPXML findings

### Lip sync (fixed by hand, not by the script)
- Leo's webcam video lagged his own audio by 9 frames (375 ms). Jared was in sync.
- Fix: inside each "Leo + Background" compound, the video `asset-clip` gets `start="9/24s"`
  and its duration shortened by 9 frames. Audio untouched. See SKILL.md for the diff.
- **Rename the changed `<media>` and `<project>` and remove their `uid`s**, or FCP matches
  them to the library copies by UID and ignores the edit.
- Verified in the export: picture now within +333…+375 ms → corrected.
- Candidate script feature: `--video-offset NAME=FRAMES` applied when building the compounds.

### Chapter markers
- Riverside puts all of its AI chapter markers on the **single top-level `<gap>`** in the
  primary storyline (20 markers on EAS-212). *Earlier notes said "connected clips" — wrong.*
- When the gap is bladed in FCP (EAS-212: at 2:18.8), each piece gets a copy of all 20
  markers; only the ones inside each piece's range are visible (3 + 17). The FCP export had 40.
- The shared .mov files had **no chapters**. Probable cause: markers on gap clips aren't
  shared (unconfirmed — test by moving one marker onto a real clip).
- Riverside's marker titles are rough ("Enchetic Coding" = "Agentic Coding") and there are
  too many. EAS-212 went from 20 to 9 chapters, recomputed from the transcript.
- Candidate script feature: warn about markers on gaps; write `chapters.txt` from them.

### Caption titles
- The original Riverside export contains **no** `<title>` elements. The ~1,981 caption
  titles in the FCP export were added in Final Cut. Not a Riverside problem.

### Choppy video
- ~35 % of Leo's frames were duplicates: webcam delivered ~15 fps, Riverside padded to 24.
  In the source; can't be fixed in the edit.

### Mapping the final timeline back to each speaker's source
- Project layout after editing: spine = transition + 2 `gap`s; each gap holds connected
  `sync-clip`s (lanes 2/3, video via `ref-clip` to the compound or `asset-clip`), muted
  `audio` elements (lanes −1/−2, −96 dB), titles and chapter markers.
- `t_local = t − gap.offset + gap.start`; for a child covering `t_local`,
  `source = child.start + (t_local − child.offset)`. Inner clips use offset = start, and all
  participants share one recording clock, so one mapping works for every speaker's wav.
- Per-speaker RMS from each raw `-audio.wav` (48 kHz mono 16-bit) in 0.25 s windows gave
  ~50–100× separation between the active and silent speaker → reliable diarization.
  Read only the needed window (`wave.setpos` + `readframes`); never load the file.

## Captions and transcripts

- Three caption sources, none usable as-is:
  - `eas-212.srt` (= `eas-212 (1).srt`): good wording but from a **longer edit** — runs to
    1:00:07 vs the 54:12 video, drifting up to ~6 min (many small pause trims, not a few cuts).
  - FCP `.itt` (transcribed from the final video): correct timing but **~11 min of speech
    missing** in short gaps, and worse proper nouns.
- What worked: word-align SRT text to ITT text (difflib, ~94 % of ITT words match), map
  SRT time → source time via matched words → video time via the FCPXML mapping above.
  Only ~10 SRT words fell outside the final cut. Re-chunk cues from speaker turns.
- Filler removal ("moderate"): um/uh/`~`, stutters/repeats, false starts, mm-hmm
  backchannels; keep meaningful "like/you know".
- Recurring mis-hearings: Empower Apps ("and Power Apps"), iOSDevUK ("iOS WK"), fastlane,
  Stewart Lynch, SwiftUI/AppKit/UIKit spacing, RevenueCat, Arborist ("arborists"),
  Baseplate, Taphouse, mise ("Mies"), Mac-assed, agentic ("energetic/engetic/enchetic"),
  Shipaton, Heartwitch, Tuist/XcodeGen, NSViewRepresentable.
- Transistor transcript format (matches EAS-211): `.txt` with CRLF line endings, first line
  `[00:00:00] `, chapter title + `---` at each chapter, paragraphs `Leo Dion (host): …` /
  `Guest Name (guest): …`, inline `[HH:MM:SS]` every minute, long turns split ~60 s.
  `.srt` with the speaker label only at speaker changes, ≤2 lines.

## Chapters (EAS rules)

- Max chapters = runtime ÷ 6 minutes (54:12 → 9). Avoid chapters under 4 minutes.
- First chapter isn't "Introduction"; last isn't "Conclusion" — merge them into the
  neighbouring topic and use that topic's name.
- Saleem-style titles: short, `&` allowed ("Licensing, Sandboxing & Subprocess").

## Exports and delivery

- **YouTube:** 4K ProRes 422 master (≈197 GB for 54 min), uploaded by Leo. No burnt-in
  captions — Share → Roles → Burn in captions = None (FCP remembers it per destination).
  Transistor must not be connected to YouTube.
- **Transistor video podcast:** one MP4/MOV (H.264/HEVC) ≤ 30 GB; delivered to Apple Podcasts
  as 1080p HLS; listeners hear this file's audio. Plan for the ~100 GB Starter limit.
  Target 1080p HEVC 8-bit ≈2.5 Mbps + AAC 256 kbps (~1.1 GB / 54 min). Compressor's HEVC
  presets are 5.8 Mbps / ~105 kbps audio — use a custom copy of "HEVC Broadband HD"; avoid
  `.m4v`. (EAS-212's file came out at AAC 148 kbps — re-encode if audio quality matters.)
- Chapters aren't embedded in either file (see above); add them in Transistor / the
  YouTube description.

## Show notes, title, thumbnail

- Transistor description: paste rich text (an HTML page with a "Copy notes" button works).
  Keep Transistor's `{{chapters}}`, `{{video}}`, `{{transcript}}`, `{{donate}}`,
  `{{supporters}}`, `{{new_supporters}}` placeholders.
- YouTube description: plain text, `Text - URL` lines, chapters as `MM:SS - Title`,
  `https://brightdigit.com/episodes/<NNN>-<title-slug>`, hashtags; stay under 5,000 chars.
- Verify every link (`curl -L` status + page title); SPA sites (Threads, Bluesky) return
  200 for missing profiles — check the title or API.
- Title: pick a funny line from the transcript, "… with Guest Name" (EAS-212: "Skynet Came
  and Automated Everything with Jared Sorge").
- Guest still: sample the raw guest video every 15 s at 480 px, contact-sheet it, refine the
  best moments at 0.5 s, then export the chosen frame at full 4K as PNG.
- Thumbnails (1280×720):
  - Brand style since ep. 207: **Cardo** serif in white with a soft drop shadow; huge stacked
    title on one side, guest face cutout on the other; small "ep. NNN" top-right; small
    "with" above the guest name.
  - As of ep. 212 Leo prefers **click-worthy** concepts over strictly matching that style:
    2–4 words of hook text (not the full title), big expressive guest face, strong contrast.
    Cardo is optional, for small brand text.
  - Past thumbnails for reference: `https://i.ytimg.com/vi/<videoId>/maxresdefault.jpg`
    (video IDs are in the Transistor feed's `podcast:contentLink`). Claude Design worked well
    for generating variations from a prompt plus the guest still.

## Related skills

`related-skills/` holds copies of the EAS skills used alongside this one
(`eas-caption-correction`, `eas-show-notes`; extracted from the `.skill` packages). Others in
the workflow: `eas-chapter-timecodes`, `riverside-4k-bulk-export`, `eas-shorts-batch-publish`.

These notes replace the episode `CLAUDE.md` that lived in `/Volumes/Media/Exports/`
(removed), with its chapter-marker explanation corrected.

## Working safely with huge media

- ProRes masters are ~200 GB; heavy analysis crashed the Mac once.
- `ffprobe` for metadata. `ffmpeg` with `nice -n 15 -threads 2`, short windows (seconds),
  input seeking (`-ss` before `-i`), low resolution, one job at a time.
- `lsof <file>` before reading something that may still be exporting (Compressor's
  `Transcode` holds it; no `moov` atom until done).
- Homebrew ffmpeg here has no `drawtext`; label contact sheets with Pillow instead.
- Never modify or delete masters/exports without asking.

## EAS-213 (Leo Dion with Stewart Lynch, October 2026, 44:26)

- Script ran cleanly: 1 green-screen recording (Leo, `6ab154cc…`), 256 cuts repointed,
  0 blank frames, no missing media. Riverside named the files by id only, so the compound
  came out as "6Ab154Cc… + Background"; renamed to "Leo + Background (6ab154cc)" by hand.
  Candidate script feature: `--name ID=Leo` or derive the name from `riverside_<name>_raw-*`.
- Leo built the background inside the compound from FCP generators (Vivid + Paper overlay)
  instead of the png, and added the Green Screen Keyer in FCP. Both carried through
  the FCPXML export and re-import.
- **Lip sync: Leo's video 12 frames (500 ms) late** (EAS-212 was 9). Stewart in sync (±1–2 f).
  Measured by onset filmstrips (mouth opened +11 and +13 frames after the sound);
  whole-recording motion/envelope correlation only leaned to +10…+11 with r ≈ 0.08.
  Fix: `start="12/24s"`, duration 72921 → 72909 frames on the video inside the compound;
  `EAS-213.fcpxmld` → `/Volumes/Media/EAS-213-sync.fcpxmld`, project "EAS-213 (sync fixed)".
  Before shortening, check no timeline `ref-clip` uses the compound's last N frames (the
  event-level browser `ref-clip` always spans the whole compound; ignore it).
- Verified in the re-export: video maps +500 ms ahead of audio in source time; mouth now
  opens ~2 frames before the sound (natural).
- Export check: 3840×2160 ProRes 422 24 fps, −18.9 LUFS integrated, true peak −1.4 dBFS
  (~5 dB under YouTube's −14), no chapter track again, no burned-in captions.
- `xmllint --dtdvalid` fails on the DTD path when it contains spaces
  ("Final Cut Pro Creator Studio.app"); copy the DTD to a path without spaces first.

## EAS-214 (Leo Dion with Tim Condon, October 2026, 46:51)

- IDs: Leo = `6ab54ab64053a41d658f991b` (3840×2160 **VFR**, avg 26.22 fps, 259 cuts),
  Tim = `6ab54ab6d74530d6896a7dab` (1920×1080 24 fps, 661 cuts). No green screen; background
  = black Color solids on lane 1; Riverside "Q" logo PNG on lane 4 (scale 0.133, top-right).
  I first mixed the two up by inferring from clip counts — always look at a frame.
- Imported as-is, the FCP render differed from Riverside's mp4 on 169 single frames, all the
  first frame of a cut where Leo's VFR clip enters: 12 fully black, the rest a wrong layout.
  The script's alignment (259 sync-clips) fixes the windows; recheck with a new render.
- Name tags: Leo 0:01.375–0:12.375 and 46:45.04–46:49.71 (bottom-left), Tim 0:07.708–0:12.0,
  0:27.167–0:29.125 and 46:45.04–46:49.33 (bottom-right). Found by counting near-white pixels
  in the bottom 20 % of Riverside's mp4, left and right halves separately, per frame.
- Leo's raw `-audio.wav` was at 0 dB alongside the enhanced track in 116 of his clips, but the
  render was **not** louder or doubled (same level vs the enhanced source as other clips,
  in FCP and in Riverside). Check a render before reporting volume flags as a problem.
- Audio sync FCP vs Riverside render: within ±1 frame; loudness within +0.4 dB median.
- Riverside left an AI note marker at 24:21 ("removed section … behind-the-scenes"), and the AI
  chapter "Conclusion and Future Directions" sat at 22:31, which is the wrong spot.
- Guest stills: Tim's camera is 1080p only; picks at 17:47 (1067.0/1067.5 s source time) look
  straight to camera. Saved in `/Volumes/Media/Exports/EAS-214-Tim-stills/`.
- Verified in a 4K ProRes render of the fixed XML (`/Volumes/Media/Exports/EAS-214.mov`):
  0 black frames (was 12), mismatching frames 169 → 65. **The remaining 65 are Riverside's fault:**
  its render switches layout one frame *after* the cut in its own XML; FCP switches on the cut.
  Audio sync and loudness are unchanged.
- First lower-third pass was ~1.6× too big (name 5.1 % / subtitle 3.3 % of height). Matched
  sizes: name 3.2 %, subtitle 2.1 % (69/45 pt in 4K), position y −37.8, x ±82.8 (% of height).

## EAS-215 (Leo Dion with Georg Tuparev, October 2026, 42:53)

- IDs: Leo = `6acf7e247e1f4913861bba38` (3840×2160 VFR, avg 16.55 fps, labeled `2160p17`),
  Georg = `6acf7e212df807b01c7a39dc` (1080p24). No green screen (Leo's teal/blue room lighting:
  pass `--no-green`). Enhanced wavs were included this time; nothing to relink.
- Alignment: 343 sync-clips, 127 showing a blank frame. First export (`/Volumes/Media/Exports/EAS-215.mov`,
  4K ProRes 422): 0 blank frames across all 549 cut points. Two layout switches one frame
  early (frames 8587, 59766) are 1-frame clips in Riverside's own XML, not a bug.
- After alignment the speakers' audio sits at a constant offset: Leo's source time = Georg's
  + 1/24 s at every overlapping moment (Riverside's original varied 29–67 ms).
- Lip sync: Leo's mouth opened 0–3 frames after his sound (avg ~1.5) — far better than
  EAS-212/213. Georg's onset picks weren't real silences; inconclusive.
- Loudness: −19.4 LUFS / −1.1 dBTP. Cause found: each mono enhanced track plays at exactly
  −6.0 dB per channel (least-squares gain vs source at 12 points). Peaks above −6.9 were
  cross-talk sums. Fixed with `--loudness -14` (gain −0.6 dB on the stereo copies, limiter
  active 1.7 % of the time, max 5.8 dB; aligned sum peak exactly −1.5 dBFS).
- Name tags: Georg's rule-4 tag ran to the end over Leo's solo shots → rule changed: tags end
  when their person leaves the shot (his now ends 42:36.1).
- Local Opal C1 recording `/Volumes/Media/OPAL/Opal-video-20261014095348.mov`: HEVC 10-bit
  4:2:2 ~12 Mbps, VFR ~16 fps (same choppiness as Riverside's copy, so it's the camera; likely
  low-light exposure). Same framing as Riverside's. Audio matched Riverside's raw wav at r=0.95
  (same mic) with offset 11.241 s; frames matched at 11.59–11.63 s; used 280/24 s.
- Export metadata carried the keyword "EAS-213" from a stale FCP share setting.
- Second export (with Opal video + `--loudness -14`): −14.1 LUFS, sample peak −1.5 dBFS,
  true peak −1.1 dBTP (as predicted); 0 blank frames; tags correct (Georg's ends 42:36).
  But Leo's picture ran 0.32–0.34 s ahead: FCP's media time for the Opal .mov starts at its
  audio stream (start_time 0.3086 s), not the video pts. Script now subtracts the latest
  stream start from the shift (11.6667 → 11.3581 s). Measured by motion correlation of the
  export's left half vs the Opal file in the 4 longest Leo clips (r ≈ 0.25, consistent).

## EAS-216 (Leo Dion with Graham Lee, recorded 2026-10-19, fixed 2026-10-21)

- IDs: Leo = `6ad61218a6593ea6114d3e0c` (3840×2160 VFR, avg ~11.8 fps, labeled `2160p12`, 563 cuts),
  Graham = `6ad6121a6141ee07e1eaece3` (1080p24, 866 cuts). No green screen auto-detected (Leo's
  room has a green curtain but the door shows). Enhanced wavs included. 296 of 563 sync-clips
  were showing a blank frame.
- Opal `/Volumes/Media/OPAL/Opal-video-20261019101414.mov` (HEVC 4K, ~11.8 fps VFR, audio
  start 0.3295 s): frames matched at −243.57…−243.68 s (4 points, no drift). Its own audio
  matched at −244.40 s (pts), so **the Opal file's audio leads its picture by ~0.8 s**. Never align it by audio.
- Riverside's Leo video lagged his audio by ~1–2 camera frames (2–4 frames at 24 fps) in onset
  filmstrips (fps=12 tiles, since the camera is ~12 fps). Used `@-5844/24` (frame match + 3 frames).
- Timeline: Graham's source time = Leo's − 4.833 s (recordings started at different times).
- Loudness `-14`: gain −0.7 dB, limiter 1.0 % of the time, max 5.7 dB.
- **Mid-sentence fades (listener complaint about EAS-214 ~38:00):** 185 enhanced-track volume
  ramps of 1–9 s (`0 dB` at clip start → `−96 dB` seconds later, hold keyframe missing), 99 over
  speech. Riverside's render (`~/Downloads/riverside_magic_episode 01_empower-apps.mp4`, mono AAC,
  same 4341.67 s timeline) holds −7 dB vs source through all 63 testable ramps and drops to −88 dB
  right after the −96 key. Script step 8 now inserts the hold 2 frames before the key (369 incl. raw tracks).
- Re-exported from Riverside after fixing smart-layout cuts: same recordings, 193 Leo cuts.
- First export: Leo silent in every on-screen cut (export −100 dB vs source; off-screen audio
  clips fine). Cause: the swap re-pointed the wavs' parent at the VFR Opal file. Rebuilt as an
  anchored overlay (see SKILL.md). Next import: Opal camera mic as an echo 0.9 s early, and
  Riverside's uncropped video over Graham in grids (FCP ignores `srcEnable` there); fixed with
  −96 dB + inactive channels on the Opal clip and the crop/transform kept on Riverside's clip.
- Opal picture ran 0.34 s ahead even with the stream-start correction (video edit list +
  pre-roll); final OFFSET −243.84. Verified in `/Volumes/Media/Exports/EAS-216.mov`: picture
  within 0.01 s in 4 solo shots, voice exact (r 0.92–0.96), no echo, −13.9 LUFS.
- True peak 0.0 dBFS at 4:33.8 only: a cut where Graham's source jumps 0.17 s breaks the
  constant speaker offset the shared limiter assumes. Nothing else above −1 dBFS.
- FCP warned "Encountered an unexpected value (format=…)" on the project sequence: the script
  named the 4K format `FFVideoFormat2160p24`; FCP's name is `FFVideoFormat3840x2160p24`. Fixed.
- Leo extended Graham's opening name tag by hand (0:36.2–1:02.4).
