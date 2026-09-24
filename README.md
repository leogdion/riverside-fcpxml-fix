# riverside-fcpxml-fix

Fixes the Final Cut Pro timeline that [Riverside.fm](https://riverside.fm) exports
(`exportedTimeline.fcpxml`). It's a standalone Python script, and it's also packaged as a
[Claude Code](https://claude.com/claude-code) skill/plugin.

## What it fixes

| Problem | What you see in FCP | Fix |
|---|---|---|
| **Blank frames** | At some cuts, one frame shows only the background (no speakers) | Riverside rounds each speaker `sync-clip`'s `start` in the source's timebase. For odd-rate media (≈23.998 fps) that's off from the clip inside it by up to a frame. The script aligns them. |
| **4K labeled as 1080p** | 4K recordings treated as 1080p | The script declares each video at its real resolution (via `ffprobe`) and sets the project to the largest source size. Riverside's crop/position values are percentages of the frame, so the layout doesn't move. |
| **Green-screen background** | You want the green keyed out and the background *inside your clip*, cropped and positioned with you | The script builds one compound clip per green-screen recording (background image + recording) and points every cut at it. You key it **once** per compound, and every cut follows. |
| **Missing media** | "Missing media" warning; speakers silent | The XML references `*-enhanced.wav` tracks that Riverside doesn't include. The script lists them so you can download and relink them. |

## Requirements

- macOS with Final Cut Pro (its DTD is used to validate the output)
- Python 3.9+
- `ffmpeg` / `ffprobe` (`brew install ffmpeg`)

## Usage

```bash
skills/riverside-fcpxml-fix/scripts/fix_riverside_fcpxml.py /path/to/export/exportedTimeline.fcpxml
```

This writes `exportedTimeline-fixed.fcpxml` next to the input and leaves the original alone.
Example output:

```
missing media: 3
  MISSING  leo_dion-3cdbe7e3-a26e-49dd-bed0-1-enhanced.wav
  ...
format: 6aad51e7c0b76179546cd9a3-video.mp4 declared 1920x1080 -> actual 3840x2160
project: 1920x1080 -> 3840x2160
green-screen videos: 6aad51e7c0b76179546cd9a3-video.mp4, 6aad620d7d14db86cb3a8d86-video.mp4
background: 6554f04d55b6ff946c2b6c7e-image-converted.png
compounds: 2; timeline clips repointed: 840
sync-clips aligned: 972 (237 were showing a blank frame)
DTD validation: OK
```

| Option | |
|---|---|
| `-o FILE` | Output path |
| `--green NAME` | Asset-name substring of a green-screen video (repeatable). Overrides auto-detection, which samples a frame and checks the border is mostly green. |
| `--background NAME` | Asset-name substring of the background image (default: the still Riverside uses most) |
| `--no-green` | Skip the background compounds |
| `--keep-formats` | Don't change resolutions or the project format |
| `--no-align` | Don't fix sync-clip starts |
| `--no-validate` | Skip DTD validation |

### Then, in Final Cut Pro

1. Delete the previous import (if there is one), then **File → Import → XML** the fixed file.
2. **Add the Keyer once per compound.** Select one of your clips, choose **Reveal in Browser** (⇧F), open
   the *Name + Background* compound, and drag **Effects → Keying → Keyer** onto the video
   (the upper layer). Tune it and check with **View → Matte**. Every cut updates.
3. **File → Relink Files → Missing** to point FCP at the enhanced audio you downloaded from Riverside.

> Why isn't the Keyer added by the script? A Keyer added through XML
> (`FxPlug:41122549-B8A6-470E-94DA-211294D20B62`) doesn't auto-sample the screen color
> like it does when dragged on in FCP. It ends up keying out the wrong thing (dark areas, not the green).

## Install as a Claude Code plugin

```
/plugin marketplace add <your-github-user>/riverside-fcpxml-fix
/plugin install riverside-fcpxml-fix@riverside-fcpxml-fix
```

Or link the skill directly:

```bash
ln -s "$PWD/skills/riverside-fcpxml-fix" ~/.claude/skills/riverside-fcpxml-fix
```

Then ask Claude to "fix this Riverside timeline". [`SKILL.md`](skills/riverside-fcpxml-fix/SKILL.md)
has the full technical notes on the FCPXML structure and the pitfalls found along the way.

## License

MIT
