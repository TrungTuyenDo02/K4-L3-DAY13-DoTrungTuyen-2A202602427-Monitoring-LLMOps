# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Đỗ Trung Tuyến
- **MSSV:** 2A202602427
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/TrungTuyenDo02/K4-L3-DAY13-DoTrungTuyen-2A202602427-Monitoring-LLMOps
- **Commit SHA cuối:** *điền sau khi commit + push lần cuối (`git log -1 --oneline`)*
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (Cohort K4, in ra bởi `load_test.py --challenge`)
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
| `pytest` | 22 passed ([output](evidence/00-baseline-pytest.txt)) | 45 passed trước commit cuối — [01](evidence/01-pytest.png) chụp trên commit cuối | Thêm 23 test: PII (CCCD/thẻ/hộ chiếu), correlation ID + không rò context, thứ tự processor, child observation, dashboard, hồi quy concurrency |
| Số traces hợp lệ | 20 trace trong project cá nhân, nhưng chỉ có observation `lab-agent-run` (chưa có retrieval/generation) | ≈ 77 trace trong project `day13-k4-l3b-2A202602427` (ảnh 06 lọc bỏ generation/retriever để mỗi dòng là 1 trace, cột Metadata thấy `correlation_id`); mọi trace từ CP2 có `lab-agent-run → retrieval + llm-generation` | Tất cả do tôi chạy `load_test.py` / request tay trên API của mình |
| Số PII leak | 0 (validator, 42 record) | 0 (validator, 89 record, gồm 1 request cố ý chứa email/SĐT/CCCD/thẻ giả) — [05](evidence/05-pii-redaction.png) | Baseline 0 là vì preview đã đi qua `summarize_text()`; CP1 thêm processor scrub mọi field trước khi ghi |
| Latency P95 / TTFT P95 | 1257 ms / 50 ms (tính từ `data/logs.jsonl` sau CP1, 11 request) | CP2 bình thường: P95 = 1,131 ms. Sau khi thử `rag_slow` (33 request trong cửa sổ): P50 155 / P95 2,657 / P99 3,609 ms, TTFT P95 50 ms | P95 cao hơn nhiều so với LLM (~150 ms) vì request đầu sau khi restart phải fetch prompt từ Langfuse (~1 s, thấy rõ trong trace `6942ad11…`: root 1.21 s, generation 0.15 s) |
| Retrieval success rate | 100% (0 `request_failed` sau CP1) | CP2 dashboard: 100.0%, error rate 0.00% (0/33) | `rag_slow` làm retrieval chậm chứ không làm fail, nên retrieval success vẫn 100% |

## 4. Logging và PII

*(nháp — đọc lại và viết bằng lời của bạn)*

