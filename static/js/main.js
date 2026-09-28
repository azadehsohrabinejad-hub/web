// توابع عمومی جاوا اسکریپت

// تابع برای نمایش پیام‌های فلش
document.addEventListener('DOMContentLoaded', function() {
    // بستن خودکار پیام‌های فلش پس از 5 ثانیه
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            alert.style.opacity = '0';
            setTimeout(function() {
                alert.remove();
            }, 300);
        }, 5000);
    });
});

// تابع برای تأیید حذف
function confirmDelete() {
    return confirm('آیا از حذف این مورد اطمینان دارید؟');
}

// تابع برای کپی کردن متن در کلیپ‌بورد
function copyToClipboard(text) {
    navigator.clipboard.writeText(text)
        .then(() => {
            alert('متن با موفقیت کپی شد');
        })
        .catch(err => {
            console.error('خطا در کپی کردن متن: ', err);
        });
}

// تابع برای نمایش زمان به صورت فارسی
function formatPersianDate(date) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(date).toLocaleDateString('fa-IR', options);
}

// تابع برای نمایش اعداد به صورت فارسی
function toPersianDigits(num) {
    const id = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];
    return num.toString().replace(/[0-9]/g, function(w) {
        return id[parseInt(w)];
    });
}