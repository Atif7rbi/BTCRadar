# BTCRadar Project Knowledge

## هدف المشروع

BTCRadar هو تطبيق مراقبة وبحث لتتبع ازدحام Long/Short في سوق عقود USDT الدائمة. المشروع يركز على BTC كرمز قائد، ثم يقارن الرموز التابعة بحالة BTC لتكوين صورة عن فرص المتابعة والمخاطر.

التطبيق ليس منصة تنفيذ تداول آلي كاملة. هو Dashboard بحثي يدعم:

- جمع بيانات Binance و Coinalyze.
- تحليل ازدحام BTC والرموز التابعة.
- عرض حالة السوق والرموز في لوحة Flask.
- تسجيل صفقات يدوية لأغراض المتابعة والتحليل.
- تتبع lifecycle للصفقات والتنبيهات.
- توليد تقارير أداء من الصفقات المغلقة.

## فلسفة BTC Driver / Followers

BTC هو Driver الأساسي:

- `BTCUSDT` هو مرجع السوق الرئيسي.
- تحليل BTC يحدد ما إذا كان الازدحام Long أو Short أو Neutral.
- عندما يكون BTC Long crowded تكون الفكرة البحثية هي مراقبة فرص Short على followers.
- عندما يكون BTC Short crowded تكون الفكرة البحثية هي مراقبة فرص Long على followers.

Followers هي الرموز التابعة:

- الافتراضي: `ETHUSDT`, `SOLUSDT`, `DOGEUSDT`, `XRPUSDT`.
- يتم قياس ازدحام كل follower بشكل مستقل.
- يتم ترتيب followers حسب `follow_score`.
- OI و CVD و Coinalyze بيانات داعمة/قراءة بحثية، وليست جزءا من قرار BTC الأساسي حسب الفلسفة الحالية.

## الملفات الأساسية

- `run.sh`
  - مشغل المشروع.
  - ينشئ `.venv` عند الحاجة.
  - يثبت `requirements.txt`.
  - يشغل `python -m src.app`.

- `config.yaml`
  - مصدر الإعدادات الرئيسي.
  - يحتوي على المنفذ، الرموز، أوزان الاستراتيجية، thresholds، التخزين، logging، Coinalyze، alerts، و trade lifecycle.

- `src/app.py`
  - نقطة إنشاء تطبيق Flask.
  - ينشئ خدمات السوق، الإشارات، الصفقات، التنبيهات، lifecycle، و Coinalyze.
  - يسجل Dashboard blueprint.
  - يحترم `BTCRADAR_PORT` إذا كان موجودا، وإلا يستخدم `config.yaml`.

- `src/binance_client.py`
  - عميل Binance Futures API.
  - يجلب السعر، funding، open interest، klines، و long/short endpoints.

- `src/collectors/snapshot_builder.py`
  - يبني `SymbolSnapshot` من Binance أو mock data.
  - يحسب VWAP ويضيف بيانات CVD/LS.

- `src/services/market_service.py`
  - يشغل حلقة تحديث السوق.
  - يدير refresh كامل و price-only refresh.
  - يحتفظ بآخر snapshots في الذاكرة ويخزن full snapshots في SQLite.

- `src/analyzers/btc_analyzer.py`
  - يحلل BTC فقط وينتج `RadarSignal`.
  - يعتمد على LS positions / ratio / account weights.

- `src/analyzers/follower_scorer.py`
  - يحسب `follow_score` للرموز التابعة.
  - لا يغير قرار BTC.

- `src/analyzers/btc_monitor.py`
  - Narrative/Health monitor للـ BTC والرموز.
  - يستخدم في dashboard والتنبيهات ومراقبة الصفقات.

- `src/dashboard/routes.py`
  - API و routes الخاصة بالـ Dashboard.
  - يحتوي على state endpoint، reports، Coinalyze، lifecycle، و manual trade endpoints.

- `src/services/trade_service.py`
  - فتح وإغلاق الصفقات اليدوية.
  - مزامنة PnL.
  - تطبيق auto guard عند تفعيلها.
  - حفظ metadata الدخول والإغلاق.

- `src/storage/database.py`
  - إنشاء الجداول و migrations الإضافية الآمنة.

- `src/storage/trades.py`
  - تخزين الصفقات المفتوحة والمغلقة.
  - حساب PnL و stats.

- `src/services/trade_lifecycle.py`
  - يسجل أحداث حياة الصفقة.
  - لا يفتح ولا يغلق صفقات.

