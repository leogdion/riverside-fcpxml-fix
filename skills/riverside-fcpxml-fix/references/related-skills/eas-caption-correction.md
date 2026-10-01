---
name: eas-caption-correction
description: Correct terminology, proper nouns, and brand/product spellings in a video caption file (.itt iTunes Timed Text, or .vtt/.srt video captions) so they match the higher-quality audio transcript for the same episode — fixing things like mistranscribed guest names, framework names, package names, tool names, and handles, while preserving every timecode, region, and the XML structure exactly. Use this whenever the user uploads a video caption file (.itt/.vtt) alongside an audio transcript (.txt) and/or audio subtitle (.srt) file and asks to "fix the terminology", "correct the captions", "match the audio", "fix the spelling in the captions", or similar. The audio transcript/SRT is the ground truth; the video caption is what gets corrected. Derive all corrections from the provided transcript — do not invent a fixed glossary.
---

# EmpowerApps Show — Video Caption Terminology Correction

Video captions (often auto-generated, e.g. a `.itt` from a video editor) mistranscribe proper nouns — guest names, Apple frameworks, open-source package names, AI tool names, social handles, URLs. The audio podcast transcript (`.txt`) and audio subtitles (`.srt`) are produced from cleaner audio and are far more accurate. Treat them as **ground truth** and correct the video caption to match, **without touching timecodes or structure**.

## Inputs

- **Caption to fix** (required): `.itt` (TTML XML), `.vtt`, or `.srt` — the video captions.
- **Ground truth** (at least one required): `.txt` transcript and/or `.srt` audio subtitles for the same episode.

## Core principle: derive corrections, don't hardcode

Do **not** apply a fixed list of terms. Every episode has different guests and topics. Instead:

1. Extract the plain caption text from the file to fix.
2. Scan it for likely-mistranscribed proper nouns: personal names, company/brand names, product/framework names, package names, handles (`@...`), URLs, and domain-specific jargon. Auto-transcription errors cluster on exactly these — common words are usually fine.
3. For each candidate, find the corresponding passage in the ground-truth transcript/SRT (search by surrounding context words) and read the correct spelling there.
4. Build a correction map of `wrong → right` only for terms the transcript confirms.

The transcript itself is occasionally wrong on a proper noun too. When the audio `.txt` and `.srt` agree, trust them. When they conflict, or when both look phonetically wrong for a known entity (e.g. a website or handle the speaker is spelling out), prefer the spelling that matches what the speaker is literally spelling, and note the ambiguity to the user.

## Workflow

1. **Extract caption text.** For `.itt`, pull the text of each `<p>` (e.g. `grep -oP '(?<=region="bottom">).*?(?=</p>)'`, adjusting for the actual region id). For `.srt`/`.vtt`, strip indices and timecodes.
2. **Identify candidate error terms.** List proper nouns and count occurrences. Cross-check each against the ground-truth transcript.
3. **Confirm each correction** against the `.txt`/`.srt` before applying. Show the user the proposed `wrong → right` map with counts.
4. **Apply edits to a writable copy.** The uploaded file is read-only — copy it to a working dir first. Use targeted, case-aware `sed`/`str_replace` so you only change the intended tokens. Be careful with substrings (e.g. don't let a name fix corrupt a spelled-out handle — see pitfall below).
5. **Preserve structure absolutely.** Do not alter `begin`/`end` timecodes, `region`, frame rates, styling, or the number/order of cues. Only the visible text inside cues changes.
6. **Validate.** For `.itt`, confirm the XML still parses:
   `python3 -c "import xml.etree.ElementTree as ET; ET.parse('fixed.itt'); print('XML OK')"`
   Re-extract the text and verify each target term is fixed and no count went wrong.
7. **Deliver** the corrected file to `/mnt/user-data/outputs/` with the original filename, and present it. Summarize the corrections as a table (`wrong → right`, count).

## Pitfall: spelled-out handles and acronyms

Speakers often spell their handle aloud ("I'm @Jeehut, J-E-E-Hut, like Pizza Hut"). A blunt name-substitution (`Jihad → Cihat`) will wrongly rewrite the spelled-out letters. After running substitutions, **re-read any line where a person spells something** and restore the literal spelling/handle. Verify handles against the transcript's exact rendering.

## Example correction map (illustrative — derive per episode, do not reuse)

| Wrong (video caption) | Right (from audio transcript) |
|---|---|
| Jihad Gunduz / Jihad | Cihat Gündüz / Cihat |
| Cloud code / clot code | Claude Code |
| Quinn / Quinn 3.6 | Qwen / Qwen 3.6 |
| Macedon | Mastodon |
| flying.dev | FlineDev |

These are examples from one episode. Always rebuild the map from the actual transcript provided.
