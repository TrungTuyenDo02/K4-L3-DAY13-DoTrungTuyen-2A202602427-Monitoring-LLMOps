# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert mẫu để tham khảo

Ví dụ dưới đây minh họa mức độ cụ thể cần có. Học viên không cần copy nguyên, nhưng ba alert trong bài nộp nên rõ ràng tương tự: điều kiện là gì, kéo dài bao lâu, ảnh hưởng tới user ra sao và người trực cần kiểm tra gì trước.

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: latency P95 của `response_sent.latency_ms`
- Điều kiện và thời gian duy trì: `p95(latency_ms) > 3000ms` trong 5 phút
- Ảnh hưởng tới người dùng: người dùng phải chờ lâu hơn trước khi nhận câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Mở dashboard latency để xác nhận P95/P99 và khoảng thời gian tăng.
  2. Lọc `data/logs.jsonl` trong khoảng đó, lấy một `correlation_id` có `latency_ms` cao.
  3. Mở trace cùng `correlation_id` trên Langfuse, so sánh các span chính để xác định bước nào bất thường.
- Mitigation tạm thời: dựa trên evidence thực tế để rollback prompt, khôi phục cấu hình liên quan, tắt practice scenario hoặc giảm tải khi demo.
- Owner: `student-<MSSV>`

## Alert 1

- Tên: `HighLatencyP95`
- Severity: `warning`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: SLO chính `fast_successful_requests` trong `config/slo.yaml` (99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày); panel **Latency percentiles and TTFT**.
- Điều kiện và thời gian duy trì: `p95(response_sent.latency_ms) > 3000ms` liên tục 5 phút.
- Ảnh hưởng tới người dùng: người dùng chờ hơn 3 giây mới có câu trả lời; mỗi request chậm bị tính là "bad" và làm tiêu error budget.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** mở dashboard, panel Latency. Xác nhận P95/P99 vượt đường SLO 3000 ms từ phút nào. So với TTFT P95: nếu TTFT vẫn thấp mà tổng latency cao thì phần chậm nằm trước hoặc sau lúc LLM trả token đầu tiên (ví dụ retrieval), không phải do model trả token đầu chậm.
  2. **Logs:** lọc `data/logs.jsonl` trong khoảng đó, lấy `correlation_id` có `latency_ms` cao nhất (hoặc xem tab "Điều tra" của dashboard):
     `Get-Content data/logs.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.event -eq "response_sent" -and $_.latency_ms -gt 3000 } | Select-Object ts, correlation_id, latency_ms, ttft_ms`
  3. **Traces:** trên Langfuse (project `day13-k4-l3b-2A202602427`), tìm trace có metadata `correlation_id` trùng, mở waterfall và so thời lượng `retrieval` với `llm-generation` để biết span nào chiếm phần lớn latency.
- Mitigation tạm thời: nếu span `retrieval` chậm, kiểm tra và tắt nguyên nhân phía RAG (khi luyện tập: `python scripts/inject_incident.py --scenario rag_slow --disable`); nếu `llm-generation` chậm sau khi đổi prompt, rollback label `production` về version ổn định; giảm concurrency trong lúc điều tra.
- Owner: `student-2A202602427`
- Kiểm chứng alert: bật `--scenario rag_slow` (retrieval ngủ thêm 2.5 s), chạy `python scripts/load_test.py --concurrency 5`. Kết quả đo thật (CP2): `latency_ms` mỗi request ~2.66 s, P95 = 2,657 ms (sát ngưỡng) và P99 = 3,609 ms (request lạnh phải fetch prompt ~1 s). Lần thử đầu, client thấy 13–15 s vì `/chat` chặn event loop nên 5 request xếp hàng (đã sửa bằng `run_in_threadpool`, sau đó client đo 2.67–2.69 s). Bài học cho người trực: khi user báo chậm mà dashboard vẫn xanh, so latency phía client (cột ms của `load_test.py` hoặc header `x-response-time-ms`) với `latency_ms` trong log để phát hiện thời gian xếp hàng.

## Alert 2

