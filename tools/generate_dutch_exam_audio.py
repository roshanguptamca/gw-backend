"""Offline neural-media build. Only original public teaching scripts are sent.

Authoring dependencies: edge-tts and ffmpeg; neither is needed by the server.
All resulting files and checksums must be committed with the bank migration.
"""

import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import edge_tts


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    previous_clips = {}
    if args.manifest.exists():
        previous_clips = {clip["code"]: clip for clip in json.loads(args.manifest.read_text())["clips"]}
    scripts = {}
    for question in json.loads(args.bank.read_text())["questions"]:
        if "mediaCode" not in question:
            continue
        key = question["mediaCode"]
        script = question["transcript"]
        kind = question["mediaKind"]
        if key in scripts and scripts[key][:2] != (script, kind):
            raise ValueError(f"Inconsistent shared media: {key}")
        scripts[key] = (script, kind, question["level"])
    semaphore = asyncio.Semaphore(6)
    clips = []

    async def generate(code, script, kind, level):
        async with semaphore:
            extension = ".mp4" if kind == "video" else ".mp3"
            output = args.output / (code + extension)
            raw = args.output / (code + ".working.mp3")
            signature = hashlib.sha256(script.encode()).hexdigest()
            stamp = args.output / (code + ".script-sha256")
            previous = previous_clips.get(code)
            verified_cache = output.exists() and (
                stamp.exists()
                and stamp.read_text() == signature
                or previous is not None
                and previous["script_sha256"] == signature
                and hashlib.sha256(output.read_bytes()).hexdigest() == previous["sha256"]
            )
            if not verified_cache:
                speech = edge_tts.Communicate(
                    script, "nl-NL-ColetteNeural", rate="-10%" if level in ("A1", "A2") else "+0%"
                )
                await speech.save(str(raw))
                command = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
                if kind == "video":
                    # Original abstract explanatory illustration, not copied official footage.
                    command += [
                        "-f",
                        "lavfi",
                        "-i",
                        "color=c=0x142138:s=480x270:r=1",
                        "-i",
                        str(raw),
                        "-vf",
                        "drawbox=x=30:y=30:w=420:h=190:color=0x324870:t=fill,"
                        "drawbox=x=55:y=70:w=140:h=110:color=0x8470ee:t=fill,"
                        "drawbox=x=220:y=75:w=180:h=12:color=white:t=fill,"
                        "drawbox=x=220:y=110:w=150:h=12:color=white:t=fill,"
                        "drawbox=x=220:y=145:w=180:h=12:color=white:t=fill",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "32",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "48k",
                        "-af",
                        "loudnorm=I=-18:TP=-2:LRA=11",
                        "-shortest",
                        "-movflags",
                        "+faststart",
                    ]
                else:
                    command += [
                        "-i",
                        str(raw),
                        "-af",
                        "loudnorm=I=-18:TP=-2:LRA=11",
                        "-ar",
                        "24000",
                        "-ac",
                        "1",
                        "-b:a",
                        "48k",
                    ]
                await asyncio.to_thread(subprocess.run, command + [str(output)], check=True)
                raw.unlink()
                stamp.write_text(signature)
            result = subprocess.run([args.ffmpeg, "-hide_banner", "-i", str(output)], capture_output=True, text=True)
            import re

            match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
            if not match:
                raise RuntimeError(f"No complete audio: {output}")
            duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
            content = output.read_bytes()
            clips.append(
                {
                    "code": code,
                    "file": output.name,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "script_sha256": signature,
                    "duration_seconds": duration,
                    "bytes": len(content),
                    "mime_type": "video/mp4" if kind == "video" else "audio/mpeg",
                }
            )
            print(f"{len(clips)}/{len(scripts)}: {code}", flush=True)

    await asyncio.gather(*(generate(code, *value) for code, value in scripts.items()))
    args.manifest.write_text(
        json.dumps(
            {
                "generator": "Microsoft Edge neural Dutch synthesis (offline authoring), original scripts and illustrations",
                "voice": "nl-NL-ColetteNeural",
                "verified_on": "2026-10-04",
                "clips": sorted(clips, key=lambda item: item["code"]),
            },
            indent=2,
        )
        + "\n"
    )
    required_files = {clip["file"] for clip in clips}
    for file in args.output.iterdir():
        if file.is_file() and file.name.startswith("v3-") and file.name not in required_files:
            file.unlink()


if __name__ == "__main__":
    asyncio.run(main())
