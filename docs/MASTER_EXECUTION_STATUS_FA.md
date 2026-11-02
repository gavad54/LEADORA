# داشبورد اجرای LEADORA — وضعیت مستند و زنده

آخرین بازبینی: 2026-11-02  
Repository: `gavad54/LEADORA`  
Branch: `fix/public-home-optional-auth`  
PR مرجع: [#46](https://github.com/gavad54/LEADORA/pull/46)

> VERIFIED فقط برای شواهد مستقیم همان Commit/محیط استفاده می‌شود. موفقیت CI یا اجرای Activity به‌تنهایی معادل پذیرش Production یا تحویل تجاری نیست.

## خط مبنای زنده GitHub

- `main`: `ead6a400347314f16303520bc016fb988fd621de`
- PR #46 HEAD در snapshot فعلی: `e83236df8d95177dca4fe813232240075ede2bc3`
- Compare زنده: PR شاخه نسبت به main دارای 154 commit جلو و صفر commit عقب؛ 29 فایل تغییرکرده.
- PR #46: Open، Unmerged، Draft=false، mergeable=true؛ 154 commit.
- Review رسمی و inline review thread: صفر.
- PR #47: Open و Draft؛ شاخه مستقل نصب‌های مشتریان است و جایگزین PR #46 نیست.

## جدول وضعیت اجرایی

| ID | موضوع | اولویت | وضعیت | Commit / Run | محیط | شواهد و تست | وابستگی | اقدام بعدی | معیار پذیرش |
|---|---|---|---|---|---|---|---|---|---|
| GIT-01 | خط مبنای شاخه‌ها | بحرانی | VERIFIED | `649d4d0` / `ead6a40` | GitHub | compare زنده: 154 جلو، 0 عقب، 29 فایل | ندارد | بازبینی نهایی Diff و کامنت‌ها | SHA نهایی و تغییرات دقیق تأیید شود |
| PR-01 | PR مرجع | بالا | CONFIRMED | PR #46 | GitHub | Open، Unmerged، mergeable؛ بدون Review رسمی | بازبینی انسانی | تکمیل Review و تعیین تکلیف همه یافته‌ها | Review و تصمیم Merge مستند |
| PR-02 | PR معماری نصب مستقل | متوسط | CONFIRMED | PR #47 HEAD `24c7601` | GitHub | Draft=true؛ 65 commit؛ مستقل از PR #46 | تثبیت هسته | جدا از PR اصلی نگه داشته شود | ادغام مستقل پس از آزمون و تأیید |
| CI-01 | CI اصلی | بالا | VERIFIED | Run [41381631260](https://github.com/gavad54/LEADORA/actions/runs/41381631260) | GitHub Actions | همه Stepهای Job موفق؛ compileall، pytest، JS syntax، manifest، Compose و Docker build موفق | یک هشدار وابستگی/deprecation | تعیین تکلیف هشدار | همه تست‌ها و Stepهای اجباری موفق |
| SEC-01 | Regression/Security | بحرانی | VERIFIED | Run [41381631254](https://github.com/gavad54/LEADORA/actions/runs/41381631254) | GitHub Actions | `115 passed, 1 warning`؛ Job و همه Stepها موفق | هشدار Starlette/httpx | برنامه اصلاح سازگاری وابستگی | تست‌ها سبز و هشدار مستند/رفع شود |
| AND-01 | Android Build و نصب/اجرا | بالا | VERIFIED | Run [41381631242](https://github.com/gavad54/LEADORA/actions/runs/41381631242) | Emulator API 30 | Gradle Debug build، نصب، اجرای Activity، foreground، screenshot و نبود FATAL EXCEPTION موفق | این PASS فقط اجرای برنامه را اثبات می‌کند | پذیرش محتوای صفحه و مسیر عمومی | صفحه عمومی صحیح، نه صرفاً Activity |
| AND-02 | DOM واقعی WebView | بالا | VERIFIED | Artifact 13112998593؛ source `c2ef68f` | Android Emulator | `ready=complete`؛ title=LEADORA؛ textLength=1259؛ visibleTextNodes=117؛ bodyHeight=1577؛ screenshot غیرسفید | صفحه Production هنوز قدیمی است | تکرار بعد از Deploy تأییدشده | صفحه عمومی صحیح در WebView و عناصر مورد انتظار |
| AND-03 | محتوای صفحه آغازین Android | بحرانی | BLOCKED | Artifact 13112998593 | Android Emulator / Production | Screenshot صفحه «نمای کلی» و Workspace را نشان می‌دهد، نه Landing عمومی؛ Production smoke نیز BLOCKED | Backup/Restore و Deploy کنترل‌شده | استقرار نسخه تأییدشده و اجرای دوباره Android | کاربر ناشناس Landing عمومی را ببیند؛ ورود فقط با انتخاب کاربر |
| AND-04 | خطای CSS فونت | متوسط | IN_PROGRESS | Run 41381631242 | Android WebView | Console: stylesheet درخواست فونت با MIME نوع application/json رد شده است؛ Runtime fatal error ثبت نشده | نسخه قدیمی Production | بررسی پس از همسان‌سازی Production؛ اطمینان از عدم درخواست خارجی معیوب | صفر خطای CSS/font و صفر 404 مرتبط |
| WEB-01 | صفحه عمومی Production | بحرانی | BLOCKED | Production `4b9ba54`; PR `649d4d0` | Railway | Smoke: API health PASS؛ شش شرط public-home ناموفق؛ publicHome موجود/نمایان نیست، auth overlay پنهان نیست، workspace پنهان نیست، startup و login action ناموفق | Backup/Restore و مجوز Deploy | استقرار امن Commit تأییدشده | مرورگر ناشناس Landing عمومی و جریان ورود/ثبت‌نام صحیح |
| WEB-02 | تطبیق Source و Deployment | بحرانی | CONFIRMED | deployed `4b9ba54f594f6a90f53656333880f805fe8a8028`; source pin `7d92398a8e8e9b457fdfbf5f4dd1b75250506df7` | Railway | Deployment فعال متعلق به 2026-10-21؛ source branch=main و pin با Commit مستقرشده متفاوت است | Backup و rollback | برنامه تطبیق Source/Deployment پس از Gate داده | Commit واقعی دقیقاً برابر Commit تأییدشده |
| OPS-01 | سلامت زیرساخت | بالا | VERIFIED | Deployment `224694ef-5e27-42e8-bc8c-ac1d0975a7d2` | Railway Production | سرویس Online؛ 1/1 replica؛ صفر failure اخیر و صفر warning/critical در snapshot وضعیت | سلامت برنامه و UI جداگانه | Smoke کامل بعد از Deploy | Health، UI، API، Auth، tenant و Android موفق |
| DATA-01 | Volume و مسیر داده | بحرانی | CONFIRMED | Volume `leadora-data` | Railway Production | Volume زنده 500MB در `/data`؛ بدون تغییر staged | مجوز Backup مستقل | تهیه Backup کامل خارج از Volume با مسیر امن | اندازه، زمان، SHA-256 و محل مستقل ثبت شود |
| DATA-02 | Backup کامل مستقل | بحرانی | BLOCKED | — | Production | Backup مستقل خارج از Volume اثبات نشده؛ snapshot tenant-specific معادل DB کامل نیست | مجوز مالک/دسترسی امن | مالک Backup کامل را از مسیر امن مجاز کند | فایل مستقل و قابل بازیابی با SHA-256 |
| DATA-03 | Restore ایزوله | بحرانی | BLOCKED | — | محیط ایزوله | Restore واقعی Production و تطبیق داده اثبات نشده | DATA-02 | Restore در مقصد ایزوله و اجرای تست برنامه | SQLite integrity، جداول، روابط و آزمون کاربردی موفق |
| FIN-01 | بازنشسته‌سازی مشارکت مالی فعال | بالا | VERIFIED | `649d4d0` | کد/CI | تست حفظ تاریخچه legacy و غیرفعال‌سازی مسیرهای فعال در CI | ممیزی داده واقعی | بازبینی نهایی و داده تاریخی پس از Backup | عملیات فعال بسته و تاریخچه حفظ شود |
| FIN-02 | صحت IRR و عدم تبدیل دوباره | بحرانی | UNVERIFIED | `649d4d0` | کد/داده | آزمون‌های کد وجود دارد؛ ممیزی واحد تمام فیلدهای Production انجام نشده | Backup و Restore | ممیزی نمونه داده واقعی و lineage تبدیل | هیچ تبدیل مضاعف؛ تطبیق مالی مستند |
| SEC-02 | Tenant Isolation واقعی | بحرانی | UNVERIFIED | — | دو شرکت آزمایشی/Production | CI سبز است؛ آزمون end-to-end دو شرکت واقعی و عدم دسترسی متقاطع هنوز شواهد مستقل ندارد | دو tenant آزمایشی و محیط ایمن | اجرای ماتریس read/write/update/delete/API | رد قطعی تمام دسترسی‌های cross-tenant |
| AND-05 | مشخصات APK فعلی | بالا | CONFIRMED | Run 41381631242؛ source `c2ef68f` | Artifact | package `com.leadora.app`؛ versionCode 1؛ versionName 1.0.0؛ minSdk 23؛ targetSdk 35؛ size=14,588 bytes؛ APK SHA-256 `9f66fc397d29aa91791bda18554279348bc4697fcdaf543f7a1ca6070199ee7a` | APK صریحاً Debuggable است | Build Release از Commit نهایی | Release از SHA نهایی، نصب و UAT |
| AND-06 | امضای تجاری Release | بحرانی | BLOCKED | — | GitHub Protected Secrets | APK فعلی Debuggable؛ workflow انتشار تجاری Skip شده؛ کلید رسمی مالک تأیید نشده | کلید معتبر مالک در Protected Secrets | مالک کلید را فقط در Secret Manager تنظیم کند | apksigner، fingerprint و امضای Release معتبر |
| AND-07 | UAT دستگاه واقعی | بالا | UNVERIFIED | — | Android واقعی | Emulator CI جایگزین آزمون گوشی واقعی نیست | APK Release تأییدشده | UAT پس از تولید نسخه نهایی | نصب، ورود، RTL، ناوبری و عملیات اصلی موفق |
| UI-01 | فارسی، RTL و طراحی | بالا | IN_PROGRESS | `649d4d0` | Web/Android | HTML شاخه PR دارای Landing RTL و طراحی neon/glass است؛ Production هنوز نسخه قدیمی را ارائه می‌کند | Deploy امن | بازبینی بصری پس از استقرار | خوانایی، responsive، accessibility و RTL در وب/Android |
| REL-01 | انتشار تجاری | بحرانی | BLOCKED | — | Production/Android | Backup/Restore، Production landing، tenant isolation، امضای رسمی و UAT باز هستند | Gateهای A تا G | ادامه اصلاحات مستقل؛ توقف تغییر Production تا ایمنی داده | همه Gateها با شواهد مستقل PASS |

## یافته‌های ریشه‌ای و محدودیت‌های فعلی

### صفحه عمومی و علت رفتار فعلی
HTML شاخه PR #46 دارای `#publicHome`، توابع `showPublicHome()` و `showWorkspace()` و Startup عمومی است. HTML شاخه `main` هنوز auth overlay را در شروع نمایش می‌دهد و منطق Landing عمومی را ندارد. APK به URL ثابت Production متصل است؛ Railway همچنان Commit قدیمی `4b9ba54` را اجرا می‌کند. بنابراین APK ساخته‌شده از PR، محتوای قدیمی Production را دریافت می‌کند تا نسخه وب به‌صورت امن مستقر شود.

### Android
شواهد Artifact جدید، صفحه سفید کامل را رد می‌کند: DOM ساخته شده و Screenshot محتوای قابل مشاهده دارد. اما همان Screenshot نمای Workspace/«نمای کلی» است، نه Landing عمومی. پس «WebView غیرخالی» VERIFIED است ولی «صفحه شروع صحیح» BLOCKED می‌ماند. خطای CSS فونت نیز در Console ثبت شده است.

### CI
Runهای جدید برای HEAD فعلی PR #46 موفق‌اند. Regression/Security تعداد 115 تست موفق و یک هشدار را ثبت کرده است. موفقیت این تست‌ها به‌معنی تأیید Production، tenant isolation واقعی، Backup/Restore یا انتشار تجاری نیست.

### Railway و داده
سرویس Production آنلاین است، اما آخرین Deployment در 2026-10-21 انجام شده و Commit آن با source pin فعلی یکسان نیست. Volume زنده `leadora-data` با ظرفیت 500MB روی `/data` متصل است. هیچ Deployment، Migration، تغییر DB یا تغییر Volume در این بررسی انجام نشده است.

## اقدامات نیازمند مالک

1. مجوز امن برای Backup کامل Production خارج از Volume و Restore ایزوله؛ هیچ رمز یا Token در چت ارسال نشود.
2. کلید معتبر امضای Release فقط از طریق GitHub Protected Secrets/Secret Manager.
3. Review یا تأیید انسانی الزامی طبق سیاست مخزن.
4. UAT روی گوشی واقعی در صورت الزام تجاری.

## سیاست و تصمیم فعلی

- PR #46 ادغام نشده است.
- Production، Volume و DB تغییر داده نشده‌اند.
- آخرین Deployment شناخته‌شده همان Deployment موفق قدیمی است؛ Deploy جدید انجام نشده است.
- CI و اجرای Emulator موفق‌اند، اما Production smoke صفحه عمومی را رد می‌کند.
- تصمیم: **DEPLOYMENT BLOCKED**.
- هیچ ادعای تحویل تجاری تا عبور Gateهای داده، امنیت، Production، Android و امضای رسمی مجاز نیست.


## الحاقیهٔ بازبینی زنده — 2026-11-02 07:xx (snapshot پس از اجرای جدید)

این الحاقیه بر اطلاعات قدیمی‌تر همین فایل مقدم است. همهٔ نتایج زیر به اجرای مشخص‌شده متصل‌اند.

### GitHub و PR
- PR #46 همچنان مرجع اصلی است: Open، Unmerged، Draft=false، mergeable=true؛ HEAD زنده: `e83236df8d95177dca4fe813232240075ede2bc3`.
- PR #47 مستقل و Draft است؛ جایگزین PR #46 نیست.
- Review رسمی PR #46: صفر؛ Review Thread: صفر.
- سه اجرای تازهٔ PR #46 روی head SHA بالا تکمیل شدند:
  - CI: [41383618938](https://github.com/gavad54/LEADORA/actions/runs/41383618938) — Job موفق؛ compileall، pytest، JS syntax، manifest، Compose و Docker image build موفق.
  - Android: [41383618961](https://github.com/gavad54/LEADORA/actions/runs/41383618961) — Build، نصب و اجرای Emulator موفق؛ Artifact [13113784909](https://github.com/gavad54/LEADORA/actions/runs/41383618961/artifacts/13113784909) ثبت شد.
  - Regression/Security: [41383618880](https://github.com/gavad54/LEADORA/actions/runs/41383618880) — `115 passed, 1 warning`؛ هشدار Starlette/httpx همچنان باز است.
- Android Artifact:
  - PR head: `e83236df8d95177dca4fe813232240075ede2bc3`; Build metadata مقدار `GITHUB_SHA` را به‌صورت merge-test SHA برابر `3f07ee629c08126376007500e8d17b5955abd5c2` ثبت کرده است؛ این SHA را با head PR یکی فرض نکنید.
  - APK SHA-256: `f0f2766154712b23604ab662083ade92a7cf979d06719b3739ff9d6e9498f5cb`.
  - Artifact ZIP SHA-256: `d68a1ec865b9f4a8ad1ad74f4b5863f65d94b4c96493b38b937fc2d3d37300a9`.
  - `apksigner verify` موفق است، اما workflow از `assembleDebug` استفاده می‌کند؛ این APK امضای تجاری مالک را اثبات نمی‌کند. مرحله Publish APK release در اجرای PR Skip شده است.
  - Smoke سلامت API موفق بود؛ اما public-home acceptance در همان اجرای تازه شکست خورد: `public_home_present=false`, `public_home_visible=false`, `auth_overlay_hidden=false`, `workspace_hidden=false`, `startup_renders_public_home=false`, `public_login_action=false`. بنابراین Production smoke همچنان BLOCKED است.
  - نصب و اجرای Activity در Emulator موفق است؛ این تست به‌تنهایی اثبات Landing صحیح در WebView نیست. محتوای DOM و screenshot باید از Artifact همان اجرا بازبینی شود.
- CI regression warning: `StarletteDeprecationWarning` دربارهٔ استفاده از httpx با `starlette.testclient`; این هشدار هنوز رفع نشده است.

### Railway snapshot
- Project: `LEADORA`; Environment: `production`.
- سرویس `leadora-web` آنلاین، 1/1 replica، صفر failure اخیر، صفر warning/critical در snapshot و بدون pending work است.
- Deployment فعال همچنان `224694ef-5e27-42e8-bc8c-ac1d0975a7d2` با وضعیت SUCCESS از 2026-10-21 است.
- تنظیم Source سرویس: repo `gavad54/LEADORA`, branch `main`, pinned commit `7d92398a8e8e9b457fdfbf5f4dd1b75250506df7`; هیچ Deployment تازه‌ای انجام نشده است.
- Volume `leadora-data` با ظرفیت 500MB در `/data` متصل و بدون staged change است.
- Backup مستقل و Restore ایزوله هنوز اثبات نشده‌اند؛ به همین دلیل هیچ deploy یا migration روی Production انجام نشد.

### تصمیم و اقدام بعدی
- تصمیم فعلی: **DEPLOYMENT BLOCKED**.
- کارهای مستقل ادامه‌پذیر: بازبینی دقیق diff و workflow، بررسی فایل‌های Android/Web، اصلاح مستندات و اجرای تست‌های ایزوله.
- مواردی که پیش از هر تغییر Production لازم‌اند: Backup مستقل خارج از Volume و Restore آزمایشی اثبات‌شده؛ rollback قابل اجرا؛ تطبیق Commit نهایی با Deployment.
- موارد مالک: مجوز امن Backup/Restore؛ کلید رسمی Release در Protected Secrets؛ Review انسانی طبق سیاست مخزن؛ UAT دستگاه واقعی.
- هیچ دادهٔ Production، Volume، Migration یا تنظیم Railway در این snapshot تغییر نکرده است.
