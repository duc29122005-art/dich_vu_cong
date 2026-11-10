# Đặc tả chuyển giao dữ liệu nghiên cứu

**DỰ THẢO để cơ quan và nhóm nghiên cứu thống nhất; không phải giấy phép sử dụng.**

## Mục đích và quyền

Nghiên cứu phân loại chủ đề, cảm xúc và mức độ nghiêm trọng của phản ánh dịch vụ
công bằng tiếng Việt. Đề nghị 2.000–5.000 bản ghi; số thực tế, thời gian và tính đại
diện do cơ quan xác nhận. Xin quyền gán nhãn, phân tích, huấn luyện và đánh giá.
Xin điều kiện riêng cho bài báo, thống kê, ví dụ, dữ liệu chia sẻ, mô hình và trọng số.
Quyền tiếp nhận không mặc nhiên cho phép công bố hoặc chuyển cho bên thứ ba.

## Định dạng và trường

Tệp CSV UTF-8 (chấp nhận BOM) hoặc JSONL UTF-8, không nén và không kèm macro.
Giới hạn tiếp nhận hiện tại: 20 MiB/tệp, 10.000 dòng dữ liệu; chia lô theo thỏa thuận
nếu lớn hơn. Không nhận Excel, archive hoặc tệp thực thi. CSV có tiêu đề duy nhất,
số cột nhất quán; JSONL mỗi dòng là một object, không lặp khóa.

| Trường chuẩn | Yêu cầu |
|---|---|
| feedback_id | Mã giả danh không truy ngược danh tính; không gửi bảng ánh xạ gốc |
| content | Văn bản tiếng Việt đã được cơ quan rà soát khử định danh |
| created_at | Thời điểm sự kiện thật dạng ISO datetime có múi giờ khi biết, hoặc null |
| source_id | Mã nguồn được thống nhất với bên nhận; có thể ánh xạ cột trong STEP 04 |
| domain, agency, channel | Chỉ metadata được phép, có thể null |
| processing_status, response_date | Chỉ khi thực sự có và được phép; không suy diễn |

Thiếu dữ liệu phải để null/ô trống; không tự tạo ngày, nhãn, SLA hay lĩnh vực.
Nếu chỉ có tháng/quý, mô tả mức thời gian trong tài liệu bàn giao và để datetime
không biết là null; không tự đặt ngày đầu tháng. Nhãn có sẵn cần tài liệu riêng về
nguồn và quyền; pipeline không tự coi đó là nhãn chuẩn đã được con người thẩm định.
Ánh xạ tên cột khác chuẩn được cấu hình/duyệt tại STEP 04, không sửa tệp nguồn tại chỗ.

## Khử định danh và vận chuyển

Cơ quan loại bỏ định danh trực tiếp và rà soát văn bản tự do, địa chỉ, tên người,
mã hồ sơ, tệp đính kèm và nguy cơ tái nhận diện từ các trường kết hợp. Bên nhận tiếp
tục cách ly, sàng lọc và duyệt thủ công; không có bảo đảm ẩn danh chỉ bằng regex.

Hai bên chọn kênh được phê duyệt: kho truyền tệp có kiểm soát hoặc phương tiện ngoại
tuyến được quản lý. Nếu dùng mã hóa, bên quản lý phải triển khai và xác minh riêng;
module này không mã hóa tệp và không thực hiện truyền qua mạng.
Xác minh danh tính người gửi và thẩm quyền qua kênh chính thức đã kiểm tra độc lập.

Bên gửi cung cấp: source/export reference không định danh, tên định dạng, số byte,
SHA256 và điều kiện sử dụng. Xác nhận checksum qua kênh xác thực độc lập, không chỉ
tin một tệp checksum đi cùng dữ liệu từ người gửi chưa xác minh. Tại PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath 'DUONG_DAN_TEP_DUOC_PHEP.csv'
(Get-Item -LiteralPath 'DUONG_DAN_TEP_DUOC_PHEP.csv').Length
```

Người phụ trách ghi Handoff sau xác minh, không đưa dữ liệu, PII hoặc tài liệu ký
vào Git. Thời hạn giữ/xóa/trả, bản sao lưu, sự cố và thu hồi phải được ghi trong
thỏa thuận thực tế. Nhận tệp thành công chỉ xác nhận tính toàn vẹn vận chuyển;
STEP 04 vẫn phải kiểm tra schema, PII, chất lượng và con người duyệt trước xuất bản.
