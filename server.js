const express = require('express');
const bodyParser = require('body-parser');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const app = express();
const port = 3000;

// فعال‌سازی Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// اتصال به دیتابیس (در صورت نبود، ساخته می‌شود)
const db = new sqlite3.Database('./reports.db');

// ایجاد جدول گزارش‌ها
db.run(`
  CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    date TEXT,
    status TEXT
  )
`);

// ثبت گزارش جدید
app.post('/report', (req, res) => {
  const { title, description } = req.body;
  const date = new Date().toISOString();
  const status = 'در انتظار پاسخ';

  db.run(
    `INSERT INTO reports (title, description, date, status) VALUES (?, ?, ?, ?)`,
    [title, description, date, status],
    function (err) {
      if (err) return res.status(500).json({ error: err.message });
      res.json({ id: this.lastID, message: 'گزارش ثبت شد ✅' });
    }
  );
});

// دریافت همه‌ی گزارش‌ها
app.get('/reports', (req, res) => {
  db.all(`SELECT * FROM reports ORDER BY id DESC`, [], (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

// سرور اجرا شود
app.listen(port, () => {
  console.log(`Server running on http://172.16.60.88:${port}`);
});
