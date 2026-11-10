# MASTER PLAN V2.1 — PUBLIC SERVICE FEEDBACK AI

> **Ngày rà soát:** 2026-11-04 (bổ sung STEP 03B — Real Dataset Discovery & Acquisition)  
> **Trạng thái:** Kế hoạch cập nhật từ V2; trạng thái các STEP dựa trên **báo cáo Codex do người dùng cung cấp**, không phải kiểm toán trực tiếp repository.  
> **Môi trường phát triển ưu tiên:** Windows 10/11 + VS Code + PowerShell + Python 3.11. Docker/GPU là tùy chọn tới khi cần.  
> **Tài liệu nguồn:** `[QLNN][SƠ KHẢO ĐỀ TÀI - MAZE][Elia] (1).docx`, 7 trang.  
> **Mục tiêu:** NLP/ML phân tích phản ánh về dịch vụ công theo **chủ đề, cảm xúc, mức độ nghiêm trọng**, kết hợp **thống kê, cảnh báo, dashboard** và đánh giá cải thiện quy trình **AI + human review**.

## Trạng thái thực tế đã báo cáo tại thời điểm cập nhật (2026-11-04)

| Hạng mục | Trạng thái dựa trên báo cáo Codex | Ý nghĩa |
|---|---|---|
| STEP 01–08A | TECHNICAL PASS; lần gần nhất **353 pytest PASS** | Hệ thống code/test trên synthetic, không đồng nghĩa có dữ liệu nghiên cứu |
| STEP 03B | **CHƯA TRIỂN KHAI** | Thiếu quy trình discovery → xin quyền → secure receipt → bàn giao STEP 04 |
| Taxonomy human approval | PENDING | Chưa bắt đầu pilot người thật |
| External permission | NONE / BLOCKED_PERMISSION | Không được nhận/truy xuất dữ liệu thật chưa được cấp quyền |
| Pilot 07B, research dataset 08B | NOT_STARTED | Chưa có gold labels/split cho nghiên cứu |
| STEP 09 | Prompt đã chuẩn bị; trạng thái triển khai chưa được người dùng báo cáo | Chỉ synthetic baseline cho đến khi 08B đạt |

**Quyết định tiến độ:** Ưu tiên triển khai STEP 03B ngay để giải quyết critical path của dữ liệu thật; việc huấn luyện synthetic ở STEP 09 chỉ là test phần mềm. Không tự ý thay đổi các STEP 01–08A đã hoàn thành.

---

## 0. Kết luận review bản V1

Bản 12 bước V1 định hướng hợp lý nhưng chưa đủ điều kiện triển khai/kiểm chứng end-to-end. V2.1 giữ kiến trúc chính với **17 bước gốc + STEP 03B bổ sung (tổng 18 đơn vị công việc)** có thể giao việc độc lập; **không đổi số 04–17** để tránh làm hỏng CLI/docs hiện có. Các thay đổi quan trọng:

1. Tách **quyền truy cập/nguồn dữ liệu (STEP 02)** khỏi **download benchmark (STEP 03)** và **thu thập dữ liệu thật có kiểm soát (STEP 03B)**. Không mặc định tải dữ liệu license unknown khi chưa được người chịu trách nhiệm duyệt phạm vi dùng.
2. Tách **import được cấp quyền (04)**, **audit/clean/redact (05)**, **taxonomy (06)**, **pilot/độ đồng thuận (07)**, **đóng băng dataset và chống leakage (08)**.
3. Có **hai đường chạy**: `synthetic/benchmark` để test code và `authorized_agency_export` cho nghiên cứu. **Không được đánh đồng số liệu 2 đường chạy**.
4. Kết quả RQ1–RQ4, lệch mẫu, độ tin cậy nhãn, chất lượng tập test, hiệu chỉnh xác suất/abstention và quy trình human review được định nghĩa từ trước.
5. Phân tách đơn vị đo `created_at`, `processed_at`, `ingested_at`; không được suy đoán cơ quan hoặc SLA từ văn bản khi không có metadata/quy định.
6. An toàn dữ liệu: data contracts, quyền dùng, PII scanning, review, truy cập/giữ-xóa dữ liệu, logging redacted, CI không tải dữ liệu nhạy cảm.
7. Mỗi bước có **prompt Codex**, **lệnh PowerShell người chạy**, **human gate**, **PASS/FAIL và STOP condition**. Codex phải báo kết quả thực chạy, không được đoán.

### Đối chiếu yêu cầu đề cương

| Yêu cầu nghiên cứu gốc | Bước bảo đảm | Minh chứng cần thu |
|---|---|---|
| Dữ liệu 2.000–5.000 phản ánh được phép dùng và ẩn danh | 02, **03B**, 04–08 | Permission record, dataset card, checksum, tỷ lệ trùng/PII, nhãn được kiểm định |
| Topic taxonomy + sentiment + severity | 06–11 | Nhãn định nghĩa rõ, agreement, metrics riêng từng task |
| TF-IDF + Logistic Regression; TF-IDF + SVM; PhoBERT | 09–11 | Run config, artifact, confusion matrix, bảng so sánh trên cùng test |
| Dashboard thời gian/lĩnh vực/đơn vị, cảnh báo | 12–14 | API, thống kê, bộ lọc, test aggregation và false-alert diagnostics |
| RQ1 – vấn đề phổ biến | 08, 14, 15 | Thống kê kèm mẫu số, nguồn và giới hạn đại diện |
| RQ2 – AI phân loại chính xác tới đâu | 09–11 | Macro-F1, per-class P/R/F1, CI, error analysis |
| RQ3 – chỉ báo hỗ trợ quản lý | 14–15 | KPI được định nghĩa, kiểm định công thức, nghiên cứu tính hữu ích |
| RQ4 – AI + người so với thủ công | 15 | Protocol ngẫu nhiên/counterbalanced, thời gian và độ chính xác thật |

---

## 1. Quyết định nghiên cứu, dữ liệu và giới hạn

### 1.1. Bộ dữ liệu được chọn, nhưng phân vai rõ ràng

| ID | Nguồn / đường dẫn | Vai trò | Tình trạng xác minh 2026-11-03 | Quyết định |
|---|---|---|---|---|
| `uit_vsfc` | https://huggingface.co/datasets/uitnlp/vietnamese_students_feedback | **Benchmark phần mềm**, không làm dữ liệu chính | 16.175 dòng theo card, 3 split; `sentence`, `sentiment`, `topic`; **license unknown** | Viết adapter; chỉ tải/sử dụng sau khi người phụ trách cho phép dựa trên quyền được xác minh. Nếu không, chạy fixture synthetic. Không công bố kết quả như dịch vụ công |
| `public_service_official` | https://vpcp.dichvucong.gov.vn/p/phananhkiennghi/pakn-tra-loi.html | **Ưu tiên dataset nghiên cứu chính** | Có trang tra cứu; chưa xác minh API/tải hàng loạt/quyền dùng để train; nguy cơ PII | `permission_pending`, **KHÔNG scrape/crawl** hoặc import dữ liệu chưa được cấp quyền |
| `authorized_agency_export` | File CSV/JSONL do cơ quan có thẩm quyền cung cấp | Phương án ưu tiên tương đương nếu có văn bản cấp quyền | Chưa có file | Chấp nhận sau human gate về phạm vi dùng, retention, PII, provenance |
| `neu_esc` | https://huggingface.co/datasets/hung20gg/NEU-ESC | Benchmark bổ trợ, tùy chọn | Card ghi Apache-2.0; dataset **gated** yêu cầu chấp thuận | Không bypass gating; chỉ thêm adapter khi thật cần |
| `vn_mps_qa` | https://github.com/doanhieung/vn-mps-public-service-dataset | Tham khảo từ vựng/QA | Không phải nhãn phản ánh | Không trộn làm nhãn thực nghiệm |
| `sipas` | https://huggingface.co/datasets/letrinhan/vn-sipas-provincial | Chỉ báo đối chiếu ở cấp tổng hợp | License `other`; không phải phản ánh cá nhân | Không dùng làm nhãn từng phản ánh |
| `synthetic_demo` | Fixtures tự tạo, gắn nhãn `SYNTHETIC` | Kiểm thử offline, CI, demo code | Không có dữ liệu người thật, không được dùng làm kết quả khoa học | Luôn tách storage và báo cáo khỏi dữ liệu nghiên cứu |

**Đây là lựa chọn kiến trúc, không phải tuyên bố quyền sử dụng.** Dữ liệu trang web công khai vẫn có thể chứa thông tin cá nhân hoặc điều khoản không cho phép tái sử dụng cho ML.

### 1.2. Gate chọn dataset (bắt buộc trước research training)

Một nguồn chỉ được đánh dấu `approved_for_research` khi đủ bằng chứng của người có trách nhiệm:

- `source_owner`, `source_url`, `access_method`, `data_fields`, `coverage_period`, `collection_context`;
- **bằng chứng quyền xử lý**: mục đích, phạm vi, chia sẻ/không chia sẻ, có được huấn luyện/publish artifact không, thời gian lưu giữ/xóa;
- danh sách trường nhạy cảm, phương pháp giảm thiểu/ẩn danh, người phê duyệt, ngày kiểm tra;
- số mẫu dự kiến, ngôn ngữ, domain-fit và availability của metadata `created_at`, `agency`, `domain`;
- bias: chỉ những người gửi khiếu nại? chỉ case đã trả lời? mất các mẫu offline? dữ liệu có chu kỳ thu thập ổn định?

Nếu quyền chưa rõ: trạng thái `pending_permission` hoặc `rejected`, **không có đường rẽ kỹ thuật nào được phép bỏ qua gate này**.

