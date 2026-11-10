# Sổ tay gán nhãn phản ánh dịch vụ công — bản đề xuất 1.0.0

**Trạng thái: ĐỀ XUẤT, CHỜ CON NGƯỜI PHÊ DUYỆT.** Chưa kiểm định khoa học,
chưa thực hiện gán nhãn thử nghiệm, chưa đo độ đồng thuận. Toàn bộ ví dụ trong
tài liệu này là **SYNTHETIC**, do dự án tự tạo, không phải phản ánh hay nhãn vàng.

## 1. Phạm vi và người thực hiện

Người gán nhãn phải đọc hiểu tiếng Việt, hoàn thành hướng dẫn bảo mật và được
người phụ trách nghiên cứu phân công bằng mã giả danh. Chỉ truy cập dữ liệu đã
được cấp phép, kiểm tra chất lượng và duyệt quyền riêng tư. Không tìm kiếm danh
tính người dân, không bổ sung dữ kiện từ Internet, không suy đoán cơ quan hay
lĩnh vực dịch vụ từ nhãn chủ đề. Chưa được bắt đầu thử nghiệm STEP 07 khi chưa
phê duyệt công cụ nghiên cứu và điều kiện dữ liệu.

Ba nhiệm vụ độc lập: chủ đề nói về vấn đề gì; cảm xúc là thái độ được bộc lộ;
mức độ nghiêm trọng dựa vào tác động có bằng chứng. Không suy từ nhãn này sang
nhãn khác. Nội dung phản ánh không mặc nhiên tiêu cực hay nghiêm trọng.

## 2. Trình tự quyết định

1. Kiểm tra quyền truy cập, phiên bản dữ liệu, mã phản ánh không định danh và
   phiên bản/checksum taxonomy. Không tự sửa dữ liệu nguồn.
2. Nếu phát hiện thông tin cá nhân còn sót, dừng xử lý nội dung đó, chuyển quy
   trình bảo mật STEP 04. Không chép tên, số điện thoại, địa chỉ hay nguyên văn
   nhạy cảm vào lý do gán nhãn, báo cáo hoặc kênh công khai.
3. Xác định phạm vi. `OUT_OF_SCOPE` là nội dung rõ nghĩa nhưng ngoài dịch vụ công.
   `UNLABELABLE` là không đủ khả năng diễn giải, bị cắt, hoặc thiếu ngữ cảnh để
   xác định nhiệm vụ. Hai trạng thái này không nhận nhãn của ba nhiệm vụ.
4. Nếu trong phạm vi và có thể hiểu, chọn đúng một chủ đề chính. Đánh dấu
   `multiple_issues=true` khi có từ hai vấn đề độc lập. Không lưu nhiều nhãn
   chủ đề trong một ô, không tự tách phản ánh thành nhiều mẫu.
5. Chọn cảm xúc và mức độ độc lập; viết lý do riêng cho từng nhãn. Nếu thiếu
   bằng chứng mức độ, dùng `unknown`, lý do rõ ràng và `REQUIRES_REVIEW`.
6. Kiểm tra phủ định, mỉa mai, thông tin thiếu và các ranh giới bên dưới. Mọi
   nghi ngờ chưa giải quyết dùng `REQUIRES_REVIEW`, không đoán nhãn để đủ mẫu.

**Quy tắc hòa chủ đề:** ưu tiên trọng tâm/yêu cầu giải quyết mà người viết nêu
rõ; tiếp theo là vấn đề có tác động được mô tả cụ thể nhất; nếu vẫn hòa thì
chọn vấn đề xuất hiện đầu tiên và giải thích. Nếu không đủ ngữ cảnh áp dụng
quy tắc, để trống chủ đề và yêu cầu xem xét. Thứ tự nhãn trong tệp taxonomy
không phải thứ tự ưu tiên. Với cảm xúc hỗn hợp, xét đối tượng của chủ đề chính
và kết luận rõ của người viết; nếu chưa thể quyết định thì chuyển xem xét.

## 3. Chủ đề — đúng tám nhãn

### delayed_processing — Chậm xử lý hồ sơ

