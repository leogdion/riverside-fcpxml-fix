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
- Thumbnails: brand serif is **Cardo**; Leo wants click-worthy concepts (2–4 words of hook
  text, big face, strong contrast) rather than strict matching of past thumbnails.

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
