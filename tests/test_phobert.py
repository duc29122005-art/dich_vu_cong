"""Offline SYNTHETIC random models only; no real PhoBERT weights or citizen records."""

import json
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pfa.annotation import pilot_store as store
from pfa.cli import main
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.registry import load_registry
from pfa.data.splitting import SplitConfig
from pfa.ml import baseline, phobert, phobert_smoke, segmentation
from pfa.ml.segmentation import SegmentationConfig, Segmenter

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("Network forbidden"))
    transformers.utils.logging.disable_progress_bar()


@pytest.fixture
def tiny_built(tmp_path):
    registry = load_registry(ROOT / "configs/dataset_sources.yaml")
    with store.synthetic_session(tmp_path):
        rows, provenance = corpus_smoke.fixture(48)
        corpus._publish(tmp_path, "synthetic_transformer_v1", rows, provenance, SplitConfig(), 42)
        partitions, _ = baseline.development(tmp_path, registry, "synthetic_transformer_v1")
        yield tmp_path, registry, [row.content for row in partitions["train"]]


def train_tiny(workspace, task="sentiment", epochs=1, resume=None):
    root, registry, texts = workspace
    model, tokenizer, segmenter, checkpoint = phobert_smoke.tiny(root, texts, task)
    result = phobert.fit(
        root,
        registry,
        "synthetic_transformer_v1",
        task,
        42,
        phobert_smoke.config(epochs),
        model,
        tokenizer,
        segmenter,
        checkpoint,
        resume,
    )
    return result


@pytest.fixture
def trained(tiny_built):
    return (*tiny_built, train_tiny(tiny_built))


@pytest.mark.parametrize("task", list(baseline.TASKS))
def test_heads_labels_training_loss_and_reload(tiny_built, task):
    root, registry, _ = tiny_built
    run = train_tiny(tiny_built, task)
    assert run["label2id"] == {code: i for i, code in enumerate(baseline.TASKS[task])}
    assert run["optimizer_steps"] > 0 and run["finite_backward_verified"]
    assert run["history"][0]["training_loss"] > 0
    assert run["dataset"]["dataset_type"] == "SYNTHETIC"
    assert not run["dataset"]["test_labels_read"] and run["checkpoint"]["pretrained"] is False
    result = phobert.predict(
        root,
        registry,
        run["run_id"],
        ["SYNTHETIC: hướng dẫn thủ tục chưa rõ."] * 3,
        phobert_smoke.config().segmenter,
        batch_size=2,
    )
    assert len(result["predictions"]) == 3
    assert result["score_semantics"] == "UNCALIBRATED_SOFTMAX_NOT_CONFIDENCE"
    for prediction in result["predictions"]:
        assert prediction["label"] in phobert.mapping(task)
        assert prediction["label_id"] == run["label2id"][prediction["label"]]
        assert sum(prediction["uncalibrated_softmax_scores"]) == pytest.approx(1.0)
    assert list(phobert.location(root, run["run_id"]).rglob("*.bin")) == []
    assert list(phobert.location(root, run["run_id"]).rglob("*.pkl")) == []
    if task == "severity":
        assert "unknown" not in run["label2id"]
        assert (
            sum(
                run["task_exclusions"][split].get("UNKNOWN_SEVERITY_SYNTHETIC", 0)
                for split in ("train", "validation")
            )
            > 0
        )


def test_tokenization_dynamic_padding_and_truncation(tiny_built):
    root, _, texts = tiny_built
    model, tokenizer, segmenter, _ = phobert_smoke.tiny(root, texts, "topic")
    encoded, statistics = phobert.prepare(
        ["SYNTHETIC: thủ tục", "SYNTHETIC: " + "hướng dẫn chưa rõ " * 60],
        ["other", "unclear_guidance"],
        "topic",
        tokenizer,
        segmenter,
        32,
    )
    assert statistics["truncated_records"] == 1
    assert max(map(lambda row: len(row["input_ids"]), encoded)) == 32
    assert all(row["input_ids"][0] == 0 and row["input_ids"][-1] == 2 for row in encoded)
    assert len(encoded[0]["input_ids"]) < len(encoded[1]["input_ids"])
    batch = transformers.DataCollatorWithPadding(tokenizer)(encoded)
    assert tuple(batch["input_ids"].shape) == (2, 32)
    assert batch["attention_mask"][0].sum().item() == len(encoded[0]["input_ids"])
    with pytest.raises(IngestionError):
        phobert.maximum_length(model, tokenizer, 33)
    with pytest.raises(IngestionError):
        phobert.prepare(["SYNTHETIC"], ["unknown"], "severity", tokenizer, segmenter, 32)


