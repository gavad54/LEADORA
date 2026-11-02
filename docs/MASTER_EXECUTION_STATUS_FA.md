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


---

## الحاقیهٔ اجرای زنده — 2026-11-02 (بازبینی مستقل Runهای 413859*)

این الحاقیه از نتایج مستقیم GitHub Actions و Railway تهیه شده و بر snapshotهای قدیمی‌تر همین فایل مقدم است. هیچ نتیجه‌ای به SHA دیگری تعمیم داده نشده است.

### خط مبنای GitHub
- مخزن: `gavad54/LEADORA`؛ شاخه مرجع: `fix/public-home-optional-auth`.
- PR #46 باز، ادغام‌نشده، Draft=false و mergeable=true است.
- HEAD زنده PR و SHA ثبت‌شده در Artifact جدید Android: `5e25f4b06cafbe249cfd5a183126ef4e01d22788`.
- متن قبلی PR و بخش‌های قدیمی این داشبورد هنوز SHA قدیمی `e83236df...` را ذکر می‌کنند؛ این تناقض مستنداتی باید اصلاح شود.
- PR #47 مستقل و Draft است و جایگزین PR #46 نیست.
- Review رسمی PR #46 در بررسی فعلی صفر است.

### Workflowهای تازه — همگی روی SHA مربوط به PR #46
- CI: [Run 41385902850](https://github.com/gavad54/LEADORA/actions/runs/41385902850) — موفق؛ تمام Stepهای ثبت‌شده موفق.
- Regression/Security: [Run 41385902868](https://github.com/gavad54/LEADORA/actions/runs/41385902868) — موفق؛ **115 passed, 1 warning**. هشدار: `StarletteDeprecationWarning` دربارهٔ استفاده از httpx با `starlette.testclient`.
- Android: [Run 41385902889](https://github.com/gavad54/LEADORA/actions/runs/41385902889) — Job موفق؛ Build، نصب و اجرای Emulator موفق؛ مرحله Publish APK Release عمداً Skip شده است.
- Artifact: [LEADORA-Android-APK — 13114964196](https://github.com/gavad54/LEADORA/actions/runs/41385902889/artifacts/13114964196)؛ SHA-256 آرشیو Artifact: `926cb0516fd13bd0e8cfa26a13037b8835c2110ca0ef5ac1d72e53534ed1ad67`.
- APK SHA-256 از Log همان Run: `dac07e5ca22ddfd9554c3093595994b80bf8731ac103228de34b9076b8690652`؛ اندازه 14,588 bytes. خروجی `assembleDebug` و Debug است؛ امضای معتبر تجاری مالک نیست.
- `apksigner verify` امضای APK را از نظر ساختار فنی تأیید کرده، اما این امر Debug بودن را به Release تجاری تبدیل نمی‌کند.

### نتیجهٔ قطعی Production Smoke
در همان Android Run، درخواست `/api/health` موفق بود؛ اما صفحه اصلی Production شش شرط پذیرش را رد کرد:
- `public_home_present=false`
- `public_home_visible=false`
- `auth_overlay_hidden=false`
- `workspace_hidden=false`
- `startup_renders_public_home=false`
- `public_login_action=false`

این شکست با `continue-on-error` در Workflow به‌صورت تشخیصی ثبت شده تا Emulator نیز اجرا شود؛ بنابراین وضعیت کلی Job=success نباید به‌عنوان PASS صفحه عمومی گزارش شود. فایل `production-smoke.txt` در Artifact وضعیت BLOCKED را ثبت می‌کند.

### علت ریشه‌ای Landing / Android
- `MainActivity` در شاخه PR به‌صورت صریح URL ثابت Production یعنی `https://leadora-web-production.up.railway.app/` را بارگذاری می‌کند؛ منطق آن صفحه Workspace را به‌صورت hard-code نمایش نمی‌دهد.
- فایل `app/static/index.html` در شاخه PR دارای `#publicHome`، تابع `showPublicHome()` برای نمایش Landing و مخفی‌کردن Workspace و Auth Overlay، و دکمه عمومی «ورود / ساخت حساب» است.
- Production هنوز HTML قدیمی را ارائه می‌کند و Smoke دقیقاً همین عدم تطابق را اثبات می‌کند. بنابراین ساخت مجدد APK به‌تنهایی مشکل را حل نمی‌کند؛ نسخه وب باید پس از Gateهای Backup/Restore و Rollback به‌صورت کنترل‌شده مستقر شود.
- هیچ Deployment، Migration، تغییر DB یا Volume در این اجرا انجام نشده است.

### Railway زنده
- Project: `LEADORA`؛ Environment: `production`؛ Service: `leadora-web`.
- سرویس Online، یک Replica از یک، صفر failure اخیر، صفر warning/critical و بدون pending work است.
- Deployment فعال: `224694ef-5e27-42e8-bc8c-ac1d0975a7d2`، وضعیت SUCCESS، ایجادشده در 2026-10-21.
- Commit واقعی Deployment: `4b9ba54f594f6a90f53656333880f805fe8a8028`؛ branch=`main`. این نسخه با SHA شاخه اصلاحات تطبیق ندارد.
- Volume همچنان متصل است؛ Backup مستقل خارج از Volume و Restore ایزوله اثبات نشده‌اند.

### وضعیت Gateها و اقدام بعدی
- Code/CI: CI و Regression روی SHA آزموده‌شده موفق؛ Review انسانی PR هنوز ثبت نشده.
- Landing/Production: BLOCKED؛ شش شرط Smoke رد شده‌اند.
- Android: Emulator نصب و اجرا را تأیید کرده، اما APK Debug است و صفحه عمومی Production را نمایش نمی‌دهد.
- Data Safety: Backup مستقل و Restore ایزوله UNVERIFIED/BLOCKED.
- Tenant Isolation واقعی دو شرکت: UNVERIFIED.
- Release Signing و UAT دستگاه واقعی: BLOCKED/UNVERIFIED.
- تصمیم: **DEPLOYMENT BLOCKED**.
- اقدام بعدی امن: بازبینی کامل workflow و diff، تکمیل مستندات دقیق، رفع هشدارهای تست و آماده‌سازی مسیر Backup/Restore مستقل؛ هیچ تغییر Production یا داده‌ای پیش از اثبات Gate داده انجام نشود.


### تکمیل شواهد HTTP و Assets — 2026-11-02
- موجودی زنده Railway تأیید کرد: سرویس `leadora-web` از repo `gavad54/LEADORA`، branch=`main` و pin=`7d92398a8e8e9b457fdfbf5f4dd1b75250506df7` استفاده می‌کند؛ Deployment زنده commit=`4b9ba54f594f6a90f53656333880f805fe8a8028` است.
- Volume `leadora-data` با اندازه 500MB در `/data` متصل است؛ هیچ Bucket، staged change یا pending patch وجود ندارد.
- HTTP logs زنده برای درخواست‌های Android در 2026-11-02، پاسخ 200 برای `/`، `/api/health`، `/icon.svg`، `/static/leadora-mark.svg`، `/static/leadora-banner.svg`، `/service-worker.js` و `/manifest.webmanifest` نشان می‌دهند.
- همان لاگ‌ها درخواست نامعتبر font را با مسیر `/url('https://fonts.googleapis.com/css2` و HTTP 404 ثبت کرده‌اند. فایل `app/static/index.html` در شاخه PR دارای توضیح offline-safe font stack است و رشته `fonts.googleapis` در نسخه شاخه PR یافت نشد؛ بنابراین رفع سمت کد در PR موجود است، اما هنوز در Production قدیمی اعمال نشده است.
- این شواهد، خطای فونت را از حدس به یک 404 واقعی در Production ارتقا می‌دهد؛ با این حال، به‌تنهایی علت شش شکست Landing نیست. علت Landing همچنان عدم استقرار HTML اصلاح‌شده است.


---

## اجرای مستقل و بازبینی زنده — 2026-11-02 پس از Runهای 413877*

این بخش جدیدترین snapshot است و در صورت تعارض، بر الحاقیه‌های قبلی مقدم است.

### GitHub و PR
- PR #46: OPEN، UNMERGED، Draft=false، mergeable=true.
- HEAD فعلی شاخه `fix/public-home-optional-auth`: `03cf2f292417c6e0f887f4875d0e4f7256557b60`.
- Base `main`: `ead6a400347314f16303520bc016fb988fd621de`.
- Compare زنده: 158 commit جلوتر و صفر عقب‌تر؛ 29 فایل تغییرکرده.
- PR #47 همچنان مستقل و Draft است؛ جایگزین PR #46 نیست.
- Review رسمی PR #46: صفر؛ هیچ review submission ثبت نشده است.
- مخزن عمومی است و مجوزهای اتصال GitHub برای این مخزن Admin=true و Push=true گزارش شدند.

### Workflowهای متصل به HEAD فعلی
- CI: [Run 41387761587](https://github.com/gavad54/LEADORA/actions/runs/41387761587) — Job و تمام Stepها موفق؛ Python compile، pytest، JS syntax، manifest، Compose و Docker image build.
- Regression/Security: [Run 41387761559](https://github.com/gavad54/LEADORA/actions/runs/41387761559) — موفق؛ **115 passed, 1 warning**. هشدار: StarletteDeprecationWarning درباره استفاده از httpx با starlette.testclient؛ نیازمند بررسی سازگاری وابستگی، نه سرکوب کورکورانه هشدار.
- Android: [Run 41387761566](https://github.com/gavad54/LEADORA/actions/runs/41387761566) — Build، نصب و اجرای Activity روی Emulator موفق؛ مرحله انتشار Release عمداً Skip شده است.
- Android Artifact: [Artifact 13116501187](https://github.com/gavad54/LEADORA/actions/runs/41387761566/artifacts/13116501187)، SHA-256 آرشیو: `965399b4d89c8a83229446cae6660b23c118ec33b9b9cf2e29e30e7ed60f9c5e`.
- APK با `assembleDebug` ساخته شده؛ SHA-256: `6d8ed1cb0cdc39d50670ab663d9184d099d3ea924be3711238201d97512ebde4`؛ اندازه 14,588 bytes. `apksigner verify` از نظر ساختاری موفق است، اما APK Debug است و امضای تجاری مالک را اثبات نمی‌کند.
- Emulator package را نصب و `MainActivity` را اجرا کرد؛ این نتیجه فقط Runtime/Activity را تأیید می‌کند، نه Landing صحیح در Production.
- هشدارهای ابزار زنجیره Android شامل setup-java@v4 منسوخ و Node.js 20 در برخی Actions است؛ باید به نسخه‌های پشتیبانی‌شده ارتقا یابند.

### نتیجه دقیق Production Smoke
در Run 41387761566، health endpoint و دریافت صفحه پاسخ 200 داشتند؛ اما شش شرط صفحه عمومی در Production رد شدند:
- `public_home_present=false`
- `public_home_visible=false`
- `auth_overlay_hidden=false`
- `workspace_hidden=false`
- `startup_renders_public_home=false`
- `public_login_action=false`

این مرحله در Workflow با continue-on-error تشخیصی است تا آزمون Emulator اجرا شود؛ بنابراین موفقیت کلی Job به معنی موفقیت Production smoke نیست. فایل Artifact وضعیت Smoke را BLOCKED ثبت می‌کند.

### Railway زنده
- Project: LEADORA؛ Environment: production.
- Service: `leadora-web`؛ ID: `13aa3d75-48b6-4ad1-8064-a7846ffe6739`.
- سرویس Online، 1/1 replica، صفر failure اخیر، صفر warning/critical و بدون pending work.
- Deployment فعال: `224694ef-5e27-42e8-bc8c-ac1d0975a7d2`، SUCCESS از 2026-10-21.
- Source: `gavad54/LEADORA`، branch=`main`، pinned SHA=`7d92398a8e8e9b457fdfbf5f4dd1b75250506df7`.
- Volume زنده `leadora-data` با ظرفیت 500MB در `/data` متصل است؛ هیچ Bucket و هیچ staged change وجود ندارد.
- لاگ HTTP در اجرای جدید: `/api/health` و `/` پاسخ 200؛ آیکون، بنر، Service Worker و Manifest نیز 200. درخواست فونت نامعتبر `/url('https://fonts.googleapis.com/css2` همچنان 404 می‌دهد.
- هیچ Deployment، Migration، DB یا Volume mutation انجام نشده است.

### علت ریشه‌ای و تصمیم
- شاخه PR فایل `app/static/index.html` را با `#publicHome`، `showPublicHome()` و دکمه ورود عمومی دارد.
- APK به URL ثابت Production متصل است؛ Production هنوز HTML قدیمی را ارائه می‌کند. بنابراین Build مجدد APK مشکل صفحه شروع را رفع نمی‌کند؛ ابتدا باید اصلاح وب پس از Gateهای داده و بازیابی، به‌صورت کنترل‌شده مستقر شود.
- Backup مستقل خارج از Volume و Restore ایزوله هنوز اثبات نشده‌اند.
- Tenant Isolation واقعی بین دو شرکت هنوز UNVERIFIED.
- امضای رسمی Release و UAT گوشی واقعی هنوز BLOCKED/UNVERIFIED.
- PR Review رسمی هنوز انجام نشده است.
- **تصمیم فعلی: DEPLOYMENT BLOCKED.** هیچ تغییر Production یا داده‌ای در این بازبینی انجام نشده است.

### اقدامات مستقل بعدی
1. تکمیل بررسی امنیت و جداسازی Tenant با دو Tenant آزمایشی و داده ساختگی در محیط ایزوله.
2. بررسی هشدار Starlette/httpx و هشدارهای GitHub Actions؛ اصلاح فقط با سازگاری و آزمون مجدد.
3. ممیزی فایل‌های workflow و قرارداد انتشار؛ آماده‌سازی Release فقط پس از وجود Secretهای معتبر و تایید سیاست انتشار.
4. آماده‌سازی طرح Backup مستقل/Restore؛ اجرای آن فقط از مسیر امن مالک و در محیط غیر Production.
5. اصلاح مستندات و PR summary برای جلوگیری از تعمیم نتایج قدیمی به HEAD جدید.
