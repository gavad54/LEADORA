# LEADORA — وضعیت اجرایی انتشار و نقطه ادامه

**وضعیت کلی: مسدود برای انتشار تجاری تا تکمیل دروازه‌های حیاتی.**  
**آخرین بررسی شواهد:** 2026-10-25  
**قاعده:** وضعیت VERIFIED فقط برای شواهدی است که در همین بازبینی یا اجرای مشخص CI قابل مشاهده بوده‌اند؛ موفقیت Build به معنی نصب/اجرای واقعی یا آمادگی تجاری نیست.

## نقطه ادامه فعلی

- مخزن: https://github.com/gavad54/LEADORA
- PR مرجع: https://github.com/gavad54/LEADORA/pull/46
- شاخه کاری: fix/public-home-optional-auth
- HEAD شاخه در شروع این بررسی: 4a588219a8ad9ae50a7bc205bbbb984f93180420
- Base/شاخه مقصد: main، SHA هنگام بررسی: ead6a400347314f16303520bc016fb988fd621de
- وضعیت PR: باز، ادغام‌نشده و mergeable طبق API؛ تأیید انسانی و وضعیت کامل branch protection از اتصال فعلی قابل اثبات نیست.
- تغییر این سند روی همان شاخه یک Commit مستندات ایجاد می‌کند؛ پس از آن باید SHA جدید شاخه و CI تازه دوباره خوانده شود.

## فهرست اجرایی یکتا

