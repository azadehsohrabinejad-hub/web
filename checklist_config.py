"""Replace these labels with the ten approved inspection items before rollout."""

CHECKLIST_ITEMS = [
    {"id": str(i), "label": f"مورد بازدید {i} — متن نهایی را وارد کنید"}
    for i in range(1, 11)
]

ANSWER_LABELS = {"ok": "سالم", "issue": "مشکل دارد", "unknown": "قابل بررسی نبود"}
