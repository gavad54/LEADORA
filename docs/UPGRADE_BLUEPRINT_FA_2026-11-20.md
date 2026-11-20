# LEADORA — نقشه ارتقای ساختار و UX | 2026-11-20

مخزن: gavad54/LEADORA | مبنای main: 7bfebf39766cc5fbdf135489eb0d6127f6ae4e2c

## مبنای موجود
FastAPI/Python، SQLite، UI فارسی در app/static/index.html و دامنه‌هایی در app/*.py شامل distribution_erp، procurement، commercial_ops، payroll، pricing_modules، ai_command_center و worker. README و docs/ARCHITECTURE_FA.md درباره سطح پیاده‌سازی ناسازگاری دارند. UI یک فایل بزرگ است؛ پیش از refactor باید همه DOM IDs، eventها، routeها، APIها و فرم‌ها crosswalk شوند.

## معماری دامنه هدف
Identity/Tenant؛ CRM/Accounts؛ Catalog/SKU/Pricing؛ Sales/Orders/Returns؛ Procurement؛ Inventory/Multi-warehouse؛ Warehouse Execution؛ Distribution/Fleet/Delivery؛ Customer Service/SLA؛ Analytics؛ Automation/Jobs؛ Integrations؛ Audit/Compliance. modular monolith حفظ شود تا نیاز جداسازی سرویس اثبات شود.

## UX
داشبوردهای نقش‌محور مالک، مدیر عملیات، فروش، انبار، تدارکات، پخش و پشتیبانی. timeline سفارش: ثبت، تأیید، تخصیص، برداشت، بسته‌بندی، بارگیری، ارسال، تحویل/مرجوعی. جداول دارای فیلتر ذخیره‌شونده، جست‌وجوی SKU/مشتری، bulk action امن و drill-down. فرم کوتاه با draft و خطای فارسی قابل اقدام. PWA موبایل‌محور؛ آفلاین فقط با صف امن، conflict resolution و idempotency. RTL واقعی، keyboard navigation، contrast و حالت‌های loading/empty/error/offline/success.

## KPI
نرخ تبدیل فرصت به سفارش، زمان چرخه سفارش، تحویل به‌موقع، fill rate، دقت موجودی، نرخ مرجوعی، روزهای موجودی، تأمین به‌موقع و حل شکایت. هر KPI فرمول، منبع، timestamp و drill-down داشته باشد.

## AI و مرز مالی
AI برای پیشنهاد سفارش مجدد، پیش‌بینی تقاضا و کشف ناهنجاری فقط با داده معتبر؛ سفارش قطعی/تغییر قیمت/پرداخت/تسویه نیازمند تأیید. LEADORA سیستم دفترکل نیست؛ حسابداری، سند نهایی و بستن دوره فقط ARIANA. ارتباط API نسخه‌دار و مجاز، بدون DB مشترک. ماژول‌های مالی/مشارکت قدیمی با آخرین تصمیم مالک و branchهای مهندسی تطبیق داده شوند؛ حذف فقط با crosswalk و تأیید.

## پذیرش
تکراری نبودن routeها؛ auth و authorization سروری؛ آزمون دو tenant؛ چرخه سفارش تا تحویل/مرجوعی؛ رزرو موجودی و concurrency؛ CSV خراب/تکراری و rollback؛ worker retry/idempotency؛ backup/restore جدا؛ E2E موبایل و PWA؛ تست امنیت، dependency audit، CI و rollback.

## اولویت
P0 baseline، tenant isolation، auth/RBAC، backup/restore و همسان‌سازی اسناد. P1 modularization UI/API و چرخه سفارش/انبار/تحویل. P2 داشبورد نقش‌محور، PWA، analytics و integrations. P3 AI معتبر و اتوماسیون approval-based.

## Benchmark
Dynamics 365، SAP Business One و Infor برای عمق توزیع؛ Zoho Inventory برای پیوستگی workflow؛ Odoo برای الگوی فرم و navigation. الگوها اقتباس شوند، نه کپی.
