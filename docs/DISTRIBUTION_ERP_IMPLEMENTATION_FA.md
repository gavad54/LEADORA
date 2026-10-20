# ماژول یکپارچه حسابداری و پخش LEADORA

این ماژول بر پایه بررسی سورس ARIANA v0.42 و با تطبیق با پایگاه داده و احراز هویت چندشرکتی LEADORA ساخته شده است؛ سورس ARIANA مستقیماً به عنوان یک سرور مستقل داخل محصول اجرا نمی‌شود.

## قابلیت‌های پیاده‌سازی‌شده
- کدینگ حساب پایه و اسناد دوطرفه با کنترل برابری بدهکار و بستانکار.
- ثبت پیش‌نویس سفارش فروش؛ نهایی‌سازی فروش، کنترل موجودی، کسر موجودی و ثبت سند درآمد/بهای تمام‌شده.
- دریافت خرید، افزایش موجودی و ثبت سند موجودی/بدهی تأمین‌کننده.
- ثبت تحویل با مرجع بارنامه یا رسید.
- صندوق و بانک، تراکنش‌های دریافت/پرداخت، وصول جزئی فاکتور.
- تراز آزمایشی، سود و زیان، دفتر حساب، ترازنامه و گردش کالا.
- قالب‌های Excel مولد، پیش‌نمایش، کنترل اولیه و ثبت اتمیک برای مشتریان، تأمین‌کنندگان، کالاها، انبارها، بانک، صندوق، مطالبات، بدهی‌ها و مانده‌های افتتاحیه.
- تفکیک داده‌ها بر اساس شرکت و ثبت رویدادهای ممیزی.

## API اصلی
- GET /api/distribution/overview
- GET/POST /api/distribution/warehouses
- GET/POST /api/distribution/sales
- POST /api/distribution/sales/{id}/post
- POST /api/distribution/sales/{id}/deliver
- POST /api/distribution/sales/receipt
- POST /api/distribution/purchases
- POST /api/distribution/purchases/{id}/receive
- GET/POST /api/distribution/treasury/accounts
- POST /api/distribution/treasury/movements
- GET/POST /api/distribution/journals
- GET /api/distribution/reports/trial-balance
- GET /api/distribution/reports/profit-loss
- GET /api/distribution/reports/balance-sheet
- GET /api/distribution/reports/ledger/{account_code}
- GET /api/distribution/reports/stock-movements
- GET /api/distribution/import/catalog
- GET /api/distribution/import/template/{dataset}
- POST /api/distribution/import/{dataset}/preview
- POST /api/distribution/import/{batch_id}/commit

## گیت‌های لازم پیش از استفاده عملیاتی مالی
این پیاده‌سازی، فاز پایه یکپارچه‌سازی است و نباید هنوز جایگزین دفترکل رسمی شرکت شود. پیش از مهاجرت واقعی باید دست‌کم این موارد تکمیل و آزموده شوند:
1. تطبیق کدینگ و سیاست‌های حسابداری، مالیات و ارزش افزوده با کشور هدف.
2. ثبت و تطبیق کامل مرجوعی، تخفیف‌های مالی، مالیات، هزینه حمل، چندارزی، چندشعبه‌ای و قیمت تمام‌شده FIFO/میانگین موزون.
3. تکمیل گزارش‌های سنی مطالبات/بدهی، گردش حساب تفصیلی، جریان وجوه نقد، بستن دوره، برگشت/ابطال سند با سند معکوس و کنترل سطح دسترسی نقش‌محور.
4. اجرای مهاجرت واقعی با نسخه پشتیبان، گزارش مغایرت، آزمون بازیابی و پذیرش کاربر (UAT).
5. آزمون بار همزمان، ممیزی امنیتی مستقل و تأیید نسخه اندروید روی دستگاه واقعی.

## نکته مهم مهاجرت
برای جلوگیری از دو بار ثبت مانده‌ها، مانده افتتاحیه مشتری/تأمین‌کننده را یا در ستون مانده فایل مشتریان/تأمین‌کنندگان وارد کنید یا در فایل جداگانه مطالبات/بدهی‌ها؛ هر دو روش را برای یک کد طرف حساب هم‌زمان اجرا نکنید. قبل از ثبت نهایی، جمع افتتاحیه دفترکل باید تراز باشد.