**Khung pháp lý tham chiếu (không thay ý kiến pháp lý):** Luật 91/2025/QH15 có hiệu lực 01/01/2026 và Nghị định 356/2025/NĐ-CP có hiệu lực 01/01/2026. Người phụ trách pháp lý/đơn vị cung cấp dữ liệu xác nhận việc áp dụng.

### 1.3. Ba nhánh quyết định sau STEP 02/03B

- **A — Có tập phản ánh và quyền rõ:** thực hiện đủ 04–17 bằng dữ liệu chính sau anonymization và annotation.
- **B — Chưa có dữ liệu chính:** hoàn thiện repo, synthetic tests, benchmark có quyền (nếu có), xây API/dashboard demo có nhãn `SYNTHETIC`; **BLOCK final domain metrics, RQ1/RQ3 thực tế và RQ4**.
- **C — Không được cấp quyền:** chỉ tìm nguồn thay thế có quyền hoặc xin dữ liệu ẩn danh từ cơ quan đối tác; điều chỉnh phạm vi nghiên cứu với người hướng dẫn. Không cố lấy từ website/ẩn điều kiện truy cập.

### 1.4. Kết quả nghiên cứu bắt buộc

- **Primary metrics:** Macro-F1 theo task; Recall nhãn `high` cho severity; Precision/Recall/F1 từng lớp; confusion matrix.
- **Secondary metrics:** Accuracy, Weighted-F1, thời gian huấn luyện, độ trễ suy luận, calibration (ECE/Brier nếu dùng score như xác suất), tỷ lệ `requires_review` và coverage.
- **No leakage:** dedup/near-duplicate cùng group, text giống/same-case/same-thread vào cùng split; tách trước augmentation. Test holdout khóa trước khi tuning; chạy test cuối cùng một lần theo protocol đã định.
- **Không có cam kết PhoBERT sẽ thắng:** báo kết quả theo cùng test và cùng version dataset.
- **Không dùng sentiment làm severity**; chủ đề phản ánh ở v1 là single-primary-label, có cờ `multiple_issues` để phân tích mở rộng.
- **Các chỉ báo của dashboard là proxy từ phản ánh**. Không coi `% negative` = `% toàn dân không hài lòng`; không so sánh đơn vị như kết luận chất lượng nếu thiếu mẫu số tổng số hồ sơ/cơ cấu dân số.

---

## 2. Kiến trúc và giao ước triển khai

```text
AUTHORIZED DATA SOURCE (Human-approved)              SYNTHETIC / BENCHMARK (Test only)
   STEP 03B: discover / request / receive / verify
             |                                                     |
             v                                                     v
       Secure Import                                      Separate adapter and schema
             |                                                     |
       PII Redaction + Human review                   Smoke-test ML pipeline only
             |
       Quality audit + annotation (two annotators)
             |
       Frozen data version / group-aware splits
             |
        +----+----------------------+--------------------+
        |                           |                    |
      TF-IDF LR                  TF-IDF SVM           PhoBERT
        +---------------------------+--------------------+
                                    |
                    FAIR EVALUATION + MODEL REGISTRY
                                    |
                  FASTAPI PREDICT + REVIEW POLICY
                                    |
                 POSTGRESQL + AUTH + AUDIT TRAIL
                                    |
                ANALYTICS + STREAMLIT DASHBOARD
                                    |
                   HUMAN-AI EXPERIMENT (RQ4)
                                    |
                          REPORT + DEPLOY
```

**Source tree mục tiêu:**

```text
public-feedback-ai/
├── src/pfa/{cli.py,config.py,data/,annotation/,ml/,api/,db/,analytics/}
├── configs/{dataset_sources.yaml,taxonomy_v1.yaml,train_baselines.yaml,phobert.yaml}
├── data/{fixtures/,benchmarks/,restricted/,processed/,annotations/}  # dữ liệu thực bị gitignore
├── dashboard/app.py
├── docs/{DATASET_DECISION.md,PERMISSION_REGISTER.md,ANNOTATION_GUIDELINES.md,
│        EXPERIMENT_PROTOCOL.md,DATASET_CARD.md,MODEL_CARD.md,PRIVACY_REVIEW.md}
├── reports/{dataset/,annotation/,experiments/,rq4/,e2e/}
├── tests/{unit/,integration/,e2e/}
├── scripts/
├── .github/workflows/ci.yml
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

**Quy ước CLI:** `python -m pfa.cli ...` (Python thực tế trên Windows là `./.venv/Scripts/python.exe`; dùng cú pháp PowerShell ở các bước dưới). **CLI trong bước sau là CONTRACT yêu cầu Codex hiện thực, không có sẵn trước khi Codex tạo.**

**Data schema nghiên cứu tối thiểu** (thiết kế, chưa phải dữ liệu hiện có):

```text
feedback_id: UUID/random non-identifying ID
source_id: enum; permission_ref: evidence ID (không lưu bằng chứng nhạy cảm trong repo)
source_record_hash: optional pseudonymized record ID; không lưu mã hồ sơ gốc
text_redacted: str; text_normalized: str
received_at: datetime | null (theo timestamp nguồn, với timezone/precision)
ingested_at: datetime (thời điểm nhập; không dùng thay received_at cho trend)
agency_code: str | null (chỉ metadata được cấp quyền)
domain_code: str | null
status: str | null; grouping_key: str (near-duplicate/group leakage)
topic_label: str | null; sentiment_label: str | null; severity_label: str | null
annotation_status: unreviewed/dual_labeled/adjudicated/unknown
source_version: str; taxonomy_version: str
```

**V1 taxonomy đề xuất:**
- `topic`: delayed_processing, complex_procedure, unclear_guidance, online_system_error, staff_attitude, fees, unsatisfactory_result, other.
- `sentiment`: negative, neutral, positive.
- `severity`: low, medium, high; khi chưa đủ chứng cứ là **`unknown` ở annotation/workflow**, không phải tự gán `low`.
- `requires_review` là quyết định workflow, **không phải nhãn huấn luyện severity**.

**Thông số cần người hướng dẫn quyết định:** nhãn v1 có bao phủ nội dung thực tế không; severity dựa trên tác động + thời hạn pháp lý nào; cách chọn nhãn chính với multi-issue; mức độ cho phép lưu và tái sử dụng văn bản đã ẩn danh.

---

## 3. Prompt chung cho MỌI phiên Codex (dán đầu, sau đó dán prompt từng bước)

> Bạn là principal Python/ML engineer của dự án Public Service Feedback AI. Đọc README, cây repo, `MASTER_PLAN_CODEX_PUBLIC_FEEDBACK_AI_V2_1.md`, và trạng thái Git trước khi sửa. Chỉ thực hiện STEP được yêu cầu, không tự nhảy bước; tôn trọng contract và các source IDs trong plan. Python 3.11, PowerShell, src-layout `src/pfa`, CLI `python -m pfa.cli`, tests offline dùng fixtures gắn nhãn SYNTHETIC, code có type hints và logging an toàn. Không crawl dữ liệu chính phủ, không truy cập nguồn cần quyền khi chưa được duyệt, không chạy script từ dataset repo, không đưa PII/secrets/raw data lên Git, không ngụy tạo metrics/mẫu thật/terminal output. Trước khi sửa: lập checklist file đầu ra và test. Sau sửa: chạy lint và test trong khả năng. Báo chính xác `Changed files`, `Commands executed`, `Tests PASS/FAIL/SKIPPED`, `Human actions`, `Unresolved blockers`, `Next STEP gate`. Đối với bất kỳ CLI nào được yêu cầu, phải tạo command thật hoặc nêu BLOCKED; không dùng placeholder giả làm thành công. Không xóa file người dùng khi chưa được phép.

*Ghi chú:* Đặt bản plan này tại root và file `.gitignore` phải bỏ qua `data/restricted/`, `data/annotations/` chứa dữ liệu thật, `.env`, `private/`, model weights, dữ liệu benchmarks không được phép phân phối. Chỉ commit file config/template và synthetic fixtures đã kiểm tra.

---

## 4. Các STEP thực thi, prompts, lệnh người chạy và tiêu chí nghiệm thu

### STEP 01 — Repository foundation (prerequisite)

**Dependency:** Python 3.11; Git; VS Code. **Output:** repo cài editable, CLI doctor, lint/test chạy được.

**PROMPT CODEX — 01:**

> Triển khai STEP 01. Trước tiên đọc repo hiện tại và không ghi đè file quan trọng. Tạo `pyproject.toml` với extras `dev`, `data`, `ml`, `api`, `dashboard`; Python 3.11, Typer CLI, pytest, ruff, pydantic-settings nếu cần; src-layout `src/pfa`. Thêm `.gitignore` mặc định deny đối với dữ liệu thô, dữ liệu người thật, export annotation, checkpoint, `.env`, credentials; `.env.example` không chứa secret; README PowerShell. Viết CLI `doctor` kiểm tra package import, Python, thư mục/cấu hình; tạo tối thiểu 3 synthetic smoke tests (CLI/schema/gitignore). Không download dataset/GPU/Docker. Chạy các lệnh có thể và báo output thật.

**NGƯỜI CHẠY (PowerShell):**

```powershell
# Chạy ở nơi muốn đặt dự án; bỏ qua mkdir/git init nếu đã có repo
mkdir public-feedback-ai
cd public-feedback-ai
git init
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
code .
# Sau khi Codex triển khai STEP 01:
.\.venv\Scripts\python.exe -m pip install -e ".[dev,data]"
.\.venv\Scripts\python.exe -m pfa.cli doctor
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
git status --short
```

**HUMAN GATE:** Không có tác vụ pháp lý; chọn thư mục chứa repo, xem `.gitignore`.  
**PASS:** `doctor`, pytest, ruff PASS; `git check-ignore data/restricted/test.csv` có tác dụng; không có dữ liệu thật.

### STEP 02 — Dataset source research & permission gate [ƯU TIÊN HIỆN TẠI]

**Dependency:** STEP 01. **Output:** source registry, quyết định nguồn, hồ sơ quyền dùng, **không tải file nào**.

**PROMPT CODEX — 02:**

> Triển khai STEP 02 nhưng chưa tải dữ liệu. Tạo `configs/dataset_sources.yaml` với đầy đủ 7 IDs trong master plan (uit_vsfc, public_service_official, authorized_agency_export, neu_esc, vn_mps_qa, sipas, synthetic_demo); các trường `source_url`, `domain_fit`, `dataset_role`, `task_labels`, `license_status`, `permission_status`, `approval_ref`, `PII_risk`, `retrieval_method`, `coverage`, `last_checked`, `owner`, `allowed_processing`, `allowed_training`, `allowed_publication`, `retention_status`. Tạo CLI `dataset sources`, `dataset assess --source ...` và `dataset approve --source ... --approval-ref ...` **chỉ ghi quyết định sau khi người có quyền ký duyệt**, có validation/evidence và audit trail, không tự động cấp quyền. Tạo `docs/DATASET_DECISION.md`, `docs/PERMISSION_REGISTER.md` với bảng so sánh có scoring rubric (domain 30%, permission/privacy 30%, label fit 20%, coverage/metadata 10%, repeatability 10%), được phép bỏ nguồn nếu critical criteria không đạt. Tạo `docs/DATA_REQUEST_TEMPLATE.md` hỏi bên sở hữu dữ liệu về phạm vi dùng, fields, cách giao dữ liệu đã ẩn danh và retention. Mặc định official source `pending_permission`, UIT-VSFC `license_unknown`, NEU-ESC `gated`. Tests: không cho approve khi missing evidence, không cho fetch nguồn chưa approved, không để bằng chứng nhạy cảm xuất vào Git. Không viết scraper.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset sources
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source public_service_official
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source uit_vsfc
.\.venv\Scripts\python.exe -m pytest -q
Get-Content docs\DATASET_DECISION.md
Get-Content docs\DATA_REQUEST_TEMPLATE.md
```

