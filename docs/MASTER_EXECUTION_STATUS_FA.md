# داشبورد اجرای LEADORA — وضعیت مستند و زنده

آخرین بازبینی: 2026-11-02  
مخزن: `gavad54/LEADORA`  
شاخه اجرایی: `fix/public-home-optional-auth`  
PR مرجع: [#46](https://github.com/gavad54/LEADORA/pull/46)

> این داشبورد فقط وضعیت‌هایی را VERIFIED می‌نامد که برایشان شواهد مستقیم ثبت شده باشد. وضعیت Workflow در حال اجرا، موفقیت Build، یا آنلاین بودن سرویس به‌تنهایی به معنی آماده‌بودن انتشار نیست.

## خط مبنای Git

- شاخه پیش‌فرض: `main`
- آخرین SHA تأییدشده `main`: `ead6a400347314f16303520bc016fb988fd621de`
- آخرین HEAD شاخه PR #46 در زمان ثبت: `ae4aeaaadbf3e89f0d1e7be428fb03ef138e19ec`
- اختلاف شاخه: 149 commit جلوتر، 0 commit عقب‌تر از `main`
- PR #46: باز، ادغام‌نشده، mergeable=true؛ 28 فایل تغییرکرده؛ هیچ فایل موجودی در مقایسه گزارش‌شده حذف نشده است.
- بازبینی رسمی و inline review ثبت‌شده: صفر.
- PR #47 یک PR جداگانه و Draft برای نصب مستقل مشتریان است؛ جایگزین PR #46 نیست و هنوز نباید ادغام شود.

## وضعیت اجرایی

| ID | موضوع | اولویت | وضعیت | Commit | محیط | شواهد | تست | وابستگی | اقدام بعدی | معیار پذیرش |
|---|---|---|---|---|---|---|---|---|---|---|
| GIT-01 | تطبیق main و شاخه PR | بحرانی | VERIFIED | `ae4aeaa` / `ead6a40` | GitHub | مقایسه زنده: 149 جلو، 0 عقب | compare API موفق | ندارد | ادامه بازبینی | SHA و اختلاف ثبت‌شده |
| PR-01 | وضعیت PR مرجع | بالا | CONFIRMED | `ae4aeaa` | GitHub | PR #46 باز و mergeable؛ بدون Review رسمی | بررسی metadata و review threads | بازبینی انسانی | تکمیل review و پاسخ به یافته‌ها | Review و تصمیم ادغام مستند |
| CI-01 | CI اصلی | بالا | VERIFIED | `ae4aeaa` | GitHub Actions | Run [41381068869](https://github.com/gavad54/LEADORA/actions/runs/41381068869) موفق | 114 passed، 1 warning؛ compileall، JS syntax، manifest، Docker build موفق | هشدار deprecation وابستگی | تعیین تکلیف هشدار | تمام مراحل اجباری موفق |
| SEC-01 | Regression و Security | بحرانی | VERIFIED | `ae4aeaa` | GitHub Actions | Run [41381068910](https://github.com/gavad54/LEADORA/actions/runs/41381068910) موفق | 114 passed، 1 warning | هشدار Starlette/httpx | به‌روزرسانی وابستگی در چرخه بعدی | تست‌های امنیت/رگرسیون سبز |
| AND-01 | ساخت APK آزمایشی | بالا | VERIFIED | `ae4aeaa` | GitHub Actions | Run [41381068998](https://github.com/gavad54/LEADORA/actions/runs/41381068998) | Gradle build موفق | نتیجه Emulator هنوز نهایی نیست | تکمیل مرحله Emulator | APK از SHA نهایی و نصب/اجرا اثبات شود |
| AND-02 | راه‌اندازی Emulator و ADB | بحرانی | IN_PROGRESS | `ae4aeaa` | GitHub Actions | اصلاح KVM در `a5683e6` و تست قراردادی در `ae4aeaa` | مرحله نصب/اجرا در Run 41381068998 در حال اجرا هنگام ثبت | دسترسی KVM در runner | بررسی نتیجه، ADB، screenshot و Logcat | Boot، install، launch، foreground و screenshot موفق |
| WEB-01 | صفحه عمومی Production | بحرانی | BLOCKED | Production: `4b9ba54`؛ PR: `ae4aeaa` | Railway | در Run 41381068998، API health موفق اما 6 شرط DOM صفحه عمومی ناموفق گزارش شد | publicHome، visibility، authOverlay، workspaceShell، startup و login action ناموفق | استقرار نسخه PR پس از Backup/Restore و ادغام | اصلاح و استقرار کنترل‌شده پس از عبور Gate داده | مرورگر واقعی Production صفحه عمومی را نمایش دهد |
| WEB-02 | اختلاف نسخه Production | بحرانی | CONFIRMED | deployed `4b9ba54`; source pin `7d92398` | Railway | Deployment `224694ef-5e27-42e8-bc8c-ac1d0975a7d2`؛ Source branch=main و pin متفاوت | سرویس Online، یک replica | Backup/Restore و تصمیم Release | تطبیق Source و Deployment با rollback مشخص | Commit مستقرشده دقیقاً Commit تأییدشده باشد |
| OPS-01 | سلامت سرویس | بالا | VERIFIED | `4b9ba54` | Railway Production | Online؛ 1/1 replica؛ 0 crash؛ 0 هشدار و 0 critical در آخرین status | Health API در Android workflow موفق | سلامت کامل محصول هنوز اثبات نشده | ادامه smoke و E2E پس از استقرار | Health + صفحه + API + auth + tenant E2E |
| DATA-01 | Volume و مسیر داده | بحرانی | CONFIRMED | — | Railway Production | Volume `leadora-data`، مسیر `/data`، ظرفیت 500MB | فقط inventory خواندنی | مجوز Backup مستقل | تهیه Backup خارج از Volume | فایل مستقل با اندازه، زمان و SHA-256 |
| DATA-02 | Restore واقعی | بحرانی | BLOCKED | — | ایزوله | مدرک Restore مستقل در دسترس نیست | انجام نشده | Backup معتبر و دسترسی مالک | Restore در محیط ایزوله و تطبیق داده | SQLite integrity، جداول، روابط و تست کاربردی |
| FIN-01 | بازنشسته‌سازی مشارکت مالی فعال | بالا | VERIFIED | `ae4aeaa` | کد/CI | routeهای فعال settlement و owner overview در Router جاری وجود ندارند؛ داده legacy حفظ می‌شود | `test_legacy_participation_preservation.py`؛ 404 مسیرهای بازنشسته و حفظ سوابق | بررسی انسانی نهایی | مرور Diff و گزارش نهایی | عملیات فعال غیرفعال؛ تاریخچه محفوظ |
| FIN-02 | واحد پول IRR | بحرانی | UNVERIFIED | `ae4aeaa` | کد/داده | کدهای محافظ مالی موجودند؛ ممیزی داده زنده و تبدیل‌های قدیمی انجام نشده | پوشش آزمون محدود | Backup/Restore و نمونه داده واقعی | ممیزی واحد هر فیلد و عدم تبدیل دوباره | نمونه‌های مستقل و تطبیق مالی |
| AND-03 | امضای رسمی APK | بحرانی | BLOCKED | — | GitHub Secrets | Workflow رسمی به 4 Secret امضا نیاز دارد؛ وجود/اعتبار کلید تأیید نشده | امضای تجاری اجرا نشده | کلید معتبر مالک در Protected Secrets | مالک کلید را فقط در Secret Manager تنظیم و workflow را اجرا کند | apksigner و certificate fingerprint معتبر |
| AND-04 | نصب روی گوشی واقعی | بالا | UNVERIFIED | — | دستگاه واقعی | تست فیزیکی در دسترس نیست | انجام نشده | گوشی/آزمونگر | UAT پس از APK تأییدشده | نصب و گردش‌های اصلی روی دستگاه واقعی |
| SEC-02 | Tenant Isolation | بحرانی | UNVERIFIED | — | کد/Production | تست‌های خودکار موجودند؛ آزمون دو نصب مستقل روی محیط واقعی ثبت نشده | Regression CI موفق؛ آزمون استقرار مستقل انجام نشده | دو محیط مستقل و داده آزمایشی | تست نفوذ/جداسازی دو نصب | هیچ دسترسی متقاطع بین مشتریان |
| UI-01 | فارسی، RTL و Static Assets | بالا | IN_PROGRESS | `ae4aeaa` | Web/Android | سند HTML شاخه RTL است؛ صفحه Production قدیمی است | JS syntax و CI موفق | استقرار نسخه PR | بررسی بصری مرورگر و Android | بدون 404، صفحه RTL خوانا و responsive |
| REL-01 | انتشار تجاری | بحرانی | BLOCKED | — | Production/Android | Gateهای داده، صفحه Production، Emulator، امضای رسمی و UAT باز هستند | انتشار تجاری انجام نشده | تکمیل Gateهای A تا G | عدم ادغام/Deploy تا رفع موانع | همه Gateها با شواهد مستقل PASS |

## علت ریشه‌ای موانع فعلی

### صفحه اصلی

Android `MainActivity` نشانی ثابت Production را باز می‌کند؛ HTML شاخه PR دارای منطق صفحه عمومی است، اما نسخه مستقرشده در Railway قدیمی است. آزمون Production در Workflow روی Run جدید، API health را موفق دید ولی شرایط DOM صفحه عمومی را رد کرد. بنابراین ساخت APK از شاخه PR بدون استقرار نسخه وب صحیح، مشکل صفحه شروع را حل نمی‌کند.

### Android Emulator

Artifact اجرای قبلی نشان داد runner به `/dev/kvm` دسترسی نداشت و Emulator x86_64 با خطای نیاز به hardware acceleration متوقف شد. Workflow جدید پیش از ساخت/اجرای AVD دسترسی KVM را روی runner موقت تنظیم می‌کند. نتیجه نهایی این اصلاح هنوز در حال آزمون است و تا پایان job، VERIFIED محسوب نمی‌شود.

## اقدامات نیازمند مالک

1. مجوز امن تهیه Backup کامل و مستقل از Volume تولیدی؛ هیچ رمز یا توکنی در چت ارسال نشود.
2. اجرای Restore در محیط ایزوله و ارائه شواهد قابل ممیزی.
3. تنظیم کلید امضای معتبر Release فقط در Protected GitHub Secrets؛ کلید خصوصی نباید در Repository یا چت قرار گیرد.
4. تأیید انسانی Review و تصمیم ادغام طبق سیاست مخزن.
5. آزمون نهایی APK روی دستگاه واقعی در صورت نیاز به تأیید تجاری.

## سیاست انتشار

- هیچ تغییر Production، Migration، Volume یا DB در این مرحله اعمال نشده است.
- PR #46 ادغام نشده است.
- Deploy جدید انجام نشده است.
- وضعیت نهایی فعلی: **DEPLOYMENT BLOCKED**؛ تا عبور Gateهای داده، صفحه Production، Android، Security و امضای رسمی، ادعای تحویل تجاری مجاز نیست.
