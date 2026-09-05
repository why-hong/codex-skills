#!/usr/bin/env python3
"""Install the optional local audio runtime. Network is used only during setup.

Usage: python setup_audio.py --runtime-root ABSOLUTE_DIRECTORY [--models-only]
Models total about 727 MB, plus the isolated Python environment. Keep downloaded
model attribution/license files. This setup never uploads audio or uses API keys.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

MODELS = [
    {"folder": "whisper-small", "repo": "Systran/faster-whisper-small",
     "revision": "536b0662742c02347bc0e980a01041f333bce120",
     "files": ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "README.md"]},
    {"folder": "sensevoice", "repo": "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
     "revision": "2365baeacb507f821a0c8120fcee3d484dba7a07",
     "files": ["model.int8.onnx", "tokens.txt", "README.md", "LICENSE"]},
]


def request(url):
    return urllib.request.urlopen(urllib.request.Request(
        url, headers={"User-Agent": "Codex-extract-text-audio-setup"}), timeout=60)


def file_hash(path, info):
    algorithm = hashlib.sha256() if "lfs" in info else hashlib.sha1()
    if "lfs" not in info:
        algorithm.update(("blob " + str(path.stat().st_size) + "\0").encode())
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            algorithm.update(chunk)
    return algorithm.hexdigest()


def fetch_model(root, model):
    repo, revision = model["repo"], model["revision"]
    with request(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true") as response:
        metadata = json.load(response)
    if metadata["sha"] != revision:
        raise RuntimeError(f"Unexpected model revision: {repo}")
    siblings = {item["rfilename"]: item for item in metadata["siblings"]}
    folder = root / "models" / model["folder"]
    folder.mkdir(parents=True, exist_ok=True)
    records = []
    for name in model["files"]:
        info = siblings[name]
        expected = info.get("lfs", {}).get("sha256", info["blobId"])
        target = folder / name
        if target.exists():
            if target.stat().st_size != info["size"] or file_hash(target, info) != expected:
                raise RuntimeError(f"Existing model file differs from pinned version; kept unchanged: {target}")
        else:
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}"
            temporary = target.with_name(target.name + ".part")
            print(f"Downloading {model['folder']}/{name} ({info['size'] / 1e6:.1f} MB)", flush=True)
            downloaded = 0
            progress = 0
            with request(url) as response, temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > info["size"]:
                        raise RuntimeError(f"Unexpected oversized download: {name}")
                    if downloaded - progress >= 64 * 1024 * 1024:
                        print(f"  {model['folder']}: {downloaded / 1e6:.0f} MB", flush=True)
                        progress = downloaded
            if downloaded != info["size"] or file_hash(temporary, info) != expected:
                raise RuntimeError(f"Downloaded file failed size/hash verification: {name}")
            temporary.replace(target)
        records.append({"file": name, "bytes": info["size"],
                        "hash_type": "sha256" if "lfs" in info else "git_blob_sha1", "hash": expected})
    print(f"Verified {model['folder']}", flush=True)
    return {**model, "files": records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--models-only", action="store_true", help="Dependencies are already installed")
    args = parser.parse_args()
    root = args.runtime_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    environment = root / "venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not args.models_only:
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check",
                        "faster-whisper==1.2.1", "sherpa-onnx==1.13.7"], check=True)
    if not python.is_file():
        parser.error("Runtime Python missing; run setup without --models-only")
    subprocess.run([str(python), "-c", "import faster_whisper,sherpa_onnx; print('ASR dependencies OK')"], check=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda model: fetch_model(root, model), MODELS))
    manifest = {"python": str(python), "models": records,
                "sources": ["https://github.com/SYSTRAN/faster-whisper", "https://github.com/k2-fsa/sherpa-onnx",
                            "https://github.com/FunAudioLLM/SenseVoice"],
                "note": "ASR inference runs locally; model agreement is not proof of transcript accuracy."}
    (root / "setup-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Audio runtime ready: {root}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        sys.exit(2)