- **Định nghĩa:** trọng tâm là chờ đợi, tiến độ hoặc trả kết quả chậm.
- **Bao gồm:** phản ánh hồ sơ chưa xử lý, thời gian chờ dài được người viết nêu.
- **Loại trừ:** nhiều bước/giấy tờ là trọng tâm; lỗi kỹ thuật cụ thể là trọng tâm.
- **Ví dụ SYNTHETIC:** “Tôi chỉ muốn biết vì sao hồ sơ vẫn chưa có kết quả sau nhiều lần hỏi.”
- **Ranh giới:** “Chờ lâu” đủ xác định vấn đề tiến độ, chưa đủ kết luận vi phạm hạn.
- **Dễ nhầm:** `complex_procedure` đếm gánh nặng thủ tục, không phải thời gian tự nó.
- **Xử lý hòa:** nếu chờ là hậu quả phụ của việc bổ sung nhiều giấy tờ và yêu cầu
  chính là giảm giấy tờ, chọn `complex_procedure`; nếu yêu cầu đẩy nhanh tiến độ, chọn nhãn này.
- **Bằng chứng:** nội dung về tiến độ; chỉ dùng SLA/thời hạn khi có tài liệu đã xác minh.
- **Chuyển xem xét:** không rõ hồ sơ nào/trạng thái gì; mức độ `unknown` nếu chưa rõ tác động.

### complex_procedure — Thủ tục phức tạp

- **Định nghĩa:** gánh nặng do số bước, giấy tờ hoặc lần bổ sung.
- **Bao gồm:** phải đi lại nhiều bước, nộp nhiều bản, bổ sung lặp lại được mô tả.
- **Loại trừ:** chỉ không hiểu hướng dẫn hoặc chỉ chờ xử lý mà không nói đến gánh nặng thủ tục.
- **Ví dụ SYNTHETIC:** “Tôi phải thực hiện nhiều bước và nộp lại cùng loại giấy tờ; đề nghị đơn giản hóa.”
- **Ranh giới:** biết rõ từng bước nhưng thấy quá nhiều vẫn là nhãn này.
- **Dễ nhầm:** `unclear_guidance` là thiếu rõ ràng, không nhất thiết nhiều bước.
- **Xử lý hòa:** yêu cầu giảm bước/giấy tờ ưu tiên nhãn này; yêu cầu giải thích cách làm ưu tiên hướng dẫn.
- **Bằng chứng:** mô tả cụ thể bước hoặc yêu cầu gây gánh nặng; không tự kết luận thủ tục trái luật.
- **Chuyển xem xét:** chỉ nói “rắc rối” mà không xác định được khía cạnh cần giải quyết.

### unclear_guidance — Hướng dẫn không rõ ràng

- **Định nghĩa:** thông tin thiếu, khó hiểu hoặc mâu thuẫn khiến không biết cách làm.
- **Bao gồm:** biểu mẫu không giải thích, các hướng dẫn khác nhau, câu hỏi về cách thực hiện.
- **Loại trừ:** lời nói xúc phạm là trọng tâm; không đồng ý kết quả đã trả là trọng tâm.
- **Ví dụ SYNTHETIC:** “Hai phần hướng dẫn ghi khác nhau; xin cho biết tôi cần dùng mẫu nào.”
- **Ranh giới:** câu hỏi lịch sự không có bất mãn vẫn có thể thuộc chủ đề này, cảm xúc trung tính.
- **Dễ nhầm:** `staff_attitude` là cách ứng xử; `unsatisfactory_result` là nội dung kết quả cuối.
- **Xử lý hòa:** cần giải thích thông tin chọn nhãn này; yêu cầu xử lý cách cư xử chọn thái độ.
- **Bằng chứng:** nội dung chưa rõ hoặc nhu cầu hướng dẫn được nêu, không suy từ giọng văn.
- **Chuyển xem xét:** câu hỏi bị cắt mất đối tượng, không biết cần hướng dẫn việc gì.

### online_system_error — Lỗi hệ thống trực tuyến

- **Định nghĩa:** sự cố kỹ thuật cụ thể trong chức năng dịch vụ trực tuyến.
- **Bao gồm:** không đăng nhập được, tải tệp lỗi, trang báo lỗi khi gửi hồ sơ.
- **Loại trừ:** hồ sơ gửi thành công nhưng chờ xử lý; không hiểu quy trình trên một trang đang hoạt động.
- **Ví dụ SYNTHETIC:** “Trang báo lỗi mỗi lần tải tệp nên tôi chưa gửi được hồ sơ.”
- **Ranh giới:** không có thông báo trạng thái chưa chắc là lỗi kỹ thuật; cần xem ngữ cảnh.
- **Dễ nhầm:** `delayed_processing` khi hệ thống nhận hồ sơ nhưng cơ quan chưa trả kết quả.
- **Xử lý hòa:** yêu cầu sửa chức năng lỗi ưu tiên nhãn này; yêu cầu trả hồ sơ đã tiếp nhận ưu tiên tiến độ.
- **Bằng chứng:** hành vi hoặc thông báo lỗi được mô tả, không đoán nguyên nhân kỹ thuật.
- **Chuyển xem xét:** chỉ ghi “không được” mà thiếu mô tả thao tác và kết quả.

