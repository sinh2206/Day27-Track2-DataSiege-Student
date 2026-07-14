# Reflection (≤1 page)

**Which fault types were hardest to catch, and why?**

Các lỗi khó nhất là những sai lệch nhỏ nằm gần vùng biến thiên tự nhiên, đặc
biệt là distribution shift, feature training-serving skew và runtime anomaly.
Ngưỡng baseline mean ± 3σ bắt tốt lỗi rõ ràng nhưng có thể bỏ sót các điểm bất
thường nhẹ. Trường std_amount còn không có ngưỡng công khai, nên chỉ nhìn
mean_amount sẽ bỏ qua thay đổi hình dạng phân phối. Lineage cũng khó vì một
cạnh upstream bị thiếu phải được phân biệt với topology hợp lệ, không chỉ dựa
vào runtime.

Tôi dùng baseline công khai làm hard gate và bổ sung median/MAD trên lịch sử
trong ctx.state. Cách này tạo ngưỡng robust theo chính lần chạy, có thể phát
hiện outlier tinh vi mà không cần thêm RPC. Các điểm quá xa trung tâm không
được học ngược vào lịch sử để giảm nguy cơ fault làm lệch baseline động.

**What would you change about your cost/coverage tradeoff, if you had another pass?**

Tôi ưu tiên coverage đầy đủ nhưng giới hạn đúng một metered call cho mỗi event,
vì đó là tín hiệu trực tiếp nhất và vẫn phù hợp với ngân sách private. Nếu có
thêm một lượt, tôi sẽ dùng confusion matrix của practice để hiệu chỉnh riêng
MIN_HISTORY, Z_ALERT và hướng kiểm tra cho từng metric, thay vì dùng chung một
ngưỡng robust. Tôi cũng sẽ đánh giá FPR theo từng pillar trước khi hạ ngưỡng:
chỉ giữ soft signal nào tăng TPR nhiều hơn mức phạt cảnh báo nhầm. Phần chi phí
không cần tăng; cải thiện nên đến từ kết hợp tín hiệu và thống kê miễn phí trong
ctx.state, không phải gọi lặp lại toolkit.
