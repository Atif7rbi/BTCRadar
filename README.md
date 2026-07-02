# BTCRadar

مشروع مستقل بالكامل عن Hunter Bot.

## التشغيل

```bash
cd BTCRadar
./run.sh
```

ثم افتح:

```text
http://localhost:5005
```

## ملاحظات
- السعر يحدث كل دقيقة حسب `price_refresh_sec`.
- LS يحدث كل خمس دقائق حسب `ls_refresh_sec`.
- LS يعرض Long أخضر وShort أحمر كنسبة مئوية.
- `config.yaml` هو المتحكم في الرموز، الأوزان، العتبات، والألوان.
- OI وCVD قراءة فقط حالياً ولا تدخل في قرار BTC.
