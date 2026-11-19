"""LEADORA-owned marketing and growth module catalog.

This catalog records ownership and current implementation evidence. It does not
enable outbound messaging, social publishing, or third-party integrations.
"""
MARKETING_GROWTH_MODULES = (
    {
        "id": "ARIA-PROBLEM-MODULE-035",
        "name": "موتور بازاریابی و جذب مشتری",
        "purpose": "مدیریت سرنخ، کانال جذب و گردش‌کار کمپین",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/campaigns", "/api/prospecting/search", "/api/prospecting/leads"],
        "next_gate": "اتصال داده مجاز، انتساب منبع و آزمون قیف سرتاسری",
    },
    {
        "id": "ARIA-PROBLEM-MODULE-037",
        "name": "مدیریت شبکه اجتماعی",
        "purpose": "تقویم محتوا، نسخه‌بندی، تأیید و انتشار مجاز",
        "implementation_status": "DESIGNED_NOT_IMPLEMENTED",
        "connected_routes": [],
        "next_gate": "OAuth و API رسمی هر شبکه، رضایت مالک حساب و آزمون sandbox",
    },
    {
        "id": "ARIA-PROBLEM-MODULE-040",
        "name": "تحلیل بازده بازاریابی",
        "purpose": "تحلیل هزینه، سرنخ، تبدیل، درآمد و انتساب کمپین",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/campaigns", "/api/operations/report", "/api/agents/overview"],
        "next_gate": "تعریف مدل انتساب، اعتبارسنجی داده و آزمون KPI",
    },
    {
        "id": "ARIA-IDEA-MODULE-016",
        "name": "فضای ورود مشتری سازمانی",
        "purpose": "آغاز همکاری، معرفی محیط کار و تکمیل اطلاعات سازمان",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/register", "/api/account/license"],
        "next_gate": "چک‌لیست onboarding، نقش‌ها و آزمون پذیرش سازمانی",
    },
    {
        "id": "ARIA-IDEA-MODULE-017",
        "name": "شاخص سلامت مشتری",
        "purpose": "نمایش نشانه‌های تعامل، ریسک و نیاز به پیگیری",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/agents/overview"],
        "next_gate": "مدل توضیح‌پذیر با داده کافی، بازبینی انسانی و ارزیابی خطا",
    },
    {
        "id": "ARIA-IDEA-MODULE-018",
        "name": "آمادگی تمدید قرارداد",
        "purpose": "پایش سررسید، وضعیت خدمت و آمادگی تمدید",
        "implementation_status": "DESIGNED_NOT_IMPLEMENTED",
        "connected_routes": [],
        "next_gate": "مدل قرارداد و تمدید، اعلان رضایت‌محور و آزمون زمان‌بندی",
    },
    {
        "id": "ARIA-IDEA-MODULE-020",
        "name": "کشف فرصت توسعه حساب مشتری",
        "purpose": "یافتن فرصت‌های توسعه همکاری بر پایه داده مجاز",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/opportunities", "/api/agents/overview"],
        "next_gate": "پیوند فرصت به حساب مشتری و سنجش کیفیت پیشنهاد",
    },
    {
        "id": "ARIA-IDEA-MODULE-022",
        "name": "پرتال توانمندسازی نمایندگان فروش",
        "purpose": "آموزش، محتوای فروش و پیگیری عملکرد نمایندگان",
        "implementation_status": "DESIGNED_NOT_IMPLEMENTED",
        "connected_routes": [],
        "next_gate": "مدل نماینده، نقش‌ها، محتوا و گزارش پیشرفت",
    },
    {
        "id": "ARIA-IDEA-MODULE-024",
        "name": "کیت کمپین محلی شعب",
        "purpose": "ساخت کمپین متناسب با شعبه و محدوده جغرافیایی",
        "implementation_status": "EXISTING_FOUNDATION_PARTIAL",
        "connected_routes": ["/api/campaigns"],
        "next_gate": "افزودن شعبه، منطقه، بودجه و مقایسه عملکرد شعب",
    },
    {
        "id": "ARIA-IDEA-MODULE-038",
        "name": "تبدیل بازخورد به پرونده رسیدگی",
        "purpose": "ثبت بازخورد، تعیین مسئول، پیگیری و بستن پرونده",
        "implementation_status": "DESIGNED_NOT_IMPLEMENTED",
        "connected_routes": [],
        "next_gate": "مدل پرونده بازخورد، SLA، مالک و audit trail",
    },
    {
        "id": "ARIA-IDEA-MODULE-045",
        "name": "مدیریت گواهی مهارت و آموزش",
        "purpose": "ثبت مهارت، آموزش، ارزیابی و اعتبار گواهی",
        "implementation_status": "DESIGNED_NOT_IMPLEMENTED",
        "connected_routes": [],
        "next_gate": "مدل مهارت، برنامه آموزشی، ارزیابی و سوابق",
    },
)

MARKETING_GROWTH_SHARED_DEPENDENCIES = (
    {
        "id": "ARIA-PROBLEM-MODULE-034",
        "name": "تولید محتوای حرفه‌ای",
        "owner": "ARIA / NEGAH",
        "consumer": "LEADORA",
        "access": "permissioned_asset_connector",
    },
)

MARKETING_GROWTH_EXECUTION_POLICY = {
    "outbound_messaging_enabled": False,
    "social_publishing_enabled": False,
    "third_party_integrations_connected": False,
    "payment_execution_enabled": False,
    "human_approval_required_for_external_actions": True,
}
