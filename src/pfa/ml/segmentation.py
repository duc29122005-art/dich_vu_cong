"""Local VnCoreNLP/RDRSegmenter adapter; no downloader or raw-text diagnostics."""

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pfa.annotation import pilot_store as store
from pfa.data.official_io import IngestionBlocked, IngestionError, protect_directory, safe_path
from pfa.data.preprocessing import TRANSFORMATION_VERSION, normalize_text
from pfa.data.registry import Metadata


class SegmentationConfig(Metadata):
    backend: Literal["vncorenlp", "synthetic_fixture"] = "vncorenlp"
    model_directory: str | None = None
    version: str | None = None


class Segmenter:
    """Explicit real Java backend or internal synthetic phrase fixture, never a fallback."""

    def __init__(self, root: Path, config: SegmentationConfig):
        self.root, self.config = root, config
        self.model_directory = None
        self.java = None
        if config.backend == "synthetic_fixture":
            store.require_synthetic(root)
            if config.model_directory is not None or config.version != "synthetic-phrase-1":
                raise IngestionError("Explicit synthetic phrase fixture version required")
            self.metadata = {
                "backend": "SYNTHETIC_PHRASE_FIXTURE_NOT_VIETNAMESE_SEGMENTER",
                "version": config.version,
                "model_sha256": {},
                "normalization": TRANSFORMATION_VERSION,
            }
            return
        if not config.model_directory or not config.version or config.version.upper() == "UNKNOWN":
            raise IngestionBlocked(
                "SEGMENTER_NOT_READY: reviewed local VnCoreNLP files/version required"
            )
        self.model_directory = safe_path(Path(config.model_directory))
        names = [
            "VnCoreNLP-1.2.jar",
            "models/wordsegmenter/wordsegmenter.rdr",
            "models/wordsegmenter/wordsegmenter.dict",
        ]
        checksums = {}
        for name in names:
            path = safe_path(self.model_directory / name, self.model_directory)
            if not path.is_file():
                raise IngestionBlocked("SEGMENTER_NOT_READY: local VnCoreNLP model files missing")
            checksums[name] = store.file_checksum(path, 1024**3)
        self.java = shutil.which("java")
        if not self.java:
            raise IngestionBlocked("SEGMENTER_NOT_READY: Java runtime required for VnCoreNLP")
        try:
            result = subprocess.run(
                [self.java, "-version"], capture_output=True, timeout=20, check=False
            )
        except (OSError, subprocess.TimeoutExpired):
            raise IngestionBlocked("SEGMENTER_NOT_READY: Java runtime probe failed") from None
        if result.returncode:
            raise IngestionBlocked("SEGMENTER_NOT_READY: Java runtime probe failed")
        self.metadata = {
            "backend": "VnCoreNLP_RDRSegmenter",
            "version": config.version,
            "model_sha256": checksums,
            "normalization": TRANSFORMATION_VERSION,
            "java_runtime_output_sha256": store.digest((result.stdout + result.stderr).hex()),
            "annotators": ["wseg"],
            "heap": "512m",
        }

    def segment(self, text: str) -> str:
        text = normalize_text(text)
        if self.config.backend == "synthetic_fixture":
            store.require_synthetic(self.root)
            for phrase in (
                "thủ tục",
                "hướng dẫn",
                "hài lòng",
                "trực tuyến",
                "kết quả",
                "xử lý",
                "dịch vụ",
                "phản hồi",
            ):
                text = text.replace(phrase, phrase.replace(" ", "_"))
            return text
        directory = safe_path(self.root / "data/private/phobert_segmenter", self.root)
        store.private_directory(directory)
        # ponytail: one JVM per record; use a reviewed persistent adapter if throughput matters.
        with TemporaryDirectory(prefix=".segment-", dir=directory) as temporary:
            work = Path(temporary)
            protect_directory(work)
            source, output = work / "input.txt", work / "output.txt"
            source.write_text(text, encoding="utf-8")
            if os.name != "nt":
                source.chmod(0o600)
            try:
                result = subprocess.run(
                    [
                        self.java,
                        "-Xmx512m",
                        "-jar",
                        str(self.model_directory / "VnCoreNLP-1.2.jar"),
                        "-fin",
                        str(source),
                        "-fout",
                        str(output),
                        "-annotators",
                        "wseg",
                    ],
                    cwd=self.model_directory,
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                raise IngestionError("Local word segmentation failed; no content logged") from None
            if result.returncode or not output.is_file() or output.stat().st_size > 1024**2:
                raise IngestionError("Local word segmentation failed; no content logged")
            tokens = []
            try:
                for line in safe_path(output, work).read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    fields = line.split("\t")
                    if len(fields) < 2 or not fields[0].isdigit() or not fields[1].strip():
                        raise IngestionError("Unsupported local segmenter output format")
                    tokens.append(fields[1])
                return normalize_text(" ".join(tokens))
            except UnicodeError:
                raise IngestionError("Invalid local segmenter output encoding") from None
