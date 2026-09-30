# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Đỗ Trung Tuyến
- **MSSV:** 2A202602427
- **Lớp:** K4-L3B
- **Repository URL:**
- **Commit SHA cuối:**
- **Challenge ID:**
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602427`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | [`evidence/01-pytest.png`](evidence/01-pytest.png) |
| Log validator | [`evidence/02-log-validator.png`](evidence/02-log-validator.png) |
| Dashboard validator | [`evidence/03-dashboard-validator.png`](evidence/03-dashboard-validator.png) |
| Structured log | [`evidence/04-structured-log.png`](evidence/04-structured-log.png) |
| PII redaction | [`evidence/05-pii-redaction.png`](evidence/05-pii-redaction.png) |
| Trace list | [`evidence/06-trace-list.png`](evidence/06-trace-list.png) |
| Trace waterfall | [`evidence/07-trace-waterfall.png`](evidence/07-trace-waterfall.png) |
| Trace metadata | [`evidence/08-trace-metadata.png`](evidence/08-trace-metadata.png) |
| Prompt versions | [`evidence/09-prompt-versions.png`](evidence/09-prompt-versions.png) |
| Prompt promote / rollback | [`evidence/10a-prompt-promote.png`](evidence/10a-prompt-promote.png), [`evidence/10b-prompt-rollback.png`](evidence/10b-prompt-rollback.png) |
| Dashboard runtime | [`evidence/11a-dashboard-latency-errors.png`](evidence/11a-dashboard-latency-errors.png), [`evidence/11b-dashboard-cost-token-quality.png`](evidence/11b-dashboard-cost-token-quality.png) |
| Incident metric | [`evidence/12-incident-metric.png`](evidence/12-incident-metric.png) |
| Incident log | [`evidence/13-incident-log.png`](evidence/13-incident-log.png) |
| Incident trace | [`evidence/14-incident-trace.png`](evidence/14-incident-trace.png) |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 ([output](evidence/00-baseline-validate-logs.txt)) | 100/100 sau CP1/CP2 (89 record, 0 thiếu field, 0 thiếu enrichment, 37 correlation ID, 0 PII leak) — [02](evidence/02-log-validator.png); *chạy lại trên commit cuối ở CP4* | Baseline: 40/42 record thiếu field bắt buộc, 40 record thiếu enrichment, 0 correlation ID duy nhất |
| `validate_dashboard.py` | HỢP LỆ 6/6 panel ([output](evidence/00-baseline-validate-dashboard.txt)) | HỢP LỆ 6/6 panel — [03](evidence/03-dashboard-validator.png); dashboard runtime ở [11a](evidence/11a-dashboard-latency-errors.png), [11b](evidence/11b-dashboard-cost-token-quality.png) | Validator chỉ kiểm tra contract trong `config/dashboard.yaml`, chưa chứng minh có dashboard runtime |
| `pytest` | 22 passed ([output](evidence/00-baseline-pytest.txt)) | | |
| Số traces hợp lệ | 20 trace trong project cá nhân, nhưng chỉ có observation `lab-agent-run` (chưa có retrieval/generation) | | |
| Số PII leak | 0 (validator, 42 record) | 0 (validator, 89 record, gồm 1 request cố ý chứa email/SĐT/CCCD/thẻ giả) — [05](evidence/05-pii-redaction.png) | Baseline 0 là vì preview đã đi qua `summarize_text()`; CP1 thêm processor scrub mọi field trước khi ghi |
| Latency P95 / TTFT P95 | 1257 ms / 50 ms (tính từ `data/logs.jsonl` sau CP1, 11 request) | CP2 bình thường: P95 = 1,131 ms. Sau khi thử `rag_slow` (33 request trong cửa sổ): P50 155 / P95 2,657 / P99 3,609 ms, TTFT P95 50 ms | P95 cao hơn nhiều so với LLM (~150 ms) vì request đầu sau khi restart phải fetch prompt từ Langfuse (~1 s, thấy rõ trong trace `6942ad11…`: root 1.21 s, generation 0.15 s) |
| Retrieval success rate | 100% (0 `request_failed` sau CP1) | CP2 dashboard: 100.0%, error rate 0.00% (0/33) | `rag_slow` làm retrieval chậm chứ không làm fail, nên retrieval success vẫn 100% |
| `pytest` (CP2) | | 45 passed (sau fix event loop) | Thêm test correlation/PII/child observation/dashboard + test hồi quy concurrency |

## 4. Logging và PII

*(nháp — đọc lại và viết bằng lời của bạn)*

- **Cách tạo/nhận và truyền correlation ID:** [`app/middleware.py`](../app/middleware.py) gọi `clear_contextvars()` đầu mỗi request để không rò context từ request trước; nếu header `x-request-id` đúng dạng `req-<8 hex>` thì dùng lại, ngược lại sinh mới bằng `uuid4().hex[:8]` (không tin header lạ vì có thể chứa text/PII). ID được `bind_contextvars` nên mọi dòng log trong request tự có `correlation_id`, được truyền vào `agent.run()` → metadata trace, và trả về client qua header `x-request-id` + `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, và context request bind trong [`app/main.py`](../app/main.py) trước `request_received`: `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id gốc), `session_id`, `feature`, `model`, `env`. `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`; `request_failed` có `error_type`. Ảnh: [04](evidence/04-structured-log.png).
- **Cách bảo đảm PII được scrub trước khi ghi:** [`app/logging_config.py`](../app/logging_config.py) đăng ký `scrub_event` sau `format_exc_info` (exception đã thành text) và trước `JsonlFileProcessor` + `JSONRenderer`, nên file và stdout chỉ nhận dữ liệu đã che. `scrub_event` scrub đệ quy mọi field trừ 4 field do app sinh (`ts`, `level`, `correlation_id`, `user_id_hash`). [`app/pii.py`](../app/pii.py) có pattern email, thẻ, CCCD, SĐT VN, hộ chiếu; thẻ và CCCD được che trước SĐT để một đoạn số thẻ không bị nhận nhầm thành SĐT.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 30 → 100/100; gửi request có PII giả (`test@example.com`, `0901234567`, `012345678901`, `4111 1111 1111 1111`) với `x-request-id: req-1a2b3c4d` và thấy log chỉ còn `[REDACTED_*]` ([05](evidence/05-pii-redaction.png)); test tự động ở [`tests/test_pii.py`](../tests/test_pii.py) và [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py) (ID không rò giữa 2 request, thứ tự processor, PII không vào file).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:**
- **Cấu trúc root/retrieval/generation observations:**
- **Cách nối trace với log:**
- **Prompt name:**
- **Version/label baseline:**
- **Version/label candidate:**
- **Trace ID của mỗi version:**
  - v1 (label `baseline`): trace `b92e606fe2a94d405f8a05f3fae95727`, `correlation_id=req-2546963e`, 21:33:51 — generation liên kết `day13-chat - v1`, 32 input / 80 output tokens, cost 0.001296 USD
  - v2 (label `candidate`): trace `6942ad1118e83c10e4ab7b57a063f154`, `correlation_id=req-d7590160`, 21:56:17 — metadata `prompt_label=candidate`, `prompt_version=2`, `prompt_source=langfuse`, 172 tokens, cost 0.002064 USD
  - Cùng input `"Explain why metrics traces and logs work together"`, chỉ đổi `LANGFUSE_PROMPT_LABEL` trong `.env` rồi restart API; không sửa code.
- **Cách promote và rollback `production`:**
  - App luôn gọi `LANGFUSE_PROMPT_LABEL=production`; việc label `production` trỏ tới version nào do Langfuse quyết định, nên promote/rollback không cần sửa code hay deploy lại (chỉ cần chờ cache prompt 60 s hết hạn hoặc restart API).
  - Promote: chuyển label `production` từ v1 sang v2 trên Langfuse UI ([10a](evidence/10a-prompt-promote.png)). Trace sau promote: `bc5988de997d1267156491f267ee9851`, `correlation_id=req-3feffad1`, `prompt_version=2`.
  - Rollback: chuyển label `production` về lại v1 ([10b](evidence/10b-prompt-rollback.png)), restart API để xóa cache prompt. Trace sau rollback: `45a9eb718ba5f46f7ec8289dfa19c5d5`, `correlation_id=req-f3538f60`, `prompt_version=1`.
  - Trace `5d6a4cc2b34e150822f429d8d8e74242` (`correlation_id=req-542d1094`) ra `prompt_version=2` vì được gửi **trước** khi chuyển label về v1 (lúc `production` vẫn ở v2 như ảnh 10a), nên nó là thêm một trace ở trạng thái promote, không phải lỗi rollback. Promote → rollback được làm 2 lần để chụp đủ ảnh trạng thái trước (10a) và sau (10b).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** Streamlit + pandas + Altair ([`dashboard/streamlit_app.py`](../dashboard/streamlit_app.py), tính toán ở [`dashboard/data.py`](../dashboard/data.py)), chạy bằng `streamlit run dashboard/streamlit_app.py`. Nguồn duy nhất là `data/logs.jsonl`; tiêu đề panel, đơn vị, threshold, time range 60′ và refresh 30 s đều đọc từ `config/dashboard.yaml` nên không lệch contract. Percentile dùng chung hàm với `app/metrics.py`. Ảnh: [11a](evidence/11a-dashboard-latency-errors.png), [11b](evidence/11b-dashboard-cost-token-quality.png).

  | Panel | Giá trị lúc chụp (CP2, sau 2 lần `load_test.py --concurrency 5`) | Ngưỡng |
  |---|---|---|
  | Latency | P95 = 1,131 ms | P95 ≤ 3000 ms |
  | Traffic | 20 req/phút (phút gần nhất có traffic) | ≥ 1 req/phút |
  | Errors | error rate 0.00% | ≤ 2% |
  | Cost | tổng 0.0472 USD | ≤ 2.5 USD |
  | Tokens | field lớn nhất 2,985 tokens | ≤ 50,000 tokens |
  | Quality | mean 0.870 | ≥ 0.75 |

  Kiểm tra runtime bằng practice `rag_slow` + `load_test.py --concurrency 5` (10 request lúc ~23:10): panel Latency đổi đúng hướng (P95 2,657 ms, P99 3,609 ms; trước đó P95 1,131 ms), traffic đỉnh 10 req/phút, error 0/33, cost tổng 0.0669 USD, tokens 1,132 in / 4,233 out, quality 0.873. Phía client `load_test.py` đo 13.3–15.2 s/request trong khi `latency_ms` chỉ ~2.66 s → xem phần blocker ở mục 8.

- **SLO và lý do chọn:** giữ 99.5% request có `response_sent` với `latency_ms ≤ 3000` trong 28 ngày ([`config/slo.yaml`](../config/slo.yaml)). Baseline P95 ≈ 1.1–1.3 s nên 3000 ms chừa khoảng 2.4 lần headroom: request bình thường không đốt budget, còn một bước chậm cỡ `rag_slow` (+2.5 s ở retrieval) sẽ vượt ngưỡng.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5% số request. Với 10,000 request/28 ngày thì tối đa 50 request được phép lỗi hoặc chậm hơn 3000 ms. Burn rate = (bad/total) / 0.005; ví dụ 1 request chậm trong 10 request của một lần load test là 10% bad, tức burn rate 20, nhanh gấp 20 lần mức cho phép.
- **Ba alert và runbook tương ứng:** định nghĩa ở [`config/alert_rules.yaml`](../config/alert_rules.yaml), runbook ở [`docs/alerts.md`](../docs/alerts.md). Owner `student-2A202602427`, Slack `#k4-l3b-alerts`.
  - [Alert 1](../docs/alerts.md#alert-1) `HighLatencyP95` (warning, 5m): P95 > 3000 ms. Kiểm chứng bằng practice `rag_slow`.
  - [Alert 2](../docs/alerts.md#alert-2) `HighErrorRateOrRetrievalFailure` (critical, 5m): error rate > 2% hoặc retrieval success < 90%, với ≥ 10 request. Kiểm chứng bằng `tool_fail`.
  - [Alert 3](../docs/alerts.md#alert-3) `CostPerRequestSpike` (warning, 15m): cost/request > 0.004 USD (khoảng 2 lần baseline) hoặc dự báo ngày > 2.5 USD. Kiểm chứng bằng `cost_spike`.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID:**
- **Khoảng thời gian điều tra:**
- **Triệu chứng từ metrics:**
- **Log line và correlation ID liên quan:**
- **Trace ID và span gây ảnh hưởng:**
- **Root cause:**
- **Fix action:**
- **Preventive measure:**

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
- **Một lỗi/blocker đã gặp:** *(nháp — viết lại bằng lời của bạn)* Khi thử practice `rag_slow` với `--concurrency 5`, `load_test.py` đo 13.3–15.2 s/request nhưng dashboard (đọc `latency_ms` trong log) chỉ báo P95 2,657 ms và vẫn "Đạt ngưỡng".
- **Cách tìm nguyên nhân và xử lý:** *(nháp)* So hai nguồn đo: `latency_ms` ~2.66 s/request = 2.5 s retrieval + ~0.15 s generation, khớp với span trong trace; nhưng 5 request đồng thời mất ~5 × 2.66 s. Endpoint `/chat` là `async def` mà gọi `agent.run()` đồng bộ (`time.sleep`) nên chặn event loop, các request xếp hàng tuần tự; `latency_ms` đo bên trong agent nên không thấy thời gian chờ. Xử lý: trong [`app/main.py`](../app/main.py) gọi `await run_in_threadpool(agent.run, ...)` để phần code đồng bộ chạy ở worker thread, event loop tiếp tục nhận request khác; anyio copy contextvars sang thread nên `correlation_id` và trace context vẫn đúng request. Test hồi quy `test_slow_requests_run_concurrently_and_keep_their_own_ids` trong [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py): 4 request có retrieval chậm 0.4 s phải xong < 1.5 s (tuần tự ~2.2 s) và mỗi log giữ đúng ID. Đo lại cùng workload (`rag_slow` + `load_test.py --concurrency 5`) sau khi sửa: 10/10 request 200, phía client 2,666–2,687 ms/request (trước khi sửa 13,318–15,156 ms), tức latency client khớp lại với `latency_ms` phía server; pytest 45 passed. Bài học: SLI phía server có thể xanh trong khi user chờ lâu; cần đối chiếu latency phía client.
- **Cách hiểu luồng Metrics → Logs → Traces:**
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
- **Điều quan trọng nhất đã học:**
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
