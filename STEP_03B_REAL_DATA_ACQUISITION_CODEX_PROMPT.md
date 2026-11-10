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