### staff_attitude — Thái độ phục vụ

- **Định nghĩa:** trọng tâm là giao tiếp, ứng xử hoặc thái độ người phục vụ.
- **Bao gồm:** nhận xét lịch sự, tận tình, quát mắng, thiếu tôn trọng được diễn đạt rõ.
- **Loại trừ:** thông tin chuyên môn khó hiểu nhưng không có nhận xét về cách cư xử.
- **Ví dụ SYNTHETIC:** “Nhân viên giải thích rất kiên nhẫn, tôi cảm ơn cách phục vụ đó.”
- **Ranh giới:** một người giải thích chưa đủ rõ không tự động là thái độ xấu.
- **Dễ nhầm:** `unclear_guidance` khi yêu cầu chính là làm rõ thông tin.
- **Xử lý hòa:** ưu tiên yêu cầu xử lý/ghi nhận ứng xử nếu người viết xác định đó là trọng tâm.
- **Bằng chứng:** mô tả hành vi giao tiếp hoặc đánh giá thái độ, không suy động cơ cá nhân.
- **Chuyển xem xét:** cáo buộc nhạy cảm hoặc danh tính chưa được bảo vệ; không chép tên vào lý do.

### fees — Chi phí / lệ phí

- **Định nghĩa:** trọng tâm là khoản thu, mức thu, thanh toán hoặc minh bạch chi phí.
- **Bao gồm:** hỏi mức phí, xác nhận phí đã công bố, phản ánh khoản bổ sung chưa được giải thích.
- **Loại trừ:** hậu quả tài chính chỉ là thông tin phụ của vấn đề khác mà người viết ưu tiên.
- **Ví dụ SYNTHETIC:** “Tôi muốn biết khoản thu thêm này được giải thích ở đâu.”
- **Ranh giới:** phí được cho phép vẫn thuộc `fees`; câu hỏi mức phí không mặc nhiên tiêu cực.
- **Dễ nhầm:** nhầm “thu thêm” với kết luận “thu trái phép”; nhãn này không đưa ra kết luận pháp lý.
- **Xử lý hòa:** yêu cầu chính về khoản thu chọn nhãn này; yêu cầu tiến độ kèm chi phí phụ thì xét trọng tâm.
- **Bằng chứng:** nội dung về chi phí; chỉ gọi là phí được phép khi có căn cứ đã xác minh.
- **Chuyển xem xét:** căn cứ pháp lý chưa rõ, thông tin tài khoản hoặc thanh toán còn định danh.

### unsatisfactory_result — Kết quả xử lý chưa phù hợp

- **Định nghĩa:** trọng tâm là kết quả hoặc nội dung trả lời đã có nhưng chưa đáp ứng vấn đề.
- **Bao gồm:** kết quả thiếu nội dung, trả lời không giải quyết điều đã hỏi, đề nghị xem lại kết quả.
- **Loại trừ:** chưa có kết quả vì chậm; chưa biết cách nộp hay điền mẫu.
- **Ví dụ SYNTHETIC:** “Tôi đã nhận trả lời nhưng câu hỏi chính vẫn chưa được giải quyết.”
- **Ranh giới:** không hài lòng với kết quả không chứng minh kết quả đó trái luật.
- **Dễ nhầm:** `unclear_guidance` khi thông tin cần rõ là hướng dẫn trước hoặc trong thủ tục.
- **Xử lý hòa:** yêu cầu sửa/xem lại kết quả ưu tiên nhãn này; yêu cầu hướng dẫn cách làm ưu tiên hướng dẫn.
- **Bằng chứng:** cho biết đã có kết quả hoặc phản hồi và điểm chưa phù hợp.
- **Chuyển xem xét:** không xác định được đang nói về kết quả hay hướng dẫn, thiếu ngữ cảnh.

### other — Vấn đề khác