- **Cách tạo/nhận và truyền correlation ID:** [`app/middleware.py`](../app/middleware.py) gọi `clear_contextvars()` đầu mỗi request để không rò context từ request trước; nếu header `x-request-id` đúng dạng `req-<8 hex>` thì dùng lại, ngược lại sinh mới bằng `uuid4().hex[:8]` (không tin header lạ vì có thể chứa text/PII). ID được `bind_contextvars` nên mọi dòng log trong request tự có `correlation_id`, được truyền vào `agent.run()` → metadata trace, và trả về client qua header `x-request-id` + `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `ts`, `level`, `service`, `event`, `correlation_id`, và context request bind trong [`app/main.py`](../app/main.py) trước `request_received`: `user_id_hash` (SHA-256 cắt 12 ký tự, không log user_id gốc), `session_id`, `feature`, `model`, `env`. `response_sent` có thêm `latency_ms`, `ttft_ms`, `tokens_in/out`, `cost_usd`, `quality_score`, `tool_name`, `tool_success`; `request_failed` có `error_type`. Ảnh: [04](evidence/04-structured-log.png).
- **Cách bảo đảm PII được scrub trước khi ghi:** [`app/logging_config.py`](../app/logging_config.py) đăng ký `scrub_event` sau `format_exc_info` (exception đã thành text) và trước `JsonlFileProcessor` + `JSONRenderer`, nên file và stdout chỉ nhận dữ liệu đã che. `scrub_event` scrub đệ quy mọi field trừ 4 field do app sinh (`ts`, `level`, `correlation_id`, `user_id_hash`). [`app/pii.py`](../app/pii.py) có pattern email, thẻ, CCCD, SĐT VN, hộ chiếu; thẻ và CCCD được che trước SĐT để một đoạn số thẻ không bị nhận nhầm thành SĐT.
- **Cách kiểm chứng kết quả:** `validate_logs.py` 30 → 100/100; gửi 1 request chứa email, SĐT, CCCD và số thẻ **giả** (dữ liệu test, xem ảnh 05) với `x-request-id: req-1a2b3c4d` và thấy log chỉ còn `[REDACTED_*]` ([05](evidence/05-pii-redaction.png)); test tự động ở [`tests/test_pii.py`](../tests/test_pii.py) và [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py) (ID không rò giữa 2 request, thứ tự processor, PII không vào file).

## 5. Tracing và prompt versioning

*(nháp — đọc lại và viết bằng lời của bạn)*

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** mọi ảnh Langfuse (06–10, 14) có breadcrumb `Trung's Organization / day13-k4-l3b-2A202602427`; key trong `.env` là key của chính project này (không commit). Trace sinh từ `load_test.py` và request tay của tôi, có `session_id`/`correlation_id` khớp với dòng log trong `data/logs.jsonl` trên máy tôi (vd `req-1c45a3e3` ở ảnh 13 và 14).
- **Cấu trúc root/retrieval/generation observations:** `day13-agent-request` (tên trace) → `lab-agent-run` (agent, `@observe` trên `LabAgent.run`, không capture input/output thô) → `retrieval` (retriever: input `query_preview` đã scrub, output `doc_count` + `docs_preview`; lỗi thì `level=ERROR`) và `llm-generation` (generation: `model`, usage input/output, `cost_details`, `completion_start_time` để Langfuse tính TTFT, metadata `prompt_*`, `tokens_*`, `cost_usd`). Child observation mở bằng helper `start_observation()` trong [`app/tracing.py`](../app/tracing.py) (bọc `start_as_current_observation` của SDK v4), dùng trong [`app/agent.py`](../app/agent.py). Ảnh: [07](evidence/07-trace-waterfall.png), [08](evidence/08-trace-metadata.png).
- **Cách nối trace với log:** cùng một `correlation_id` do middleware sinh được (1) bind vào mọi dòng log và (2) đưa vào `propagate_attributes(metadata={"correlation_id": ...})` nên có trên mọi observation của trace. Khi điều tra: lấy `correlation_id` từ log → lọc Metadata `correlation_id` trên Langfuse → ra đúng trace. Trace ID là ID nội bộ của Langfuse nối các span, khác với correlation ID.
- **Prompt name:** `day13-chat` (text prompt, giữ 3 biến `{{feature}}`, `{{docs}}`, `{{message}}`), liên kết với generation qua `propagate_attributes(prompt=...)`; trang Prompts đếm được số observation liên kết.
- **Version/label baseline:** v1 = 3 dòng `Feature=... / Docs=... / Question=...`, labels `baseline` + `production` ([09](evidence/09-prompt-versions.png)).
- **Version/label candidate:** v2 = v1 + dòng `Answer in at most 3 short bullet points.`, label `candidate`.
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

