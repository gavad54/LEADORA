# داشبورد اجرای LEADORA — وضعیت مستند و زنده

آخرین بازبینی: 2026-11-02  
Repository: `gavad54/LEADORA`  
Branch: `fix/public-home-optional-auth`  
PR مرجع: [#46](https://github.com/gavad54/LEADORA/pull/46)

> وضعیت‌ها فقط بر پایه شواهد مستقیم تعیین می‌شوند. Build موفق یا اجرای Activity به‌تنهایی معادل نمایش صحیح UI یا آمادگی انتشار نیست.

## خط مبنای GitHub

- `main`: `ead6a400347314f16303520bc016fb988fd621de`
- آخرین HEAD کد PR #46 هنگام ثبت این داشبورد: `d7b41be5b824c0742360a29cb7ff186ffc216fad`
- PR #46: باز، ادغام‌نشده، mergeable=true؛ 153 commit؛ 29 فایل تغییرکرده.
- هیچ Review رسمی یا inline review thread ثبت نشده است.
- PR #47 یک PR مستقل و Draft برای نصب مجزای مشتریان است؛ جایگزین PR #46 نیست و نباید با PR اصلی ادغام شود.

## جدول وضعیت

| ID | موضوع | اولویت | وضعیت | Commit / Run | محیط | شواهد و تست | وابستگی | اقدام بعدی | معیار پذیرش |
|---|---|---|---|---|---|---|---|---|---|
| GIT-01 | تطبیق شاخه‌ها | بحرانی | VERIFIED | `d7b41be` / `ead6a40` | GitHub | PR قابل ادغام؛ 153 commit و 29 فایل | ندارد | بازبینی نهایی Diff | SHA و اختلاف دقیق ثبت شود |
| PR-01 | PR مرجع | بالا | CONFIRMED | PR #46 | GitHub | Open، Unmerged، mergeable؛ بدون Review | بازبینی انسانی | بازبینی رسمی و تعیین تکلیف کامنت‌ها | Review مستند و تصمیم ادغام |
| CI-01 | CI اصلی | بالا | VERIFIED | Run [41381427572](https://github.com/gavad54/LEADORA/actions/runs/41381427572) | GitHub Actions | موفق؛ 114 تست، 1 هشدار؛ compileall، بررسی JS، manifest و Docker build موفق | هشدارهای deprecation | تعیین تکلیف هشدارها | تمام تست‌های اجباری موفق |
| SEC-01 | Regression/Security | بحرانی | VERIFIED | Run [41381427707](https://github.com/gavad54/LEADORA/actions/runs/41381427707) | GitHub Actions | موفق؛ 114 تست و 1 هشدار | هشدار Starlette/httpx | اصلاح وابستگی در چرخه بعدی | تمام آزمون‌های امنیت/رگرسیون سبز |
| AND-01 | APK آزمایشی و نصب | بالا | VERIFIED | Run [41381068998](https://github.com/gavad54/LEADORA/actions/runs/41381068998)؛ build source `2d8e6d2` | Emulator API 30 | Gradle build، نصب، اجرای MainActivity و ADB موفق | آزمون UI قبلی ناکافی بود | اجرای تست DOM جدید | DOM قابل مشاهده و صفحه مورد انتظار |
| AND-02 | صحت محتوای WebView | بحرانی | BLOCKED | Artifact 13113422946 | Android Emulator | screenshot واقعی سفید/خالی؛ فقط Activity foreground و نبود FATAL EXCEPTION قبلاً بررسی شده بود | تشخیص DOM و بارگذاری صفحه | اجرای DOM probe جدید و بررسی screenshot/logcat | متن قابل مشاهده و UI واقعی؛ صفحه عمومی پس از انتشار نسخه صحیح |
| AND-03 | DOM/Console diagnostics | بحرانی | IN_PROGRESS | `e15b8c6`, `26f00a5`, `d7b41be` | Android/CI | افزودن لاگ DOM، Console و خطای WebView؛ Workflow اکنون textLength و visibleTextNodes را الزام می‌کند | Run [41381427618](https://github.com/gavad54/LEADORA/actions/runs/41381427618) در حال اجرا هنگام ثبت | بررسی نتیجه و artifact جدید | DOM متن و عنصر قابل مشاهده داشته باشد؛ screenshot بررسی شود |
| WEB-01 | صفحه عمومی Production | بحرانی | BLOCKED | Production `4b9ba54`; PR `d7b41be` | Railway | Run 41381068998: `public_home_present=false`، `public_home_visible=false`، `authOverlay_hidden=false`، `workspace_hidden=false`، startup و login action ناموفق | استقرار امن پس از Backup/Restore | رفع mismatch و deploy کنترل‌شده | صفحه عمومی واقعی در Production و Android نمایش داده شود |
| WEB-02 | اختلاف Source/Deployment | بحرانی | CONFIRMED | deployed `4b9ba54`; source pin `7d92398` | Railway | Deployment `224694ef-5e27-42e8-bc8c-ac1d0975a7d2`؛ source branch=main؛ commitها متفاوت‌اند | Backup و rollback | تطبیق Source و deployment | Commit مستقرشده دقیقاً Commit تأییدشده باشد |
| OPS-01 | سلامت سرویس | بالا | VERIFIED | `4b9ba54` | Railway | سرویس Online، یک replica؛ Health API در smoke موفق | سلامت کامل محصول اثبات نشده | E2E پس از استقرار | Health، UI، API، Auth و tenant E2E موفق |
| DATA-01 | Volume داده | بحرانی | CONFIRMED | — | Railway | `leadora-data`، mount در `/data`، ظرفیت 500MB | مجوز مالک برای Backup مستقل | تهیه نسخه خارج از Volume | SHA-256، اندازه، زمان و محل مستقل |
| DATA-02 | Restore مستقل | بحرانی | BLOCKED | — | محیط ایزوله | Restore واقعی Production اثبات نشده | Backup کامل و مجوز معتبر | Restore ایزوله و آزمون کاربردی | SQLite integrity، جداول، روابط و تست برنامه |
| FIN-01 | بازنشسته‌سازی مشارکت مالی فعال | بالا | VERIFIED | `d7b41be` | کد/CI | routeهای settlement و owner overview غیرفعال؛ سوابق legacy حفظ می‌شوند | آزمون `test_legacy_participation_preservation.py` | مرور انسانی نهایی | عملیات فعال بسته؛ تاریخچه دست‌نخورده |
| FIN-02 | صحت IRR و عدم تبدیل دوباره | بحرانی | UNVERIFIED | `d7b41be` | داده/کد | کنترل‌های کد و تست‌های IRR وجود دارد؛ ممیزی داده واقعی و واحد تمام فیلدها انجام نشده | Backup مستقل | ممیزی داده و نمونه‌های مستقل | بدون تبدیل مضاعف؛ مبالغ منطبق |
| SEC-02 | Tenant Isolation واقعی | بحرانی | UNVERIFIED | — | محیط واقعی | تست‌های خودکار موفق؛ دو نصب مستقل در محیط واقعی آزموده نشده | محیط‌های مستقل و داده آزمایشی | تست جداسازی دو شرکت | هیچ خواندن/نوشتن بین tenantها |
| AND-04 | امضای رسمی Release | بحرانی | BLOCKED | — | GitHub Secrets | Workflow نیازمند 4 Secret امضاست؛ اعتبار کلید و certificate تأیید نشده | کلید معتبر مالک در Protected Secrets | اجرای release workflow پس از تنظیم امن | apksigner و fingerprint معتبر |
| AND-05 | مشخصات APK آزمایشی | بالا | CONFIRMED | Run 41381068998 | Artifact | package `com.leadora.app`؛ versionCode 1؛ versionName 1.0.0؛ minSdk 23؛ targetSdk 35؛ 13,495 bytes؛ SHA-256 `178bee1ff1977f578a8e3b152a35e618b1a6a75c56e590c70c7f308072f609f3` | این APK Debug است و build source آن merge SHA `2d8e6d2` بوده | Build مجدد از Commit نهایی و UAT | APK Release امضاشده از Commit نهایی |
| UI-01 | فونت و Static Assets | بالا | IN_PROGRESS | `d7b41be` | Web/Android | WebView log خطای CSS font از Production قدیمی نشان داد؛ شاخه PR از فونت سیستم آفلاین استفاده می‌کند | Deploy نسخه PR | بررسی پس از Deploy | بدون خطای CSS/font و 404 |
| REL-01 | انتشار تجاری | بحرانی | BLOCKED | — | Production/Android | صفحه عمومی، DOM واقعی WebView، Backup/Restore، امضای رسمی و UAT باز هستند | عبور تمام Gateها | ادامه اصلاحات و آزمون | تمام Gateهای A تا G با شواهد PASS |

## یافته‌های ریشه‌ای

### صفحه عمومی وب

نسخه Production روی Commit قدیمی است. در HTML شاخه PR صفحه عمومی وجود دارد، اما HTML نسخه `main` و Commit مستقرشده قدیمی هنوز ساختار قبلی ورود/Workspace را دارد. Smoke check واقعی در Run 41381068998 شش شرط اصلی صفحه عمومی را رد کرد. APK به همین نشانی ثابت Production متصل می‌شود؛ ساخت APK به‌تنهایی مشکل را رفع نمی‌کند.

### صفحه سفید Android

Artifact قبلی نشان داد Emulator boot، نصب و اجرای `MainActivity` موفق بوده، اما screenshot سفید است. Logcat یک خطای stylesheet مربوط به درخواست فونت در Production ثبت کرد. آزمون قبلی DOM یا متن قابل مشاهده را کنترل نمی‌کرد؛ بنابراین PASS قبلی برای UI کافی نبود. Commitهای جدید تشخیص DOM، Console و WebView error را اضافه کرده‌اند و Run 41381427618 باید مشخص کند آیا WebView واقعاً محتوای قابل مشاهده دارد یا خیر.

### Emulator/KVM

علت شکست قبلی AVD، دسترسی نداشتن Runner به `/dev/kvm` بود. اصلاح دسترسی KVM در Workflow ثبت شد و Run 41381068998 نشان داد AVD بالا آمد، ADB دستگاه را دید و APK نصب و اجرا شد.

## موارد نیازمند مالک

1. مجوز امن Backup کامل و مستقل از Volume Production؛ هیچ رمز یا توکنی در چت ارسال نشود.
2. Restore واقعی در محیط ایزوله و ارائه شواهد قابل ممیزی.
3. کلید رسمی امضای Release فقط در Protected GitHub Secrets.
4. Review انسانی و تصمیم ادغام طبق سیاست مخزن.
5. UAT نهایی روی دستگاه واقعی در صورت الزام تجاری.

## سیاست انتشار فعلی

- هیچ تغییر Production، Volume، DB یا Migration انجام نشده است.
- PR #46 ادغام نشده است.
- Deploy جدید انجام نشده است.
- وضعیت: **DEPLOYMENT BLOCKED**.
- تا اثبات Backup/Restore، رفع صفحه Production، اثبات محتوای واقعی WebView، امضای رسمی و تکمیل Gateهای امنیتی، انتشار تجاری مجاز نیست.
