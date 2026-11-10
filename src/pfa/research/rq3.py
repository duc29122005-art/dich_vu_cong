"""Numerical correctness, reference-event quality and human usability stay separate."""

from collections import Counter
from statistics import mean

from pfa.research.statistics import ratio

TASKS = {
    "denominator": {
        "answer": "B",
        "question": "Có 100 phản ánh, 80 có nhãn cảm xúc, 40 tiêu cực. Tỷ lệ tiêu cực?",
        "choices": ["A: 40/100", "B: 40/80", "C: Không thể tính dù đủ nhãn"],
    },
    "missing_dates": {
        "answer": "C",
        "question": "Phản ánh thiếu ngày sự kiện được xử lý thế nào trong biểu đồ?",
        "choices": [
            "A: Dùng ngày nhập",
            "B: Bỏ và không báo",
            "C: Báo thiếu ngày, không gán ngày giả",
        ],
    },
    "alert_support": {
        "answer": "A",
        "question": "Một ngày có 1 phản ánh, chưa đủ đường nền. Có kết luận sự cố?",
        "choices": [
            "A: Không đủ bằng chứng",
            "B: Chắc chắn có khủng hoảng",
            "C: Chắc chắn không có vấn đề",
        ],
    },
    "basis": {
        "answer": "B",
        "question": "Nhãn mô hình và nhãn đã phân xử có thể gộp ngầm không?",
        "choices": [
            "A: Có",
            "B: Không, phải chọn và ghi rõ cơ sở nhãn",
            "C: Luôn dùng dự đoán thay nhãn thiếu",
        ],
    },
}


def usability(rows, questionnaires):
    result = []
    for task in TASKS:
        selected = [r for r in rows if r.task_id == task]
        complete = [r for r in selected if r.completion_status == "COMPLETED"]
        result.append(
            {
                "task_id": task,
                "completion": ratio(len(complete), len(selected)),
                "accuracy": ratio(
                    sum(r.answer_code == TASKS[task]["answer"] for r in complete), len(complete)
                ),
                "mean_completed_seconds": mean(r.duration_seconds for r in complete)
                if complete
                else None,
            }
        )
    answers = {}
    for field in ("perceived_usefulness", "perceived_workload"):
        values = [getattr(r, field) for r in questionnaires if getattr(r, field) is not None]
        answers[field] = {
            "responses": len(values),
            "missing": len(questionnaires) - len(values),
            "distribution": [
                {"rating": rating, "count": count}
                for rating, count in sorted(Counter(values).items())
            ],
            "mean": mean(values) if values else None,
        }
    return {
        "status": "DESCRIPTIVE_ONLY" if rows else "BLOCKED_ON_EXPERIMENT",
        "tasks": result,
        "questionnaire": answers,
        "limitations": [
            "No usability claim without real participants; no validated workload scale inferred",
            "Repeated tasks are descriptive, not independent observations",
        ],
    }


def alert_quality(events):
    """Tuples (eligible, triggered, independently_referenced_event_or_None)."""
    comparable = [
        (triggered, actual)
        for eligible, triggered, actual in events
        if eligible and actual is not None
    ]
    tp = sum(pred and actual for pred, actual in comparable)
    fp = sum(pred and not actual for pred, actual in comparable)
    fn = sum(not pred and actual for pred, actual in comparable)
    tn = sum(not pred and not actual for pred, actual in comparable)
    return {
        "status": "DESCRIPTIVE_ONLY" if comparable else "INSUFFICIENT_EVIDENCE",
        "eligible_reference_windows": len(comparable),
        "excluded_windows": len(events) - len(comparable),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": ratio(tp, tp + fp),
        "recall": ratio(tp, tp + fn),
        "false_positive_rate": ratio(fp, fp + tn),
        "limitations": [
            "Reference events required; eligibility exclusion is not a true negative",
            "No exposure, seasonality or real-world utility claim",
        ],
    }