**HUMAN GATE:** Nghiên cứu viên/người hướng dẫn liên hệ nguồn; lưu email/văn bản cấp quyền ngoài Git; đánh dấu rõ được phép dùng dữ liệu để nghiên cứu, train, chia sẻ artifact hay không. **Không có command nào có thể thay quyết định này.**  
**PASS:** Registry+decision+request template hợp lệ; không download; trạng thái chưa được duyệt hiển thị `BLOCKED`. Nếu không có nguồn chính, chuyển nhánh B để phát triển code; không claim hoàn tất dataset nghiên cứu.

### STEP 03 — Benchmark adapter & optional download

**Dependency:** STEP 02; human license review/approval **nếu muốn download**. **Output:** adapter + benchmark manifest (hoặc chỉ synthetic tests nếu bị block).

**PROMPT CODEX — 03:**

> Triển khai STEP 03. Viết adapter `pfa.data.adapters.uit_vsfc` cho benchmark `uitnlp/vietnamese_students_feedback`. Tra danh sách các Parquet file train/validation/test thực tế qua Hugging Face dataset viewer API hoặc branch `refs/convert/parquet` và giữ nguyên schema `sentence`, `sentiment`, `topic`. Nhãn tham chiếu theo card: sentiment `0 negative, 1 neutral, 2 positive`; topic `0 lecturer, 1 training_program, 2 facility, 3 others`. Tạo CLI `dataset benchmark inspect`, `dataset benchmark fetch --source uit_vsfc --approval-ref <non-sensitive-id>`, `dataset benchmark verify --source uit_vsfc`. Lệnh fetch phải từ chối nếu registry chưa có quyền/phạm vi sử dụng được xác nhận; không bỏ qua gated sources; không dùng `trust_remote_code`, không tự chạy Python từ dataset repo. Lưu local `data/benchmarks/uit_vsfc/` và `manifest.json` với từng URL/split, SHA256, schema, row count, thời gian, resolved revision/etag nếu có. In cảnh báo đây là data giáo dục, không phải dữ liệu dịch vụ công. Dùng offline synthetic test để kiểm adapter, error 403/404/offline, checksum. Không hard-code coi 16.175 mẫu là kết quả tải thành công; kiểm tra thực tế sau download.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark inspect
# CHỈ sau khi có approval_ref hợp lệ và đã ghi trong registry:
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark fetch --source uit_vsfc --approval-ref "APPROVAL-ID"
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark verify --source uit_vsfc
.\.venv\Scripts\python.exe -m pytest -q
Get-ChildItem data\benchmarks\uit_vsfc -Recurse
```

**HUMAN GATE:** Xác nhận benchmark được sử dụng trong phạm vi được phép; không xem `license unknown` là đồng nghĩa với giấy phép mở.  
**PASS:** 11.426/1.583/3.166 split theo card nếu tải thành công, metadata và hashes khớp; nếu blocked thì test synthetic PASS và status là `BLOCKED_LICENSE`, không được tô thành PASS của dữ liệu thật.

### STEP 03B — REAL DATASET DISCOVERY & ACQUISITION [ƯU TIÊN HIỆN TẠI]

**Vị trí:** Sau STEP 03 và trước STEP 04; có thể thực hiện khi các bước 04–08A đã code xong. **Mục đích:** Khắc phục khoảng trống giữa "có source registry" và "có file CSV/JSONL thật được phép dùng".

**Dependency:** STEP 02 (registry/permission audit), STEP 04 importer đã sẵn ở repository hiện tại. **Output kỹ thuật:** candidate shortlist + request package + CLI acquisition metadata/preflight/secure receive/verify + receipts/handoff; **output nghiên cứu:** chỉ có khi người có thẩm quyền cho phép và thực sự bàn giao một file hợp lệ.

**Nguồn ưu tiên theo thứ tự:**

1. `authorized_agency_export` — cơ quan quản lý cung cấp **file đã giảm thiểu/ẩn danh**, kèm văn bản quyền mục đích sử dụng, quy định lưu/xóa và phạm vi huấn luyện/công bố.
2. `public_service_official` — danh sách phản ánh trên cổng quốc gia: hiện chỉ xác minh **có trang công khai**, **chưa xác minh quyền tải hàng loạt/API/ML training**; không thu thập tự động tới khi có bằng chứng phù hợp.
3. Dataset phản ánh công/tương đương có giấy phép rõ ràng và được phê duyệt theo scope; không lấy UIT-VSFC làm kết quả chính vì domain giáo dục.

**PROMPT CODEX — 03B (đầy đủ, sao chép phần dưới; có file riêng `STEP_03B_REAL_DATA_ACQUISITION_CODEX_PROMPT.md`):**

~~~~text
# CODEX PROMPT — STEP 03B: REAL DATASET DISCOVERY & ACQUISITION

## Vai trò và bối cảnh

Bạn là Principal Data Engineer, Data Governance Engineer và ML Research Engineer cho dự án **Public Service Feedback AI** tại repository hiện tại.

Trạng thái do người dùng báo cáo tính tới 2026-11-04:
- STEP 01–08A: technical PASS; **353 offline tests PASS** tại STEP 08A.
- STEP 02: có registry 7 nguồn, permission evidence và audit trail, fail-closed.
- STEP 03: adapter benchmark; không được phép tải thực.
- STEP 04: import CSV/JSONL, privacy screening, kiểm duyệt, storage, manifest.
- STEP 05: profiling/quality/privacy/duplicate audit.
- STEP 06: taxonomy + annotation contract; chờ human approval.
- STEP 07A: sampling, independent annotation, agreement, adjudication synthetic.
- STEP 08A: versioning, group-aware splitting, holdout synthetic.
- **Không có tập dữ liệu phản ánh công thật**, mọi external source hiện `effective_scope=NONE`.

Hãy triển khai bước mới **STEP 03B**, chèn về mặt logic **sau STEP 03, trước STEP 04**, nhưng KHÔNG xóa/viết lại các STEP đã PASS. Bước này nhằm tạo con đường có thể kiểm toán để nhận dữ liệu nghiên cứu *thực* khi được phép: **source discovery → provenance/terms review → human permission → secure handoff → receipt/verification → STEP 04 import**.

## TASK 0 — Inspect & baseline

1. Đọc `README.md`, `pyproject.toml`, `docs/architecture.md`, `MASTER_PLAN_CODEX_PUBLIC_FEEDBACK_AI_V2_1.md` nếu có; kiểm tra git status.
2. Đọc code STEP 02: registry, assessment, permissions, evidence, audit; STEP 03: benchmark; STEP 04: `official.py`, `official_io.py`, schema, review; STEP 05: quality/PII; CLI/tests hiện có.
3. Chạy pytest, Ruff và doctor trước khi sửa, báo baseline thật.
4. Lập implementation checklist. Tái sử dụng permission gate và source IDs; không tự tạo hệ thống phê duyệt song song.

## TASK 1 — Discovery registry & candidate decision report (metadata only)

- Giữ nguyên 7 `source_id` đã có. Bổ sung thông tin *nếu chưa có* để theo dõi acquisition: `data_owner/contact_route`, `contact_status`, `dataset_role`, `available_fields`, `coverage_period`, `estimated_records`, `data_format`, `handoff_method`, `terms_evidence_ref`, `license_status`, `permitted_scopes`, `privacy_risk`, `last_checked`, `reviewed_by`, `next_action`.
- Dùng thêm `configs/acquisition_candidates.yaml` hoặc mở rộng registry theo kiến trúc hiện hữu; không bịa tên email cá nhân, địa chỉ nhận dữ liệu, giấy phép, endpoint, volume, SLA hay trạng thái chấp thuận.
- Ít nhất lập hồ sơ 3 luồng: `authorized_agency_export` (ưu tiên), `public_service_official` (ứng viên, chưa có bulk-use authorization), `licensed_open_feedback` (nhóm/slot candidate, chỉ tạo `source_id` mới nếu registry validation cho phép và có nguồn thật đã được xác minh). `uit_vsfc` tiếp tục là benchmark giáo dục, KHÔNG phải dữ liệu chính.
- Tạo bảng quyết định `docs/REAL_DATA_SOURCE_SHORTLIST.md`: domain fit, PII, quyền, phương thức xin, định dạng, metadata, feasibility, rủi ro đại diện mẫu, evidence và next action; phân biệt `VERIFIED`, `UNVERIFIED`, `NOT_AVAILABLE`.
- Không thực hiện HTTP download, crawl, scrape, browser automation hay API enumeration của các trang phản ánh. Cho phép tài liệu research metadata do con người kiểm tra; không coi trang hiển thị công khai là quyền train ML.

## TASK 2 — Human data request package

Tái sử dụng `docs/DATA_REQUEST_TEMPLATE.md`; tạo/gia cố:
- `docs/REAL_DATA_REQUEST_CHECKLIST.md` và `docs/DATA_TRANSFER_SPEC.md` bằng tiếng Việt.
- Mẫu xin **2.000–5.000 phản ánh tiếng Việt đã giảm thiểu dữ liệu/ẩn danh**, nếu có, kèm dữ liệu `feedback_id` thay thế, `content` đã rà soát, `created_at` (nguồn/timezone), `domain`, `agency` mã hóa, `processing_status`, `response_date` tùy quyền. Không yêu cầu CCCD, họ tên, số điện thoại, địa chỉ, mã hồ sơ gốc.
- Điều khoản cần chủ dữ liệu xác nhận: mục đích nghiên cứu, xử lý nội bộ, training, evaluation, xuất bản thống kê/weights/text examples, quyền chia sẻ, thời gian lưu/xóa, biện pháp ẩn danh, phương thức giao bảo mật, đầu mối và cách yêu cầu thu hồi, xử lý các quy định liên quan.
- Tạo form human approval/evidence metadata với reference ID trỏ đến tài liệu lưu ngoài Git; KHÔNG tự cấp quyền, ký thay, gọi email hay gửi yêu cầu tự động.
- Tài liệu quy trình tiếp nhận an toàn: kênh trao đổi được đồng ý, thư mục bảo vệ riêng, không email/file share công khai nếu có PII, không đưa bản gốc vào Git, cloud/sync hoặc tool telemetry mà chưa được phép.

## TASK 3 — Acquisition state machine & CLI (không đọc file thật nếu chưa được phép)

Tạo module ở `src/pfa/data/acquisition/` hoặc tương đương, tái sử dụng các API đã có.

Định nghĩa trạng thái có audit:
`DISCOVERED → CONTACT_PENDING → REQUESTED → PERMISSION_REVIEW → APPROVED_FOR_SCOPE → READY_FOR_HANDOFF → RECEIVED_QUARANTINED → VERIFIED_RECEIPT → READY_FOR_STEP04`, và nhánh `REJECTED`, `REVOKED`, `BLOCKED`, `NOT_AVAILABLE`.

Lưu ý: không phải mọi trạng thái phải có command chuyển tự động; **bất kỳ state có quyền** phải phụ thuộc vào human decision đã được STEP 02 xác minh.

CLI mục tiêu (điều chỉnh theo conventions của repo, tài liệu và tests phải khớp code thật):

1. `python -m pfa.cli dataset acquisition status --source authorized_agency_export` — metadata/state, không đọc dữ liệu.
2. `python -m pfa.cli dataset acquisition request-pack --source authorized_agency_export --output reports/acquisition/request_pack.md` — tạo checklist/tài liệu **không chứa dữ liệu thật**.
3. `python -m pfa.cli dataset acquisition preflight --source authorized_agency_export --scope internal_analysis` — permission/evidence/expiry/retention/source check; không mở file. Sử dụng scope thực tế được hỗ trợ bởi governance, ghi rõ nếu `internal_analysis` không đủ cho training/publication.
4. `python -m pfa.cli dataset acquisition receive --source authorized_agency_export --input PATH --approval-ref EVIDENCE_ID --handoff-id HANDOFF_ID` — chỉ cho phép sau preflight hợp lệ; kiểm tra extension CSV/JSONL, file size, symlink/path, conflict, giới hạn tài nguyên; tiếp nhận nội dung file qua protected/quarantined staging; ghi receipt SHA256, size, file format, source, trusted handoff/ref, time, handling policy; atomic operations; không có tùy chọn bỏ gate.
5. `python -m pfa.cli dataset acquisition verify --receipt-id RECEIPT_ID` — đối chiếu manifest/checksum/permission/revocation; không tự publish.
6. `python -m pfa.cli dataset acquisition smoke` — toàn pipeline trên synthetic fixture trong thư mục tạm, không cần bất kỳ real permission nào và không tự tạo approval "thật".

Đảm bảo `receive` từ chối **trước khi mở/đọc bytes của file thật** nếu permission không được phép; không đặt tên `--source synthetic_demo` để mở bất kỳ arbitrary file nào chứa dữ liệu thật. Fixture synthetic phải nằm trong path xác định và có checksum/provenance.

## TASK 4 — Secure handoff receipt & integration with STEP 04

- Dùng storage đã có của STEP 04 (`data/private`/`data/staging` hay tương đương), không tạo hệ thống raw storage riêng không có kiểm soát.
- Chỉ cho phép `CSV`, `JSONL` ở v1. Không hỗ trợ nén/Excel/API remote chưa được kiểm tra.
- Chặn symlinks, directory traversal, huge files, overwrite, path escape; xử lý import bằng chunks khi cần. Preserve nguyên bản nhận bàn giao trong vùng hạn chế theo retention đã được duyệt; không echo nội dung / mã hồ sơ / PII vào log/manifest report.
- Receipt metadata: `source_id`, `handoff_id`, `approval_ref` (nonsensitive), `scope`, `source_manifest_ref`, `sha256`, `size_bytes`, `received_at`, `file_format`, `storage_reference`, `status`, `audit_ref`, `retention_policy_ref`. Receipt và raw file phải bảo vệ quyền truy cập; output CLI chỉ hiển thị ID, counts, status không hiển thị raw path nếu nhạy cảm.
- Handoff `READY_FOR_STEP04` chỉ sau integrity + evidence validation; **STEP 04** vẫn phải tự kiểm tra permission/privacy trước khi preview/import/commit. Không cho receipt tự bỏ qua PII review.
- Nếu STEP 04 CLI chỉ nhận `--input`, cung cấp đường dẫn protected staging từ receipt trong tài liệu nội bộ, không in trên màn hình public/logs. Ưu tiên giao diện tích hợp receipt nếu đã có, tránh breaking change.
- Không tự động gọi `dataset official import --mode commit` sau `receive`.

## TASK 5 — Governance, audit and legal constraints

- Phải phân biệt `access/read`, `internal_analysis`, `train`, `publish`, `share` và `derivative models` theo các scopes thực sự tồn tại. Không tự suy ra training permission từ quyền xem trang web hoặc quyền download.
- Support expiry, revocation and retention requirements; fail closed khi evidence/audit sai/missing.
- Không scrape/crawl website phản ánh chính phủ; nếu bên cấp dữ liệu xác nhận có API chính thức và quyền sử dụng, chỉ **thiết kế interface**, triển khai connector cụ thể trong change request riêng sau human approval.
- Việc tìm kiếm các trang/tài liệu public bằng tay để đánh giá metadata không được biến thành bulk content capture.
- Code không tự tuyên bố đã đáp ứng đầy đủ luật bảo vệ dữ liệu; yêu cầu privacy/legal reviewer kiểm tra nghĩa vụ thực tế.

## TASK 6 — Offline tests & security regression

Ít nhất phải test:
- nguồn không tồn tại / không có permission / expired / revoked / inconsistent audit;
- pending -> no file read (mock file read để kiểm chứng);
- empty approval / fake approval bị chặn; thiếu scope train khác scope analysis;
- synthetic smoke nhận file fixture an toàn, không biến thành research data;
- file không tồn tại, định dạng lạ, symlink, path traversal, file quá lớn, file thay đổi trong khi nhận;
- SHA256 mismatch, corrupt/tampered receipt, retry/idempotency, duplicate handoff ID, atomic cleanup;
- không log raw feedback/PII/secret; Git không track storage/receipts;
- handoff STEP 04 vẫn enforce privacy review;
- regression tất cả 353 tests trở lên (số thực tế có thể tăng).

Tests offline, không gọi web/network, không tải dữ liệu thật, không liên hệ cơ quan bên ngoài.

## TASK 7 — Documentation + acceptance

Tạo:
- `docs/REAL_DATA_ACQUISITION.md` (step-by-step pipeline, commands, source priority and blockers),
- `docs/REAL_DATA_SOURCE_SHORTLIST.md`,
- `docs/REAL_DATA_REQUEST_CHECKLIST.md`,
- `docs/DATA_TRANSFER_SPEC.md`,
- `docs/ACQUISITION_SECURITY.md`.

Cập nhật README, architecture docs, CLI help. Không thay đổi phiên bản taxonomy hoặc kết quả các STEP đã PASS.

Tiêu chí **TECHNICAL PASS**: CLI status/request-pack/preflight/receive/verify/smoke có code thật; synthetic smoke PASS; unapproved real receive BLOCKED; receipt/sha/atomic/quarantine và integration STEP 04 được kiểm thử; pytest + Ruff PASS; không có real-data access.

Tiêu chí **REAL ACQUISITION PASS** (khác với technical): đã nhận được file từ nguồn hợp pháp, approval theo scope, human custody review, verified secure receipt, và STEP 04 có thể nhập preview theo quyền. Không được tuyên bố PASS khi chỉ có synthetic.

### Báo cáo cuối bắt buộc

- Files created/modified;
- Candidate matrix và source quyền/coverage chưa xác minh;
- CLI thật, stdout/exit codes;
- Synthetic smoke, receipt/sha result;
- Permission-before-read evidence;
- Regression pytest, Ruff;
- Human actions cần làm (người liên hệ, pháp lý, privacy/custodian);
- Real-data blockers và trạng thái bàn giao STEP 04.

Return riêng các trạng thái:

```
TECHNICAL_IMPLEMENTATION: PASS / PARTIAL / FAIL
REAL_DATA_ACQUISITION: NOT_STARTED / PERMISSION_PENDING / REQUESTED / RECEIVED_QUARANTINED / VERIFIED
REAL_DATASET: BLOCKED_PERMISSION / AVAILABLE
STEP04_HANDOFF: BLOCKED / READY
```

**Hãy inspect repo và chạy baseline, sau đó implement STEP 03B ngay. Không thu thập dữ liệu từ internet hoặc nguồn thực trong bước code này.**
~~~~

**NGƯỜI CHẠY — PowerShell (lệnh CONTRACT cần Codex hiện thực, chỉ chạy sau khi nhận được báo cáo technical implementation):**

```powershell
cd D:\congviec\nckh-van
# Kiểm tra code đã có trước khi Codex sửa
.\.venv\Scripts\python.exe -m pfa.cli doctor
.\.venv\Scripts\python.exe -m pytest -q
git status --short
# Sau khi Codex triển khai 03B, chỉ chạy các lệnh KHÔNG mở dữ liệu thật:
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition status --source authorized_agency_export
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition request-pack --source authorized_agency_export --output reports/acquisition/request_pack.md
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition preflight --source authorized_agency_export --scope internal_analysis
# Preflight dự kiến BLOCKED_PERMISSION khi chưa có quyền, đây là kết quả ĐÚNG.
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
git diff --check
```

**CHỈ KHI ĐÃ CÓ VĂN BẢN CẤP QUYỀN PHÙ HỢP, QUY TRÌNH BÀN GIAO VÀ FILE THẬT Ở VÙNG BẢO VỆ:**

```powershell
# Các chuỗi trong <...> phải thay bằng tham số THẬT đã được xác thực.
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition preflight --source authorized_agency_export --scope internal_analysis
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition receive --source authorized_agency_export --input "D:\secure-data\feedback_authorized.csv" --approval-ref "<real-evidence-id>" --handoff-id "<real-handoff-id>"
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition verify --receipt-id "<receipt-id-from-actual-output>"
# Sau handoff VERIFIED, dùng đúng path/receipt và hướng dẫn của STEP 04 tại repository để chạy mode preview.
# KHÔNG tự động commit và KHÔNG nhận raw PII đã được coi là an toàn.
```

**HUMAN GATE (không được để Codex làm thay):** người hướng dẫn/đơn vị sở hữu xác nhận phạm vi, ký/ghi nhận bằng chứng, chọn đường chuyển file bảo mật; data custodian đối chiếu checksum, giấy phép/retention và nhận bàn giao; privacy reviewer duyệt dữ liệu xử lý theo STEP 04/05. Nếu xin phép chưa thành công, đánh dấu `PERMISSION_PENDING` và tiếp tục nhánh synthetic, không giả lập nguồn chính.

**PASS kỹ thuật:** `status`, `request-pack`, `preflight`, `receive`, `verify`, `smoke` hoạt động bằng synthetic fixture; đọc dữ liệu thật bị block nếu chưa có quyền; receipt SHA256/manifest, atomic/quarantine và regression tests PASS.  
**PASS acquisition thật:** có approved scope + transferred real file + verified receipt + sẵn sàng STEP 04 preview. Hai PASS này **phải báo tách biệt**.

### STEP 04 — Official authorized import + safe storage

**Dependency:** STEP 02 và STEP 03B cho đường dữ liệu thật, permission approved; có CSV/JSONL đã kiểm tra nguồn gốc hoặc dùng synthetic fixtures để test. **Output:** import command, schema/data contract, quarantine, không lộ PII.

**PROMPT CODEX — 04:**

> Triển khai STEP 04. Thiết kế `configs/feedback_schema_v1.yaml` và Pydantic models gồm `feedback_id`, `source_id`, `source_record_hash`, `text_redacted`, `received_at`, `ingested_at`, `agency_code`, `domain_code`, `status`, `permission_ref`, `annotation_status`. Tạo `dataset import-official --input <file> --source-id authorized_agency_export --approval-ref <id> --dry-run` và chế độ import thật chỉ sau permission check; riêng `synthetic_demo` cho phép `--dry-run` và lưu fixture với watermark SYNTHETIC nhưng không bao giờ bật chế độ research-training; JSONL/CSV UTF-8 và BOM, file nhiều dòng, schema errors rõ ràng. Tối thiểu dữ liệu đầu vào được quản lý ở vùng hạn chế, không log raw text, token, ID, đường dẫn chứa secret; redact PII sớm nhất có thể; records nghi ngờ chuyển `quarantine/requires_human_privacy_review`, không tự ghi văn bản chưa ẩn danh sang processed. Có dry-run báo số dòng/schema/PII risk dưới dạng tổng hợp không echo thông tin cá nhân. Tạo chính xác `data/fixtures/synthetic_feedback.csv` chỉ chứa ví dụ giả có đánh dấu `SYNTHETIC` để lệnh dry-run của bước này chạy được. Tests với fixture synthetic (phone/email/ID/address, malformed row), audit events. Xây `docs/PRIVACY_REVIEW.md` và retention/delete procedures; không tự khẳng định ẩn danh hoàn toàn.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset import-official --input data\fixtures\synthetic_feedback.csv --source-id synthetic_demo --dry-run
.\.venv\Scripts\python.exe -m pytest -q
# Chỉ sau khi có file thật trong vùng hạn chế VÀ văn bản cho phép:
.\.venv\Scripts\python.exe -m pfa.cli dataset import-official --input "C:\secure-data\authorized_feedback.csv" --source-id authorized_agency_export --approval-ref "APPROVAL-ID"
```