- **Định nghĩa:** nội dung dịch vụ công rõ nghĩa nhưng không khớp bảy nhãn trên.
- **Bao gồm:** vấn đề khác có đối tượng/yêu cầu cụ thể trong phạm vi nghiên cứu.
- **Loại trừ:** nội dung ngoài dịch vụ công, văn bản rỗng, từ rời rạc hoặc không thể hiểu.
- **Ví dụ SYNTHETIC:** “Đề nghị bổ sung ghế ngồi ở khu vực chờ tiếp nhận dịch vụ công.”
- **Ranh giới:** thiếu nhãn chuyên biệt khác với thiếu bằng chứng để hiểu phản ánh.
- **Dễ nhầm:** `OUT_OF_SCOPE` là ngoài phạm vi; `UNLABELABLE` là không thể gán nhãn đáng tin cậy.
- **Xử lý hòa:** chỉ chọn sau khi đã loại bảy nhãn và ghi rõ vì sao không phù hợp.
- **Bằng chứng:** nội dung rõ ràng về dịch vụ công, không suy lĩnh vực hoặc cơ quan.
- **Chuyển xem xét:** nhiều phản ánh rơi vào nhóm này; đề nghị đánh giá taxonomy ở phiên bản tương lai.

## 4. Cảm xúc — ba nhãn độc lập

### negative — Tiêu cực

- **Định nghĩa:** thái độ không hài lòng trực tiếp hoặc gián tiếp đủ rõ.
- **Bao gồm:** phàn nàn, thất vọng, phản đối, bất mãn có ngữ cảnh.
- **Loại trừ:** câu hỏi thuần thông tin; sự kiện bất lợi được nêu mà không có thái độ đủ rõ.
- **Ví dụ SYNTHETIC:** “Tôi không hài lòng vì vẫn chưa được giải thích rõ.”
- **Ranh giới:** “không hài lòng” khác “không phàn nàn”; phải đọc cả phạm vi phủ định.
- **Dễ nhầm:** tiêu cực không đồng nghĩa mức độ `high`.
- **Xử lý hòa:** theo thái độ đối với chủ đề chính và kết luận rõ của người viết; chưa rõ thì xem xét.
- **Bằng chứng:** biểu hiện ngôn ngữ/ngữ cảnh; không dùng nhãn chủ đề để quyết định.
- **Chuyển xem xét:** mỉa mai không rõ, đánh giá trái chiều không có trọng tâm.

### neutral — Trung tính

- **Định nghĩa:** thông tin/câu hỏi rõ nghĩa chưa bộc lộ thái độ tích cực hay tiêu cực đủ rõ.
- **Bao gồm:** hỏi giấy tờ, hỏi mức phí, mô tả sự kiện thuần túy.
- **Loại trừ:** văn bản không thể hiểu; lời bất mãn gián tiếp có bằng chứng rõ.
- **Ví dụ SYNTHETIC:** “Xin cho biết cần dùng biểu mẫu nào cho thủ tục này?”
- **Ranh giới:** không đủ ngữ cảnh hiểu câu không phải lý do tự gán trung tính.
- **Dễ nhầm:** câu hỏi có tiền giả định bất mãn có thể tiêu cực; cần xét toàn câu.
- **Xử lý hòa:** nếu thái độ thực sự không được bộc lộ thì trung tính; nếu tín hiệu xung đột chưa rõ thì xem xét.
- **Bằng chứng:** câu có nội dung hiểu được, không có tín hiệu thái độ đủ mạnh.
- **Chuyển xem xét:** chỉ có “vậy à”, đoạn cắt hoặc câu khó xác định mục đích.

### positive — Tích cực

- **Định nghĩa:** hài lòng, ghi nhận hoặc cảm ơn đủ rõ theo ngữ cảnh.
- **Bao gồm:** khen phục vụ, ghi nhận kết quả hoặc sự cải thiện.
- **Loại trừ:** lời khen bị phủ định hoặc mỉa mai có ngữ cảnh trái ngược.
- **Ví dụ SYNTHETIC:** “Tôi hài lòng vì được hướng dẫn tận tình, cảm ơn.”
- **Ranh giới:** “không tệ” có thể ghi nhận nhẹ; không suy thái độ mạnh hơn văn bản.
- **Dễ nhầm:** tích cực không tự quyết định mức độ `low`.
- **Xử lý hòa:** lời cảm ơn xã giao không tự lấn át phàn nàn chính; theo đối tượng và kết luận chính.
- **Bằng chứng:** biểu hiện ghi nhận có thể giải thích, không dựa một từ khóa đơn lẻ.
- **Chuyển xem xét:** câu khen có khả năng mỉa mai nhưng thiếu ngữ cảnh.

## 5. Mức độ nghiêm trọng — dựa trên bằng chứng tác động

