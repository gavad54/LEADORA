# افزوده ممیزی جاری — 2026-10-25T06:40Z

> این بخش خط مبنای جاری است. هر وضعیت قدیمی‌تر در ادامه سند فقط سابقه محسوب می‌شود و در صورت تعارض، این بخش و شواهد زنده GitHub/Railway ملاک‌اند. پس از هر تغییر جدید کد یا تنظیمات، نتایج مربوطه منقضی می‌شوند.

## خط مبنای زنده

- Repository: https://github.com/gavad54/LEADORA
- PR #46: https://github.com/gavad54/LEADORA/pull/46 — باز و ادغام‌نشده.
- Branch کاندید: `fix/public-home-optional-auth`
- آخرین SHA کد بررسی‌شده: `9320596c1a3390478c7c40f77c03ac58a65c025a`
- Base `main`: `ead6a400347314f16303520bc016fb988fd621de`
- آخرین بررسی API: 2026-10-25؛ `main` بدون branch protection گزارش شده است. این مورد مجوز Merge/Deploy محسوب نمی‌شود.
- فایل اصلی صفحه: `app/static/index.html`; راه‌اندازی فعلی ابتدا `showPublicHome()` را اجرا می‌کند و فقط پس از اعتبارسنجی نشست ذخیره‌شده، فضای کاری را باز می‌کند.

## نتایج آزمون روی SHA کاندید