**HUMAN GATE:** Cơ quan/nhóm xác nhận quyền xử lý và những trường được tiếp nhận; người có quyền kiểm tra các bản ghi cần privacy review trên máy bảo mật.  
**PASS:** Synthetic importer test PASS, raw PII không xuất log/Git; import thật chỉ PASS khi có quyền, schema đạt và privacy quarantine được xử lý.

### STEP 05 — Quality profiling, clean, redact and duplicate audit

**Dependency:** STEP 04 (hoặc synthetic fixtures). **Output:** data profiling report, pipeline xử lý có version và bản ghi bị flag.

**PROMPT CODEX — 05:**

> Triển khai STEP 05, các module `profile`, `validate`, `clean`, `redact`, `duplicate`. CLI `dataset profile --source ...`, `dataset preprocess --source ...`, `dataset audit-privacy --source ...`. Kiểm tra nulls, length, UTF-8/Vietnamese diacritics, thời gian bất hợp lệ, phân bố agency/domain, language, spam, near-duplicate groups. Clean giữ chữ có dấu và phủ định `không/chưa/chẳng`; không tự sửa meaning; mọi transform có version/log số record thay đổi. Redaction hỗ trợ email/phone/CCCD/mã hồ sơ pattern, bổ sung human review cho tên/ngữ cảnh/địa chỉ (regex không đủ), cấm in PII ví dụ vào report. Duplicate/near-duplicate chỉ flag group, không tự xóa hàng loạt. Test synthetic cho negation, noise, timezone, PII và logs; report chỉ được chứa aggregate và sample được kiểm tra đã ẩn danh.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset profile --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset preprocess --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset audit-privacy --source synthetic_demo
.\.venv\Scripts\python.exe -m pytest -q
Get-ChildItem reports\dataset
```

**HUMAN GATE:** Rà soát thủ công một mẫu ngẫu nhiên văn bản sau ẩn danh và tất cả case nghi ngờ rò PII; xác nhận quy tắc clean không đổi ngữ nghĩa.  
**PASS:** Không còn PII trong test fixtures đã redacted và public logs; có report audit + lineages; nếu data thật chưa có, chỉ PASS code/synthetic, `BLOCKED_REAL_DATA` cho nghiên cứu.

### STEP 06 — Taxonomy & annotation handbook

**Dependency:** 02,05; không cần dữ liệu thật để hoàn thiện công cụ. **Output:** taxonomy version, guideline, schema annotation.

**PROMPT CODEX — 06:**

> Triển khai STEP 06. Tạo `configs/taxonomy_v1.yaml` chứa 8 topic labels theo master plan, 3 sentiment labels và 3 severity labels + `unknown` khi không đủ bằng chứng. `requires_review` thuộc workflow, không nằm trong supervised severity class. Tạo `docs/ANNOTATION_GUIDELINES.md` bao gồm định nghĩa từng nhãn, ví dụ ghi SYNTHETIC, trường hợp ranh giới, phủ định, phản ánh nhiều chủ đề, văn bản hỏi đáp không phải phàn nàn, nhãn `other`, severity rubric dựa impact/delay/risk có tham chiếu metadata/SLA nếu được cung cấp; chưa có SLA thì không suy đoán. Tạo file schema và template annotation CSV/JSONL, validate CLI hỗ trợ `--schema-only` khi file chưa có nhãn. Không tự dùng LLM prediction làm ground-truth. Bổ sung versioning taxonomy; tests invalid labels, unknown severity, missing justification.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation template --output data\fixtures\annotation_template.csv
.\.venv\Scripts\python.exe -m pfa.cli annotation validate --input data\fixtures\annotation_template.csv --schema-only
Get-Content docs\ANNOTATION_GUIDELINES.md
.\.venv\Scripts\python.exe -m pytest -q
```

