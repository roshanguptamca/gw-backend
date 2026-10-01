"""Offline authoring tool, not a web request dependency.

Install piper-tts==1.8.0 and ffmpeg. Download nl_NL-pim-medium.onnx and
its .onnx.json from rhasspy/piper-voices. Review the model card before use.
Run with a NEW bank/manifest; do not overwrite released migration assets.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
import wave
from pathlib import Path

from piper import PiperVoice, SynthesisConfig


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bank", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    voice = PiperVoice.load(str(args.model))
    clips = []
    for question in json.loads(args.bank.read_text())["questions"]:
        if question["skill"] != "listening":
            continue
        code, level = question["id"], question["level"]
        if args.output.joinpath(code + ".mp4").exists():
            raise ValueError("Refusing to overwrite an existing clip; use a new bank version.")
        with tempfile.TemporaryDirectory() as temporary:
            wav = Path(temporary) / "speech.wav"
            with wave.open(str(wav), "wb") as output:
                voice.synthesize_wav(
                    question["transcript"],
                    output,
                    syn_config=SynthesisConfig(
                        length_scale=1.12 if level in ("A1", "A2") else 1.0,
                    ),
                )
            with wave.open(str(wav)) as audio:
                duration = audio.getnframes() / audio.getframerate()
            target = Path(temporary) / "clip.mp4"
            graphics = (
                "drawbox=x=24:y=24:w=432:h=220:color=0x253958:t=fill,"
                "drawbox=x=290:y=76:w=140:h=100:color=0x3d587c:t=fill,"
                "drawbox=x=70:y=157:w=105:h=77:color=0x8470ee:t=fill,"
                "drawbox=x=94:y=76:w=58:h=79:color=0xeebc94:t=fill,"
                "drawbox=x=102:y=97:w=5:h=5:color=0x142138:t=fill,"
                "drawbox=x=138:y=97:w=5:h=5:color=0x142138:t=fill,"
                "drawbox=x=115:y=130:w=18:h=5:color=0x142138:t=fill,"
                "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                f"text='Luisteren · {level}':x=292:y=98:fontsize=17:fontcolor=white,"
                "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                "text='Oefenfragment':x=294:y=135:fontsize=12:fontcolor=white,"
                "drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:"
                "text='GuideWisey · gegenereerde oefenvideo':x=24:y=254:fontsize=11:fontcolor=white"
            )
            filters = "[0:v]" + graphics + ",fade=t=in:st=0:d=0.4[bg];"
            filters += "[1:a]showwaves=s=130x20:mode=line:colors=0xa798ff:rate=12[wave];"
            filters += "[bg][wave]overlay=292:160[v]"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=0x142138:s=480x280:r=12",
                    "-i",
                    str(wav),
                    "-filter_complex",
                    filters,
                    "-map",
                    "[v]",
                    "-map",
                    "1:a",
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
                    "40k",
                    "-shortest",
                    "-movflags",
                    "+faststart",
                    str(target),
                ],
                check=True,
            )
            content = target.read_bytes()
            args.output.joinpath(code + ".mp4").write_bytes(content)
            clips.append(
                {
                    "question": code,
                    "file": code + ".mp4",
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "duration_seconds": round(duration, 3),
                    "bytes": len(content),
                }
            )
    args.manifest.write_text(
        json.dumps(
            {
                "generator": "Piper nl_NL-pim-medium + original ffmpeg graphics",
                "voice_dataset_license": "CC0 (Pim model card)",
                "clips": clips,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
