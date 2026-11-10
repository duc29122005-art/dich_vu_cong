"""Cached model objects; current registry/control evidence is rechecked without reloading."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pfa.annotation import pilot_store as store
from pfa.annotation.taxonomy import CHECKSUM, VERSION
from pfa.api.schemas import TaskPrediction, TaskStatus
from pfa.api.settings import ApiSettings
from pfa.data.official_io import IngestionBlocked, IngestionError
from pfa.data.preprocessing import TRANSFORMATION_VERSION
from pfa.data.registry import load_registry
from pfa.ml import baseline, evaluation, model_adapters, model_registry
from pfa.ml import evaluation_policy as policy

TaskResults = dict[str, tuple[TaskPrediction, list[str]]]


class PredictionProvider(Protocol):
    def load(self) -> None: ...
    def check(self) -> dict[str, TaskStatus]: ...
    def predict(self, texts: list[str]) -> list[TaskResults]: ...
    def close(self) -> None: ...


class DemoProvider:
    """Constant fixtures, deliberately unrelated to the meaning of submitted text."""

    def __init__(self):
        self.loaded = False

    def load(self):
        self.loaded = True

    def check(self):
        return {
            task: TaskStatus(
                available=self.loaded,
                family="mock",
                model_version="mock-fixture-v1",
                deployment_status="DEMO_ONLY" if self.loaded else "UNAVAILABLE",
            )
            for task in baseline.TASKS
        }

    def predict(self, texts):
        result = [{} for _ in texts]
        for task, label in {"topic": "other", "sentiment": "neutral", "severity": "medium"}.items():
            decisions = policy.review(
                [label] * len(texts), None, task, None, policy.Protocol(), calibrated=False
            )
            for index, decision in enumerate(decisions):
                result[index][task] = (
                    TaskPrediction(
                        available=True,
                        label=label,
                        score_type="MOCK_NO_SCORE",
                        model_version="mock-fixture-v1",
                    ),
                    [*decision["reasons"], "DEMO_ONLY_MOCK_NOT_NLP"],
                )
        return result

    def close(self):
        self.loaded = False


@dataclass
class Runtime:
    record: dict
    experiment: dict
    experiment_sha256: str
    model: dict
    protocol: policy.Protocol
    adapter: model_adapters.Adapter


class RegistryProvider:
    def __init__(self, root: Path, settings: ApiSettings):
        self.root, self.settings = root, settings
        self.runtimes: dict[str, Runtime] = {}
        self.states = {
            task: TaskStatus(
                available=False,
                deployment_status="UNAVAILABLE",
                blocker="APPROVED_MODEL_UNAVAILABLE",
            )
            for task in baseline.TASKS
        }
        self.failed_tasks: set[str] = set()

    def material(self, task):
        record = model_registry.active(self.root, self.registry, task)
        descriptor = record["model"]
        if (
            descriptor["dataset"]["dataset_type"] != "RESEARCH"
            or descriptor["model_kind"] == "SYNTHETIC_TINY_MODEL"
            or descriptor["taxonomy_checksum"] != CHECKSUM
            or descriptor["taxonomy_version"] != VERSION
            or descriptor["labels"] != list(baseline.TASKS[task])
            or descriptor["task"] != task
            or descriptor["preprocessing"]["normalization"] != TRANSFORMATION_VERSION
        ):
            raise IngestionBlocked("Approved model taxonomy or preprocessing incompatible")
        events, _ = model_registry.history(self.root)
        eligible = [
            e
            for e in events
            if e["run_id"] == record["run_id"] and e["action"] == "RESEARCH_APPROVED"
        ]
        if not eligible:
            raise IngestionBlocked("Research evidence unavailable")
        reference = eligible[-1]["evaluation"]
        documents, checksum = store.bundle(
            model_registry.base(self.root) / "final_results" / store.identifier(reference["id"])
        )
        report = documents["report.json"]
        if (
            checksum != reference["sha256"]
            or report["dataset_type"] != "RESEARCH"
            or report["dataset"] != descriptor["dataset"]
            or report["selected_by_task"].get(task) != record["run_id"]
        ):
            raise IngestionBlocked("Approved final evaluation incompatible")
        documents, checksum = store.bundle(
            model_registry.base(self.root)
            / "experiments"
            / store.identifier(report["experiment_id"])
        )
        experiment = documents["experiment.json"]
        locked, _ = store.bundle(model_registry.base(self.root) / "locks" / report["experiment_id"])
        if (
            checksum != report["experiment_sha256"]
            or locked["lock.json"]["experiment_sha256"] != checksum
            or experiment["dataset"] != descriptor["dataset"]
        ):
            raise IngestionBlocked("Frozen experiment binding incompatible")
        protocol = policy.Protocol.model_validate(experiment["protocol"])
        if experiment["selected_by_task"] != evaluation.selection(experiment["models"], protocol):
            raise IngestionBlocked("Validation model selection changed")
        model = experiment["models"][record["run_id"]]
        provenance = {
            "evaluation_split": "validation",
            "dataset": descriptor["dataset"],
            "model_sha256": store.digest(descriptor),
            "protocol_sha256": store.digest(protocol.model_dump()),
            "roles": experiment["roles"],
        }
        if model["descriptor"] != descriptor or any(
            model[key]["provenance"] != provenance for key in ("calibrator", "threshold")
        ):
            raise IngestionBlocked("Calibration or threshold provenance incompatible")
        trust_ref = experiment["trust_references"].get(record["run_id"])
        if descriptor["family"] in baseline.MODELS:
            model_registry.authorize(
                self.root, trust_ref, "TRUST_ARTIFACT", store.digest(descriptor)
            )
        return record, experiment, checksum, model, protocol, trust_ref

    def load(self):
        try:
            self.registry = load_registry(self.root / "configs/dataset_sources.yaml")
            segmenters = {}
            if self.settings.segmenters_file:
                path = self.settings.segmenters_file
                path = path if path.is_absolute() else self.root / path
                segmenters = store.read_json(store.safe_path(path, self.root / "data/private"))
            for task in baseline.TASKS:
                try:
                    record, experiment, checksum, model, protocol, trust_ref = self.material(task)
                    adapter = model_adapters.Adapter(
                        self.root,
                        self.registry,
                        record["model"],
                        trust_ref=trust_ref,
                        segmenter_config=evaluation.segmentation(segmenters, record["run_id"]),
                    )
                    self.runtimes[task] = Runtime(
                        record, experiment, checksum, model, protocol, adapter
                    )
                except Exception:
                    # Exception text may contain private paths or inputs.
                    self.states[task].blocker = "MODEL_AUTHORIZATION_OR_INTEGRITY_UNAVAILABLE"
            self.check()
        except Exception:
            self.close()

    def check(self):
        for task, runtime in self.runtimes.items():
            try:
                record, experiment, checksum, _, _, _ = self.material(task)
                if (
                    task in self.failed_tasks
                    or record != runtime.record
                    or experiment != runtime.experiment
                    or checksum != runtime.experiment_sha256
                ):
                    raise IngestionError("Restart required after model/control change")
                self.states[task] = TaskStatus(
                    available=True,
                    family=record["model"]["family"],
                    model_version=record["run_id"],
                    deployment_status="APPROVED_MODEL",
                )
            except Exception:
                self.states[task] = TaskStatus(
                    available=False,
                    deployment_status="UNAVAILABLE",
                    blocker="MODEL_AUTHORIZATION_OR_INTEGRITY_UNAVAILABLE",
                )
        return self.states

    def predict(self, texts):
        result = [{} for _ in texts]
        for task in baseline.TASKS:
            try:
                runtime = self.runtimes[task]
                if not self.states[task].available:
                    raise IngestionBlocked("Task unavailable")
                predicted = runtime.adapter.predict(texts)
                if predicted["label_order"] != list(baseline.TASKS[task]) or len(
                    predicted["labels"]
                ) != len(texts):
                    raise IngestionError("Prediction label order or batch length mismatch")
                values = policy.apply_calibrator(
                    runtime.model["calibrator"], predicted["scores"], task
                )
                decisions = policy.review(
                    predicted["labels"],
                    values,
                    task,
                    runtime.model["threshold"],
                    runtime.protocol,
                    calibrated=values is not None,
                )
                for index, label in enumerate(predicted["labels"]):
                    score = None
                    if values is not None:
                        score = values[index][list(baseline.TASKS[task]).index(label)]
                    # Uncalibrated native scores are intentionally not exposed as confidence.
                    score_type = (
                        "CALIBRATED_PROBABILITY"
                        if values is not None
                        else "UNCALIBRATED_DECISION_SCORE"
                        if runtime.record["model"]["family"] in baseline.MODELS
                        else "UNCALIBRATED_LOGIT"
                    )
                    result[index][task] = (
                        TaskPrediction(
                            available=True,
                            label=label,
                            score=score,
                            score_type=score_type,
                            calibrated=values is not None,
                            model_version=runtime.record["run_id"],
                        ),
                        decisions[index]["reasons"],
                    )
            except Exception:
                self.failed_tasks.add(task)
                for item in result:
                    item[task] = (TaskPrediction(available=False), ["MODEL_INFERENCE_UNAVAILABLE"])
        return result

    def close(self):
        self.runtimes.clear()
        for task in self.states:
            self.states[task] = TaskStatus(
                available=False,
                deployment_status="UNAVAILABLE",
                blocker="APPROVED_MODEL_UNAVAILABLE",
            )