**HUMAN GATE:** Người hướng dẫn và người gán nhãn duyệt taxonomy/rubric; chốt rule `other`, mixed topics, severity.  
**PASS:** Guideline v1 signed-off, schema ổn định, các nhãn có ví dụ và tie-break rule rõ.

### STEP 07 — 200-record pilot, dual annotation & agreement

**Dependency:** STEP 06, data thật đã được phép và ẩn danh. **Output:** pilot + disagreement report + frozen guideline v1.x.

**PROMPT CODEX — 07:**

> Triển khai STEP 07. CLI `annotation sample-pilot --source ... --n 200`, `annotation export --annotator A|B --pilot pilot_v1`, `annotation import --annotator ... --input ...`, `annotation agreement --pilot pilot_v1`, `annotation adjudicate --pilot pilot_v1`. Lấy 200 mẫu từ dữ liệu chính được phép, có cố gắng phủ agency/topic/time nhưng không coi pilot là ngẫu nhiên đại diện khi cố oversample; lưu sampling seed và logic. Hai người annotator làm độc lập, ít nhất 20–30% toàn tập cuối được double annotate (đây là target dự án, tùy nhân lực). Agreement riêng topic/sentiment/severity bằng Cohen's kappa + raw agreement; báo lớp hiếm và tranh chấp, không ghi đè nhãn gốc. Adjudication tạo gold label và lưu người duyệt/thời điểm; `unknown` được hỗ trợ khi thiếu ngữ cảnh. Tests fake annotation pairs có kappa biết trước. Nếu không có authorized data, command chặn `BLOCKED_ON_DATA`; chỉ test với synthetic.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation sample-pilot --source authorized_agency_export --n 200
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator A --pilot pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator B --pilot pilot_v1
# Người A/B điền file trên máy kiểm soát truy cập rồi import:
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator A --input "C:\secure-data\pilot_A.csv"
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator B --input "C:\secure-data\pilot_B.csv"
.\.venv\Scripts\python.exe -m pfa.cli annotation agreement --pilot pilot_v1
.\.venv\Scripts\python.exe -m pytest -q
```

**HUMAN GATE:** Ít nhất hai annotator gán độc lập; người thứ ba/nhóm hòa giải; sửa rubric nếu tranh chấp cao. **Kappa ≥ 0.7 là mục tiêu tham khảo, không phải kết quả được bảo đảm**; nếu dưới ngưỡng cần phân tích nguyên nhân, chứ không tự đổi nhãn cho đẹp.  
**PASS:** 200 real approved examples (hoặc BLOCKED), dual labels, kappa, adjudicated gold, version guideline đã duyệt; không có dữ liệu cá nhân rò trong report.

### STEP 08 — Full corpus labeling, frozen dataset version and leakage-free splits

**Dependency:** STEP 07 PASS thực. **Output:** `service_feedback_v1`, dataset card, locked holdout, lineage.

**PROMPT CODEX — 08:**

> Triển khai STEP 08. Import nhãn production đã adjudicated từ annotation workflow, target 2.000–5.000 records nếu có (không làm giả số mẫu). Tạo `dataset build --version service_feedback_v1 --seed 42` và `dataset check-leakage --version ...`; schema version, taxonomy version, permission refs, preprocessing checksum, SHA256, source coverage/time, class distribution, missingness, bias và known limitations trong DATASET_CARD. Split train/val/test mục tiêu 70/15/15 nếu khả thi; group-aware dựa same case/source_record/thread/near-duplicate để không trùng giữa tập; stratify theo primary task khi feasible và báo rủi ro nhãn hiếm hoặc phân bố khác nhau giữa tasks. Đánh giá thêm temporal holdout nếu có timestamp thật và đủ mẫu; không dùng `ingested_at` giả làm event time. Freeze test checksum/IDs; cấm đụng test trong hyperparameter tuning. Tạo reports về exact/near duplicates, class imbalance, timespan, group overlap; no zero-denominator bugs. Command fail khi thiếu gold label/data approval, không export unredacted text.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset build --version service_feedback_v1 --seed 42
.\.venv\Scripts\python.exe -m pfa.cli dataset check-leakage --version service_feedback_v1
.\.venv\Scripts\python.exe -m pytest -q
Get-ChildItem data\processed\service_feedback_v1
Get-Content docs\DATASET_CARD.md
```