def test_segmenter_explicit_and_no_real_fallback(tmp_path):
    with pytest.raises(IngestionBlocked, match="SEGMENTER_NOT_READY"):
        Segmenter(tmp_path, SegmentationConfig())
    with pytest.raises(IngestionBlocked):
        Segmenter(tmp_path, phobert_smoke.config().segmenter)
    with store.synthetic_session(tmp_path):
        segmenter = Segmenter(tmp_path, phobert_smoke.config().segmenter)
        assert (
            segmenter.segment("thủ tục không rõ, chưa hài lòng")
            == "thủ_tục không rõ, chưa hài_lòng"
        )
        assert "NOT_VIETNAMESE_SEGMENTER" in segmenter.metadata["backend"]


def test_local_java_adapter_without_real_models(tmp_path, monkeypatch, capsys, caplog):
    model_dir = tmp_path / "synthetic_java_fixture"
    for name in (
        "VnCoreNLP-1.2.jar",
        "models/wordsegmenter/wordsegmenter.rdr",
        "models/wordsegmenter/wordsegmenter.dict",
    ):
        path = model_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"SYNTHETIC NONEXECUTABLE TEST FILE")
    monkeypatch.setattr(segmentation.shutil, "which", lambda *args: "java")

    def simulated_java(args, **kwargs):
        assert kwargs["capture_output"]
        if "-fout" in args:
            Path(args[args.index("-fout") + 1]).write_text(
                "1\tthủ_tục\n2\tchưa\n", encoding="utf-8"
            )
        return subprocess.CompletedProcess(args, 0, b"SYNTHETIC PRIVATE DIAGNOSTIC", b"")

    monkeypatch.setattr(segmentation.subprocess, "run", simulated_java)
    segmenter = Segmenter(
        tmp_path,
        SegmentationConfig(model_directory=str(model_dir), version="SYNTHETIC_JAVA_TEST_ONLY"),
    )
    assert segmenter.segment("SYNTHETIC input") == "thủ_tục chưa"
    assert len(segmenter.metadata["model_sha256"]) == 3
    assert not list((tmp_path / "data/private/phobert_segmenter").iterdir())
    assert not capsys.readouterr().out and not caplog.text


def test_holdout_no_deserialization(tiny_built, monkeypatch):
    original = corpus._read_partition

    def guarded(path):
        assert path.name != "test.parquet"
        return original(path)

    monkeypatch.setattr(corpus, "_read_partition", guarded)
    run = train_tiny(tiny_built)
    assert not run["dataset"]["test_labels_read"]
    with pytest.raises(IngestionBlocked):
        corpus.model_selection(tiny_built[0], tiny_built[1], "synthetic_transformer_v1", "test")


def test_resume_exact_and_deterministic_seed(tiny_built):
    from safetensors.torch import load_file

    root, registry, _ = tiny_built
    first = train_tiny(tiny_built)
    repeat = train_tiny(tiny_built)
    assert first["history"][0]["validation"] == repeat["history"][0]["validation"]
    assert first["history"][0]["training_loss"] == repeat["history"][0]["training_loss"]
    resumed = train_tiny(tiny_built, epochs=2, resume=first["run_id"])
    full = train_tiny(tiny_built, epochs=2)
    assert resumed["previous_run"] == first["run_id"]
    left = load_file(phobert.location(root, resumed["run_id"]) / "resume/model.safetensors")
    right = load_file(phobert.location(root, full["run_id"]) / "resume/model.safetensors")
    assert all(torch.equal(value, right[name]) for name, value in left.items())
    assert phobert.inspect(root, registry, first["run_id"])["completed_epochs"] == 1