Đây là thang nghiên cứu đề xuất, không phải kết luận pháp lý hoặc cơ chế xử lý
khẩn cấp. Chỉ dùng văn bản và metadata được phép. Không tự tra cứu rồi áp một
thời hạn pháp luật/SLA chưa được xác minh cho hồ sơ. Nếu văn bản tự nói “quá hạn”
nhưng không có căn cứ được phép, ghi đây là lời phản ánh; không khẳng định vi phạm.

| Quyết định | Bằng chứng tác động | Tiến độ và thời hạn | Hành động |
|---|---|---|---|
| low | Bất tiện nhỏ được nêu rõ, hoặc câu hỏi đơn giản được mô tả không gây gián đoạn | Không suy hạn mặc định | Ghi lý do tác động nhỏ |
| medium | Gián đoạn công việc, đi lại hoặc hậu quả hành chính/tài chính cụ thể đáng kể | Chỉ so mốc đã biết, đã xác minh | Nêu tác động có bằng chứng, không tự đặt ngưỡng tiền |
| high | Hậu quả lớn hoặc rủi ro khẩn cấp cụ thể được mô tả, cần chuyên gia xem xét | Quá hạn đơn thuần không đủ; xét hậu quả | Ghi căn cứ tác động, chuyển quy trình xem xét khi cần |
| unknown | Chưa đủ thông tin về tác động; chỉ có cảm xúc hoặc lời “chậm” chung chung | Không có mốc xác minh hoặc thiếu ngữ cảnh tác động | REQUIRES_REVIEW, lý do thiếu bằng chứng; không dùng làm lớp huấn luyện |

### low — Thấp

- **Định nghĩa:** tác động nhỏ được xác định bằng chứng, không phải mặc định khi ít thông tin.
- **Bao gồm:** bất tiện nhỏ có mô tả rõ hoặc yêu cầu thông tin đơn giản không gây gián đoạn.
- **Loại trừ:** thiếu thông tin tác động; hậu quả đáng kể hay rủi ro cụ thể.
- **Ví dụ SYNTHETIC:** “Tôi chỉ hỏi vị trí biểu mẫu để tham khảo, chưa có hồ sơ và không bị gián đoạn công việc.”
- **Ranh giới:** câu “tệ quá” không mô tả hậu quả thì `unknown`, không tự gán thấp.
- **Dễ nhầm:** cảm xúc tiêu cực có thể đi cùng tác động nhỏ; không dùng cảm xúc làm tiêu chí.
- **Xử lý hòa:** nếu có bằng chứng hậu quả đáng kể cùng vấn đề thì không chọn thấp; thiếu căn cứ phân biệt thì xem xét.
- **Bằng chứng:** nêu rõ vì sao tác động nhỏ hoặc nhu cầu thông tin đơn giản.
- **Chuyển xem xét:** tác động bị bỏ lửng hoặc không thể loại trừ cách hiểu khác từ văn bản.

### medium — Trung bình

- **Định nghĩa:** tác động hành chính, tài chính hoặc gián đoạn cụ thể đáng kể, chưa có căn cứ nghiêm trọng/khẩn cấp.
- **Bao gồm:** phải đi lại, nghỉ làm, thực hiện lại công việc với hậu quả cụ thể được nêu.
- **Loại trừ:** chỉ bực tức; hậu quả lớn hoặc rủi ro khẩn cấp đã có bằng chứng.
- **Ví dụ SYNTHETIC:** “Tôi phải nghỉ một buổi làm để quay lại bổ sung, công việc bị gián đoạn nhưng không có việc khẩn cấp.”
- **Ranh giới:** không đặt ngưỡng số ngày hoặc số tiền phổ quát khi chưa được hội đồng nghiên cứu xác nhận.
- **Dễ nhầm:** số lần chờ không tự quyết định mức độ nếu không rõ tác động.
- **Xử lý hòa:** xét hậu quả mạnh nhất được mô tả đủ bằng chứng cho vấn đề chính; chưa rõ thì `unknown` và xem xét.
- **Bằng chứng:** mô tả hậu quả cụ thể, metadata hợp lệ nếu dùng; không tự tạo SLA.
- **Chuyển xem xét:** chưa xác định hậu quả đáng kể hay khẩn cấp, tài liệu căn cứ chưa được phép dùng.

### high — Cao