**HUMAN GATE:** Chủ nhiệm nghiên cứu ký duyệt dataset card, representative limits, coverage, rights, quality of gold labels; chốt held-out test.  
**PASS:** frozen manifest, split files + sha256, no cross-split group overlap, đủ nhãn theo protocol; nếu không có real data dừng ở code tests.

### STEP 09 — TF-IDF baselines (Logistic Regression + SVM)

**Dependency:** STEP 08 PASS thực. **Output:** 6 run baseline (3 tasks × 2 models) hoặc blocker hợp lệ.

**PROMPT CODEX — 09:**

> Triển khai STEP 09. CLI `ml train-baselines --dataset service_feedback_v1` và `ml train-baseline --task topic|sentiment|severity --model lr|svm`. Dùng sklearn Pipeline TF-IDF word ngrams và char ngrams (configurable), LogisticRegression, LinearSVC; fit vectorizer chỉ train; lựa hyperparams chỉ train/validation (hoặc group-CV train), bỏ `unknown` khỏi severity targets nhưng báo số excluded; safe imbalance handling; config YAML, seed, package lock/hash, training logs. Báo validation Macro-F1 + per-class + confusion matrix, speed; model artifact gồm label encoder/version, data manifest hash. Không fit/inspect test trước STEP 11. Viết tests tiny synthetic không mạng; pipeline one command từng task, metrics reproducible.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ml]"
.\.venv\Scripts\python.exe -m pfa.cli ml train-baselines --dataset service_feedback_v1
.\.venv\Scripts\python.exe -m pytest -q
Get-ChildItem reports\experiments -Recurse
```

**HUMAN GATE:** Xem phân bố từng nhãn, xác nhận có đủ samples/class; nếu class hiếm thì điều chỉnh thu thập/annotation (không tự gộp nhãn sau khi đã xem test).  
**PASS:** 6 runs có validation metrics và artifacts; nếu data chưa đủ thì blocker + synthetic integration tests PASS.

### STEP 10 — PhoBERT training

**Dependency:** STEP 08 + 09; GPU không bắt buộc cho tests, rất hữu ích khi train. **Output:** 3 model runs + resource report.

**PROMPT CODEX — 10:**

> Triển khai STEP 10, finetune `vinai/phobert-base` với torch/transformers, lựa chọn 3 models độc lập cho topic/sentiment/severity để dễ đánh giá. PhoBERT cần input có Vietnamese word segmentation phù hợp (VnCoreNLP/RDRSegmenter hoặc tokenizer được kiểm tra); cùng preprocessing ở train và predict. Dùng split frozen từ STEP 08, validation early stopping, learning rate config, max seq length, batch, gradient accumulation, seed, model revision và hash; không tune trên test, không mặc định download heavyweight weights trong unit tests. CLI `ml train-phobert --dataset ... --task ... --device auto`, hỗ trợ `--dry-run`, resume checkpoints, CPU smoke fixture và CUDA diagnostics. Log train walltime, memory, best checkpoint, validation metrics; không giả vờ rằng CPU training nhanh hay mô hình chắc thắng baseline. Viết mock tests offline.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[ml]"
.\.venv\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task topic --device auto
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task sentiment --device auto
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task severity --device auto
```

**HUMAN GATE:** Cân nhắc GPU/VRAM, tài nguyên và thời gian; kiểm tra giấy phép sử dụng model/weights và dữ liệu train.  
**PASS:** 3 run directories, versions+seeds+val report, inference local thành công; không có raw text trong logs.

### STEP 11 — Final model comparison, calibration, abstention and registry

**Dependency:** STEP 09/10; holdout frozen. **Output:** research-ready comparison, selected model artifact, policy.

**PROMPT CODEX — 11:**

> Triển khai STEP 11. Khóa trước metrics, threshold selection và model selection policy dựa trên validation. `ml evaluate --dataset ... --split test --all`, `ml compare --dataset ...`, `ml registry promote --run-id ...`. Đánh giá test final trên cùng test version: Accuracy, macro-F1, weighted-F1, per-class P/R/F1, normalized confusion matrix, severity-high recall, latency/throughput, bootstrap 95% CI nếu đủ mẫu và báo uncertainty trên nhãn hiếm. Confidence scores từ LogisticRegression/PhoBERT cần kiểm tra calibration trên validation; LinearSVC không coi margin là probability, nếu calibrate phải làm đúng trên train/val, không test. Có threshold `requires_review` từ validation và đo review_rate, coverage vs risk; không tự phê duyệt severe case. Error analysis chỉ xuất redacted/safe ID, không raw text. Promoted model phải có signature+label mapping+preprocessing version và rollback. Không nhìn test rồi retune.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pfa.cli ml evaluate --dataset service_feedback_v1 --split test --all
.\.venv\Scripts\python.exe -m pfa.cli ml compare --dataset service_feedback_v1
.\.venv\Scripts\python.exe -m pytest -q
Get-Content reports\experiments\comparison.md
```

**HUMAN GATE:** Chốt mục đích model: triage hỗ trợ, không tự quyết định hành chính; duyệt ngưỡng review, acceptable critical miss, những nhãn không đủ dữ liệu. Không tự đặt F1=0.9 như mục tiêu chắc chắn.  
**PASS:** 3-family×3-task comparison trên cùng frozen test; model registry có bản promoted, policy review và reproducibility report.

### STEP 12 — FastAPI predict service

**Dependency:** STEP 11 hoặc synthetic mock cho contract tests. **Output:** `POST /api/v1/predict`, /health, /ready, schema/API docs.

**PROMPT CODEX — 12:**

> Triển khai STEP 12. FastAPI app dùng Pydantic models, endpoint `POST /api/v1/predict`, `GET /health`, `GET /ready`, `GET /api/v1/model-info` (không lộ private data). Trả topic/sentiment/severity, calibrated confidence nếu có, `requires_review`, model version/data taxonomy version, input warnings; validation độ dài/lang, timeout/error handling. Nạp promoted artifacts một lần khi startup, không train mỗi request; `/ready=503` nếu model thật không sẵn, mock chỉ trong test. Logging không lưu raw PII; CORS theo allowlist, rate limiting/size limits, auth plan rõ trước khi public. Viết unit/integration tests TestClient và OpenAPI schema snapshot; pipeline từ segment → vectorize/tokenize → predict giống train. Không để dùng output AI như quyết định cuối cùng.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[api]"
.\.venv\Scripts\python.exe -m uvicorn pfa.api.main:app --host 127.0.0.1 --port 8000 --reload
# Terminal mới:
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
```

