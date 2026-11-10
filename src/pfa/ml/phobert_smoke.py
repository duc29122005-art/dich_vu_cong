"""Random tiny RoBERTa and a synthetic tokenizer; never pretrained PhoBERT."""

from pathlib import Path
from tempfile import TemporaryDirectory

from pfa.annotation import pilot_store as store
from pfa.data import corpus, corpus_smoke
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.registry import Registry
from pfa.data.splitting import SplitConfig
from pfa.ml import baseline, phobert
from pfa.ml.segmentation import SegmentationConfig, Segmenter


def tiny(root: Path, texts: list[str], task: baseline.Task, seed: int = 42):
    store.require_synthetic(root)
    phobert.dependencies()
    from tokenizers import Tokenizer, models, pre_tokenizers, processors
    from transformers import (
        PreTrainedTokenizerFast,
        RobertaConfig,
        RobertaForSequenceClassification,
    )

    segmenter = Segmenter(
        root, SegmentationConfig(backend="synthetic_fixture", version="synthetic-phrase-1")
    )
    words = sorted({word for text in texts for word in segmenter.segment(text).split()})
    special = ["<s>", "<pad>", "</s>", "<unk>", "<mask>"]
    vocab = {
        word: index
        for index, word in enumerate(special + [word for word in words if word not in special])
    }
    backend = Tokenizer(models.WordLevel(vocab=vocab, unk_token="<unk>"))
    backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    backend.post_processor = processors.TemplateProcessing(
        single="<s> $A </s>",
        special_tokens=[("<s>", 0), ("</s>", 2)],
    )
    tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=backend,
        bos_token="<s>",
        pad_token="<pad>",
        eos_token="</s>",
        unk_token="<unk>",
        mask_token="<mask>",
        model_max_length=32,
        model_input_names=["input_ids", "attention_mask"],
    )
    labels = phobert.mapping(task)
    phobert.seed_all(seed)
    model = RobertaForSequenceClassification(
        RobertaConfig(
            vocab_size=len(vocab),
            hidden_size=16,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=32,
            max_position_embeddings=34,
            type_vocab_size=1,
            hidden_dropout_prob=0.0,
            attention_probs_dropout_prob=0.0,
            num_labels=len(labels),
            label2id=labels,
            id2label={value: key for key, value in labels.items()},
            pad_token_id=1,
            bos_token_id=0,
            eos_token_id=2,
        )
    )
    checkpoint = {
        "kind": "TINY_RANDOM_TRANSFORMER",
        "repository": None,
        "revision": None,
        "pretrained": False,
        "tokenizer": "SYNTHETIC_WORDLEVEL_NOT_PHOBERT_BPE",
        "architecture": "RobertaForSequenceClassification",
        "human_gold": False,
    }
    return model, tokenizer, segmenter, checkpoint


def config(epochs: int = 1) -> phobert.PhobertConfig:
    return phobert.PhobertConfig(
        segmenter=SegmentationConfig(backend="synthetic_fixture", version="synthetic-phrase-1"),
        max_length=32,
        epochs=epochs,
        learning_rate=0.001,
        batch_size=8,
        gradient_accumulation=2,
        device="cpu",
    )


def smoke(registry: Registry) -> dict:
    phobert.dependencies()
    with TemporaryDirectory(prefix="pfa-phobert-tiny-synthetic-") as temporary:
        root = Path(temporary)
        with store.synthetic_session(root):
            rows, provenance = corpus_smoke.fixture(48)
            built = corpus._publish(
                root, "synthetic_phobert_v1", rows, provenance, SplitConfig(), 42
            )
            partitions, _ = baseline.development(root, registry, "synthetic_phobert_v1")
            texts = [row.content for row in partitions["train"]]
            result = {}
            for task in baseline.TASKS:
                model, tokenizer, segmenter, checkpoint = tiny(root, texts, task)
                run = phobert.fit(
                    root,
                    registry,
                    "synthetic_phobert_v1",
                    task,
                    42,
                    config(),
                    model,
                    tokenizer,
                    segmenter,
                    checkpoint,
                )
                inference = phobert.predict(
                    root,
                    registry,
                    run["run_id"],
                    ["SYNTHETIC: hướng dẫn thủ tục chưa rõ."],
                    config().segmenter,
                )
                if inference["predictions"][0]["label"] not in phobert.mapping(task):
                    raise IngestionError("Synthetic inference mapping failed")
                result[task] = {
                    "dataset_type": "SYNTHETIC",
                    "optimizer_steps": run["optimizer_steps"],
                    "finite_backward_verified": run["finite_backward_verified"],
                    "training_loss": run["history"][-1]["training_loss"],
                    "validation": run["history"][-1]["validation"],
                    "artifact_checksums_verified": run["artifact_checksums_verified"],
                    "task_exclusions": run["task_exclusions"],
                    "inference_verified": True,
                }
            resumed = phobert.fit(
                root,
                registry,
                "synthetic_phobert_v1",
                task,
                42,
                config(2),
                model,
                tokenizer,
                segmenter,
                checkpoint,
                resume_run=run["run_id"],
            )
            if resumed["completed_epochs"] != 2:
                raise IngestionError("Synthetic epoch checkpoint resume failed")
            try:
                corpus.model_selection(root, registry, "synthetic_phobert_v1", "test")
            except IngestionBlocked:
                pass
            else:
                raise IngestionError("Synthetic Transformer holdout protection failed")
            summary = {
                "status": "PHOBERT_SMOKE_PASS_SYNTHETIC_TINY_MODEL",
                "dataset_type": "SYNTHETIC",
                "model_kind": "RANDOM_TINY_TRANSFORMER_NOT_PRETRAINED_PHOBERT",
                "pretrained_checkpoint": "NOT_VERIFIED",
                "research_training_completed": False,
                "device": "cpu",
                "record_count": len(rows),
                "split_counts": built["report"]["counts"],
                "tasks": result,
                "resume_verified": True,
                "test_access_blocked": True,
                "test_labels_read": False,
                "weights_downloaded": False,
            }
    summary["temporary_storage_cleaned"] = not root.exists()
    return summary
