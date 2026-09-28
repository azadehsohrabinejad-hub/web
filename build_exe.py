# build_exe.py
import os
import sys
import subprocess
import shutil

def build_executable():
    print("در حال ساخت فایل اجرایی بدون صفحه فرمان...")
    
    # نصب پکیج PyInstaller در صورت عدم وجود
    try:
        import pyinstaller
    except ImportError:
        print("در حال نصب PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # دستور ساخت فایل exe
    cmd = [
        "pyinstaller",
        "--name=سیستم_گزارش_دهی",
        "--onefile",              # ساخت یک فایل واحد
        "--windowed",             # <--- کلیدی اصلی برای مخفی کردن کنسول
        "--icon=icon.ico",        # (اختیاری) اگر آیکون دارید
        "--add-data=templates;templates", # اضافه کردن پوشه قالب‌ها
        "--add-data=static;static",       # اضافه کردن پوشه فایل‌های استاتیک
        # اضافه کردن ماژول‌های tkinter که ممکن است به صورت خودکار شناسایی نشوند
        "--hidden-import=tkinter", 
        "--hidden-import=tkinter.messagebox",
        "run.py"
    ]
    
    print(f"اجرای دستور: {' '.join(cmd)}")
    subprocess.check_call(cmd)
    
    # کپی کردن پوشه instance به پوشه خروجی (مهم برای حفظ دیتابیس)
    dist_folder = 'dist'
    if not os.path.exists(os.path.join(dist_folder, 'instance')):
        os.makedirs(os.path.join(dist_folder, 'instance'))
    if os.path.exists('instance'):
        shutil.copytree('instance', os.path.join(dist_folder, 'instance'), dirs_exist_ok=True)
    
    print("\n" + "="*50)
    print(f"فایل اجرایی با موفقیت در پوشه '{dist_folder}' ساخته شد!")
    print("نام فایل: سیستم_گزارش_دهی.exe")
    print("اکنون می‌توانید این فایل را به کاربران خود بدهید.")
    print("="*50)

if __name__ == "__main__":
    build_executable()