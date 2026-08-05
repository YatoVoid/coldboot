"""Listen to voices on your own script, then pick one.

    python voices.py               what is available and what you use now
    python voices.py --try         download them all and render a sample of each
    python voices.py --try en_US-lessac-high en_GB-cori-high
    python voices.py --set en_US-lessac-high
    python voices.py --demo

Samples land in out/voices/. Play them, pick one, set it.
"""
import json, subprocess, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
CONFIG = ROOT / "config.json"
PIPER_DIR = ROOT / "assets" / "piper"
SAMPLES = ROOT / "out" / "voices"
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# a shortlist that suits narration. there are hundreds more at the link above,
# most are worse for this or are not english.
CHOICES = [
    ("en_US-lessac-high", "US male, warm and even. the easiest to listen to for 8 minutes"),
    ("en_US-hfc_female-medium", "US female, conversational, least announcer-like"),
    ("en_US-hfc_male-medium", "US male, conversational and relaxed"),
    ("en_GB-cori-high", "UK female, measured and calm"),
    ("en_GB-alan-medium", "UK male, quiet and dry"),
    ("en_US-ryan-high", "US male, clipped news read. the old default"),
    ("en_US-amy-medium", "US female, brighter and quicker"),
    ("en_US-joe-medium", "US male, deeper and slower"),
    ("en_GB-northern_english_male-medium", "UK northern male, distinctive"),
    ("en_US-kusal-medium", "US male, softer edges"),
]

SAMPLE = ("Researchers released the model weights this week, and the interesting "
          "part is not the benchmark score. It is that the whole thing runs on a "
          "single card. That changes who gets to experiment with this, which "
          "matters more than another point of accuracy.")


def cfg():
    return json.loads(CONFIG.read_text(encoding="utf-8-sig"))


def voice_url(name):
    """en_US-lessac-high -> en/en_US/lessac/high/en_US-lessac-high.onnx"""
    lang, speaker, quality = name.split("-", 2)
    return f"{BASE}/{lang.split('_')[0]}/{lang}/{speaker}/{quality}/{name}.onnx"


def have(name):
    return (PIPER_DIR / f"{name}.onnx").exists()


def download(name):
    if have(name):
        return True
    url = voice_url(name)
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for ext in ("", ".json"):
            dest = PIPER_DIR / f"{name}.onnx{ext}"
            if not dest.exists():
                urllib.request.urlretrieve(url + ext, dest)
        return True
    except Exception as e:
        print(f"      could not fetch {name}: {type(e).__name__}")
        for ext in ("", ".json"):
            (PIPER_DIR / f"{name}.onnx{ext}").unlink(missing_ok=True)
        return False


def sample_text():
    """Prefer a real script, so you judge the voice on your own writing."""
    for folder in (ROOT / "out", ROOT / "out" / "uploaded"):
        for txt in sorted(folder.glob("*.txt")):
            words = txt.read_text(encoding="utf-8").split()
            if len(words) > 80:
                return " ".join(words[:70])
    return SAMPLE


def speak(name, text, wav):
    import os
    exe = PIPER_DIR / ("piper.exe" if sys.platform == "win32" else "piper")
    if not exe.exists():
        sys.exit("Piper is not installed. Run setup first.")
    env = None
    if sys.platform != "win32":
        env = dict(os.environ, LD_LIBRARY_PATH=str(PIPER_DIR),
                   DYLD_LIBRARY_PATH=str(PIPER_DIR))
    c = cfg()
    r = subprocess.run(
        [str(exe), "-m", str(PIPER_DIR / f"{name}.onnx"), "-f", str(wav),
         "--sentence-silence", str(c.get("sentence_silence", 0.4)),
         "--length-scale", str(c.get("speech_rate", 1.0))],
        input=text.encode("utf-8"), capture_output=True, env=env)
    return r.returncode == 0 and wav.exists()


def try_voices(names):
    SAMPLES.mkdir(parents=True, exist_ok=True)
    text = sample_text()
    print(f"\nreading {len(text.split())} words of your own script in each voice\n")
    made = []
    for name in names:
        print(f"  {name}", flush=True)
        if not download(name):
            continue
        wav = SAMPLES / f"{name}.wav"
        if speak(name, text, wav):
            made.append(wav)
        else:
            print(f"      failed to render")
    print(f"\n{len(made)} samples in {SAMPLES}")
    print("play them, then set the one you like:")
    print(f"  python voices.py --set {names[0]}\n")


def set_voice(name):
    if not download(name):
        sys.exit(f"could not download {name}")
    c = cfg()
    c["piper_voice"] = name
    CONFIG.write_text(json.dumps(c, indent=2) + "\n", encoding="utf-8")
    print(f"voice set to {name}")
    print("this affects new videos. existing ones keep the voice they were made with.")


def demo():
    assert voice_url("en_US-lessac-high").endswith(
        "/en/en_US/lessac/high/en_US-lessac-high.onnx")
    assert voice_url("en_GB-northern_english_male-medium").endswith(
        "/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx")
    assert "hfc_female" in voice_url("en_US-hfc_female-medium")
    print("demo ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--demo" in a:
        demo()
    elif "--set" in a:
        set_voice(a[a.index("--set") + 1])
    elif "--try" in a:
        picked = [x for x in a[a.index("--try") + 1:] if not x.startswith("-")]
        try_voices(picked or [n for n, _ in CHOICES])
    else:
        current = cfg().get("piper_voice")
        print(f"\nusing: {current}\n")
        for name, desc in CHOICES:
            mark = "installed" if have(name) else ""
            star = ">" if name == current else " "
            print(f" {star} {name:<38} {desc}")
            if mark:
                print(f"   {'':38} ({mark})")
        print("\nhear them all:  python voices.py --try")
        print("pick one:       python voices.py --set en_US-lessac-high\n")