- **SLO và lý do chọn:** giữ 99.5% request có `response_sent` với `latency_ms ≤ 3000` trong 28 ngày ([`config/slo.yaml`](../config/slo.yaml)). Baseline P95 ≈ 1.1–1.3 s (phần lớn do request lạnh phải fetch prompt; request ấm chỉ ~150–400 ms) nên 3000 ms chừa headroom và request bình thường không đốt budget. Đo thật cho thấy một bước chậm cỡ `rag_slow` (+2.5 s ở retrieval) đưa request lên ~2.66 s: **sát nhưng chưa vượt** ngưỡng, chỉ request lạnh (~3.6 s) mới vượt. Ngưỡng tuyệt đối 3000 ms hợp với trải nghiệm người dùng (chờ quá 3 s là tệ) nhưng không đủ nhạy để phát hiện sớm một regression lớn; xem preventive measure ở mục 7.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5% số request. Với 10,000 request/28 ngày thì tối đa 50 request được phép lỗi hoặc chậm hơn 3000 ms. Burn rate = (bad/total) / 0.005; ví dụ 1 request chậm trong 10 request của một lần load test là 10% bad, tức burn rate 20, nhanh gấp 20 lần mức cho phép.
- **Ba alert và runbook tương ứng:** định nghĩa ở [`config/alert_rules.yaml`](../config/alert_rules.yaml), runbook ở [`docs/alerts.md`](../docs/alerts.md). Owner `student-2A202602427`, Slack `#k4-l3b-alerts`.
  - [Alert 1](../docs/alerts.md#alert-1) `HighLatencyP95` (warning, 5m): P95 > 3000 ms. Kiểm chứng bằng practice `rag_slow`: panel Latency tăng rõ nhưng P95 2,657–2,665 ms vẫn dưới ngưỡng, nên alert chỉ kêu khi có request lạnh; đây là điểm cần cải thiện (mục 7).
  - [Alert 2](../docs/alerts.md#alert-2) `HighErrorRateOrRetrievalFailure` (critical, 5m): error rate > 2% hoặc retrieval success < 90%, với ≥ 10 request. Kiểm chứng bằng `tool_fail`.
  - [Alert 3](../docs/alerts.md#alert-3) `CostPerRequestSpike` (warning, 15m): cost/request > 0.004 USD (khoảng 2 lần baseline) hoặc dự báo ngày > 2.5 USD. Kiểm chứng bằng `cost_spike`.


## 7. Điều tra challenge

*(nháp — đọc lại và viết bằng lời của bạn)*

- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1` (Cohort K4).
- **Khoảng thời gian điều tra:** 2026-09-30 23:33:30 → 23:35:40 (Asia/Ho_Chi_Minh) = 16:33:30 → 16:35:40 UTC. `incident_enabled` ghi log lúc 16:33:30Z; 5 request challenge (`feature=monitoring`) chạy 16:34:44 → 16:34:46.9Z; tắt incident và đo hồi phục lúc 16:35:39Z.
- **Triệu chứng từ metrics:** panel Latency ([12](evidence/12-incident-metric.png)): P50/P95 tăng từ 153 / 159 ms (workload bình thường lúc 22:48, 20 request) lên **2,661 / 2,665 ms** (~17 lần) ở phút 23:34. Các panel khác không đổi: TTFT P95 vẫn 50 ms, error rate 0%, retrieval success 100%, cost/request 0.00225 vs 0.00204 USD, tokens_out/request 143 vs 129 (FakeLLM random), quality 0.84 vs 0.88. → Triệu chứng là **chậm**, không lỗi, không tốn thêm token; phần LLM trả token đầu không chậm. Lưu ý khi đọc ảnh 12: ô tổng "P95 = 3,674 ms ❌" là của cả cửa sổ 60′ (gồm các lần tôi luyện tập `rag_slow` lúc 23:10–23:31); điểm của riêng challenge là phút 23:34 trên đồ thị, sau đó rơi về ~150 ms ở 23:35 khi tắt incident.
- **Log line và correlation ID liên quan:** `correlation_id=req-1c45a3e3` ([13](evidence/13-incident-log.png)) — `request_received` 16:34:44.232Z (`feature=monitoring`, `session_id=k4-l3b-challenge-s05`) và `response_sent` 16:34:46.895Z với `latency_ms=2654`, `ttft_ms=50`, `tool_name=retrieval`, `tool_success=true`, `tokens_out=132`. Cả 5 request challenge đều 2,654–2,665 ms. Generation của FakeLLM chỉ ~150 ms nên ~2.5 s nằm ngoài generation.
- **Trace ID và span gây ảnh hưởng:** trace `54759913ddf79a4ea53b6458ae9bfd62` ([14](evidence/14-incident-trace.png)), metadata `correlation_id=req-1c45a3e3`, `feature=monitoring`, session `k4-l3b-challenge-s05`, bắt đầu 23:34:44.232 — khớp đúng dòng `request_received` trong log. Waterfall: `lab-agent-run` 2.66 s = **`retrieval` 2.51 s** + `llm-generation` 0.15 s (cost 0.002085 USD). Span gây ảnh hưởng: **`retrieval`** (~94% thời gian request). Trace dùng `prompt_label=production`, `prompt_version=1`, `prompt_source=langfuse`, `prompt_fetch_error` rỗng.
- **Root cause:** bước RAG retrieval chậm ~2.5 s mỗi request (không lỗi, vẫn trả doc: `tool_success=true`, retrieval success 100%) — trùng với incident `rag_slow` mà `inject_incident.py` bật lúc 16:33:30Z (`/health` báo `rag_slow: true`). Loại trừ các nguyên nhân khác bằng evidence: LLM không chậm (generation 0.15 s, TTFT 50 ms như bình thường), không do prompt mới (đang là v1 ổn định sau rollback), không do cost/token (không đổi), không do lỗi (0/5 fail). Ba lớp metric → log → trace cùng chỉ về span `retrieval`.
- **Fix action:** tắt incident (`python scripts/inject_incident.py --disable`, `/health` → `rag_slow: false`), rồi chạy lại `load_test.py --concurrency 5`: 10/10 request 200 với 172–183 ms phía client → latency về lại mức bình thường.
- **Preventive measure:**
  1. **Alert hiện tại không bắt được sự cố này:** P95 = 2,665 ms vẫn dưới ngưỡng tuyệt đối 3000 ms của `HighLatencyP95`, dù đã chậm 17 lần. Đề xuất thêm điều kiện tương đối vào Alert 1: P95 > 3 lần baseline (~160 ms) trong 5 phút, hoặc alert riêng cho latency của span `retrieval` (bình thường ~0 ms).
  2. Ghi thêm `retrieval_ms` vào log `response_sent` để lớp log tự khoanh vùng được bước chậm, không cần mở trace mới biết.
  3. Đặt timeout cho retrieval (vd 1 s) với fallback "general answer", để một vector store chậm không kéo cả request lên nhiều giây.
  4. Runbook [Alert 1](../docs/alerts.md#alert-1) đã có bước so `retrieval` vs `llm-generation` trong waterfall.


## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** *(nháp)* Scrub PII bằng một structlog processor đặt **sau** `format_exc_info` và **trước** `JsonlFileProcessor`/`JSONRenderer`, scrub đệ quy **mọi field** thay vì chỉ `payload`. Lý do: redaction phải xảy ra trước khi dữ liệu được serialize/ghi, và scrub toàn bộ nghĩa là ai thêm field mới (hoặc exception chứa input người dùng) cũng không làm rò PII. Trace cũng chỉ nhận preview đã scrub (root tắt capture input/output). Một quyết định khác: dashboard đọc threshold/đơn vị/time range trực tiếp từ `config/dashboard.yaml` và dùng lại hàm percentile của `app/metrics.py`, để dashboard không lệch contract hay lệch `/metrics`.
- **Một lỗi/blocker đã gặp:** *(nháp — viết lại bằng lời của bạn)* Khi thử practice `rag_slow` với `--concurrency 5`, `load_test.py` đo 13.3–15.2 s/request nhưng dashboard (đọc `latency_ms` trong log) chỉ báo P95 2,657 ms và vẫn "Đạt ngưỡng".
- **Cách tìm nguyên nhân và xử lý:** *(nháp)* So hai nguồn đo: `latency_ms` ~2.66 s/request = 2.5 s retrieval + ~0.15 s generation, khớp với span trong trace; nhưng 5 request đồng thời mất ~5 × 2.66 s. Endpoint `/chat` là `async def` mà gọi `agent.run()` đồng bộ (`time.sleep`) nên chặn event loop, các request xếp hàng tuần tự; `latency_ms` đo bên trong agent nên không thấy thời gian chờ. Xử lý: trong [`app/main.py`](../app/main.py) gọi `await run_in_threadpool(agent.run, ...)` để phần code đồng bộ chạy ở worker thread, event loop tiếp tục nhận request khác; anyio copy contextvars sang thread nên `correlation_id` và trace context vẫn đúng request. Test hồi quy `test_slow_requests_run_concurrently_and_keep_their_own_ids` trong [`tests/test_correlation_logging.py`](../tests/test_correlation_logging.py): 4 request có retrieval chậm 0.4 s phải xong < 1.5 s (tuần tự ~2.2 s) và mỗi log giữ đúng ID. Đo lại cùng workload (`rag_slow` + `load_test.py --concurrency 5`) sau khi sửa: 10/10 request 200, phía client 2,666–2,687 ms/request (trước khi sửa 13,318–15,156 ms), tức latency client khớp lại với `latency_ms` phía server; pytest 45 passed. Bài học: SLI phía server có thể xanh trong khi user chờ lâu; cần đối chiếu latency phía client.
- **Cách hiểu luồng Metrics → Logs → Traces:** *(nháp)* Metrics trả lời "có vấn đề không, loại gì, từ lúc nào" (challenge: latency P50/P95 tăng ~17 lần ở 23:34, còn TTFT/error/cost bình thường). Logs trả lời "request nào bị ảnh hưởng" bằng cách lọc đúng khoảng thời gian và lấy một `correlation_id` (`req-1c45a3e3`, `latency_ms=2654`, `ttft_ms=50`). Trace của đúng request đó trả lời "bước nào gây ra" (`retrieval` 2.51 s trong 2.66 s). Đi theo thứ tự này tránh đoán mò và tránh mở trace ngẫu nhiên; chỉ kết luận khi ba lớp cùng chỉ một nguyên nhân.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** *(nháp)* Prompt là "code" của ứng dụng LLM: đổi prompt có thể đổi quality, token và cost. Nhờ mỗi trace ghi `prompt_name/label/version`, khi có regression tôi biết request dùng version nào (challenge: đang là v1 ổn định nên loại trừ prompt). Rollback chỉ là chuyển label `production` về version cũ trên Langfuse, không cần deploy. Token/cost trên generation giúp phát hiện "cost tăng mà traffic không tăng" (Alert 3). SLO + error budget biến "chậm/lỗi" thành con số để quyết định: còn budget thì được promote prompt mới, hết budget thì giữ version ổn định.
- **Điều quan trọng nhất đã học:** *(nháp)* Metric xanh chưa chắc người dùng ổn: `latency_ms` phía server từng báo ~2.66 s trong khi client chờ 13–15 s vì event loop bị chặn; và ngưỡng tuyệt đối 3000 ms không bắt được sự cố chậm 17 lần. Cần đối chiếu nhiều nguồn và đặt alert theo cả ngưỡng tuyệt đối lẫn độ lệch so với baseline.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** *(nháp)* Các preventive measure ở mục 7 (alert tương đối, `retrieval_ms` trong log, timeout retrieval) mới là đề xuất, chưa cài. Alert mới là cấu hình YAML + runbook, chưa nối Slack thật. Dashboard tính trên file log local, không phải hệ time-series; `quality_score` là heuristic, không phải đánh giá thật. `latency_ms` vẫn không gồm thời gian xếp hàng trước khi vào agent (chỉ header `x-response-time-ms`/phía client mới thấy).

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