def test_resume_rejects_changed_configuration(trained):
    root, registry, texts, run = trained
    model, tokenizer, segmenter, checkpoint = phobert_smoke.tiny(root, texts, "sentiment")
    config = phobert_smoke.config(2).model_copy(update={"learning_rate": 0.002})
    with pytest.raises(IngestionError, match="Resume"):
        phobert.fit(
            root,
            registry,
            "synthetic_transformer_v1",
            "sentiment",
            42,
            config,
            model,
            tokenizer,
            segmenter,
            checkpoint,
            run["run_id"],
        )


@pytest.mark.parametrize(
    "name", ["best/model.safetensors", "tokenizer/tokenizer.json", "optimizer.safetensors"]
)
def test_artifact_corruption_before_model_load(trained, monkeypatch, name):
    root, registry, _, run = trained
    (phobert.location(root, run["run_id"]) / name).write_bytes(b"SYNTHETIC CORRUPTION")
    monkeypatch.setattr(
        transformers.RobertaForSequenceClassification,
        "from_pretrained",
        lambda *args, **kwargs: pytest.fail("Corrupted model loaded"),
    )
    with pytest.raises(IngestionError, match="checksum"):
        phobert.load(root, registry, run["run_id"], phobert_smoke.config().segmenter)


def test_rehashed_wrong_labels_rejected(trained):
    root, registry, _, run = trained
    path = phobert.location(root, run["run_id"])
    config = json.loads((path / "best/config.json").read_text())
    config["label2id"] = {"wrong": 0}
    (path / "best/config.json").write_text(json.dumps(config))
    (path / "checksums.json").write_text(json.dumps(phobert.inventory(path)))
    with pytest.raises(IngestionError, match="labels"):
        phobert.inspect(root, registry, run["run_id"])


def test_wrong_dataset_version_rejected(trained):
    root, registry, _, run = trained
    path = phobert.location(root, run["run_id"]) / "run.json"
    value = json.loads(path.read_text())
    value["dataset"]["manifest_sha256"] = "0" * 64
    path.write_text(json.dumps(value))
    with pytest.raises(IngestionBlocked):
        phobert.inspect(root, registry, run["run_id"])


@pytest.mark.parametrize(
    "reason", ["Permission pending", "Permission revoked", "Taxonomy not approved"]
)
def test_permission_failure_before_checkpoint_access(tiny_built, monkeypatch, reason):
    root, registry, _ = tiny_built

    def blocked(*args, **kwargs):
        raise IngestionBlocked(reason)

    monkeypatch.setattr(corpus, "_authorized_manifest", blocked)
    monkeypatch.setattr(
        phobert, "approved_checkpoint", lambda *args: pytest.fail("Checkpoint accessed")
    )
    with pytest.raises(IngestionBlocked):
        phobert.train(root, registry, "synthetic_transformer_v1", "topic")


def test_synthetic_cannot_become_research_or_escape_session(trained):
    root, registry, _, run = trained
    with pytest.raises(IngestionBlocked):
        phobert.train(root, registry, "synthetic_transformer_v1", "topic")
    with pytest.raises(IngestionBlocked):
        phobert_smoke.tiny(root / "other_root", ["SYNTHETIC"], "topic")
    path = phobert.location(root, run["run_id"]) / "run.json"
    value = json.loads(path.read_text())
    value["checkpoint"]["kind"] = "PRETRAINED_PHOBERT"
    path.write_text(json.dumps(value))
    with pytest.raises(IngestionBlocked):
        phobert.inspect(root, registry, run["run_id"])


def test_atomic_cleanup(tiny_built, monkeypatch):
    root, _, _ = tiny_built
    monkeypatch.setattr(
        phobert, "write_json", lambda *args: (_ for _ in ()).throw(OSError("Simulated"))
    )
    with pytest.raises(OSError):
        train_tiny(tiny_built)
    assert list((root / "data/private/phobert_runs").iterdir()) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"max_length": 2},
        {"learning_rate": float("nan")},
        {"batch_size": 0},
        {"gradient_accumulation": 0},
        {"epochs": 0},
        {"device": "gpu"},
        {"patience": 0},
    ],
)
def test_invalid_training_configuration(changes):
    with pytest.raises(ValueError):
        phobert.PhobertConfig(**changes)


