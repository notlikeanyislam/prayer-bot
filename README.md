# PrayerBot (Telegram) - With MongoDB

## المتطلبات
- Python 3.9+
- حساب MongoDB Atlas أو سيرفر MongoDB متاح
- Token بوت Telegram
- مشروع مستضاف على Render, Heroku أو سيرفر يدعم webhooks

## ملفات المشروع
- `main.py` : الكود الرئيسي
- `database.py` : التعامل مع MongoDB
- `utils.py` : دوال مساعدة لفتح/غلق
- `config.py` : جلب المتغيرات من ENV
- `requirements.txt`
- `.env.example`

## خطوات الإعداد
1. إعداد MongoDB:
   - انشئ Cluster على MongoDB Atlas.
   - انشئ قاعدة بيانات/مستخدم وأحرز الـ `MONGO_URI`.
2. اضبط متغيرات البيئة في Render:
   - BOT_TOKEN, OWNER_ID, MONGO_URI, RENDER_EXTERNAL_URL, (PORT اختياري)
3. تأكد `requirements.txt` يحتوي على `pymongo` و `dnspython`.
4. ارفع الكود على GitHub واربطه مع Render أو ادفع الملفات مباشرة.
5. شغّل التطبيق في Render — سيتولى التطبيق تعيين webhook تلقائيًا عند التشغيل.

## ملاحظات
- أوامر `/times` مقصورة على الأدمن/مالك.
- أضفت آلية `last_action` لتجنّب تداخل أوامر يدوية مع الـ scheduler.
- إذا أردت الاحتفاظ بنسخة محلية من البيانات، يمكنك إبقاء `data/` (لكن في النسخة الحالية نعتمد على MongoDB).
