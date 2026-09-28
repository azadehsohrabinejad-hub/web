# D:\Web\wsgi.py  ← فقط این ۱۰ خط رو کپی کن
print(">>> WSGI LOADED SUCCESSFULLY")

from app import create_app
import sys
import traceback

application = create_app()
app = application  # این خط حتماً باشه

# این قسمت خطای کامل رو نشون می‌ده (موقتاً!)
@app.errorhandler(Exception)
def handle_exception(e):
    exc_type, exc_value, exc_tb = sys.exc_info()
    tb = traceback.extract_tb(exc_tb)
    error_details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    return f"""
    <h2>خطای داخلی سرور</h2>
    <pre style="background:#222;color:#0f0;padding:15px;border-radius:8px;">
{error_details}
    </pre>
    """, 500

if __name__ == "__main__":
    app.run()