- `src/services/alert_service.py`
  - محرك تنبيهات Telegram.
  - يعتمد على health states والصفقات المفتوحة.

- `tests/test_technical_fixes.py`
  - اختبارات الإصلاحات التقنية: port، logger، و close metadata.

## قاعدة البيانات

قاعدة البيانات الافتراضية:

```text
data/btc_radar.db
```

الجداول الحالية:

- `btc_radar_snapshots`
  - snapshots السوق لكل رمز.
  - تتضمن السعر، LS، funding، OI، VWAP، CVD، timestamps.

- `btc_radar_signals`
  - سجل إشارات BTC.
  - يتضمن state، recommendation، score، spread، votes.

- `btc_radar_spread_history`
  - تاريخ spread الخاص بـ BTC عند تحديث LS.
  - يستخدم لحساب trend.

- `btc_radar_coinalyze_history`
  - تاريخ بيانات Coinalyze.
  - يتضمن OI، funding، predicted funding، LS ratio، liquidations.

- `btc_radar_manual_trades`
  - الصفقات اليدوية المفتوحة والمغلقة في سجل الصفقات الأساسي.
  - يحتوي على metadata الدخول والإغلاق.

- `btc_radar_closed_trades`
  - نسخة أرشيفية من الصفقات بعد الإغلاق.
  - تستخدم في التقارير والإحصاءات.

- `btc_radar_trade_lifecycle`
  - أحداث lifecycle للصفقات.
  - يسجل ENTRY، CLOSE، وتغيرات PnL/health/pressure.

- `btc_radar_alert_events`
  - سجل التنبيهات المرسلة لمنع التكرار.

- `btc_radar_alert_state`
  - حالة التنبيهات السابقة مثل verdict/trade state.

## API Endpoints

- `GET /`
  - صفحة Dashboard الرئيسية.

- `GET /api/state`
  - الحالة الرئيسية للتطبيق.
  - يعيد BTC snapshot، signal، followers، symbol states، open/closed trades، performance، spread trend، alerts، lifecycle events، status.

- `POST /api/reports/generate`
  - توليد تقرير أداء من الصفقات المغلقة.
  - يدعم period، symbols، sections، و custom start.

- `GET /api/lifecycle/trades`
  - قائمة صفقات lifecycle حسب status.

- `GET /api/lifecycle/trades/<trade_id>`
  - تفاصيل lifecycle لصفقة محددة.

- `GET /api/coinalyze/state`
  - حالة Coinalyze collector وملخص الرموز.

- `POST /api/coinalyze/refresh`
  - refresh يدوي لـ Coinalyze مع حماية من التحديث المتكرر السريع.

- `POST /api/trades/open`
  - فتح صفقة يدوية.
  - يحتاج `symbol`, `direction`, ويمكن تمرير `size_usd`.

- `POST /api/trades/<trade_id>/close`
  - إغلاق صفقة يدويا بالسعر الحالي.

## Manual Trading Flow

1. `GET /api/state` يجمع الحالة الحالية:
   - snapshots من `MarketService`.
   - signal من `SignalService`.
   - followers من `FollowerScorer`.
   - symbol states من `BTCMonitor`.

2. فتح صفقة يدوية:
   - الواجهة ترسل `POST /api/trades/open`.
   - `TradeService.open_trade()` يتحقق من وجود سعر حي للرمز.
   - يتم بناء entry metadata من BTC signal، follower row، symbol states، و CVD.
   - `TradeStore.open_trade()` يحفظ الصفقة في `btc_radar_manual_trades`.

3. تحديث PnL:
   - عند `GET /api/state` يتم استدعاء `trade_service.sync_pnl()`.
   - يتم تحديث أسعار الصفقات المفتوحة و PnL.

4. Auto Guard:
   - إذا كان `auto_guard.enabled` مفعل، يتم إغلاق الصفقة تلقائيا عند TP/SL المحددة.
   - هذا لا يغير منطق BTC أو Follow Score.

5. إغلاق صفقة يدوية:
   - الواجهة ترسل `POST /api/trades/<trade_id>/close`.
   - `TradeService.close_trade()` يستخدم السعر الحالي.
   - close metadata تحفظ CVD عند الإغلاق و `cvd_delta_15m` و `cvd_trend` إذا كانت متاحة.
   - `TradeStore.close_trade()` يحدث الصفقة وينشئ صفا في `btc_radar_closed_trades`.

