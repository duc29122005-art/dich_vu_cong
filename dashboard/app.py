"""Run from repository root: python -m streamlit run dashboard/app.py."""

from datetime import date, timedelta

import streamlit as st
from pydantic import ValidationError

from dashboard.api_client import Client, DashboardError
from dashboard.charts import NAMES, bars, cross_rows, explain, line
from pfa.analytics.kpis import LABELS
from pfa.analytics.schemas import NOTICE, Filters

PAGES = [
    "Tổng quan",
    "Phân tích chủ đề",
    "Cảm xúc và mức độ",
    "Xu hướng và cảnh báo",
    "Mô hình và rà soát",
]
BASES = {
    "Dự đoán AI (giả lập)": "prediction",
    "Đã được rà soát (giả lập)": "reviewed",
    "Đã phân xử (giả lập)": "adjudicated",
}


def share(report, name):
    metric = report.metrics.get(name)
    return (
        f"{metric.share:.1%}"
        if metric is not None and metric.share is not None
        else "Chưa xác định / đã ẩn"
    )


def main():
    st.set_page_config(page_title="Phản ánh dịch vụ công — Giả lập", page_icon="📊", layout="wide")
    st.title("Phân tích phản ánh dịch vụ công")
    st.warning(NOTICE)
    st.caption(
        "Số liệu và rà soát đều giả lập. Không phải kết quả nghiên cứu, "
        "độ tin cậy mô hình hay quyết định hành chính."
    )
    page = st.sidebar.radio("Trang phân tích", PAGES)
    basis = BASES[st.sidebar.selectbox("Nguồn nhãn", list(BASES))]
    values = {"basis": basis}
    with st.sidebar.expander("Bộ lọc", expanded=True):
        if st.checkbox("Giới hạn ngày sự kiện"):
            dates = st.date_input(
                "Từ ngày / đến ngày", (date.today() - timedelta(days=30), date.today())
            )
            if len(dates) != 2:
                st.info("Chọn đầy đủ hai ngày.")
                return
            values.update(start=dates[0], end=dates[1])
        values["interval"] = st.selectbox(
            "Khoảng thời gian",
            ["day", "week", "month"],
            format_func=lambda c: {"day": "Ngày", "week": "Tuần", "month": "Tháng"}[c],
        )
        for field, title, codes in (
            ("agency", "Đơn vị", ["demo_agency_a", "demo_agency_b"]),
            ("domain", "Lĩnh vực", ["demo_domain_a", "demo_domain_b"]),
            ("topic", "Chủ đề", LABELS["topic"]),
            ("sentiment", "Cảm xúc", LABELS["sentiment"]),
            ("severity", "Mức độ", [*LABELS["severity"], "unknown"]),
            (
                "review_status",
                "Trạng thái rà soát",
                ["PENDING_REVIEW", "IN_REVIEW", "REVIEWED", "NEEDS_ADJUDICATION", "ADJUDICATED"],
            ),
        ):
            choice = st.selectbox(
                title,
                [None, *codes],
                format_func=lambda c: "Tất cả" if c is None else NAMES[c],
                key=field,
            )
            if choice is not None:
                values[field] = choice
        source = st.selectbox(
            "Nguồn dữ liệu",
            [None, "synthetic_demo"],
            format_func=lambda c: "Mọi nguồn được cấp quyền" if c is None else "Nguồn giả lập",
        )
        if source:
            values["source_id"] = source
        family = st.selectbox(
            "Họ mô hình của tác vụ lọc",
            [None, "mock", "lr", "svm", "phobert"],
            format_func=lambda c: c or "Tất cả",
        )
        if family:
            values["model_family"] = family
        values["model_task"] = st.selectbox(
            "Tác vụ áp dụng bộ lọc mô hình",
            ["topic", "sentiment", "severity"],
            format_func=lambda code: {
                "topic": "Chủ đề",
                "sentiment": "Cảm xúc",
                "severity": "Mức độ",
            }[code],
        )
        version = st.text_input("Phiên bản mô hình (mã công khai, tùy chọn)", max_chars=100)
        if version:
            values["model_version"] = version
    try:
        filters = Filters.model_validate(values)
        client = Client()
        report = client.fetch("summary", filters)
        st.caption(
            f"Nguồn nhãn: {next(name for name, code in BASES.items() if code == filters.basis)} "
            "· Múi giờ: Asia/Ho_Chi_Minh "
            f"· Ngưỡng ẩn ô: {report.small_group}"
        )
        if report.status != "AVAILABLE":
            st.info(
                "Không có dữ liệu phù hợp."
                if report.status == "EMPTY"
                else "Nhóm quá nhỏ; số liệu đã được ẩn."
            )
            return
        if page == "Tổng quan":
            columns = st.columns(4)
            columns[0].metric("Tổng phản ánh", report.total)
            columns[1].metric("Tỷ trọng tiêu cực", share(report, "negative_share"))
            columns[2].metric("Tỷ trọng mức độ cao", share(report, "high_severity_share"))
            columns[3].metric("AI yêu cầu rà soát", share(report, "review_required"))
            st.info(
                "Chủ đề phàn nàn nổi bật: "
                + NAMES.get(report.top_complaint_topic, "Không đủ dữ liệu / đã ẩn")
            )
            st.plotly_chart(bars(report.distributions["topic"], "Phân bố chủ đề"), width="stretch")
        elif page == "Phân tích chủ đề":
            topics = client.fetch("topics", filters)
            for dimension, title in (
                ("topic", "Chủ đề"),
                ("agency", "Đơn vị giả lập"),
                ("domain", "Lĩnh vực giả lập"),
            ):
                st.plotly_chart(
                    bars(topics.distributions.get(dimension, []), title), width="stretch"
                )
            st.caption(
                "Mẫu số là số phản ánh sau lọc. Nhãn thiếu được giữ riêng; ô nhỏ bị ẩn cả phân bố."
            )
        elif page == "Cảm xúc và mức độ":
            for dimension, title in (("sentiment", "Cảm xúc"), ("severity", "Mức độ")):
                st.plotly_chart(bars(report.distributions[dimension], title), width="stretch")
            st.dataframe(cross_rows(report.cross_tab), hide_index=True)
            st.caption(
                "Bảng chéo chỉ dùng hai nhãn đã biết. "
                "Mức độ chưa xác định không trở thành thấp/trung bình/cao."
            )
        elif page == "Xu hướng và cảnh báo":
            trend = client.fetch("trends", filters)
            st.plotly_chart(line(trend.buckets), width="stretch")
            st.caption(
                "Chỉ dùng received_at. Ngày thiếu được báo riêng; "
                "ô 0 không chứng minh thu thập đầy đủ."
            )
            for alert in client.fetch("alerts", filters).alerts:
                title = {
                    "volume": "Số lượng phản ánh",
                    "high_severity_share": "Tỷ trọng mức độ cao",
                    "topic_concentration": "Tập trung chủ đề",
                }[alert.rule]
                st.info(f"{title} · {alert.status}: {explain(alert)}")
                if alert.window_start:
                    st.caption(
                        f"Khoảng hiện tại: [{alert.window_start}, {alert.window_end_exclusive}). "
                        f"Nền: [{alert.baseline_start}, {alert.baseline_end_exclusive})."
                    )
            st.caption(
                "Chỉ báo giả lập hỗ trợ rà soát; không xác nhận sự cố hay khủng hoảng. "
                "Chưa điều chỉnh mùa vụ hoặc số lượt sử dụng dịch vụ."
            )
        else:
            st.metric("Đã rà soát", share(report, "reviewed"))
            st.metric("Có thay đổi nhãn so với AI", share(report, "corrections"))
            st.plotly_chart(
                bars(report.distributions["review_status"], "Trạng thái rà soát"), width="stretch"
            )
            st.dataframe([m.model_dump() for m in report.models], hide_index=True)
            st.caption(
                "Lịch sử dự đoán được giữ nguyên. Rà soát giả lập không chứng minh "
                "gán nhãn độc lập hoặc độ chính xác mô hình."
            )
        missing = report.metrics["missing_event_time_in_filter_scope"]
        st.caption(
            "Tỷ lệ thiếu ngày sự kiện trong phạm vi trước lọc ngày: "
            + (f"{missing.share:.1%}" if missing.share is not None else "Chưa xác định / đã ẩn")
        )
    except DashboardError as error:
        messages = {
            "MISSING_API_CREDENTIAL": "Chưa cấu hình khóa API phía máy chủ.",
            "AUTHORIZATION_DENIED": "Không được phép truy cập. Kiểm tra vai trò và phạm vi nguồn.",
        }
        st.error(
            messages.get(str(error), "API phân tích chưa sẵn sàng hoặc trả dữ liệu không hợp lệ.")
        )
    except (ValidationError, ValueError):
        st.error("Cấu hình hoặc bộ lọc không hợp lệ. Kiểm tra ngày và mã lựa chọn.")


if __name__ == "__main__":
    main()