- **Định nghĩa:** bằng chứng mô tả hậu quả nghiêm trọng hoặc rủi ro khẩn cấp cụ thể.
- **Bao gồm:** tình huống có nguy cơ mất quyền lợi thiết yếu hoặc ảnh hưởng an toàn được nêu rõ.
- **Loại trừ:** giọng giận dữ, từ “gấp”, hay “quá hạn” đứng riêng mà chưa có tác động.
- **Ví dụ SYNTHETIC:** “Kết quả sai đang khiến quyền lợi thiết yếu của tôi bị ngừng; tôi cần được xem xét ngay vì hậu quả đã phát sinh.”
- **Ranh giới:** phát biểu này là bằng chứng văn bản về tác động, không phải xác nhận sự kiện pháp lý có thật.
- **Dễ nhầm:** `negative` là thái độ, không phải bằng chứng nghiêm trọng.
- **Xử lý hòa:** không nâng mức vì cảm xúc; nếu ảnh hưởng có hai cách hiểu và chưa rõ, yêu cầu xem xét.
- **Bằng chứng:** chỉ rõ loại hậu quả/rủi ro đã được mô tả, không sao chép thông tin nhạy cảm.
- **Chuyển xem xét:** vấn đề an toàn, pháp lý, quyền riêng tư hoặc căn cứ còn nghi vấn; quy trình dự án không thay dịch vụ khẩn cấp.

### unknown — Thiếu bằng chứng, không phải lớp giám sát

`unknown` dùng khi không đủ căn cứ lựa chọn thấp/trung bình/cao. Ví dụ
**SYNTHETIC:** “Chờ lâu quá!” xác định được bất mãn và tiến độ, nhưng chưa rõ hậu
quả hay mốc thời gian. Phải có `severity_justification` nêu phần còn thiếu,
`review_reason` và trạng thái `REQUIRES_REVIEW`. Không gán mặc định `low`, không
đưa `unknown` vào tập nhãn huấn luyện. Người xem xét chỉ bổ sung nhãn khi có căn
cứ được phép, không tìm thêm thông tin cá nhân ngoài dữ liệu.

## 6. Tình huống tổng hợp và bảo mật

- **SYNTHETIC, nhiều vấn đề:** “Trang lỗi, lại không rõ cần tệp gì; tôi muốn sửa
  chức năng gửi tệp trước.” Chọn `online_system_error`, `multiple_issues=true`;
  không tự tạo hai nhãn chính. Mức độ vẫn cần bằng chứng tác động.
- **SYNTHETIC, mỉa mai:** “Nhanh thật, hỏi mãi vẫn chưa có kết quả!” Có thể là
  tiêu cực vì ngữ cảnh đối lập. Nếu chỉ có “Nhanh thật” thì không tự suy mỉa mai.
- **SYNTHETIC, phủ định:** “Tôi không phàn nàn về thái độ, chỉ chưa rõ cách làm.”
  Không chọn thái độ tiêu cực chỉ vì xuất hiện từ “phàn nàn”; xét hướng dẫn.
- **SYNTHETIC, ngoài phạm vi:** “Cửa hàng bán đồ gia dụng giao nhầm sản phẩm.”
  Rõ nghĩa nhưng ngoài phạm vi dịch vụ công: `OUT_OF_SCOPE`, không phải `other`.
- **SYNTHETIC, thiếu ngữ cảnh:** “Cái này... chưa...” dùng `UNLABELABLE` khi không
  thể hiểu; nếu chỉ một nhiệm vụ thiếu bằng chứng thì `REQUIRES_REVIEW`, không
  loại cả mẫu một cách máy móc.
- **SYNTHETIC, nhắc thời hạn:** “Theo tôi hồ sơ đã quá hạn.” Không có SLA đã xác
  minh thì không kết luận vi phạm. Chủ đề có thể là tiến độ, mức độ có thể `unknown`.
- **SYNTHETIC, quyền riêng tư:** “Nội dung còn thông tin liên hệ chưa được duyệt.”
  Không điền thông tin đó vào biểu mẫu; dùng lý do trừu tượng và chuyển người
  phụ trách bảo mật. Mọi mẫu chưa giải quyết rủi ro phải bị chặn khỏi công bố.

Mọi lý do phải diễn giải ngắn gọn bằng lời của người gán nhãn, không chép nguyên
văn nhạy cảm. Kiểm tra tự động chỉ phát hiện một số mẫu PII, không chứng minh
ẩn danh hoàn toàn. Người phụ trách nghiên cứu và quyền riêng tư phải phê duyệt
taxonomy, tiêu chí mức độ và quy trình trước STEP 07. Bất đồng được giữ nguyên
trong các bản ghi độc lập để đối soát ở STEP 07; không sửa nhãn của người khác.