6. Lifecycle:
   - `TradeLifecycleService` يسجل أحداث ENTRY/CLOSE وتغيرات مهمة.
   - الخدمة passive ولا تنفذ فتح أو إغلاق صفقات.

## Reports Roadmap

الوضع الحالي:

- `/api/reports/generate` يولد تقريرا من `btc_radar_closed_trades`.
- التقرير يدعم:
  - Performance summary.
  - Spread analysis.
  - Judgment analysis.
  - Symbol analysis.
  - Equity curve.
  - Duration analysis.
  - BTC health analysis.
  - Follower health analysis.
  - Health matrix.
  - Funding analysis.
  - Conclusions مبسطة.

اتجاهات تطوير آمنة مستقبلا:

- إضافة اختبارات للتقارير حول bucketing و equity curve.
- إضافة export JSON/CSV بدون تغيير منطق الحساب.
- إضافة filters أكثر للتقارير مع الحفاظ على نفس source table.
- توثيق schema الخاص بالتقارير.
- عدم تحويل الاستنتاجات إلى قرارات تداول آلية بدون موافقة صريحة.

## Development Roadmap / Strategy Freeze

القرار الحالي: لا نضيف Strategy جديدة قبل بناء Reports Validation Layer. الهدف الآن هو إثبات متى تنجح صفقات BTCRadar ومتى تفشل، ثم استخدام النتائج لتوجيه أي تطوير لاحق.

الأولوية المعتمدة:

1. Reports / Validation أولا
   - تحليل الصفقات المغلقة حسب BTC spread، follower alignment، funding، CVD trend، health status، duration، والرمز.
   - الهدف: معرفة شروط النجاح والفشل من البيانات الحالية قبل تعديل أي منطق.

2. Replay / Backtest ثانيا
   - اختبار BTC spread + follower alignment + funding + CVD trend تاريخيا باستخدام snapshots والبيانات المخزنة.
   - الهدف: تقييم الفكرة على بيانات تاريخية، وليس فقط على الصفقات اليدوية.

3. DB Indexes + Retention ثالثا
   - تحسين أداء آمن عبر indexes و retention/downsampling عند الحاجة.
   - يجب ألا يغير الإشارات أو القرارات أو شكل الواجهة.

4. API Backoff رابعا
   - إضافة backoff/retry أكثر هدوءا لـ Binance و Coinalyze.
   - مهم للاستقرار، لكنه يأتي بعد إثبات/فهم الاستراتيجية.

5. فصل `/api/state` لاحقا
   - تحسين إنتاجي لتقليل الحمل وفصل polling عن العمليات الثقيلة.
   - يؤجل إلى ما بعد التقارير والتحقق.

قاعدة Strategy Freeze:

- لا تضف Strategy جديدة.
- لا تدخل مؤشرات جديدة في قرار BTC.
- لا تغير Follow Score أو BTC Narrative.
- لا تحول تقارير الأداء إلى قرارات تداول آلية.
- أي تطوير قريب يجب أن يخدم Reports Validation أو Replay/Backtest أولا.

## قواعد ممنوع تغييرها

هذه القواعد تعتبر حدودا ثابتة عند العمل على المشروع:

- لا تغير منطق التداول بدون طلب صريح.
- لا تغير BTC Narrative logic بدون طلب صريح.
- لا تغير Follow Score logic بدون طلب صريح.
- لا تدخل OI أو CVD في قرار BTC الأساسي إلا بطلب صريح.
- لا تغير Dashboard UI أو styling عند تنفيذ إصلاحات backend.
- لا تعمل refactor واسع لملفات غير مرتبطة.
- لا تغير schema بطريقة destructive.
- migrations يجب أن تكون additive وآمنة.
- لا تحذف بيانات من `data/btc_radar.db` إلا بطلب صريح.
- `TradeLifecycleService` يجب أن يبقى passive ولا ينفذ فتح/إغلاق.
- الإصلاحات التقنية يجب أن تحافظ على السلوك القائم قدر الإمكان.

## طريقة تشغيل الاختبارات

فحص التجميع:

```bash
python3 -m compileall -q src
```

تشغيل الاختبارات الحالية عبر unittest:

```bash
.venv/bin/python -m unittest discover -s tests
```

إذا تم تثبيت pytest لاحقا، يمكن تشغيل نفس الاختبارات بهذه الطريقة:

```bash
.venv/bin/python -m pytest
```

ملاحظة: الاختبارات الحالية مكتوبة بصيغة `unittest` القياسية حتى تعمل بدون الاعتماد على pytest.
