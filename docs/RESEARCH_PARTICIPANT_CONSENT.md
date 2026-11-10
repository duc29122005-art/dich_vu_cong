# Thông tin người tham gia, đồng thuận và bảo vệ dữ liệu — bản mẫu

**CHƯA ĐƯỢC PHÊ DUYỆT ĐỂ TUYỂN NGƯỜI THAM GIA. Không phải bản đồng thuận đã ký.**

Người thực hiện: Dương Thị Hồng Vân, lớp EEP002-K49, Khoa BIT, UEH. Đây là nghiên cứu
độc lập của một sinh viên, không có giảng viên hướng dẫn hay nhóm nghiên cứu. Tên
trường là thông tin liên hệ học tập, không thể hiện đại diện chính thức hoặc phê
duyệt của UEH. Chưa có xác nhận phê duyệt đạo đức hoặc người tham gia thật.

## Phiếu thông tin người tham gia — participant-info-1

Mục đích: tìm hiểu cách người dùng phân loại phản ánh dịch vụ công, diễn giải dashboard
và sử dụng gợi ý AI. Nghiên cứu không giải quyết hồ sơ hành chính, đánh giá quyền lợi
cá nhân hoặc thay thế quyết định của cơ quan nhà nước.

Hoạt động dự kiến: đọc tài liệu đã được phép và loại bỏ thông tin nhận dạng; phân loại
chủ đề, cảm xúc, mức độ; thực hiện tác vụ diễn giải biểu đồ; trả lời một số câu hỏi
tự nguyện về tính hữu ích và khối lượng công việc. Thứ tự có/không gợi ý AI được phân
bổ ngẫu nhiên. Thời lượng, địa điểm, tiêu chí tuyển và hỗ trợ/chi phí: **CHƯA XÁC ĐỊNH**;
phải cung cấp thông tin thật trước khi mời tham gia. Không hứa thưởng hoặc quyền lợi.

Trong pilot giao diện, vật liệu và gợi ý có thể hoàn toàn giả lập và phải được thông
báo rõ. Gợi ý giả lập không phải kết quả mô hình đáng tin cậy. Trong nghiên cứu thật,
chỉ dùng dữ liệu được phép và mô hình đã có hồ sơ đánh giá phù hợp. Không gửi dữ liệu
cho dịch vụ AI bên thứ ba chưa được chấp thuận.

Rủi ro có thể có: mệt mỏi, khó chịu khi đọc nội dung phản ánh, ảnh hưởng từ gợi ý sai
và rủi ro bảo mật còn lại. Có thể nghỉ, bỏ qua câu hỏi hoặc dừng bất cứ lúc nào. Việc
tham gia là tự nguyện; từ chối không gây bất lợi về học tập, công việc hay dịch vụ công.
Nếu phát hiện thông tin nhận dạng công dân, dừng tác vụ và báo người thực hiện;
không sao chép, chụp hoặc chia sẻ nội dung.

Ghi nhận: mã giả danh, phân bổ tác vụ, nhãn lựa chọn, gợi ý đã hiển thị, thời điểm và
thời lượng, tình trạng hoàn thành, phản hồi thang điểm nếu có. Không thu hình ảnh,
giọng nói, địa chỉ IP hoặc định danh thiết bị trong cơ chế STEP 15. Danh tính/liên hệ
và phiếu ký giữ riêng trong kho được bảo vệ; không đưa vào Git, dashboard hay báo cáo.

Đầu mối liên hệ của người nghiên cứu và đầu mối khiếu nại/đạo đức phù hợp: **CHƯA CÓ
THÔNG TIN ĐƯỢC XÁC MINH**. Phải điền kênh thật và xác định yêu cầu của cơ sở/nhà cung
cấp dữ liệu trước khi tuyển người; không bịa email, người giám sát hoặc hội đồng.

## Mẫu đồng thuận riêng biệt

Chỉ lưu bản điền/ký ngoài Git trong kho được bảo vệ:

- Tôi đã nhận phiếu thông tin đúng phiên bản và có cơ hội đặt câu hỏi.
- Tôi hiểu mục đích, hoạt động, loại dữ liệu ghi nhận và giới hạn của gợi ý AI.
- Tôi hiểu việc tham gia tự nguyện, quyền nghỉ/dừng/rút lui và không có quyết định
  hành chính tự động dựa trên kết quả.
- Tôi đồng ý ghi nhận dữ liệu tối thiểu đã mô tả cho mục đích được nêu.
- Tôi đã được giải thích việc chỉ báo cáo số liệu tổng hợp, giới hạn ẩn danh và
  điều kiện rút dữ liệu trước thời điểm đóng băng/bất khả hồi của báo cáo tổng hợp.
- Tôi đã nhận thời hạn lưu, cách xóa, kênh liên hệ và thông tin phê duyệt/thẩm định
  thực tế áp dụng cho hoạt động này.
- Tôi hiểu rằng chia sẻ dữ liệu ra ngoài cần quyền riêng, không mặc nhiên nằm trong
  đồng thuận tham gia. Không có quyền chia sẻ dữ liệu cá nhân mặc định.

Ô lựa chọn đồng ý/không đồng ý; phiên bản tài liệu; ngày giờ; chữ ký/cách xác nhận
phù hợp; kênh rút lui: để trống trong bản mẫu. Không tự điền hoặc suy ra đồng thuận.

## Rút lui và giả danh hóa

Cấp mã `p_` cộng 16 ký tự hex ngẫu nhiên bằng `secrets.token_hex(8)`; không băm email,
MSSV, số điện thoại hoặc tên làm mã. Giữ bảng ánh xạ danh tính và chữ ký riêng, quyền
truy cập tối thiểu. Tệp thu thập chỉ có mã và tham chiếu chứng cứ.

Ghi mỗi trạng thái GRANTED/WITHDRAWN/DECLINED thành sự kiện có thứ tự, thời gian và
chứng cứ thực. Xác minh đồng thuận trước tác vụ. Rút lui chặn phân tích dữ liệu còn
giữ của người đó; xử lý xóa/loại qua quy trình được phép, không tạo người hoặc quan
sát thay thế. Đồng thuận mới không khôi phục dữ liệu đã rút tự động. Không hứa xóa
ngược từng đóng góp khỏi số liệu tổng hợp đã công bố và không còn khả năng nhận dạng;
phải giải thích giới hạn trước khi tham gia. Hiện chưa có công bố hoặc quan sát thật.

## Lưu trữ, xóa và sao lưu — đề xuất chờ duyệt

Đề xuất: giữ bảng ánh xạ/liên hệ đến 90 ngày sau thu thập; giữ bản đồng thuận và dữ
liệu quan sát giả danh tối đa 12 tháng sau khi chốt báo cáo; xóa hoặc gia hạn có lý do
và phê duyệt trước hạn. Quy định của cơ sở, pháp luật và thỏa thuận nguồn dữ liệu có
thể yêu cầu lịch khác; chưa áp dụng mặc nhiên và phải thông báo lịch được chốt thật.

Mã hóa ổ đĩa/sao lưu, giới hạn tài khoản, tách bản đồ danh tính, không gửi dữ liệu
qua email công khai hoặc dịch vụ AI bên ngoài. Sao lưu có cùng giới hạn quyền và
lịch xóa; ghi các bản cần xóa khi phục hồi để không khôi phục dữ liệu đã rút. Thực
hiện xóa bởi người quản lý được phép, kiểm tra bản sao/xuất báo cáo và ghi nhật ký
tối thiểu không chứa danh tính. STEP 15 không tự xóa bằng lịch chưa được phê duyệt.