def test_default_config_and_local_readiness_only(tmp_path):
    assert (
        phobert.PhobertConfig.model_validate(store.read_json(ROOT / "configs/phobert_v1.yaml"))
        == phobert.PhobertConfig()
    )
    result = phobert.readiness(tmp_path, phobert.PhobertConfig())
    assert result["status"] == "BLOCKED" and result["pretrained_checkpoint"] == "NOT_VERIFIED"
    assert not result["weights_downloaded"] and not result["dataset_read"]


def test_smoke_cli_and_previous_baselines(monkeypatch, capsys):
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(ROOT))
    assert main(["ml", "phobert-smoke"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "PHOBERT_SMOKE_PASS_SYNTHETIC_TINY_MODEL"
    assert result["resume_verified"] and result["temporary_storage_cleaned"]
    assert result["test_access_blocked"] and not result["test_labels_read"]
    assert not result["weights_downloaded"] and result["pretrained_checkpoint"] == "NOT_VERIFIED"
    assert set(result["tasks"]) == set(baseline.TASKS)
    assert main(["ml", "phobert-readiness"]) == 3
    assert json.loads(capsys.readouterr().out)["pretrained_checkpoint"] == "NOT_VERIFIED"
    assert main(["ml", "train-phobert", "--dataset", "missing", "--task", "topic"]) == 4
    capsys.readouterr()
    assert main(["ml", "phobert-inspect", "--run-id", "missing"]) == 4
    capsys.readouterr()
    assert main(["ml", "baseline-smoke"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "BASELINE_SMOKE_PASS_SYNTHETIC"


def test_inspection_cli_safe_metadata(trained, monkeypatch, capsys):
    root, _, _, run = trained
    (root / "configs").mkdir()
    (root / "configs/dataset_sources.yaml").write_bytes(
        (ROOT / "configs/dataset_sources.yaml").read_bytes()
    )
    monkeypatch.setenv("PFA_PROJECT_ROOT", str(root))
    assert main(["ml", "phobert-inspect", "--run-id", run["run_id"]]) == 0
    output = capsys.readouterr().out
    assert "SYNTHETIC:" not in output and "feedback_id" not in output
    assert "data/private" not in output and '"SYNTHETIC"' in output


def test_early_stopping_and_best_reload(tiny_built, monkeypatch):
    root, registry, texts = tiny_built
    model, tokenizer, segmenter, checkpoint = phobert_smoke.tiny(root, texts, "sentiment")
    original = phobert.evaluate
    calls = []

    def constant_score(*args):
        score, elapsed = original(*args)
        calls.append(score)
        score["macro_f1"] = 0.25
        return score, elapsed

    monkeypatch.setattr(phobert, "evaluate", constant_score)
    cfg = phobert_smoke.config(4).model_copy(update={"patience": 1})
    run = phobert.fit(
        root,
        registry,
        "synthetic_transformer_v1",
        "sentiment",
        42,
        cfg,
        model,
        tokenizer,
        segmenter,
        checkpoint,
    )
    assert run["completed_epochs"] == 2 and run["best_epoch"] == 1
    assert run["stale_evaluations"] == 1
    assert len(calls) == 2
    loaded, saved_tokenizer, saved_segmenter, _ = phobert.load(
        root, registry, run["run_id"], cfg.segmenter
    )
    partitions, _ = baseline.development(root, registry, "synthetic_transformer_v1")
    text, labels, _ = baseline.select(partitions["validation"], "sentiment")
    features, _ = phobert.prepare(text, labels, "sentiment", saved_tokenizer, saved_segmenter, 32)
    actual, _ = original(loaded, saved_tokenizer, features, "sentiment", "cpu", 8)
    expected = calls[0].copy()
    expected["macro_f1"] = actual["macro_f1"]
    assert actual == expected


def test_approved_local_checkpoint_inventory_and_tampering(tmp_path):
    directory = tmp_path / "synthetic_snapshot"
    directory.mkdir()
    for name in ("config.json", "model.safetensors", "vocab.txt", "bpe.codes"):
        (directory / name).write_bytes(b"SYNTHETIC NONMODEL TEST BYTES")
    evidence = dict(
        checkpoint="vinai/phobert-base",
        revision="a" * 40,
        license_name="SYNTHETIC_TEST_TERMS_NOT_ACTUAL_LICENSE",
        license_evidence_ref="synthetic_terms",
        reviewer_id="synthetic_reviewer",
        evidence_reference="synthetic_evidence",
        reviewed_at=datetime.now(UTC).isoformat(),
        human_verified=True,
        decision="APPROVED",
        files={name.name: store.file_checksum(name) for name in directory.iterdir()},
    )
    requests = tmp_path / "data/private/phobert_requests"
    store.private_directory(requests)
    path = requests / "synthetic_test.json"
    path.write_text(json.dumps(evidence))
    cfg = phobert.PhobertConfig(
        checkpoint_directory=str(directory), checkpoint_evidence_ref="synthetic_test"
    )
    actual, snapshot = phobert.approved_checkpoint(tmp_path, cfg)
    assert actual == directory and snapshot["revision"] == "a" * 40
    # Container/evidence check is not a successful pretrained readiness probe.
    assert phobert.readiness(tmp_path, cfg)["pretrained_checkpoint"] == "NOT_VERIFIED"
    (directory / "vocab.txt").write_bytes(b"CHANGED SYNTHETIC BYTES")
    with pytest.raises(IngestionError, match="checksum"):
        phobert.approved_checkpoint(tmp_path, cfg)


def test_checkpoint_unknown_terms_and_moving_revision_rejected(tmp_path):
    data = dict(
        checkpoint="vinai/phobert-base",
        revision="main",
        license_name="UNKNOWN",
        license_evidence_ref="synthetic_terms",
        reviewer_id="synthetic_reviewer",
        evidence_reference="synthetic_evidence",
        reviewed_at=datetime.now(UTC).isoformat(),
        human_verified=True,
        decision="APPROVED",
        files={
            name: "a" * 64
            for name in ("config.json", "model.safetensors", "vocab.txt", "bpe.codes")
        },
    )
    with pytest.raises(ValueError):
        phobert.CheckpointEvidence.model_validate(data)


def test_missing_dataset_revoked_load_and_cuda_guard(trained, monkeypatch):
    root, registry, _, run = trained
    with pytest.raises(IngestionError, match="NOT_AVAILABLE"):
        phobert.train(root, registry, "absent", "topic")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(IngestionBlocked, match="CUDA_NOT_AVAILABLE"):
        phobert.device_for(phobert.PhobertConfig(device="cuda"))

    def denied(*args, **kwargs):
        raise IngestionBlocked("Revoked training scope")

    monkeypatch.setattr(corpus, "_authorized_manifest", denied)
    monkeypatch.setattr(
        transformers.RobertaForSequenceClassification,
        "from_pretrained",
        lambda *args, **kwargs: pytest.fail("Revoked model loaded"),
    )
    with pytest.raises(IngestionBlocked):
        phobert.load(root, registry, run["run_id"], phobert_smoke.config().segmenter)


def test_local_phobert_bpe_and_encoder_loading_are_offline_synthetic(tmp_path):
    """Exercise HF PhoBERT classes with invented files, never genuine checkpoint verification."""
    vocabulary = tmp_path / "vocab.txt"
    vocabulary.write_text("k@@ 4\nh@@ 4\nô@@ 4\nn@@ 4\ng 4\nchưa 4\n", encoding="utf-8")
    (tmp_path / "bpe.codes").write_text("", encoding="utf-8")
    tokenizer = transformers.PhobertTokenizer(
        vocab_file=str(vocabulary),
        merges_file=str(tmp_path / "bpe.codes"),
        model_max_length=32,
    )
    tokenizer.save_pretrained(tmp_path)
    config = transformers.RobertaConfig(
        vocab_size=1024,
        hidden_size=16,
        num_hidden_layers=1,
        num_attention_heads=2,
        intermediate_size=32,
        max_position_embeddings=34,
        pad_token_id=1,
        bos_token_id=0,
        eos_token_id=2,
    )
    source = transformers.RobertaForMaskedLM(config)
    source.save_pretrained(tmp_path, safe_serialization=True)
    loaded, bpe = phobert.pretrained(tmp_path, "topic")
    assert loaded.config.label2id == phobert.mapping("topic")
    assert torch.equal(
        source.roberta.embeddings.word_embeddings.weight,
        loaded.roberta.embeddings.word_embeddings.weight,
    )
    encoded = bpe("không chưa", truncation=True, max_length=32)
    assert encoded["input_ids"][0] == 0 and encoded["input_ids"][-1] == 2
