# Public Service Feedback AI

Nghiên cứu xử lý phản ánh tiếng Việt về dịch vụ công. Package Python là `pfa`;
backend dùng FastAPI, dashboard dùng Streamlit/Plotly, lưu trữ tùy chọn bằng PostgreSQL.
Trạng thái hiện tại: **TECHNICAL_DEMO_ONLY**. Demo dùng dữ liệu tổng hợp và nhãn mock,
không phải mô hình đã được phê duyệt hay kết quả nghiên cứu thực tế.

## Mục lục chạy project

- [Cài đặt và chọn môi trường](#cài-đặt-và-chọn-môi-trường)
- [Cấu hình thực tế](#cấu-hình-thực-tế)
- [Cách 1: demo đầy đủ, SQLite tạm](#cách-1-demo-đầy-đủ-sqlite-tạm)
- [Cách 2: chỉ chạy API](#cách-2-chỉ-chạy-api)
- [Cách 3: PostgreSQL và dashboard lưu dữ liệu](#cách-3-postgresql-và-dashboard-lưu-dữ-liệu)
- [Cách 4: kiểm tra offline và CI](#cách-4-kiểm-tra-offline-và-ci)
- [CLI nghiên cứu và các workflow chi tiết](#dataset-governance-step-02)
- [Kiểm tra trước khi push](#kiểm-tra-trước-khi-push)

## Cài đặt và chọn môi trường

Chạy các lệnh từ thư mục gốc repository. Yêu cầu **Python 3.11**
(`pyproject.toml` giới hạn `>=3.11,<3.12`) và Git. Docker/PostgreSQL chỉ cần cho cách 3.
Không có Dockerfile cho ứng dụng; `compose.postgres.yaml` chỉ chạy database.

Windows PowerShell:

```powershell
# Nếu chưa cài Python: winget install --exact --id Python.Python.3.11
py -3.11 --version
py -3.11 -m venv .venv
# Chỉ sao chép khi chưa có .env, tránh ghi đè cấu hình cục bộ.
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Chọn một trong hai kiểu cài:

```powershell
# A. Môi trường đầy đủ, đúng phiên bản cho release demo, preflight và CI (CPU).
.\.venv\Scripts\python.exe -m pip install -r requirements-ci.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m pip check

# B. Hoặc cài tối thiểu để dùng doctor/CLI cấu hình, không chạy release demo.
# .\.venv\Scripts\python.exe -m pip install -e .
```

Lockfile sử dụng thêm index CPU chính thức của PyTorch. Cài package cần mạng,
không tải trọng số mô hình hoặc dataset. Các phiên bản trong lockfile là snapshot;
nếu index không cung cấp đúng phiên bản trên nền tảng đang dùng, quá trình cài có
thể thất bại. Không thay pin tùy tiện: release preflight kiểm tra từng phiên bản.

Các extra thực sự có trong `pyproject.toml`:

| Extra | Mục đích |
| --- | --- |
| `dev` | pytest, Ruff |
| `data` | pandas, NumPy, PyArrow |
| `api` | FastAPI, Uvicorn, HTTPX, SQLAlchemy, Alembic, psycopg |
| `dashboard` | Streamlit, Plotly, HTTPX |
| `phobert` | torch, transformers, safetensors, scikit-learn |
| `ml` | scikit-learn, torch, transformers, datasets, MLflow |

Ví dụ cài theo nhu cầu: `python -m pip install -e '.[dev,data,api,dashboard,phobert]'`.
Các extra không khóa phiên bản như `requirements-ci.lock`, không bảo đảm đạt release
preflight. Baseline cần `data` và scikit-learn; `dev,data` riêng lẻ không đủ cho toàn bộ tests.
MLflow chỉ là dependency tùy chọn, không có server MLflow cần chạy trong demo.

Linux/macOS (Bash, cùng Python 3.11 và lockfile; chưa khẳng định đã kiểm chứng mọi nền tảng):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-ci.lock
python -m pip install --no-deps -e .
python -m pip check
[ -f .env ] || cp .env.example .env
python -m pfa.cli doctor
```

Trên Windows có thể kích hoạt `.\.venv\Scripts\Activate.ps1` nếu policy cho phép.
Các ví dụ dưới dùng trực tiếp Python trong `.venv`, không cần đổi execution policy.
Trên Bash thay `.\.venv\Scripts\python.exe` bằng `python` sau khi kích hoạt môi trường;
đặt biến bằng `export NAME=value` thay cho `$env:NAME = 'value'`.
Sau cài editable, `pfa --help` tương đương `python -m pfa.cli --help`.

## Cấu hình thực tế

| Nhóm | Nguồn cấu hình và giá trị mặc định |
| --- | --- |
| Core | Đọc `.env` tại thư mục chạy; biến môi trường ưu tiên cao hơn. `PFA_ENVIRONMENT=development`, `PFA_LOG_LEVEL=INFO`, `PFA_PROJECT_ROOT` mặc định thư mục hiện tại. |
| API | Đọc biến môi trường tiến trình, không đọc `.env`. `PFA_API_MODE=APPROVED_MODEL`, chưa có model được duyệt thì prediction không sẵn sàng. |
| Xác thực | `PFA_API_KEY` cho prediction đơn giản; `PFA_API_PRINCIPALS` là JSON các role cho persistence, review, analytics. Gửi key qua `X-API-Key`. |
| Database | Biến môi trường `PFA_DB_MODE=DISABLED`; muốn lưu dữ liệu đặt `SYNTHETIC` và `PFA_DB_URL` dùng driver `postgresql+psycopg`. |
| Dashboard | Biến môi trường `PFA_DASHBOARD_API_URL` và `PFA_DASHBOARD_API_KEY`; key phải thuộc principal `ANALYST` cho nguồn `synthetic_demo`. |
| PostgreSQL test | `TEST_DATABASE_URL` riêng, database local có tên kết thúc `_test`; không dùng database chứa dữ liệu cần giữ. |
| Import thực | `PFA_FINGERPRINT_KEY` ổn định từ kho bí mật, cùng bằng chứng quyền sử dụng và privacy review. Demo không cần biến này. |

`configs/api_v1.yaml` ghi nhận mặc định công khai, không tự ghi đè API settings.
Các config dataset/ML/research được đọc theo workflow hoặc cờ `--config` tương ứng.
Một số `.yaml` dùng JSON subset và được đọc bằng stdlib; giữ cú pháp đang có.
`.streamlit/config.toml` bind `127.0.0.1`, bật CORS/XSRF, tắt telemetry.
Chỉ điền `.env` không đủ cấu hình API/DB/dashboard. Không đưa secret vào file được commit.

## Cách 1: demo đầy đủ, SQLite tạm

Dùng môi trường lockfile ở trên. Không cần PostgreSQL hoặc Docker. API tự tạo database
SQLite tạm với **420 phản ánh tổng hợp**; `Ctrl+C` kết thúc bình thường sẽ dọn dữ liệu,
bao gồm các sửa nhãn trong phiên. `release api` không dùng `PFA_DB_URL` hay database test.

Trong PowerShell cha, tạo credential trong bộ nhớ; không bật transcript khi thao tác secret:

```powershell
$env:PFA_ENVIRONMENT = 'development'
$env:PFA_API_MODE = 'DEMO_ONLY'
$env:PFA_API_OBSERVABILITY_ENABLED = 'true'
$env:PFA_DASHBOARD_API_URL = 'http://127.0.0.1:8000'
function New-DemoKey {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes); [Convert]::ToBase64String($bytes) } finally { $rng.Dispose() }
}
$adminKey = New-DemoKey
$reviewKey = New-DemoKey
$analystKey = New-DemoKey
$principals = @(
    @{actor_id='demo_admin'; role='ADMIN'; source_ids=@('synthetic_demo'); can_view_text=$true; key=$adminKey},
    @{actor_id='demo_reviewer'; role='REVIEWER'; source_ids=@('synthetic_demo'); can_view_text=$true; key=$reviewKey},
    @{actor_id='demo_analyst'; role='ANALYST'; source_ids=@('synthetic_demo'); can_view_text=$false; key=$analystKey}
)
$env:PFA_API_PRINCIPALS = ConvertTo-Json -InputObject $principals -Compress
$env:PFA_DASHBOARD_API_KEY = $analystKey
.\.venv\Scripts\python.exe -m pfa.cli release preflight
```

Preflight hợp lệ trả `WARNING`, exit 0: vẫn còn các hạn chế nghiên cứu/vận hành.
Nếu trả `BLOCKED`, xử lý checks bị chặn trước khi khởi động.
Từ PowerShell cha vừa cấu hình, mở hai cửa sổ con để kế thừa cùng credential:

```powershell
$python = (Resolve-Path '.venv\Scripts\python.exe').Path
Start-Process powershell -WindowStyle Normal -WorkingDirectory $PWD.Path -ArgumentList '-NoProfile','-NoExit','-Command',("& '" + $python + "' -m pfa.cli release api --port 8000 --seed 17")
Start-Process powershell -WindowStyle Normal -WorkingDirectory $PWD.Path -ArgumentList '-NoProfile','-NoExit','-Command',("& '" + $python + "' -m pfa.cli release dashboard --port 8501")
```

Các cửa sổ hiển thị để người chạy theo dõi và dừng bằng `Ctrl+C`. Terminal mới mở
độc lập không tự kế thừa biến của PowerShell cha. Có thể chạy hai lệnh sau trực tiếp
trong hai shell đã nhận cùng bộ biến môi trường từ nơi quản lý secret:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli release api --port 8000 --seed 17
# Shell thứ hai:
.\.venv\Scripts\python.exe -m pfa.cli release dashboard --port 8501
```

Nếu policy cho phép `.ps1`, wrapper tương đương là
`.\scripts\start_demo_api.ps1 -Port 8000 -Seed 17` và
`.\scripts\start_demo_dashboard.ps1 -Port 8501`. Wrapper không tạo credential.
Trên Bash, export cùng các biến ở bảng cấu hình và JSON principals theo cấu trúc trên,
rồi dùng hai lệnh Python tương ứng. Wrapper `.ps1` dành cho PowerShell.

Mở dashboard <http://127.0.0.1:8501>, Swagger <http://127.0.0.1:8000/docs>.
Trong PowerShell cha, kiểm tra API và một prediction tổng hợp:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/health/live'
Invoke-RestMethod 'http://127.0.0.1:8000/health/ready'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/operations/status' -Headers @{'X-API-Key'=$adminKey}
$body = @{text='SYNTHETIC: Hướng dẫn thủ tục giả lập chưa rõ.'; request_id='demo-001'} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/predict' -Method Post -Headers @{'X-API-Key'=$reviewKey} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

Prediction mock trả nhãn cố định, confidence null, yêu cầu người rà soát; không lưu input.
Xem [walkthrough](docs/DEMO_WALKTHROUGH.md) để tạo fixture, sửa nhãn và xem audit.
Dashboard có năm trang tổng hợp; chọn ngày **2025-01-06 đến 2025-01-13** để xem xu hướng demo.
Dừng cả hai cửa sổ bằng `Ctrl+C`, rồi đóng các shell chứa credential.
Đổi port API thì sửa `PFA_DASHBOARD_API_URL` trước khi chạy cả hai dịch vụ.

## Cách 2: chỉ chạy API

Chỉ cần extra `api` hoặc môi trường đầy đủ. Không cần database/dashboard.
Trong shell mới, không mang theo cấu hình DB của cách 3:

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
$env:PFA_ENVIRONMENT = 'development'
$env:PFA_API_MODE = 'DEMO_ONLY'
$env:PFA_DB_MODE = 'DISABLED'
$env:PFA_API_KEY = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
.\.venv\Scripts\python.exe -m pfa.cli api status
.\.venv\Scripts\python.exe -m pfa.cli api serve --host 127.0.0.1 --port 8000
```

Giữ terminal chạy; dùng `X-API-Key` chứa `$env:PFA_API_KEY` để gọi prediction.
Key legacy này không cấp role truy cập review/analytics. Dừng bằng `Ctrl+C`,
xóa credential với `Remove-Item Env:PFA_API_KEY` hoặc đóng shell.

Cách gọi trực tiếp Uvicorn cũng được hỗ trợ, sau khi đặt cùng biến môi trường:

```powershell
.\.venv\Scripts\python.exe -m uvicorn pfa.api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log --no-proxy-headers
```

Giữ một worker, loopback và các cờ tắt access log/proxy headers như CLI.
Chế độ `APPROVED_MODEL` là mặc định và kiểm tra registry, quyền dữ liệu, ba model,
checksum cùng bằng chứng đánh giá; hiện chưa có model được duyệt để chạy thực.
Không có fallback tự động sang demo. Xem [API service](docs/API_SERVICE.md).

## Cách 3: PostgreSQL và dashboard lưu dữ liệu

Chọn cách này khi cần giữ các record/review sau khi dừng API. Chỉ hỗ trợ dữ liệu
tổng hợp đã có trong project. Cài extra `api,dashboard` hoặc môi trường lockfile.
Cài PostgreSQL local, hoặc dùng Docker Compose với image **postgres:17**:

```powershell
# Cấp PFA_POSTGRES_USER, PFA_POSTGRES_PASSWORD, PFA_POSTGRES_DATABASE
# từ trình quản lý secret vào môi trường tiến trình trước khi chạy.
docker compose -f compose.postgres.yaml up -d db
docker compose -f compose.postgres.yaml ps
```

Compose bind `127.0.0.1:5432` và lưu volume `pfa_postgres`; không khởi động API/dashboard.
Với PostgreSQL cài local, tự tạo login và database phát triển riêng, bỏ qua Compose.
Cấp `PFA_DB_URL` dạng SQLAlchemy URL với driver `postgresql+psycopg` từ nơi quản lý secret;
password có ký tự đặc biệt phải URL-encode. Không ghi URL chứa password vào Git/shell history.
Thiết lập bộ `PFA_API_PRINCIPALS` và key dashboard như cách 1 trong các shell dịch vụ,
rồi chạy trên database phát triển mới, rỗng:

```powershell
$env:PFA_ENVIRONMENT = 'development'
$env:PFA_API_MODE = 'DEMO_ONLY'
$env:PFA_DB_MODE = 'SYNTHETIC'
# PFA_DB_URL phải được cấp vào môi trường trước các lệnh này.
.\.venv\Scripts\python.exe -m alembic history
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m pfa.cli db check-migrations
.\.venv\Scripts\python.exe -m pfa.cli analytics seed-demo
.\.venv\Scripts\python.exe -m pfa.cli api serve --host 127.0.0.1 --port 8000
# Shell thứ hai có PFA_DASHBOARD_API_URL và PFA_DASHBOARD_API_KEY:
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Chạy `seed-demo` đúng một lần: lệnh từ chối khi các bảng ứng dụng không rỗng.
API không tự migrate hoặc seed. Không dùng `release api` trong cách này vì lệnh đó
tạo SQLite tạm riêng. `release dashboard` kiểm tra lockfile/credential đầy đủ;
lệnh Streamlit trực tiếp ở trên phù hợp môi trường chỉ cài extra.
Dừng app bằng `Ctrl+C`; dừng Compose bằng `docker compose -f compose.postgres.yaml stop db`.
Dữ liệu vẫn trong volume. Không dùng `down -v` với dữ liệu cần giữ.
Xem [migration](docs/DATABASE_MIGRATIONS.md), [RBAC](docs/RBAC_MATRIX.md),
[dashboard](docs/DASHBOARD_GUIDE.md), [backup/restore](docs/BACKUP_RESTORE.md).

## Cách 4: kiểm tra offline và CI

Sau khi cài môi trường lockfile, các kiểm tra sau không cần server hay model tải về:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli doctor
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pfa.cli integration security-check
.\.venv\Scripts\python.exe -m pfa.cli integration smoke
.\.venv\Scripts\python.exe -m pfa.cli release preflight --isolated
.\.venv\Scripts\python.exe -m pfa.cli release smoke
```

Wrapper PowerShell tương đương cho doctor/preflight/smoke là
`.\scripts\verify_demo.ps1`; thêm `-FullTests` để chạy pytest và Ruff.
Không cần credential demo cho preflight `--isolated` hoặc các smoke cô lập.
Smoke tạo dữ liệu tổng hợp trong thư mục tạm, rồi dọn khi kết thúc bình thường.
Để khóa truy cập Hugging Face khi chạy ML checks:

```powershell
$env:HF_HUB_OFFLINE = '1'
$env:HF_DATASETS_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:CUDA_VISIBLE_DEVICES = ''
```

Kiểm tra PostgreSQL là nhánh riêng. Cấp `TEST_DATABASE_URL` cho database local mới
có tên kết thúc `_test`, login có quyền tạo schema. Runner tạo/xóa schema ngẫu nhiên
của chính nó, không reset database. Không cấu hình thì CLI trả exit 4 và tests skip.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli integration smoke-postgres
.\.venv\Scripts\python.exe -m pytest -q tests/test_postgres.py tests/test_analytics_postgres.py tests/test_integration_postgres.py
# Kiểm tra hẹp hoặc qua release:
.\.venv\Scripts\python.exe -m pfa.cli db smoke-postgres
.\.venv\Scripts\python.exe -m pfa.cli release postgres-check
```

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) có hai job Ubuntu/Python 3.11:
`offline` và `postgres` (service PostgreSQL **18.6**, khác image Compose local).
Workflow chạy khi push, pull request hoặc workflow_dispatch; không deploy ứng dụng.
Kết quả test SQLite không thay thế kết quả PostgreSQL. Xem [CI guide](docs/CI_GUIDE.md).

## Lỗi thường gặp

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| `No module named pfa` hoặc package thiếu | Dùng đúng Python `.venv`, cài editable và dependency theo cách chạy. |
| Doctor báo thiếu thư mục | Chạy từ gốc repo, giữ các `.gitkeep` trong `data/` và `reports/`. |
| Release preflight `BLOCKED` | Đọc từng check; kiểm tra Python 3.11, toàn bộ lockfile, mode demo và ba role. |
| `api status` exit 3 hoặc prediction 503 | Mặc định chưa có model; demo cần `DEMO_ONLY` và credential trong môi trường tiến trình. |
| HTTP 401 / 403 / 409 | Key thiếu/sai / thiếu role hoặc scope / version hoặc assignment đã cũ. |
| Dashboard rỗng | API phải có persistence đã seed; kiểm tra key ANALYST, URL và khoảng ngày fixture. |
| Port bị chiếm | Chọn port khác; cập nhật URL dashboard; không dừng tiến trình không liên quan. |
| `.ps1` bị chặn | Dùng trực tiếp Python như các lệnh trên, không cần đổi execution policy. |

## Cấu trúc và giới hạn

- `src/pfa/cli.py`: entry point `pfa`; các nhóm `dataset`, `annotation`, `ml`, `api`, `db`, `analytics`, `research`, `integration`, `release`.
- `src/pfa/core`, `data`, `annotation`, `ml`, `api`, `db`, `analytics`, `research`: các thành phần xử lý tương ứng.
- `dashboard/`: ứng dụng Streamlit; `configs/`: metadata và chính sách; `migrations/`: Alembic.
- `scripts/`: ba wrapper PowerShell; `templates/research/`: template trống và schema công khai.
- `tests/fixtures/`: dữ liệu tổng hợp cho tests; `data/`, `reports/`: dữ liệu và output cục bộ được ignore.
- `docs/`: hướng dẫn chi tiết và biên bản kiểm chứng; các phần dưới giữ các workflow chuyên môn.

Thu thập, gán nhãn, huấn luyện, đánh giá dữ liệu thực và triển khai public vẫn cần
bằng chứng cùng phê duyệt theo các gate trong mã nguồn. PhoBERT thực cần trọng số local
đã kiểm tra, Java và VnCoreNLP; smoke Transformer ngẫu nhiên không chứng minh PhoBERT thực.
Chưa quyết định giấy phép phân phối; xem [LICENSE_DECISION.md](LICENSE_DECISION.md).

## Kiểm tra trước khi push

`.gitignore` giữ secret, dữ liệu, tài liệu nguồn riêng tư, model, cache và output khỏi Git.
Các `.gitkeep`, fixture tổng hợp đã chỉ định, template nghiên cứu trống và lịch sử quyền
công khai vẫn được giữ để clone có đủ cấu trúc/chạy tests. Không điền dữ liệu người tham gia
vào `templates/research/`; lưu bản làm việc ở vùng `data/private/` được bảo vệ.
Ignore không loại bỏ file đã được Git theo dõi, và không thay thế việc kiểm tra nội dung.

```powershell
git status --short
git status --short --ignored
git ls-files -ci --exclude-standard
.\.venv\Scripts\python.exe -m pfa.cli integration security-check
# Sau khi tự chọn các file cần stage:
git diff --cached --stat
git diff --cached --check
git diff --cached
```

Chạy các checks phù hợp ở cách 4 trước khi commit. Không push `.env`, dữ liệu phản ánh,
PII, credential, model hoặc báo cáo cục bộ. Scanner là heuristic, không bảo đảm phát hiện mọi secret.
Các lệnh dưới chỉ tạo/kiểm chứng manifest cục bộ, không upload hoặc push:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli release manifest --output reports/releases/source_v1
.\.venv\Scripts\python.exe -m pfa.cli release verify --manifest reports/releases/source_v1
```

Output bất biến: dùng tên mới nếu thư mục đã tồn tại. Sửa README/config/source sau khi
tạo manifest sẽ khiến verify manifest cũ thất bại; tạo manifest mới sau thay đổi cuối.
Audit dependency tùy chọn cần mạng và tooling riêng:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-audit.lock
.\.venv\Scripts\python.exe -m pfa.cli release audit --output reports/releases/audit_local_v1
```

Audit gửi metadata package tới dịch vụ advisory; không tự chạy trong smoke.
Xem [dependency audit](docs/DEPENDENCY_AUDIT.md) và [release checklist](docs/RELEASE_CHECKLIST.md).

## Tài liệu workflow theo từng giai đoạn

## Dataset governance (STEP 02)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset sources
.\.venv\Scripts\python.exe -m pfa.cli dataset assess --source public_service_official
```

The seven-source registry is `configs/dataset_sources.yaml`, written in the JSON
subset of YAML 1.2 so the standard library can load it without another dependency.
Keep that syntax when editing; general YAML syntax is not supported. All unknown
facts remain UNKNOWN. No source has approved usage yet. Assessments are not legal
approvals. See `docs/DATASET_DECISION.md` for source comparisons and scoring,
`docs/PERMISSION_REGISTER.md` for the controlled approval/revocation workflow,
and `docs/DATA_REQUEST_TEMPLATE.md` for the Vietnamese agency request draft.

After a human verifies protected evidence and repository metadata is reviewed:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset approve --source SOURCE_ID --approval-ref REF
```

Do not run this with fabricated metadata. No real dataset may be accessed until
its required scope is approved. Continue offline with isolated SYNTHETIC test
fixtures while permissions are pending. No web scraping exists here.

## Benchmark adapter (STEP 03)

UIT-VSFC is student feedback, not public-service citizen feedback. Reference
label mappings remain unverified until authorized source metadata is available.

```powershell
# PyArrow is optional runtime support, required for the full offline test suite.
.\.venv\Scripts\python.exe -m pip install -e '.[dev,data]'
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark inspect --source uit_vsfc
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark verify --source uit_vsfc
```

Without local files, `verify` reports NOT_AVAILABLE (exit 4). Download remains
BLOCKED_PERMISSION (exit 3) until reviewed registry and audit records authorize
internal analysis. Only after authorization:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark inspect --source uit_vsfc --remote --approval-ref APPROVAL_ID --revision COMMIT_SHA
.\.venv\Scripts\python.exe -m pfa.cli dataset benchmark fetch --source uit_vsfc --approval-ref APPROVAL_ID --revision COMMIT_SHA
```

See `docs/BENCHMARK_DATASET.md` for schemas, mappings, permission prerequisites,
immutable revisions, safe transfers, manifest verification, and synthetic tests.

## Official local ingestion (STEP 04)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official schema
.\.venv\Scripts\python.exe -m pfa.cli dataset official smoke --fixture tests/fixtures/public_service_feedback_synthetic.csv
```

Smoke uses isolated temporary storage and invented Vietnamese records. Its human
review is explicitly simulated and its counts are software-test metrics.
Real imports remain blocked without current documented source permission,
verified license, explicit expiry, retention terms and internal-analysis scope.
Commit additionally requires publication scope and an existing human privacy
review bound to the exact preview. There are no permission-bypass flags.

After authorization, place approved inputs in protected `data/private/`, provide
a stable secret `PFA_FINGERPRINT_KEY`, then run:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/approved_export.csv --approval-ref APPROVAL_ID --mode preview
# Complete actual human review before this command:
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/approved_export.csv --approval-ref APPROVAL_ID --mode commit --review-ref REVIEW_ID
.\.venv\Scripts\python.exe -m pfa.cli dataset official verify --dataset-version VERSION_ID
```

See `docs/OFFICIAL_DATA_SCHEMA.md`, `docs/DATA_INGESTION.md`,
`docs/PRIVACY_REVIEW.md`, and `docs/DATA_QUALITY_REPORT.md`. Automatic redaction
does not guarantee anonymity, particularly for names and free-form addresses.
Staging is private; processed data contains only explicitly cleared records.

## Quality and privacy audits (STEP 05)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset profile --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset preprocess --source synthetic_demo
.\.venv\Scripts\python.exe -m pfa.cli dataset audit-privacy --source synthetic_demo
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The checksum-bound synthetic fixture produces computed software-test statistics,
not research results. Its deliberate flaws yield WARN (exit 0): 10 rows, 8 valid,
2 invalid, 3 exact duplicates, 1 near-duplicate pair, and 3 privacy-flagged rows.
Atomic immutable JSON/Markdown bundles live under ignored `reports/dataset/`.
They contain aggregates, keyed duplicate groups and transformation audit records;
no original text, raw feedback IDs or raw metadata labels are emitted.
Preprocessing preserves accents, negation and punctuation and emits an audit,
without creating an unreviewed dataset or overwriting inputs.

Real audits remain BLOCKED_PERMISSION. After actual authorization and verified
STEP 04 publication, use `--source SOURCE_ID --dataset-version VERSION_ID` on
these commands, with protected `PFA_FINGERPRINT_KEY`. Optional `--config PATH`
accepts validated JSON quality policy. No arbitrary paths can be labeled synthetic.
Publication and privacy review still use STEP 04 gates; regex is not proof of
anonymity. Research annotation remains gated; later technical components are described below.

See [DATA_QUALITY.md](docs/DATA_QUALITY.md),
[PREPROCESSING_POLICY.md](docs/PREPROCESSING_POLICY.md),
[PRIVACY_AUDIT.md](docs/PRIVACY_AUDIT.md), and
[DUPLICATE_POLICY.md](docs/DUPLICATE_POLICY.md) for thresholds, limitations,
lineage and prerequisites for STEP 06.

## Proposed taxonomy and annotation contracts (STEP 06)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation taxonomy show
.\.venv\Scripts\python.exe -m pfa.cli annotation template --output data/fixtures/annotation_template.csv
.\.venv\Scripts\python.exe -m pfa.cli annotation validate --input data/fixtures/annotation_template.csv --schema-only
# Expected exit 2: blank templates are not complete submitted annotations.
.\.venv\Scripts\python.exe -m pfa.cli annotation validate --input data/fixtures/annotation_template.csv
```

Taxonomy v1.0.0 defines eight single-primary topics, three sentiment labels and
three supervised severity labels. `multiple_issues` is a separate flag; `unknown`
severity and exclusion/review states are not supervised labels. The taxonomy is
a proposed research instrument pending human approval, not scientifically validated.
Templates have no feedback rows and include a version/checksum metadata sidecar.
Existing files are never silently overwritten. Validation supports CSV/JSONL,
preserves independent annotators, checks source membership and reports counts/errors
without source text, reasoning or PII. It never declares human gold annotations.

Real-source validation requires current permission and verified STEP 04 published
storage before reading annotation rows. Synthetic validation is restricted to
the checksum-bound project fixture. No real pilot or human agreement measurement has started.
See [Vietnamese handbook](docs/ANNOTATION_GUIDELINES.md),
[data contract](docs/ANNOTATION_SCHEMA.md), and
[workflow/versioning](docs/ANNOTATION_WORKFLOW.md). Human approval and authorized,
privacy-reviewed research data remain prerequisites for STEP 07.

## Pilot workflow (STEP 07A)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation pilot-smoke
# Expected exit 3 until genuine taxonomy approval and data authorization exist:
.\.venv\Scripts\python.exe -m pfa.cli annotation sample-pilot --source authorized_agency_export --n 200 --seed 42
```

The isolated SYNTHETIC smoke runs assignment, independent simulated imports,
agreement, simulated adjudication and verification, then removes temporary storage.
Eight invented records give software-check Kappa values 0.50/0.60/0.60 for
topic/sentiment/severity and 75% raw agreement each. These are not human research results.
It creates no real approvals or research gold.

After genuine human and data approval, a coordinator uses separate ordinary
Windows accounts for A, B and the adjudicator, plus protected evidence requests:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli annotation taxonomy record --decision-ref ACTUAL_DECISION_REF
.\.venv\Scripts\python.exe -m pfa.cli annotation sample-pilot --source authorized_agency_export --n 200 --seed 42 --pilot pilot_v1 --plan-ref pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator A --pilot pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation export --annotator B --pilot pilot_v1
# After independent human completion and verified receipt records:
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator A --pilot pilot_v1 --input data/private/annotation_deliveries/pilot_v1/A/annotation.csv --receipt-ref ACTUAL_RECEIPT_A
.\.venv\Scripts\python.exe -m pfa.cli annotation import --annotator B --pilot pilot_v1 --input data/private/annotation_deliveries/pilot_v1/B/annotation.csv --receipt-ref ACTUAL_RECEIPT_B
.\.venv\Scripts\python.exe -m pfa.cli annotation agreement --pilot pilot_v1
.\.venv\Scripts\python.exe -m pfa.cli annotation adjudicate --pilot pilot_v1
# After the correction deadline and explicit human review of every record:
.\.venv\Scripts\python.exe -m pfa.cli annotation adjudicate --pilot pilot_v1 --decision-ref ACTUAL_FINAL_DECISION
.\.venv\Scripts\python.exe -m pfa.cli annotation verify-pilot --pilot pilot_v1
```

Those references name pre-existing human-verified protected records; arguments do
not grant approval. Current status: taxonomy PENDING, real data BLOCKED_PERMISSION,
pilot research NOT_STARTED. STEP 08A infrastructure is described below. Follow
[pilot operations](docs/PILOT_ANNOTATION.md),
[taxonomy approval](docs/TAXONOMY_APPROVAL.md),
[agreement definitions](docs/INTER_ANNOTATOR_AGREEMENT.md),
[adjudication](docs/ADJUDICATION_WORKFLOW.md), and
[proposed research protocol](docs/PILOT_RESEARCH_PROTOCOL.md).

## Frozen corpus and splits (STEP 08A)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset split-smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
```

The smoke builds an isolated 120-record invented corpus with predetermined labels,
group relations and unknown severity cases. It checks immutable Parquet/checksum
storage, group-aware splits and blocked test-label access, then removes temporary
storage. Its SYNTHETIC card and metrics are software fixtures, not research gold.

Real builds remain blocked pending taxonomy approval, authorized privacy-reviewed
source data, completed STEP 07B, full adjudication and exact dataset/card approval.
After those genuine prerequisites, the coordinator may run:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset build --version service_feedback_v1 --seed 42 --preview
# Record genuine human approval of the exact proposed construction and card first.
.\.venv\Scripts\python.exe -m pfa.cli dataset build --version service_feedback_v1 --seed 42
.\.venv\Scripts\python.exe -m pfa.cli dataset check-leakage --version service_feedback_v1
```

No command grants approval. See [versioning and approval](docs/DATASET_VERSIONING.md),
[splitting](docs/DATASET_SPLITTING.md), [leakage](docs/DATASET_LEAKAGE.md),
[holdout policy](docs/TEST_HOLDOUT_POLICY.md) and
[dataset card template](docs/DATASET_CARD_TEMPLATE.md). STEP 08B and model training
have not started.

## Real-data acquisition (STEP 03B)

Discovery metadata and request drafts are separate from legal permissions. No real
data have been received. The source shortlist prioritizes an authorized agency
export; owner/contact, actual counts and rights remain UNKNOWN/PENDING until verified.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition status --source authorized_agency_export
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition request-pack --source authorized_agency_export --output reports/acquisition/agency_request_v1
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition preflight --source authorized_agency_export --scope internal_analysis
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition smoke
```

The package is an unsigned Vietnamese draft and is never sent automatically.
Human contact milestones can be recorded with `dataset acquisition record-event
--source SOURCE_ID --event-ref ACTUAL_EVENT` after genuine protected evidence exists.
Contact history grants no usage rights. Permission, handoff and verification states
derive from existing governance records and immutable receipts. Normal verification
CLI output omits the protected payload path.
Status/preflight currently report BLOCKED_PERMISSION (exit 3). Smoke uses ten
invented fixture rows, verifies a quarantined receipt and STEP 04 synthetic preview,
blocks unauthorized reception, then removes temporary storage.

Only after actual source approval and authenticated handoff evidence:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition receive --source authorized_agency_export --input data/private/incoming/approved_export.csv --approval-ref ACTUAL_APPROVAL --handoff-id agency_export_v1
.\.venv\Scripts\python.exe -m pfa.cli dataset acquisition verify --receipt-id agency_export_v1
.\.venv\Scripts\python.exe -m pfa.cli dataset official import --source authorized_agency_export --input data/private/acquisition/receipts/agency_export_v1/payload.csv --approval-ref ACTUAL_APPROVAL --receipt-id agency_export_v1 --mode preview
```

Reception never publishes data. STEP 04 retains authorization, schema, privacy
screening and human-review gates. See [operations](docs/REAL_DATA_ACQUISITION.md),
[source research](docs/REAL_DATA_SOURCE_SHORTLIST.md),
[Vietnamese checklist](docs/REAL_DATA_REQUEST_CHECKLIST.md),
[transfer requirements](docs/DATA_TRANSFER_SPEC.md) and
[security boundary](docs/ACQUISITION_SECURITY.md).

## Classical baselines (STEP 09)

```powershell
.\.venv\Scripts\python.exe -m pip install scikit-learn
.\.venv\Scripts\python.exe -m pfa.cli ml baseline-smoke
# Research examples require authorized, approved frozen STEP 08B data:
.\.venv\Scripts\python.exe -m pfa.cli ml train-baselines --dataset service_feedback_v1 --task topic --seed 42 --config configs/baseline_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml compare --dataset service_feedback_v1 --task topic
.\.venv\Scripts\python.exe -m pfa.cli ml inspect --run-id ACTUAL_RUN_ID
```

Topic, sentiment and severity each use separate TF-IDF + Logistic Regression and
TF-IDF + LinearSVC pipelines. TF-IDF fits train only; validation Macro-F1 selects
configurations. Test labels remain inaccessible to model selection. Unknown
severity is excluded by its existing task mask. Private immutable runs contain
serialized pipelines, metrics, provenance and SHA256 checksums. Synthetic smoke
scores are software tests, never research results. Real training remains blocked.
See [baseline methodology and artifact safety](docs/CLASSICAL_BASELINES.md).

## PhoBERT infrastructure (STEP 10)

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[phobert]'
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-smoke
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-readiness --config configs/phobert_v1.yaml
# Requires authorized frozen research data, approved local weights and a real segmenter:
.\.venv\Scripts\python.exe -m pfa.cli ml train-phobert --dataset service_feedback_v1 --task topic --seed 42 --config configs/phobert_v1.yaml
.\.venv\Scripts\python.exe -m pfa.cli ml phobert-inspect --run-id ACTUAL_RUN_ID
```

Smoke trains all three independent heads on a tiny randomly initialized Transformer
using synthetic fixtures. It is not pretrained PhoBERT fine-tuning. No checkpoint
weights or datasets are downloaded. Real readiness requires reviewed local
`vinai/phobert-base` safetensors/BPE files, an immutable revision/license record,
Java and a supplied VnCoreNLP segmenter. Research data gates remain unchanged.
See [training, resume and artifact policy](docs/PHOBERT_PIPELINE.md) and
[Vietnamese segmentation](docs/PHOBERT_WORD_SEGMENTATION.md).

## Evaluation and registry infrastructure (STEP 11)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli ml evaluation-smoke
.\.venv\Scripts\python.exe -m pfa.cli ml registry list
# Research commands remain gated until genuine approved experiments exist:
.\.venv\Scripts\python.exe -m pfa.cli ml compare --dataset service_feedback_v1
.\.venv\Scripts\python.exe -m pfa.cli ml evaluate --dataset service_feedback_v1 --split test --all
```

Unified LR, LinearSVC and PhoBERT adapters preserve frozen labels and explicit score
semantics. Validation groups separate calibration, threshold selection and descriptive
assessment. Final research testing additionally requires a locked protocol and explicit
human authorization; ordinary comparison never reads test labels. Immutable registry
records and hash-linked events support candidate approval, promotion and rollback.
Synthetic entries remain DEMO_ONLY and cannot enter research/production promotion.

Offline smoke uses 240 invented records, six baselines and a tiny random sentiment
Transformer. It verifies metrics, review policy, checksums and demo rollback, then
cleans temporary storage. It does not verify pretrained PhoBERT or establish research
performance. Real dataset, pilot, gold splits and research comparison remain blocked.
STEP 12 provides a local review-only API; approved-model serving remains blocked.

See [evaluation](docs/MODEL_EVALUATION.md), [calibration](docs/MODEL_CALIBRATION.md),
[review policy](docs/HUMAN_REVIEW_POLICY.md), [registry](docs/MODEL_REGISTRY.md) and
[locked protocol](docs/EXPERIMENT_PROTOCOL.md).

## Local FastAPI service (STEP 12)

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api]'
.\.venv\Scripts\python.exe -m pfa.cli api smoke
.\.venv\Scripts\python.exe -m pfa.cli api status
```

Default APPROVED_MODEL mode fails closed without credentials and approved registry
models. Explicit DEMO_ONLY mode uses constant mock labels, null confidence and mandatory
human review. All `/api/v1/` routes require an environment-provided API key. Local-only
serving, bounded requests/batches, safe errors and privacy-safe logs are implemented.
Prediction inputs are transient. STEP 13 adds explicitly enabled synthetic persistence
and a review queue below. No real model or public deployment is claimed.

See [Windows setup and lifecycle](docs/API_SERVICE.md), [security](docs/API_SECURITY.md)
and [endpoint contracts](docs/API_CONTRACT.md) before serving any requests.

## Synthetic persistence and review (STEP 13)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli db smoke
.\.venv\Scripts\python.exe -m pfa.cli db status
.\.venv\Scripts\python.exe -m alembic history
# Optional: only with a protected TEST_DATABASE_URL for a dedicated local *_test DB:
.\.venv\Scripts\python.exe -m pfa.cli db smoke-postgres
```

SQLAlchemy 2.x entities and explicit Alembic migrations target PostgreSQL. Offline
smoke uses a disposable SQLite database, invented fixtures and synthetic principals.
It checks feedback creation, three immutable mock predictions, review correction,
append-only audit, RBAC and stale-write rejection, then removes temporary files.
SQLite success does not verify PostgreSQL integration. No PostgreSQL test database
is currently configured. Persistence is disabled by default; API startup never
migrates or resets a schema.

Local PostgreSQL setup requires protected `PFA_DB_URL`, `PFA_DB_MODE=SYNTHETIC`, an
explicit Alembic upgrade and server-configured `PFA_API_PRINCIPALS`. The existing API
key grants no database role. Enabled routes accept only server-owned invented fixture
IDs; arbitrary feedback text and real intake remain blocked. Human labels are stored
separately from historical predictions. The current solo researcher's synthetic role
tests establish no independent human validation or gold annotations. STEP 14 adds
synthetic aggregates without changing these approval requirements.

See [schema](docs/DATABASE_SCHEMA.md), [Windows migrations and optional PostgreSQL
tests](docs/DATABASE_MIGRATIONS.md), [workflow and API](docs/HUMAN_REVIEW_WORKFLOW.md),
[RBAC](docs/RBAC_MATRIX.md), [audit limits](docs/REVIEW_AUDIT.md) and
[retention/backups](docs/DATA_RETENTION.md). Optional `compose.postgres.yaml` contains
only a loopback PostgreSQL service and is never started automatically.

## Synthetic analytics and Vietnamese dashboard (STEP 14)

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[api,dashboard]'
.\.venv\Scripts\python.exe -m pfa.cli analytics smoke
.\.venv\Scripts\python.exe -m pytest -q
```

Four authenticated `/api/v1/analytics/` routes provide summary, topics, trends and
descriptive alerts. Source-scoped STEP 13 roles remain enforced; text and record IDs
are never returned. AI, reviewed and adjudicated label bases stay separate. Local
day/week/month buckets use received_at only, preserve missing dates and report
Asia/Ho_Chi_Minh boundaries. Counts use feedback units, with explicit denominators,
unknown severity and server-side small-cell suppression.

Offline smoke creates 420 invented records in a disposable SQLite DB: 400 dated and
20 undated, with three mock predictions each and simulated review history. Seven
40-record days plus one 120-record spike exercise the three alert rules. These are
software fixtures, not research results. PostgreSQL integration remains NOT_VERIFIED.

For a separately provisioned empty local synthetic PostgreSQL DB, explicitly configure
STEP 13 credentials/migrations and an ANALYST dashboard principal before running:

```powershell
.\.venv\Scripts\python.exe -m pfa.cli analytics seed-demo
.\.venv\Scripts\python.exe -m pfa.cli api serve --host 127.0.0.1 --port 8000
# Separate protected shell with PFA_DASHBOARD_API_KEY:
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
```

Seeding refuses nonempty application tables and never approves source permissions.
All five Vietnamese dashboard pages display `SYNTHETIC DATA — DEMO ONLY` and consume
authenticated APIs. Credentials stay server-side; charts contain aggregate values
only. No live public server starts in tests. Real analytics and production deployment
remain blocked. STEP 15 research preparation is described below.

See [KPI dictionary](docs/KPI_DICTIONARY.md), [API/filter contract](docs/ANALYTICS_API.md),
[alert rules](docs/ALERT_ENGINE.md), [Windows dashboard guide](docs/DASHBOARD_GUIDE.md)
and [privacy/statistical limitations](docs/ANALYTICS_LIMITATIONS.md).
The [STEP 14 verification report](docs/STEP14_VERIFICATION.md) records implementation,
synthetic results, test commands and remaining blockers.

## RQ1–RQ4 research preparation (STEP 15)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli research status
.\.venv\Scripts\python.exe -m pfa.cli research protocol-check
.\.venv\Scripts\python.exe -m pfa.cli research templates
.\.venv\Scripts\python.exe -m pfa.cli research smoke
```

Prospective protocols separate synthetic engineering, consented human feasibility
and authorized research. Deterministic difficulty-matched AB/BA allocations freeze
before observations; real gold, participant access, ethics determination, consent
and model evidence remain required. RQ2 consumes STEP 11 manifests without accessing
test labels or changing selection. Participant/case-group statistics report missingness
and insufficient support explicitly. No new participant UI or actual recruitment is
provided. The sole researcher is Dương Thị Hồng Vân (EEP002-K49, BIT, UEH); there is
no supervisor or confirmed independent annotation team.

See [research protocol](docs/RESEARCH_PROTOCOL_RQ1_RQ4.md),
[human–AI design](docs/RQ4_HUMAN_AI_EXPERIMENT.md),
[statistics](docs/RESEARCH_STATISTICAL_ANALYSIS.md),
[consent/privacy](docs/RESEARCH_PARTICIPANT_CONSENT.md),
[blank collection templates](docs/RESEARCH_DATA_COLLECTION.md),
[report commands](docs/RESEARCH_REPORTING_GUIDE.md) and
[limitations](docs/RESEARCH_LIMITATIONS.md). All real RQ results remain blocked.
The [STEP 15 verification report](docs/STEP15_VERIFICATION.md) records files,
commands, synthetic evidence, test results and remaining prerequisites.
## Engineering integration and operations (STEP 16)

```powershell
.\.venv\Scripts\python.exe -m pfa.cli integration smoke
.\.venv\Scripts\python.exe -m pfa.cli integration security-check
.\.venv\Scripts\python.exe -m pfa.cli integration performance
# Requires a protected dedicated local TEST_DATABASE_URL:
.\.venv\Scripts\python.exe -m pfa.cli integration smoke-postgres
```

The isolated synthetic flow joins preprocessing, nonpersistent prediction, explicit
fixture persistence, review/audit, analytics, dashboard contracts and research blockers.
No real data or model weights are downloaded. Optional ADMIN operational status uses
`PFA_API_OBSERVABILITY_ENABLED=true`. Existing PostgreSQL 18.6 verification is historical
evidence; current-run coverage requires the dedicated test environment. Hosted CI is
configured but has not run. Real-data processing remains blocked.

See [E2E integration](docs/END_TO_END_INTEGRATION.md),
[security checks](docs/SECURITY_TESTING.md), [privacy](docs/PRIVACY_VERIFICATION.md),
[threat model](docs/THREAT_MODEL.md), [CI](docs/CI_GUIDE.md),
[observability/performance](docs/OBSERVABILITY.md),
[backup/restore](docs/BACKUP_RESTORE.md) and [STEP 16 verification](docs/STEP16_VERIFICATION.md).

## Local technical demo release and handover (STEP 17)

Classification: **TECHNICAL_DEMO_ONLY**. Scientific research is not complete.

```powershell
.\.venv\Scripts\python.exe -m pfa.cli release smoke
# Additional preflight / optional wrapper where local script policy permits:
.\.venv\Scripts\python.exe -m pfa.cli release preflight --isolated
# .\scripts\verify_demo.ps1
```

[Windows quickstart](docs/DEMO_QUICKSTART.md) explains exact installation, generated
process-only credentials, and foreground API/dashboard terminals on 127.0.0.1. Each
API session creates a separate owned temporary SQLite store with 420 invented records;
it never reuses pfa_test or external DB URLs. Stop with Ctrl+C. Predictions are constant
mock fixtures with null scores and mandatory review, not genuine NLP conclusions.

Release commands also provide explicit lock-scoped advisory audit, PostgreSQL recheck,
immutable public-source manifest generation and integrity verification. No archive,
production deployment or publication is performed. See [walkthrough](docs/DEMO_WALKTHROUGH.md),
[release checklist](docs/RELEASE_CHECKLIST.md), [release notes](docs/RELEASE_NOTES.md),
[limitations](docs/KNOWN_LIMITATIONS.md), [handover](docs/TECHNICAL_HANDOVER.md),
[dataset card](docs/DATASET_CARD_DEMO.md), [mock model card](docs/MODEL_CARD_DEMO.md),
[advisory audit](docs/DEPENDENCY_AUDIT.md), [restore rehearsal](docs/BACKUP_RESTORE_REHEARSAL.md),
[research readiness](docs/RESEARCH_READINESS_MATRIX.md),
[prospective paper outline](docs/research/PAPER_OUTLINE.md) and
[STEP 17 verification](docs/STEP17_VERIFICATION.md).
