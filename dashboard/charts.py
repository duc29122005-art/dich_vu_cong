"""Whitelisted chart data contains public labels and aggregate numbers only."""

import plotly.graph_objects as go

NAMES = {
    "delayed_processing": "Chậm xử lý hồ sơ",
    "complex_procedure": "Thủ tục phức tạp",
    "unclear_guidance": "Hướng dẫn không rõ",
    "online_system_error": "Lỗi hệ thống trực tuyến",
    "staff_attitude": "Thái độ phục vụ",
    "fees": "Chi phí / lệ phí",
    "unsatisfactory_result": "Kết quả chưa phù hợp",
    "other": "Vấn đề khác",
    "negative": "Tiêu cực",
    "neutral": "Trung tính",
    "positive": "Tích cực",
    "low": "Thấp",
    "medium": "Trung bình",
    "high": "Cao",
    "unknown": "Chưa xác định",
    "missing": "Thiếu nhãn / dữ liệu",
    "unapproved_metadata": "Siêu dữ liệu chưa được duyệt",
    "demo_agency_a": "Đơn vị giả lập A",
    "demo_agency_b": "Đơn vị giả lập B",
    "demo_domain_a": "Lĩnh vực giả lập A",
    "demo_domain_b": "Lĩnh vực giả lập B",
    "PENDING_REVIEW": "Chờ rà soát",
    "IN_REVIEW": "Đang rà soát",
    "REVIEWED": "Đã rà soát",
    "NEEDS_ADJUDICATION": "Cần phân xử",
    "ADJUDICATED": "Đã phân xử (giả lập)",
}


def distribution_rows(cells):
    return [
        {"label": NAMES[c.code], "count": c.count}
        for c in cells
        if c.code in NAMES and c.count is not None and not c.suppressed
    ]


def trend_rows(buckets):
    return [{"start": b.start.isoformat(), "count": b.count} for b in buckets]


def bars(cells, title):
    rows = distribution_rows(cells)
    figure = go.Figure(
        go.Bar(
            x=[r["count"] for r in rows],
            y=[r["label"] for r in rows],
            orientation="h",
            marker_color="#176B87",
            hovertemplate="%{y}: %{x} phản ánh<extra></extra>",
        )
    )
    figure.update_layout(
        title=title,
        xaxis_title="Số phản ánh",
        yaxis_title=None,
        template="plotly_white",
        margin=dict(l=10, r=10, t=50, b=30),
    )
    return figure


def line(buckets):
    rows = trend_rows(buckets)
    figure = go.Figure(
        go.Scatter(
            x=[r["start"] for r in rows],
            y=[r["count"] for r in rows],
            mode="lines+markers",
            connectgaps=False,
            line_color="#176B87",
            hovertemplate="%{x}: %{y} phản ánh<extra></extra>",
        )
    )
    figure.update_layout(
        title="Phản ánh theo thời điểm sự kiện",
        xaxis_title="Ngày bắt đầu khoảng",
        yaxis_title="Số phản ánh",
        template="plotly_white",
    )
    return figure


def cross_rows(cells):
    result = []
    for cell in cells:
        parts = cell.code.split(":")
        if (
            len(parts) == 2
            and all(p in NAMES for p in parts)
            and cell.count is not None
            and not cell.suppressed
        ):
            result.append(
                {"Cảm xúc": NAMES[parts[0]], "Mức độ": NAMES[parts[1]], "Số phản ánh": cell.count}
            )
    return result


REASONS = {
    "OBSERVED_VOLUME_INCREASE": "Số phản ánh tăng vượt cả ngưỡng tỷ lệ và độ lệch nền.",
    "OBSERVED_SHARE_INCREASE": "Tỷ trọng tăng vượt ngưỡng cấu hình và hàng rào dao động.",
    "WITHIN_BASELINE_RULE": "Chưa vượt điều kiện cảnh báo đã cấu hình.",
    "MISSING_EVENT_TIME_COVERAGE": "Thiếu ngày sự kiện hoặc tỷ lệ thiếu vượt ngưỡng.",
    "MISSING_LABEL_COVERAGE": "Tỷ lệ nhãn thiếu hoặc chưa xác định vượt ngưỡng cho phép.",
    "INSUFFICIENT_BASELINE_WINDOWS": "Chưa đủ khoảng lịch sử để lập nền so sánh.",
    "PARTIAL_CALENDAR_WINDOW": "Khoảng ngày chưa hoàn tất hoặc bị cắt bởi bộ lọc.",
    "INSUFFICIENT_WINDOW_SUPPORT": "Số mẫu trong khoảng hiện tại hoặc lịch sử quá ít.",
    "INSUFFICIENT_KNOWN_LABELS": "Chưa đủ nhãn hợp lệ cho so sánh tỷ trọng.",
    "SMALL_LABEL_CELL": "Đã ẩn vì ô dữ liệu nhỏ.",
    "DAILY_ALERT_WINDOWS_REQUIRED": "Quy tắc cảnh báo hiện chỉ hỗ trợ khoảng ngày đầy đủ.",
}


def explain(alert):
    return REASONS.get(alert.reason, "Không đủ thông tin để diễn giải quy tắc.")