| شناسه | وضعیت | شواهد فعلی | اقدام بعدی و معیار پایان |
|---|---|---|---|
| REL-01 | VERIFIED | PR #46 باز و mergeable؛ SHA بالا | پس از تغییر مستندات، HEAD و وضعیت PR/CI را دوباره ثبت کن؛ merge فقط بعد از عبور دروازه‌ها |
| CI-01 | VERIFIED | CI run [40162438526](https://github.com/gavad54/LEADORA/actions/runs/40162438526) موفق روی SHA 4a588... | اجرای تازه پس از Commit مستندات را بررسی کن؛ همه required checks باید روی کاندید نهایی موفق باشند |
| SEC-01 | VERIFIED | Regression & Security run [40162438515](https://github.com/gavad54/LEADORA/actions/runs/40162438515) موفق روی SHA 4a588... | نتایج را پس از تغییر کد مرتبط دوباره اجرا کن؛ تأیید مستقل امنیتی/نفوذ هنوز انجام‌شده محسوب نمی‌شود |
| APK-01 | VERIFIED | Android workflow [40162438567](https://github.com/gavad54/LEADORA/actions/runs/40162438567) موفق؛ Artifact ID 12587320566 موجود و منقضی نشده | APK موجود آزمایشی است؛ نصب/اجرای واقعی و تست گردش‌های اصلی هنوز لازم است |
| APK-02 | BLOCKED | APK com.leadora.app، version 1.0.0، versionCode=1، debug/debbugable؛ SHA-256 گزارش‌شده 7c1d8827187eba5f71fb91eeb5098dd402ef30498fdec67753594431c04838e8 | روی دستگاه یا emulator نصب و اجرا کن؛ اگر مسیر واقعی در دسترس نیست، مانع را باز نگه دار؛ برای انتشار تجاری کلید مجاز و امضای release لازم است |
| DB-01 | BLOCKED | Railway Volume leadora-data، ID 18cb4cf3-8061-43d6-94d7-170d7f043704، mount /data، حجم 500 MB؛ هیچ فایل backup مستقل و restore ایزوله با ابزار فعلی تأیید نشده | از مسیر مجاز میزبان یک backup خارج از Volume تولید تهیه/شناسایی کن؛ در محیط جداگانه restore و schema، رکوردها و فایل‌ها را اعتبارسنجی کن؛ شناسه backup و نتیجه restore را ثبت کن |
| OPS-01 | VERIFIED | Railway production service leadora-web آنلاین، یک replica، بدون failure/warning ثبت‌شده در وضعیت فعلی؛ آمار 24 ساعت: 27 پاسخ 2xx و 0 پاسخ 5xx | این فقط سیگنال سلامت پایه است؛ آزمون endpointها و پذیرش end-to-end روی نسخه هدف هنوز لازم است |
| OPS-02 | IN_PROGRESS | آخرین Deploy موفق ID 224694ef-5e27-42e8-bc8c-ac1d0975a7d2 روی SHA 4b9ba54f594f6a90f53656333880f805fe8a8028، branch main؛ زمان 2026-10-21T05:13:12Z | قبل از انتشار، منبع پیکربندی‌شده و Commit فعال را در پنل/ابزار تأیید کن؛ اختلاف SHA پیکربندی‌شده و Deploy را رفع ابهام کن |
| OPS-03 | BLOCKED | پیکربندی سرویس Railway، source branch=main و source commit SHA گزارش‌شده 7d92398a8e8e9b457fdfbf5f4dd1b75250506df7؛ آخرین Deploy موفق روی SHA متفاوت 4b9ba... | Auto Deploy، Wait for CI و روش rollback را از پنل تأیید کن؛ هیچ deploy تولیدی در این مرحله اجرا نشود |
| FIN-01 | IN_PROGRESS | PR مسیرهای عملیاتی مشارکت مالی مالک را بازنشسته می‌کند؛ ستون‌ها/داده تاریخی حذف نشده‌اند؛ ورودی‌های جدید بخش‌های اصلاح‌شده به IRR محدود شده‌اند | پیش از تبدیل داده تاریخی، واحد واقعی و منشأ هر فیلد را مشخص کن؛ مبالغ تاریخی فاقد currency نباید حدسی تبدیل شوند |
| REL-02 | BLOCKED | قواعد branch protection از API متصل قابل خواندن نبود (403)؛ endpoint rulesets پاسخ فهرست خالی داد، اما این به‌تنهایی همه سیاست‌های تأیید را اثبات نمی‌کند | در صورت الزام سیاست مخزن، تأیید انسانی را دریافت کن؛ هیچ کنترل اجباری دور زده نشود |

## شواهد CI و APK

- LEADORA CI: [40162438526](https://github.com/gavad54/LEADORA/actions/runs/40162438526) — موفق روی SHA 4a588219a8ad9ae50a7bc205bbbb984f93180420.
- Regression & Security: [40162438515](https://github.com/gavad54/LEADORA/actions/runs/40162438515) — موفق روی همان SHA.
- Android test APK: [40162438567](https://github.com/gavad54/LEADORA/actions/runs/40162438567) — موفق روی همان SHA شاخه؛ Build از merge-candidate موقت 151c4a4b366ab67028c228ebd11ecddd375fbb5e انجام شده، نه از SHA خام شاخه.
- Artifact فعلی: [GitHub Actions Artifact](https://github.com/gavad54/LEADORA/actions/runs/40162438567/artifacts/12587320566)؛ ZIP SHA-256: 43fe316b570c1cd053a7e9cd334045edbc73c48e94f7036ac20ab5c322f79093؛ انقضای گزارش‌شده 2026-11-24T04:36:24Z.
- APK debug/test است؛ امضای تجاری، نصب واقعی، اجرای صفحه اصلی و آزمون end-to-end هنوز تأیید نشده‌اند.

## وضعیت Railway و داده

- Production URL: https://leadora-web-production.up.railway.app/
- Health URL: https://leadora-web-production.up.railway.app/api/health
- Service ID: 13aa3d75-48b6-4ad1-8064-a7846ffe6739
- Environment ID: c3587e3a-9ff5-4749-bd91-2afdda4d5f77
- Active successful deployment: 224694ef-5e27-42e8-bc8c-ac1d0975a7d2, SHA 4b9ba54f594f6a90f53656333880f805fe8a8028.
- Volume تولید حفظ شده است؛ هیچ Volume یا داده‌ای حذف یا بازنویسی نشده است.
- نام متغیرهای محرمانه فقط برای بررسی پیکربندی مشاهده شد؛ مقادیر secret در این سند درج نمی‌شوند.
- شاخه backup/pre-reinstall-2026-10-24 یک نقطه بازیابی کد در SHA 7d92398a8e8e9b457fdfbf5f4dd1b75250506df7 است، نه مدرک backup پایگاه داده تولید.

## ترتیب ادامه

1. پس از Commit این سند، SHA جدید شاخه و وضعیت CI را دوباره ثبت کن.
2. از پنل/مسیر مجاز Railway یا میزبان، backup مستقل داده را شناسایی/تهیه و در محیط جدا restore کن؛ هیچ آزمایشی روی داده زنده انجام نده.
3. آزمون پذیرش end-to-end و بررسی امنیتی را روی کاندید مشخص انجام بده.
4. APK را روی دستگاه/emulator نصب و اجرا کن؛ سپس در صورت وجود کلید مجاز، release را امضا و گواهی را بررسی کن.
5. اختلاف source/deploy و Auto Deploy/Wait for CI را رفع ابهام کن؛ rollback را پیش از انتشار مستند کن.
6. فقط پس از تکمیل تمام دروازه‌های حیاتی، دریافت تأییدهای الزامی و بررسی مجدد Commit، ادغام و انتشار کنترل‌شده را انجام بده.

**محدودیت ابزار:** اتصال فعلی Railway امکان مشاهده مستقیم فایل‌های داخل /data یا اجرای امن فرمان backup/restore داخل کانتینر را در اختیار این جریان قرار نداده است. به همین دلیل، وجود Volume به‌عنوان backup تأیید نشده و هیچ ادعای restore موفق ثبت نشده است.
