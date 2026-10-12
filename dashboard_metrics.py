"""Read-only operational dashboard metrics; no migrations or outgoing requests."""
from collections import Counter, defaultdict
from models import ShiftRecord

NETWORKS = ('ایران','آوا','جوان','پیام','ورزش','معارف','قرآن','فرهنگ','سلامت','اقتصاد','گفتگو','نمایش','تهران','صبا','خبر','تلاوت','ترتیل','زیارت','برون مرزی')
REQUESTS = ('مشکلات playout','تغییر زیرنویس','تغییر لوگو','تغییر کنداکتور')
DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩','01234567890123456789')

def _key(value):
    return ''.join(str(value or '').translate(DIGITS).replace('ي','ی').replace('ك','ک').replace('‌','').replace('-','').replace('_','').split()).casefold()

ALIASES = {_key(n):n for n in NETWORKS}
ALIASES.update({_key('قران'):'قرآن',_key('مناسبتی'):'خبر',_key('قران 2'):'ترتیل',_key('قرآن ۲'):'ترتیل'})
SHARED = {_key(x) for x in ('همه شبکه ها','تمام شبکه ها','all networks')}

def _network(value):
    key = _key(value)
    if key in SHARED:
        return '__shared__'
    return ALIASES.get(key)

def _duration_seconds(value):
    if value is None:
        return None
    parts = str(value).strip().translate(DIGITS).split(':')
    if len(parts) not in (2,3) or any(not p.isdecimal() for p in parts):
        return None
    h,m = map(int,parts[:2]); s = int(parts[2]) if len(parts)==3 else 0
    return h*3600+m*60+s if m<60 and s<60 else None

def _activity(value):
    key = _key(value)
    if key == _key('مشکلات playout'): return REQUESTS[0]
    if key == _key('تغییر زیرنویس'): return REQUESTS[1]
    if key == _key('تغییر لوگو'): return REQUESTS[2]
    if key == _key('تغییر کنداکتور'): return REQUESTS[3]
    return str(value or '').strip()

def dashboard_metrics(start_date,end_date,user=None):
    rows = ShiftRecord.query.filter(ShiftRecord.date>=start_date,ShiftRecord.date<=end_date).with_entities(
        ShiftRecord.network_name,ShiftRecord.activity,ShiftRecord.duration,ShiftRecord.via_method,ShiftRecord.date
    ).all()
    pgm=easy=other_connection=0
    connection_networks={n:Counter() for n in NETWORKS}
    connection_excluded=Counter()
    easy_units=Counter(); request_counts=Counter(); request_networks={n:Counter() for n in NETWORKS}
    outage_own=Counter(); outage_own_count=Counter(); shared_seconds=shared_outages=invalid=0
    recording=0; total_outage_seconds=0; total_outage_count=0; excluded=Counter()
    daily=defaultdict(Counter); day_network=defaultdict(Counter)
    for raw_network,raw_activity,duration,via_method,record_date in rows:
        day=str(record_date or "")
        network=_network(raw_network); activity=_activity(raw_activity)
        method=_key(via_method)
        # Count connection methods only on connection activity records.
        if _key(raw_activity).startswith(_key('ارتباط با')):
            if method=='pgm':
                pgm+=1
                kind='pgm'
            elif method.startswith('easycaster'):
                easy+=1; easy_units[str(via_method).strip()]+=1
                kind='easycaster'
            else:
                kind=None
                if method: other_connection+=1
            if kind:
                if network=='__shared__':
                    for n in NETWORKS: connection_networks[n][kind]+=1
                elif network in NETWORKS:
                    connection_networks[network][kind]+=1
                else:
                    connection_excluded['ارتباط خارج از ۱۹ شبکه']+=1
        if _key(raw_activity).startswith(_key('ضبط تصویر')): recording+=1
        if activity in REQUESTS:
            daily[day]['requests']+=1
            if network in NETWORKS: day_network[day][network]+=1
            elif network=='__shared__':
                for n in NETWORKS: day_network[day][n]+=1
            request_counts[activity]+=1
            if network=='__shared__':
                for n in NETWORKS: request_networks[n][activity]+=1
            elif network in NETWORKS: request_networks[network][activity]+=1
            else: excluded['درخواست بدون شبکه منتخب']+=1
        if 'قطع صدا' in _key(raw_activity) or 'قطعـیصدا' in _key(raw_activity) or 'قطعیصدا' in _key(raw_activity):
            total_outage_count+=1
            daily[day]['outages']+=1
            sec=_duration_seconds(duration)
            if sec is None: invalid+=1; continue
            total_outage_seconds+=sec
            daily[day]['outage_seconds']+=sec
            if network=='__shared__': shared_seconds+=sec; shared_outages+=1
            elif network in NETWORKS: outage_own[network]+=sec; outage_own_count[network]+=1
            else: excluded['قطعی خارج از ۱۹ شبکه']+=1
    network_rows=[]
    for n in NETWORKS:
        seconds=outage_own[n]+shared_seconds
        network_rows.append({'name':n,'seconds':seconds,'minutes':round(seconds/60,2),'own_seconds':outage_own[n],
                             'count':outage_own_count[n]+shared_outages,'requests':sum(request_networks[n].values())})
    network_rows.sort(key=lambda x:(-x['seconds'],x['name']))
    request_rows=[{'name':n,'total':sum(request_networks[n].values()),'items':[request_networks[n][a] for a in REQUESTS]} for n in NETWORKS]
    request_rows.sort(key=lambda x:(-x['total'],x['name']))
    return {'total':len(rows),'pgm':pgm,'easycaster':easy,'other_connection':other_connection,
            'easy_units':easy_units.most_common(),'recording':recording,
            'connection_rows':sorted([{'name':n,'pgm':connection_networks[n]['pgm'],'easycaster':connection_networks[n]['easycaster'],'total':sum(connection_networks[n].values())} for n in NETWORKS],key=lambda r:(-r['total'],r['name'])),
            'connection_excluded':dict(connection_excluded),
            'outage_count':total_outage_count,'outage_seconds':total_outage_seconds,
            'outage_minutes':round(total_outage_seconds/60,2),'outage_invalid_count':invalid,
            'shared_outage_seconds':shared_seconds,'shared_outage_count':shared_outages,
            'network_rows':network_rows,'request_types':REQUESTS,'request_counts':request_counts,
            'request_rows':request_rows,'request_total':sum(request_counts.values()),
            'excluded':dict(excluded),'start_date':start_date,'end_date':end_date,
            'daily_rows':[{'date':d,'requests':daily[d]['requests'],'outages':daily[d]['outages'],'outage_minutes':round(daily[d]['outage_seconds']/60,2)} for d in sorted(daily)],
            'heatmap_rows':[{'date':d,'values':[day_network[d][n] for n in NETWORKS]} for d in sorted(day_network)],
            'network_names':list(NETWORKS)}