- Tên: `HighErrorRateOrRetrievalFailure`
- Severity: `critical`
- Duration: `5m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `error_rate_pct_max: 2` và `retrieval_success_rate_pct_min: 90` trong `config/slo.yaml`; SLO chính (request lỗi không có `response_sent` nên cũng là "bad"); panel **Error rate and retrieval success**.
- Điều kiện và thời gian duy trì: `request_failed / request_received * 100 > 2%` **hoặc** retrieval success `< 90%`, liên tục 5 phút, chỉ xét khi có ít nhất 10 request trong cửa sổ (để 1 lỗi lẻ khi traffic thấp không gây nhiễu).
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500 hoặc câu trả lời không có context; error budget bị tiêu rất nhanh.
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** panel Errors, xem error rate và retrieval success lệch ngưỡng từ phút nào; xem bảng breakdown theo `error_type` để biết loại lỗi chiếm đa số.
  2. **Logs:** lọc log lỗi, lấy `correlation_id` và `error_type`:
     `Get-Content data/logs.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.event -eq "request_failed" } | Select-Object ts, correlation_id, error_type, tool_name, tool_success`
  3. **Traces:** mở trace cùng `correlation_id`, tìm observation có level `ERROR` (span `retrieval` sẽ có `status_message` là tên exception) và xác nhận `llm-generation` không được gọi.
- Mitigation tạm thời: khôi phục dependency đang lỗi (vector store/tool); khi luyện tập: `python scripts/inject_incident.py --scenario tool_fail --disable`. Nếu lỗi xuất hiện ngay sau khi đổi prompt/config thì rollback thay đổi đó. Thông báo trên `#k4-l3b-alerts` vì đây là alert `critical`.
- Owner: `student-2A202602427`
- Kiểm chứng alert: bật `--scenario tool_fail`, chạy load test; mọi request trả 500 với `RuntimeError`, retrieval success về 0%.

## Alert 3

- Tên: `CostPerRequestSpike`
- Severity: `warning`
- Duration: `15m`
- Kênh thông báo: Slack `#k4-l3b-alerts`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` trong `config/slo.yaml`; panel **Cost over time** và **Input and output tokens**.
- Điều kiện và thời gian duy trì: cost trung bình mỗi `response_sent` `> 0.004 USD` (khoảng 2 lần baseline 0.002 USD) **hoặc** `sum(cost_usd)` của 1 giờ nhân 24 `> 2.5 USD` (dự báo vượt ngân sách ngày), liên tục 15 phút.
- Ảnh hưởng tới người dùng: người dùng chưa thấy lỗi ngay, nhưng câu trả lời dài hoặc tốn kém hơn, và dịch vụ có nguy cơ vượt ngân sách (có thể phải hạ cấp hoặc chặn traffic).
- Ba bước kiểm tra đầu tiên:
  1. **Metrics:** so panel Cost với panel Traffic. Nếu cost tăng mà traffic không tăng thì vấn đề nằm ở **mỗi request**; xem panel Tokens: `tokens_out` hay `tokens_in` tăng.
  2. **Logs:** lọc các `response_sent` có `cost_usd`/`tokens_out` cao nhất:
     `Get-Content data/logs.jsonl | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.event -eq "response_sent" } | Sort-Object cost_usd -Descending | Select-Object -First 5 ts, correlation_id, tokens_in, tokens_out, cost_usd`
  3. **Traces:** mở trace cùng `correlation_id`, xem observation `llm-generation`: usage input/output, cost, `model` và `prompt_version`/`prompt_label` để biết do prompt mới, model khác hay do output dài bất thường.
- Mitigation tạm thời: nếu tăng sau khi promote prompt thì rollback `production` về version trước; giới hạn độ dài output (max tokens); khi luyện tập: `python scripts/inject_incident.py --scenario cost_spike --disable`.
- Owner: `student-2A202602427`
- Kiểm chứng alert: bật `--scenario cost_spike` (output tokens gấp 4 lần), chạy load test; cost/request và `tokens_out` tăng mạnh trong khi traffic giữ nguyên.
