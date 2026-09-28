# utils_charts.py

import io
import base64
import logging
import pandas as pd
import numpy as np
import arabic_reshaper
from bidi.algorithm import get_display
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.font_manager import FontProperties
from typing import List, Optional, Dict, Any, Tuple
from models import db, ShiftRecord

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- تنظیمات فونت و ظاهر ---
CONFIG = {
    # فونت Tahoma در ویندوز برای نمایش همزمان فارسی و علائم (پرانتز) بسیار مطمئن است
    "font_names": ['Vazir', 'Tahoma', 'Segoe UI', 'B Nazanin', 'Arial', 'DejaVu Sans'],
    "default_font_size": 18,
    "title_font_size": 30,
    "label_font_size": 22,
    "tick_font_size": 18,
    "table_font_size": 20,         # فونت درشت برای جدول
    "color_palette": {
        "primary": '#3498db',
        "secondary": '#2ecc71',
        "tertiary": '#e74c3c',
        "quaternary": '#f39c12',
        "quinary": '#9b59b6'
    },
    "figure_size": (14, 12),
    "dpi": 150
}

class ChartGenerator:
    def __init__(self):
        self.font_props = self._setup_persian_font()

    def _setup_persian_font(self) -> FontProperties:
        try:
            available_fonts = [f.name for f in fm.fontManager.ttflist]
            for font_name in CONFIG["font_names"]:
                if font_name in available_fonts:
                    logging.info(f"Selected font: {font_name}")
                    return FontProperties(family=font_name, size=CONFIG["default_font_size"])
            return FontProperties(family='sans-serif', size=CONFIG["default_font_size"])
        except Exception as e:
            logging.error(f"Error setting up Persian font: {e}")
            return FontProperties()

    def _get_persian_text(self, text: Any) -> str:
        """متن را برای نمایش صحیح فارسی آماده می‌کند."""
        if not text:
            return ""
        try:
            text_str = str(text)
            reshaped_text = arabic_reshaper.reshape(text_str)
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except Exception:
            return str(text)

    @staticmethod
    def _duration_to_minutes(duration_str: Optional[str]) -> float:
        if not duration_str:
            return 0.0
        try:
            h, m, s = map(int, str(duration_str).split(':'))
            return h * 60 + m + s / 60
        except (ValueError, TypeError):
            return 0.0

    def _fetch_data(self, filters: Dict[str, Any]) -> pd.DataFrame:
        try:
            query = db.session.query(ShiftRecord)
            
            # فیلترهای عمومی
            if 'start_date' in filters and filters['start_date']:
                query = query.filter(ShiftRecord.date >= filters['start_date'])
            if 'end_date' in filters and filters['end_date']:
                query = query.filter(ShiftRecord.date <= filters['end_date'])
            if 'network_list' in filters and filters['network_list']:
                query = query.filter(ShiftRecord.network_name.in_(filters['network_list']))
            if 'activity_list' in filters and filters['activity_list']:
                query = query.filter(ShiftRecord.activity.in_(filters['activity_list']))
            
            # فیلترهای خاص (Like)
            if 'activity_like' in filters and filters['activity_like']:
                query = query.filter(ShiftRecord.activity.like(f"%{filters['activity_like']}%"))
            
            # اضافه شدن via_method_like برای پیدا کردن Easy Caster 1, 2, ...
            if 'via_method_like' in filters and filters['via_method_like']:
                query = query.filter(ShiftRecord.via_method.like(f"%{filters['via_method_like']}%"))
            
            # فیلتر دقیق (Exact Match)
            if 'via_method' in filters and filters['via_method']:
                query = query.filter(ShiftRecord.via_method == filters['via_method'])
            
            records = query.all()
            if not records:
                return pd.DataFrame(columns=['id', 'date', 'network_name', 'activity', 'duration', 'via_method'])

            data = [{col.name: getattr(row, col.name) for col in row.__table__.columns} for row in records]
            return pd.DataFrame(data)
            
        except Exception as e:
            logging.error(f"Error fetching data: {e}")
            return pd.DataFrame(columns=['id', 'date', 'network_name', 'activity', 'duration', 'via_method'])

    def _plot_generic_chart(self, ax: plt.Axes, df: pd.DataFrame, chart_type: str, **kwargs):
        title = kwargs.get('title', '')
        title_fa = self._get_persian_text(title)
        ax.set_title(title_fa, fontproperties=self.font_props, size=CONFIG["title_font_size"], pad=30, weight='bold')

        if df.empty:
            ax.text(0.5, 0.5, self._get_persian_text('داده‌ای موجود نیست'),
                    ha='center', va='center', fontsize=24, color='red', fontproperties=self.font_props)
            ax.set_xticks([])
            ax.set_yticks([])
            return

        x_col = kwargs.get('x_col')
        y_col = kwargs.get('y_col')
        label_col = kwargs.get('label_col', x_col)

        if chart_type == 'pie':
            if label_col not in df.columns or y_col not in df.columns: return
            labels = df[label_col].apply(self._get_persian_text)
            sizes = df[y_col]
            if 'sum_other_threshold' in kwargs:
                threshold = kwargs['sum_other_threshold']
                others = sizes[sizes / sizes.sum() < threshold]
                if not others.empty:
                    sizes = sizes[sizes / sizes.sum() >= threshold]
                    sizes = pd.concat([sizes, pd.Series([others.sum()], index=[self._get_persian_text('سایر')])])
                    labels = sizes.index.to_series().apply(self._get_persian_text)

            patches, texts, autotexts = ax.pie(
                sizes, labels=labels, autopct='%1.1f%%', startangle=140,
                textprops={'fontproperties': self.font_props, 'fontsize': 20}
            )
            for autotext in autotexts:
                autotext.set_fontproperties(self.font_props)
                autotext.set_fontsize(18)

        elif chart_type == 'bar':
            if x_col not in df.columns or y_col not in df.columns: return
            x = df[x_col].apply(self._get_persian_text)
            y = df[y_col]
            bars = ax.bar(x, y, color=kwargs.get('color', CONFIG["color_palette"]["secondary"]))
            
            ax.tick_params(axis='x', rotation=45, labelsize=CONFIG["tick_font_size"])
            ax.tick_params(axis='y', labelsize=CONFIG["tick_font_size"])
            for label in ax.get_xticklabels(): label.set_fontproperties(self.font_props)
            
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2., height, f'{int(height)}', 
                        ha='center', va='bottom', fontproperties=self.font_props, fontsize=18)

        elif chart_type == 'line':
            if x_col not in df.columns or y_col not in df.columns: return
            x = df[x_col].apply(self._get_persian_text)
            y = df[y_col]
            ax.plot(x, y, marker='o', linestyle='-', linewidth=4, color=kwargs.get('color', CONFIG["color_palette"]["primary"]))
            ax.tick_params(axis='x', rotation=45, labelsize=CONFIG["tick_font_size"])
            ax.tick_params(axis='y', labelsize=CONFIG["tick_font_size"])
            ax.grid(True, linestyle='--', alpha=0.6)
            for label in ax.get_xticklabels(): label.set_fontproperties(self.font_props)

        ax.set_xlabel(self._get_persian_text(kwargs.get('xlabel', '')), fontproperties=self.font_props, fontsize=CONFIG["label_font_size"])
        ax.set_ylabel(self._get_persian_text(kwargs.get('ylabel', '')), fontproperties=self.font_props, fontsize=CONFIG["label_font_size"])

    def _plot_scatter_with_table(self, ax: plt.Axes, df: pd.DataFrame, title: str):
        title_fa = self._get_persian_text(title)
        ax.set_title(title_fa, fontproperties=self.font_props, size=CONFIG["title_font_size"], pad=30, weight='bold')

        if df.empty or 'network_name' not in df.columns or 'duration' not in df.columns:
            ax.text(0.5, 0.5, self._get_persian_text('داده‌ای موجود نیست'),
                    ha='center', va='center', fontsize=24, color='red', fontproperties=self.font_props)
            ax.set_xticks([])
            ax.set_yticks([])
            return

        df['network_fa'] = df['network_name'].apply(self._get_persian_text)
        df['duration_min'] = df['duration'].apply(self._duration_to_minutes)
        
        counts = df['network_fa'].value_counts()
        ax.scatter(df['network_fa'], df['duration_min'], alpha=0.7, s=200, color=CONFIG["color_palette"]["tertiary"])
        
        for network, count in counts.items():
            max_dur = df[df['network_fa'] == network]['duration_min'].max()
            if pd.isna(max_dur): max_dur = 0
            label_text = self._get_persian_text(f"{count} مورد")
            ax.text(network, max_dur + max_dur * 0.05 + 0.5, label_text, ha='center', va='bottom',
                    fontproperties=self.font_props, fontsize=16, color='darkred', weight='bold')

        ax.set_ylabel(self._get_persian_text('مدت زمان (دقیقه)'), fontproperties=self.font_props, fontsize=CONFIG["label_font_size"])
        
        ax.tick_params(axis='x', rotation=45, labelsize=CONFIG["tick_font_size"])
        ax.tick_params(axis='y', labelsize=CONFIG["tick_font_size"])
        for label in ax.get_xticklabels():
            label.set_fontproperties(self.font_props)
        ax.grid(True, linestyle='--', alpha=0.6)

        # جدول
        total_events = len(df)
        total_min = df['duration_min'].sum()
        avg_min = df['duration_min'].mean() if total_events > 0 else 0
        max_min = df['duration_min'].max() if total_events > 0 else 0

        cell_text = [[f'{total_events}', f'{total_min:.1f}', f'{avg_min:.1f}', f'{max_min:.1f}']]
        col_labels = [self._get_persian_text(l) for l in ['تعداد', 'مجموع (دقیقه)', 'میانگین', 'بیشینه']]
        
        plt.subplots_adjust(left=0.1, right=0.95, top=0.88, bottom=0.35)

        table = ax.table(cellText=cell_text, rowLabels=[self._get_persian_text('جمع کل')],
                         colLabels=col_labels, loc='bottom', cellLoc='center',
                         bbox=[0.0, -0.45, 1.0, 0.3])
        
        table.auto_set_font_size(False)
        table.set_fontsize(CONFIG["table_font_size"])
        table.scale(1, 3.0) 
        
        for (i, j), cell in table.get_celld().items():
            cell.set_text_props(fontproperties=self.font_props)

    def _save_and_encode(self, fig: plt.Figure) -> str:
        try:
            img = io.BytesIO()
            fig.savefig(img, format='png', bbox_inches='tight', dpi=CONFIG["dpi"])
            img.seek(0)
            plot_url = base64.b64encode(img.getvalue()).decode('utf8')
            plt.close(fig)
            return plot_url
        except Exception as e:
            logging.error(f"Error saving plot: {e}")
            plt.close(fig)
            return ""

    # --- Wrapper Functions ---
    def create_timeline_chart(self, ax=None, **filters):
        df = self._fetch_data(filters)
        if df.empty:
            if ax: self._plot_generic_chart(ax, df, 'line', title='روند فعالیت‌ها')
            return None
        timeline_df = df.groupby('date').size().reset_index(name='count')
        if ax:
            self._plot_generic_chart(ax, timeline_df, 'line', x_col='date', y_col='count', title='روند فعالیت‌ها', ylabel='تعداد')
            return None
        fig, ax = plt.subplots(figsize=CONFIG["figure_size"])
        self._plot_generic_chart(ax, timeline_df, 'line', x_col='date', y_col='count', title='روند فعالیت‌ها', ylabel='تعداد')
        return self._save_and_encode(fig)

    def create_network_chart(self, ax=None, **filters):
        df = self._fetch_data(filters)
        if df.empty or 'network_name' not in df.columns:
            if ax: self._plot_generic_chart(ax, df, 'bar', title='تعداد بر اساس شبکه')
            return None
        network_df = df[df['network_name'].notna() & (df['network_name'] != '')]
        if network_df.empty:
             if ax: self._plot_generic_chart(ax, network_df, 'bar', title='تعداد بر اساس شبکه')
             return None
        network_counts = network_df['network_name'].value_counts().reset_index()
        network_counts.columns = ['network_name', 'count']
        
        if ax:
            self._plot_generic_chart(ax, network_counts, 'bar', x_col='network_name', y_col='count', title='تعداد بر اساس شبکه', xlabel='شبکه', ylabel='تعداد')
            return None
        fig, ax = plt.subplots(figsize=CONFIG["figure_size"])
        self._plot_generic_chart(ax, network_counts, 'bar', x_col='network_name', y_col='count', title='تعداد بر اساس شبکه', xlabel='شبکه', ylabel='تعداد')
        return self._save_and_encode(fig)

    def create_activity_pie_chart(self, ax=None, **filters):
        df = self._fetch_data(filters)
        if df.empty or 'activity' not in df.columns:
            if ax: self._plot_generic_chart(ax, df, 'pie', title='توزیع فعالیت‌ها')
            return None
        activity_counts = df['activity'].value_counts().reset_index()
        activity_counts.columns = ['activity', 'count']
        
        if ax:
            self._plot_generic_chart(ax, activity_counts, 'pie', label_col='activity', y_col='count', title='توزیع فعالیت‌ها')
            return None
        fig, ax = plt.subplots(figsize=CONFIG["figure_size"])
        self._plot_generic_chart(ax, activity_counts, 'pie', label_col='activity', y_col='count', title='توزیع فعالیت‌ها')
        return self._save_and_encode(fig)

    def create_scatter_table_chart(self, title, ax=None, **filters):
        df = self._fetch_data(filters)
        if ax:
            self._plot_scatter_with_table(ax, df, title)
            return None
        fig, ax = plt.subplots(figsize=CONFIG["figure_size"])
        self._plot_scatter_with_table(ax, df, title)
        return self._save_and_encode(fig)

# --- Wrapper Instance ---
chart_gen = ChartGenerator()

def create_timeline_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_timeline_chart(ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list)

def create_network_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_network_chart(ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list)

def create_activity_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_activity_pie_chart(ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list)

def create_audio_outage_scatter_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_scatter_table_chart(title='جزئیات قطعی صدا', ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list, activity_like='قطعی صدا')

def create_pgm_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_scatter_table_chart(title='ارتباط‌های کابلی (PGM)', ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list, via_method_like='PGM')

def create_easycaster_chart(start_date=None, end_date=None, network_list=None, activity_list=None, ax=None):
    return chart_gen.create_scatter_table_chart(title='ارتباط‌های اینترنتی (Easy Caster)', ax=ax, start_date=start_date, end_date=end_date, network_list=network_list, activity_list=activity_list, via_method_like='Easy Caster')

create_pie_chart_activity = create_activity_chart
def duration_to_seconds(duration_str): return int(chart_gen._duration_to_minutes(duration_str) * 60)
def get_persian_text(text): return chart_gen._get_persian_text(text)