**HUMAN GATE:** Không mở port ra Internet trước security review.  
**PASS:** endpoint contract test, model version matched, missing model returns honest 503, no PII in logs.

### STEP 13 — PostgreSQL, human review, RBAC and audit

**Dependency:** STEP 12; local DB optional Docker, có thể dùng PostgreSQL cài local. **Output:** migrations, review queue, correction workflow.

**PROMPT CODEX — 13:**

> Triển khai STEP 13 bằng SQLAlchemy 2 + Alembic + PostgreSQL. Entities `feedback`, `prediction`, `review_event`, `model_version`, `source_registry` với constraints/indexes, timezones, foreign keys; chỉ lưu `text_redacted`, không lưu raw PII theo mặc định. `POST/GET /api/v1/feedback`, `GET /api/v1/reviews/queue`, `PATCH /api/v1/reviews/{id}`; reviewer edit và adjudication append-only audit, giữ prediction lịch sử. Auth cho 3 role admin/reviewer/analyst, RBAC theo endpoint, reject unauthorized writes, no hardcoded production credentials, secret from env; paging/filter, optimistic concurrency để tránh review overwrite. Unit tests SQLite khi hợp lý và integration tests Postgres; migration không reset production. Docker Compose chỉ tùy chọn cho local DB, không kéo các images lớn khác.

**NGƯỜI CHẠY:**

```powershell
# Chỉ khi chủ động chọn Docker và máy có dung lượng:
docker compose up -d db
.\.venv\Scripts\python.exe -m pip install -e ".[api]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
```

**HUMAN GATE:** Tạo credentials trong `.env` cục bộ, phân quyền người dùng; kiểm tra retention/deletion policy.  
**PASS:** migrations và role tests PASS trên local; không lưu raw PII; audit không bị sửa trực tiếp bằng API.

### STEP 14 — Analytics, trend, alerts, dashboard

**Dependency:** STEP 13 hoặc synthetic DB fixtures. **Output:** dashboard, KPI dictionary, safe alert tests.

**PROMPT CODEX — 14:**

> Triển khai STEP 14. Backend `GET /api/v1/analytics/summary`, `/trends`, `/topics`, `/alerts`; Streamlit + Plotly dashboard đọc API có auth. Bộ lọc theo `received_at` (nếu có), agency, domain, topic, severity, sentiment, model version, human-review status. KPI: count, share negative/high severity, top topic, trend per stable time window, unknown/missingness, AI vs human corrections. Báo cáo rõ numerator/denominator, timezone Asia/Ho_Chi_Minh, null-date exclusions; không dùng `ingested_at` giả làm event date. Cảnh báo tăng bất thường từ moving baseline with exposure/missing-data guard; đo false positives trên lịch sử nếu có, không khẳng định AI tự phát hiện khủng hoảng. Trang không tiết lộ raw PII; nếu demo thì watermark `SYNTHETIC DATA`. Lưu `docs/KPI_DICTIONARY.md`, tests về filter, time boundary, denominator zero, class imbalance, alerts false positives. Ghi caveat: phản ánh là mẫu tự chọn, không trực tiếp đo tỷ lệ hài lòng toàn dân; so sánh đơn vị cần denominators/điều chỉnh phù hợp.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dashboard]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py
```

**HUMAN GATE:** Người dùng nghiệp vụ duyệt định nghĩa KPI, tình huống cảnh báo có ích, tính đúng thời gian và quyền truy cập dashboard.  
**PASS:** test aggregation/alerts pass, dashboard hoạt động, synthetic watermark, không có kết luận quá mức về chất lượng dịch vụ công.

### STEP 15 — RQ1–RQ4 research protocol and controlled human-AI experiment

**Dependency:** 08, 11, 14; cần người tham gia thật cho RQ4. **Output:** protocol, data collection templates, results only after experiment.

**PROMPT CODEX — 15:**

> Triển khai STEP 15 cho cả RQ1–RQ4. Viết `docs/EXPERIMENT_PROTOCOL.md`: RQ1 tần suất chủ đề có scope/representativeness và confidence interval thích hợp; RQ2 kết quả ML từ STEP 11; RQ3 KPI và tính hữu ích của cảnh báo không đánh đồng với satisfaction survey; RQ4 so sánh xử lý thủ công vs AI+human review theo randomized/counterbalanced design. Đo time-on-task, gold accuracy, severe issue recall, critical miss, reviewer override rate, perceived usefulness; kiểm soát learning/order effects, không dùng người tham gia xử lý 2 lần một mẫu mà không counterbalance. Sample thí nghiệm không overlap training; consent/ethics/privacy rõ. Tạo templates CSV/JSONL không chứa PII, script tính thống kê và biểu đồ chỉ từ dữ liệu thu thật, chạy tests bằng synthetic fixtures, không generate fake result làm nghiên cứu. `research report --rq all --source ...` phải BLOCK khi thiếu observed experiments.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
Get-Content docs\EXPERIMENT_PROTOCOL.md
# Chỉ sau khi thực hiện thí nghiệm thực và nhập kết quả:
.\.venv\Scripts\python.exe -m pfa.cli research report --rq all --source "C:\secure-data\rq4_observations.csv"
```

**HUMAN GATE:** Hội đồng/người hướng dẫn duyệt protocol; tuyển người tham gia hợp lệ, cung cấp thông tin/đồng ý cần thiết, đo thời gian thật và xác minh gold labels.  
**PASS:** Có protocol + template + tests; RQ4 chỉ PASS khi có dữ liệu quan sát thực và báo cáo thống kê; nếu thiếu thì `BLOCKED_ON_EXPERIMENT`.

### STEP 16 — E2E, security, privacy, CI and observability

**Dependency:** API/DB/dashboard; synthetic test workflow nếu data thật thiếu. **Output:** stable stack, security checklist, CI.

**PROMPT CODEX — 16:**

> Triển khai STEP 16: tích hợp pipeline authorized import → redaction → frozen dataset/model (test fixture) → predict → review event → dashboard → analytics. Test synthetic-only E2E trong CI, có bước permission-denied regression, input injection/overlong/invalid schema, auth/role/IDOR risks, SQL injection parameterization, log redaction, no-secret/no-PII git scan, quota/error/health/readiness, dependency pinning. Tạo `.github/workflows/ci.yml` chạy ruff/pytest/security scans mà không tải model lớn/dữ liệu ngoài và không push artifacts nhạy cảm. Backup/restore hướng dẫn, DB migration smoke, basic latency/throughput test. Không chạy destructive tests trên DB thật. Docker Compose local tùy chọn và tài nguyên tối thiểu; không tự động bật external services.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pfa.cli doctor
# Docker là tùy chọn, chạy khi đã kiểm tra dung lượng:
docker compose up --build -d
docker compose ps
```

**HUMAN GATE:** Review secrets, role matrix, retention, PII redaction, backup destination, scope demo vs production.  
**PASS:** CI clean synthetic fixtures, kiểm thử auth/PII, E2E demo pass, không cần quyền mạng để chạy unit tests.

### STEP 17 — Research deliverables, deployment and handover

**Dependency:** các bước bắt buộc đạt PASS, human acceptance. **Output:** usable demo + reproducible research package.

**PROMPT CODEX — 17:**

> Triển khai STEP 17. Tổng hợp `docs/README_DEPLOY.md`, `docs/DATASET_CARD.md`, `docs/MODEL_CARD.md`, `docs/RISK_REGISTER.md`, `docs/RELEASE_CHECKLIST.md`; script export bảng/figure cho Chương 4: data distribution, per-task/per-model metrics, confusion matrices, trends, RQ4 table nếu có quan sát thật. Làm quickstart mới trên Windows sạch, config secrets qua `.env.example`, health checks, disaster recovery/rollback, model registry active version và API contract. Ghi rõ nguồn dữ liệu và license, model limitations, review required, deployment restrictions. Không đưa PII/raw data/model weights restricted vào release; nếu chưa có data chính/RQ4 thì phát hành `TECHNICAL_DEMO_ONLY`, không gọi là hoàn thành đề tài nghiên cứu. Codex tạo release report với checklist PASS/FAIL/SKIPPED và tất cả lệnh tái lập.

**NGƯỜI CHẠY:**

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pfa.cli doctor
Get-Content docs\RELEASE_CHECKLIST.md
git status --short
```

