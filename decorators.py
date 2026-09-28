from functools import wraps
from flask import abort
from flask_login import current_user

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # اگر کاربر وارد نشده باشد یا ادمین نباشد، دسترسی را ممنوع کن
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403) # نمایش خطای 403 Forbidden
        return f(*args, **kwargs)
    return decorated_function