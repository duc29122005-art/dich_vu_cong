# Danh mục kiểm tra đề nghị cung cấp dữ liệu

**DỰ THẢO — chỉ người được giao trách nhiệm mới rà soát, ký và gửi. Phần mềm không gửi.**

## Trước khi gửi

- Xác minh đúng cơ quan sở hữu/quản lý dữ liệu và thẩm quyền của người phê duyệt.
  Địa chỉ liên hệ chưa xác minh phải ghi UNKNOWN; không tự tạo email hoặc API.
- Điền đơn vị nghiên cứu, người đại diện, mục đích và phạm vi đề tài vào mẫu
  `DATA_REQUEST_TEMPLATE.md`. Xin khoảng 2.000–5.000 bản ghi đã khử định danh;
  không trình bày đây là số bản ghi cơ quan đã cam kết cung cấp.
- Đề nghị mô tả trường, khoảng thời gian, phương pháp chọn mẫu, độ đầy đủ và hạn chế.
- Xin riêng quyền phân tích nội bộ, lưu trữ, gán nhãn, huấn luyện và đánh giá;
  hỏi riêng quyền công bố thống kê, trích đoạn, mô hình/trọng số và chia sẻ dữ liệu.
  Không suy diễn quyền chia sẻ dữ liệu từ quyền công bố bài báo.
- Thống nhất bên chịu trách nhiệm khử định danh trước bàn giao và rà soát lại
  sau tiếp nhận. Không yêu cầu tên, số điện thoại, email, CCCD, địa chỉ chi tiết
  hoặc mã hồ sơ có thể truy ngược. Regex không bảo đảm ẩn danh hoàn toàn.
- Thống nhất người được truy cập, nơi lưu, thời hạn giữ, thu hồi, xóa/trả và xử lý
  bản sao lưu. Ghi điều kiện thực tế, không tự đặt thời hạn thay cho cơ quan.
- Thống nhất kênh chuyển an toàn, cách xác minh người gửi và checksum qua kênh
  xác thực độc lập. Không đưa hồ sơ hoặc mật khẩu lên Git hay dịch vụ công cộng.

## Sau khi có phản hồi

- Lưu văn bản thật trong kho được bảo vệ; mã nguồn chỉ giữ tham chiếu không nhạy cảm.
- Người có trách nhiệm xác minh giấy phép, phạm vi, ngày hết hạn và chính sách giữ
  dữ liệu; cập nhật registry, evidence và audit theo STEP 02. Không dùng đối số CLI
  hoặc `human_verified: true` thay cho chứng cứ thật.
- Nếu đã gửi yêu cầu, giữ bằng chứng gửi/nhận trong kho được bảo vệ. Gói dự thảo
  được tạo không có nghĩa yêu cầu đã được gửi, đã được chấp thuận hay đã có dữ liệu.
- Chạy `acquisition preflight` cho từng phạm vi cần dùng. Reception yêu cầu ít nhất
  `internal_analysis`; các bước sau vẫn kiểm tra riêng training/publication.
- Trước tiếp nhận, xác minh người cung cấp, mã lần xuất, định dạng, số byte và SHA256
  do bên gửi xác nhận. Lập bản ghi Handoff có người rà soát và tham chiếu chứng cứ.

## Sau tiếp nhận

- Xác minh receipt và checksum; tệp vẫn là dữ liệu cách ly, chưa được công bố.
- Bàn giao STEP 04 preview để kiểm tra schema, nguồn, quyền, PII và chất lượng.
- Thực hiện duyệt quyền riêng tư bởi con người trước commit; không tự tạo nhãn.
- Theo dõi thời hạn quyền và điều kiện thu hồi cho mọi bản sao; dừng sử dụng khi hết
  hạn/thu hồi. Không tuyên bố đã mã hóa hoặc xóa an toàn nếu chưa triển khai/xác minh.