**HUMAN GATE:** Giảng viên/người hướng dẫn kiểm tra kết luận khoa học, nguồn trích dẫn, quyền sử dụng, kết quả RQ1–RQ4; nghiệp vụ nghiệm thu demo.  
**PASS:** có nguồn/giấy phép, dataset/model card, code chạy lặp lại, đánh giá khoa học và demo có kiểm duyệt; nếu thiếu research evidence, bản phát hành phải nêu giới hạn.

---

## 5. Human Gate Matrix — việc phải do người thực hiện

| Thời điểm | Vai trò con người | Đầu vào | Quyết định / hành động |
|---|---|---|---|
| STEP 02–03 | Người phụ trách nghiên cứu/đơn vị sở hữu | Data owner, terms, văn bản/email | Phê duyệt hay từ chối phạm vi download/use/train/share |
| **STEP 03B** | **Người phụ trách đề tài + đầu mối đơn vị cung cấp + data custodian** | **Đề nghị cung cấp, văn bản cho phép, secure handoff, receipt/checksum** | **Xin dữ liệu, xác minh quyền theo scope, nhận và kiểm tra file; không ủy quyền Codex tự scrape** |
| STEP 04–05 | Data custodian/privacy reviewer | Authorized export, privacy flags | Kiểm tra PII/quarantine và retention |
| STEP 06 | Giảng viên/nghiệp vụ | 8 topics + rubric severity | Chốt taxonomy, tiêu chí phân loại |
| STEP 07 | Annotator A, B, adjudicator | 200 mẫu đã ẩn danh | Gán độc lập, giải quyết bất đồng, duyệt gold |
| STEP 08 | Chủ nhiệm nghiên cứu | Dataset card/split report | Khóa test, xác nhận bias và phạm vi kết luận |
| STEP 09–11 | ML researcher | Validation/test reports | Duyệt lựa chọn model và threshold, không tune theo test |
| STEP 13–14 | Admin/người quản lý | Role matrix/KPI dictionary | Xác nhận quyền truy cập, KPI và cảnh báo |
| STEP 15 | Người tham gia thí nghiệm / giảng viên | RQ4 protocol | Thực hiện và xác minh thực nghiệm thật |
| STEP 16–17 | Reviewer triển khai và nghiệm thu | Security checklist, release | Nghiệm thu phạm vi demo/research release |

**Không có lệnh nào cho phép Codex thay thế các quyết định trên.**

## 6. Quy tắc GO / NO-GO và risk register

| Gate | GO khi | NO-GO khi | Đường xử lý |
|---|---|---|---|
| G-ACQUISITION | Quyền/retention/transfer được xác nhận, nguồn gốc có evidence, file nhận qua protected storage, receipt verified | Chỉ thấy trang công khai, thiếu bulk use/training right hoặc không có dữ liệu chuyển giao | Gửi data request, tìm nguồn thay thế; cấm scrape/receive chưa được phép |
| G-DATA | Quyền dùng rõ, có dữ liệu hợp pháp, PII processing được duyệt | Chưa được cấp quyền / license unknown | Chỉ tạo pipeline + tests synthetic, xin quyền/thay nguồn |
| G-LABEL | Guideline rõ, pilot được gán độc lập và tranh chấp đã xử lý | Severity không có tiêu chí; low agreement kéo dài | Sửa guideline, huấn luyện annotators, thêm metadata |
| G-SPLIT | Dataset version frozen, no near-duplicate group leakage, đủ class | Dữ liệu quá ít, test có overlap | Thu thêm dữ liệu, xử lý group trước split |
| G-MODEL | Baseline và PhoBERT báo đủ metrics, review policy phù hợp mục đích | Model severe miss không được review, calibration không ổn | Mở rộng human review hoặc dừng automation |
| G-DASH | Timestamps/metadata chính xác, KPI có mẫu số/giới hạn | Trend chỉ dựa `ingested_at` hoặc sample coverage méo | Chỉ hiện descriptive demo, không kết luận biến động dịch vụ |
| G-RESEARCH | RQ1–RQ4 có minh chứng nếu claim nghiên cứu hoàn tất | Thiếu thực nghiệm RQ4 hoặc dữ liệu chính | Chỉ nêu partial completion, không bịa kết quả |

### Tiêu chí chất lượng tối thiểu cho bản V1

1. 100% **bản ghi dataset nghiên cứu** truy được source, permission status, taxonomy version và transformation lineage.
2. 100% train/val/test có split manifest và kiểm tra duplicate groups; không để cùng group rơi vào nhiều split.
3. 100% dữ liệu demo public/trong Git không chứa PII cố ý. **Không tuyên bố ẩn danh hoàn hảo** nếu chưa qua review.
4. Mỗi task có label distribution, per-label F1, Macro-F1, error report và những trường hợp không đủ nhãn.
5. Với severity có `unknown/requires_review` thực sự được xử lý bằng con người; không đánh đồng xác suất model với mức nghiêm trọng.
6. Dashboard hiện provenance/updated time và caveat về sampling; alerts có kiểm tra denominator/data gaps.
7. Báo cáo RQ4 chỉ sinh từ thời gian/độ chính xác đo được ở con người thật.

---

## 7. Lộ trình dự kiến và parallelism

Các mốc là *ước tính quản lý*, không phải cam kết: 

| Pha | Bước | Ước tính | Có thể chạy song song? |
|---|---|---|---|
| Foundation / Dataset decision | 01–03 | 1 tuần | Các bước code đã được báo cáo hoàn thành kỹ thuật |
| **Real-data critical path** | **03B → 04–08 (research)** | **Phụ thuộc phản hồi đơn vị cung cấp, không cam kết thời lượng** | **Bắt đầu xin quyền ngay; phát triển acquisition CLI bằng synthetic song song với STEP 09** |
| Privacy / Taxonomy | 04–06 | 1–2 tuần | Annotation guideline có thể chuẩn bị khi chờ data |
| Pilot / Full dataset | 07–08 | 1–3+ tuần | Phụ thuộc quyền data và số annotators; thường là critical path |
| ML experiments | 09–11 | 2–3 tuần | Baselines trước PhoBERT, một số tác vụ có thể train song song khi đủ GPU |
| API / Database / Dashboard | 12–14 | 2–3 tuần | Code contract bằng synthetic fixture có thể làm trước khi có trained model |
| Research / Release | 15–17 | 1–3+ tuần | Protocol RQ4 nên chuẩn bị sớm, thực nghiệm thật sau pipeline hoàn thiện |

Nếu **không có dữ liệu chính được phép sử dụng**, không đặt deadline giả định cho STEP 07–11/15. Khi đó phát triển `technical_demo` với synthetic fixtures là phạm vi hợp lệ, nhưng không được trình bày như kết quả khoa học.

---

## 8. START HERE — đúng thứ tự để dùng với Codex

**Với repository hiện tại:** STEP 01–08A đã báo TECHNICAL PASS, vì vậy **chạy STEP 03B ngay** để mở đường nhận dữ liệu thật, không chạy lại các bước cũ. **Nếu chưa có repo:** bắt đầu STEP 01. Nếu STEP 01 đã PASS, bỏ qua nó và bắt đầu STEP 02. Tại mỗi bước, dán *Prompt chung* ở mục 3 một lần trong phiên Codex, tiếp theo dán **PROMPT CODEX — NN** tương ứng.

```powershell
# Check environment, tại repo root
py -3.11 --version
git status --short
.\.venv\Scripts\python.exe -m pfa.cli doctor

# Sau STEP 02 được Codex implement
.\.venv\Scripts\python.exe -m pfa.cli dataset sources
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source public_service_official
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source uit_vsfc
.\.venv\Scripts\python.exe -m pytest -q
```

**Đầu ra cần gửi lại cho người review sau mỗi bước:**

```text
STEP: 02
Files changed: ...
Commands executed: ...
Tests: PASS/FAIL/SKIPPED, actual stdout/error excerpts
Dataset status: pending_permission / approved / blocked
Security/privacy checks: ...
Human tasks pending: ...
Known limitations: ...
Suggested next step only after gate: ...
```

**Nguyên tắc cuối:** Người dùng chạy PowerShell theo từng step. Prompt giao Codex code và tests; lệnh PowerShell chứng minh triển khai có chạy thật. Không dùng kết quả dự đoán trên synthetic hoặc benchmark giáo dục để viết kết luận khoa học về phản ánh dịch vụ công.

---

## 9. Tham chiếu đã kiểm tra (2026-11-03)

- Đề cương dự án người dùng cung cấp (7 trang): mục tiêu/đóng góp/câu hỏi RQ1–RQ4/phương pháp.
- UIT-VSFC dataset card: https://huggingface.co/datasets/uitnlp/vietnamese_students_feedback (license: unknown; schema/splits trên card).
- Hugging Face auto-converted Parquet: https://huggingface.co/docs/dataset-viewer/parquet (branch `refs/convert/parquet` có thể thay đổi; ghi lại resolved revision và checksum).
- Cổng Dịch vụ công Quốc gia: https://vpcp.dichvucong.gov.vn/p/phananhkiennghi/pakn-tra-loi.html (public lookup; không hàm ý có quyền bulk use).
- Trang giới thiệu Cổng Dịch vụ công Quốc gia: https://vpcp.dichvucong.gov.vn/p/home/dvc-gioi-thieu.html (xác nhận chức năng tiếp nhận phản ánh).
- NEU-ESC: https://huggingface.co/datasets/hung20gg/NEU-ESC (gated, Apache-2.0 được ghi trên card).
- PhoBERT model card: https://huggingface.co/vinai/phobert-base (MIT; Vietnamese word segmentation).
- Luật BV dữ liệu cá nhân 91/2025/QH15: https://chinhphu.vn/?classid=1&docid=214590&orggroupid=1&pageid=27160 (hiệu lực 01/01/2026).
- Nghị định 356/2025/NĐ-CP: https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-356-2025-nd-cp-468371.htm (hiệu lực 01/01/2026).
