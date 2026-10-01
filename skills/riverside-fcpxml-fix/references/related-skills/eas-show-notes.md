---
name: eas-show-notes
description: Convert an EmpowerApps Show (BrightDigit) episode's HTML episode-description into clean, plain-text YouTube show notes — flattening links into "Text - URL" lines, preserving section order, and rendering the chapter list as plain timecode lines. Use this whenever the user pastes or uploads an episode-description HTML block (a section with class episode-description, or HTML with Guest / Related Links / Related Episodes / Chapters / Social Media sections) and asks for "YouTube show notes", "YouTube description", "show notes", or "convert this to a description". Also use when they ask to reformat, clean up, or strip the HTML from an episode description. If transcript or SRT files are also present and the chapters look approximate, defer chapter timecodes to the eas-chapter-timecodes skill.
---

# EmpowerApps Show — HTML → YouTube Show Notes

Convert the HTML `episode-description` block from a BrightDigit / EmpowerApps Show episode page into plain-text show notes ready to paste into a YouTube description.

## Input

Either pasted HTML or an uploaded `.html`/`.txt` file containing the episode description. The relevant content is usually inside `<section class="episode-description">` and contains some subset of these sections, in this order: an intro paragraph, **Guest**, **Related Links**, **Related Episodes**, **Chapters**, **Watch**, **Transcript**, **Support the Show**, **Social Media**, **Credits**.

## Output

Plain text, copy-paste ready, emitted directly in chat (not a file) unless the user asks for a file. No Markdown, no HTML, no bullet characters. YouTube descriptions are plain text — every link must appear as a literal URL on its own.

## Conversion rules

Apply these consistently:

1. **Intro paragraph** — keep as-is, first, no header.
2. **Section headers** — render the bold label (e.g. `Guest`, `Related Links`) as a plain line ending in a colon: `Guest:`. Drop the `<strong>` markup.
3. **Links** — flatten every `<a href="URL">Text</a>` into `Text - URL` on its own line. Use the visible link text, then ` - `, then the raw URL. One link per line. Never leave a link as bare text without its URL, and never leave a URL without describing text if text was present.
4. **Lists** — each `<li>` becomes its own line. No bullet characters, dashes, or numbers as list markers.
5. **Chapters** — render each chapter as `TIMECODE - Title` (e.g. `09:56 - SwiftData`). **No parentheses around the timecode** and no `#t=` anchor links — just the bare `MM:SS` (or `HH:MM:SS` for long episodes). Strip any HTML anchor wrapping.
6. **Support the Show** — keep the Patreon line as `★ Support this podcast on Patreon ★ - https://www.patreon.com/brightdigit`. Render supporter names as plain lines under a `Thanks to our monthly supporters:` label. Drop empty "Welcome new supporters:" if there are none.
7. **Watch / Transcript** — if these sections are empty placeholders in the source, omit them rather than emitting an empty header (unless the user wants placeholders kept).
8. **Social Media** — flatten to `Platform - @handle - URL` lines.
9. **Credits** — keep the music attribution text, flattening its inline links to `(URL)` form, matching the source phrasing.

Preserve the source's section ordering. Don't invent, reorder, or editorialize content.

## Chapters: verify before trusting

The HTML chapter timecodes are frequently approximate and drift several minutes from where topics actually start. **If the user also provides a transcript (`.txt`) and/or subtitle (`.srt`) file for the episode, do not blindly copy the HTML timecodes.** Use the **eas-chapter-timecodes** skill to locate the real topic-pivot timestamps, then emit those corrected values in the Chapters section. If only the HTML is present, use its timecodes as-is but mention they weren't verified against a transcript.

## Example

Input fragment:
```html
<div><strong>Guest</strong></div>
<ul><li><a href="https://x.com/Jeehut">Cihat Gündüz (@Jeehut) / X</a></li></ul>
<div><strong>Chapters</strong><br><ul>
<li>(<a href="#t=9m9s">09:09</a>) - SwiftData</li></ul></div>
```

Output fragment:
```
Guest:
Cihat Gündüz (@Jeehut) / X - https://x.com/Jeehut

Chapters:
09:09 - SwiftData
```

Keep a single blank line between sections.