| مورد | نتیجه | مدرک |
|---|---|---|
| LEADORA CI | PASS | [Run 40169583303](https://github.com/gavad54/LEADORA/actions/runs/40169583303), SHA `9320596...` |
| LEADORA CI (اجرای تکراری خودکار) | PASS | [Run 40169580324](https://github.com/gavad54/LEADORA/actions/runs/40169580324), SHA `9320596...` |
| Regression & Security | PASS | [Run 40169583265](https://github.com/gavad54/LEADORA/actions/runs/40169583265), SHA `9320596...`; `107 passed`, یک هشدار deprecation از Starlette/httpx |
| Android APK + emulator smoke test | IN PROGRESS / NOT VERIFIED | [Run 40169583285](https://github.com/gavad54/LEADORA/actions/runs/40169583285); هنگام ثبت این افزوده، مرحله نصب/اجرای APK در Android emulator هنوز در حال اجراست |
| نصب روی گوشی فیزیکی | NOT VERIFIED | ابزار/دستگاه فیزیکی در دسترس نیست |
| امضای تجاری Android | NOT VERIFIED | شواهد موجود مربوط به APK آزمایشی/debug است؛ کلید مجاز Release اثبات نشده |
| صفحه اصلی در Production | NOT VERIFIED | ابزار وب نتوانست URL را بخواند و دسترسی Railway به سرویس رد شد؛ نتیجه را از CI یا health قبلی استنتاج نکن |
| تطبیق source/deployment در Railway | BLOCKED | ابزار متصل Railway برای سرویس‌ها و deploymentها خطای role `viewer` می‌دهد |
| Backup خارج از Volume و Restore ایزوله | BLOCKED | دسترسی مجاز به فایل DB/میزبان و محیط Restore مستقل موجود نیست؛ هیچ داده زنده‌ای تغییر نکرده است |

## Railway — مانع دسترسی جاری

- Railway account connection شناسایی شد و فهرست پروژه‌ها شامل پروژه LEADORA است.
- خواندن سرویس‌ها، deploymentها و وضعیت محیط با خطای `You don't have the required role (viewer) on this resource.` رد می‌شود.
- این تناقض با گزارش قبلی کاربر مبنی بر Admin بودن، علت را به‌تنهایی مشخص نمی‌کند؛ ممکن است نقش پروژه یا اتصال/هویت مجاز متصل باشد. هیچ تغییری در تنظیمات یا deploy انجام نشده است.
- Production URL: https://leadora-web-production.up.railway.app
- آخرین مدرک تاریخی ثبت‌شده در پایین سند درباره deployment در 2026-10-21 است؛ تا دسترسی خواندن مجاز بازیابی نشود، آن را به‌عنوان نسخه فعلی قطعی تلقی نکن.

## جلوگیری از تکرار

در اجرای بعدی ابتدا همین سند و API زنده GitHub را بخوان؛ سپس فقط مواردی را دوباره اجرا کن که SHA، workflow، artifact، تنظیمات، مجوز، deployment یا پایگاه داده‌شان تغییر کرده یا شواهدشان منقضی شده است. هر نتیجه باید به SHA و Run ID مشخص گره بخورد. نتیجه CI سبز، وجود APK، آنلاین بودن سرویس یا وجود Volume جایگزین نصب واقعی، امضای تجاری، Production smoke test، Backup مستقل و Restore ایزوله نیست.

---

# LEADORA — وضعیت اجرایی انتشار و نقطه ادامه

**وضعیت کلی: مسدود برای انتشار تجاری تا تکمیل دروازه‌های حیاتی.**  
**آخرین بررسی شواهد:** 2026-10-25؛ شواهد تازه برای Commit کاندید `633f5ffe4ffa9e18f764c870614135dd7d0dcd49`  
**قاعده:** وضعیت VERIFIED فقط برای شواهدی است که در همین بازبینی یا اجرای مشخص CI قابل مشاهده بوده‌اند؛ موفقیت Build به معنی نصب/اجرای واقعی یا آمادگی تجاری نیست.

## نقطه ادامه فعلی

- مخزن: https://github.com/gavad54/LEADORA
- PR مرجع: https://github.com/gavad54/LEADORA/pull/46
- شاخه کاری: fix/public-home-optional-auth
- Commit کاندید تأییدشده برای این بررسی: `633f5ffe4ffa9e18f764c870614135dd7d0dcd49` (PR head)
- Base/شاخه مقصد: main، SHA هنگام بررسی: ead6a400347314f16303520bc016fb988fd621de
- وضعیت PR: باز، ادغام‌نشده و mergeable طبق API؛ تأیید انسانی و وضعیت کامل branch protection از اتصال فعلی قابل اثبات نیست.
- CI و تست‌ها در ادامه این سند برای Commit کاندید بالا بررسی شده‌اند؛ تغییر این سند پس از آن فقط مستنداتی است و نباید به‌عنوان تغییر برنامه تلقی شود.

## فهرست اجرایی یکتا

| شناسه | وضعیت | شواهد فعلی | اقدام بعدی و معیار پایان |
|---|---|---|---|
| REL-01 | VERIFIED | PR #46 باز و mergeable؛ SHA بالا | پس از تغییر مستندات، HEAD و وضعیت PR/CI را دوباره ثبت کن؛ merge فقط بعد از عبور دروازه‌ها |
| CI-01 | VERIFIED | [CI run 40164048187](https://github.com/gavad54/LEADORA/actions/runs/40164048187) موفق روی PR head `633f5ffe...`; pytest: 107 passed; Node syntax checks و Docker image build نیز موفق | پس از هر تغییر کد مرتبط، کنترل‌های لازم روی SHA جدید اجرا شوند |
| SEC-01 | VERIFIED | [Regression & Security run 40164048177](https://github.com/gavad54/LEADORA/actions/runs/40164048177) موفق روی PR head `633f5ffe...`; pytest: 107 passed, یک هشدار deprecation از Starlette/httpx | بررسی امنیتی مستقل/نفوذ جداگانه انجام نشده است؛ هشدار وابستگی برای رسیدگی غیرمسدودکننده ثبت شود |
| APK-01 | VERIFIED | [Android workflow 40164048176](https://github.com/gavad54/LEADORA/actions/runs/40164048176) موفق روی PR head `633f5ffe...`; Artifact ID `12587133683`, expires 2026-11-24 | Build و apksigner verification موفق‌اند؛ APK آزمایشی است و نصب/اجرای واقعی هنوز لازم است |
| APK-02 | BLOCKED | APK `com.leadora.app`, `versionName=1.0.0`, `versionCode=1`, `minSdk=23`, `targetSdk=35`, `debuggable`; source commit داخل build metadata: `661f1a55456962b0d228e2551a4f898ca88012cb` (synthetic PR merge); APK SHA-256 `d1411ab956a4c9856c64a75a24313c533a619480d8bb0de858d749e22f3736ea`; ZIP SHA-256 `f0eb5a472794d4e39bfd77bd21998178feca2b606c16e32a78f63edf83b84636` | نصب/اجرای واقعی مسدود است: این محیط `adb` و `emulator` ندارد. Release signing workflow موجود است اما secrets/کلید مجاز و اجرای Release تأیید نشده‌اند |
| DB-01 | BLOCKED | Railway Volume leadora-data، ID 18cb4cf3-8061-43d6-94d7-170d7f043704، mount /data، حجم 500 MB؛ هیچ فایل backup مستقل و restore ایزوله با ابزار فعلی تأیید نشده | از مسیر مجاز میزبان یک backup خارج از Volume تولید تهیه/شناسایی کن؛ در محیط جداگانه restore و schema، رکوردها و فایل‌ها را اعتبارسنجی کن؛ شناسه backup و نتیجه restore را ثبت کن |
| OPS-01 | VERIFIED | Railway production `leadora-web` آنلاین، یک replica، صفر failure/warning ثبت‌شده؛ متریک آخرین 24 ساعت: 29 پاسخ 2xx و صفر 4xx/5xx؛ لاگ آخرین مشاهده `/api/health` برابر 200 در 2026-10-25 | این فقط سلامت پایه نسخه فعلی را نشان می‌دهد؛ نسخه PR در Production مستقر نیست و پذیرش end-to-end آن انجام نشده است |
| OPS-02 | IN_PROGRESS | آخرین Deploy موفق ID 224694ef-5e27-42e8-bc8c-ac1d0975a7d2 روی SHA 4b9ba54f594f6a90f53656333880f805fe8a8028، branch main؛ زمان 2026-10-21T05:13:12Z | قبل از انتشار، منبع پیکربندی‌شده و Commit فعال را در پنل/ابزار تأیید کن؛ اختلاف SHA پیکربندی‌شده و Deploy را رفع ابهام کن |
| OPS-03 | BLOCKED | پیکربندی سرویس Railway، source branch=main و source commit SHA گزارش‌شده 7d92398a8e8e9b457fdfbf5f4dd1b75250506df7؛ آخرین Deploy موفق روی SHA متفاوت 4b9ba... | Auto Deploy، Wait for CI و روش rollback را از پنل تأیید کن؛ هیچ deploy تولیدی در این مرحله اجرا نشود |
| FIN-01 | IN_PROGRESS | PR مسیرهای عملیاتی مشارکت مالی مالک را بازنشسته می‌کند؛ ستون‌ها/داده تاریخی حذف نشده‌اند؛ ورودی‌های جدید بخش‌های اصلاح‌شده به IRR محدود شده‌اند | پیش از تبدیل داده تاریخی، واحد واقعی و منشأ هر فیلد را مشخص کن؛ مبالغ تاریخی فاقد currency نباید حدسی تبدیل شوند |
| REL-02 | BLOCKED | قواعد branch protection از API متصل قابل خواندن نبود (403)؛ endpoint rulesets پاسخ فهرست خالی داد، اما این به‌تنهایی همه سیاست‌های تأیید را اثبات نمی‌کند | در صورت الزام سیاست مخزن، تأیید انسانی را دریافت کن؛ هیچ کنترل اجباری دور زده نشود |

## شواهد CI و APK

- LEADORA CI: [40162438526](https://github.com/gavad54/LEADORA/actions/runs/40162438526) — موفق روی SHA 4a588219a8ad9ae50a7bc205bbbb984f93180420.
- Regression & Security: [40162438515](https://github.com/gavad54/LEADORA/actions/runs/40162438515) — موفق روی همان SHA.
- Android test APK: [40162438567](https://github.com/gavad54/LEADORA/actions/runs/40162438567) — موفق روی همان SHA شاخه؛ Build از merge-candidate موقت 151c4a4b366ab67028c228ebd11ecddd375fbb5e انجام شده، نه از SHA خام شاخه.
- Artifact فعلی: [GitHub Actions Artifact](https://github.com/gavad54/LEADORA/actions/runs/40162438567/artifacts/12587320566)؛ ZIP SHA-256: 43fe316b570c1cd053a7e9cd334045edbc73c48e94f7036ac20ab5c322f79093؛ انقضای گزارش‌شده 2026-11-24T04:36:24Z.
- APK debug/test است؛ `apksigner verify --verbose` در CI موفق بوده، اما نصب واقعی، اجرای صفحه اصلی و آزمون end-to-end هنوز تأیید نشده‌اند. Log build هشدارهای deprecation در Gradle/Node را نیز دارد؛ شکست Build گزارش نشده است.
- Workflow امضای تجاری در `.github/workflows/android-release.yml` موجود است و اجرای دستی می‌خواهد؛ وجود و صحت Secrets کلید امضا از اتصال فعلی قابل بررسی نیست. Workflow در صورت نبود Secrets باید متوقف شود؛ هیچ کلید یا secretی ساخته/تغییر داده نشده است.

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
4. محیط آزمون Android با `adb` یا emulator راه‌اندازی شود و APK موجود نصب/اجرا شود؛ سپس فقط با کلید مجاز و Secrets تأییدشده workflow `.github/workflows/android-release.yml` اجرا شود.
5. اختلاف source/deploy و Auto Deploy/Wait for CI را رفع ابهام کن؛ rollback را پیش از انتشار مستند کن.
6. فقط پس از تکمیل تمام دروازه‌های حیاتی، دریافت تأییدهای الزامی و بررسی مجدد Commit، ادغام و انتشار کنترل‌شده را انجام بده.

**محدودیت‌های واقعی:** اتصال Railway امکان خواندن مستقیم `/data` یا اجرای امن backup/restore داخل کانتینر را ندارد؛ بنابراین Backup مستقل و restore ایزوله هنوز اثبات نشده‌اند. محیط اجرای فعلی نیز `adb` و Android emulator ندارد؛ در نتیجه نصب/اجرای APK مسدود است. ابزار Railway، Volume را نشان می‌دهد اما این Volume پشتیبان مستقل محسوب نمی‌شود. هیچ داده یا Volume تولیدی حذف یا بازنویسی نشده است.
