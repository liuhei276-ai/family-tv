#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频聚合拉取器
- 用 WBI 签名调用 B站搜索接口，按关键词拉取视频
- 过滤版权内容、付费内容、超长视频
- 按主题分类，生成前端可直接读取的 data.json
用法: python fetch_bili.py
"""
import urllib.request, urllib.parse, json, time, hashlib, re, os, sys
from datetime import datetime, timezone, timedelta

H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.bilibili.com/',
    'Accept': 'application/json, text/plain, */*',
}

# ---------- 分类配置：想加内容就改这里 ----------
# 每个分类配关键词，程序会逐个搜索；age 是建议年龄，max_dur 是最长秒数
CATEGORIES = [
    {'name': '儿歌律动', 'icon': '🎵', 'age': 3, 'max_dur': 600, 'quota': 12,
     'keywords': ['宝宝巴士儿歌', '儿童儿歌 精选', '经典儿歌 动画']},
    {'name': '恐龙动物', 'icon': '🦕', 'age': 4, 'max_dur': 600, 'quota': 12,
     'keywords': ['恐龙科普 儿童', '动物世界 少儿', '认识动物 小朋友']},
    {'name': '科学小实验', 'icon': '🔬', 'age': 5, 'max_dur': 600, 'quota': 12,
     'keywords': ['科学小实验 儿童', '趣味科学实验 小学生', '吴姥姥 物理 科普']},
    {'name': '识字启蒙', 'icon': '📝', 'age': 4, 'max_dur': 600, 'quota': 12,
     'keywords': ['识字 幼儿 动画', '认字 宝宝 早教', '拼音 启蒙 儿童']},
    {'name': '绘本故事', 'icon': '📚', 'age': 4, 'max_dur': 900, 'quota': 12,
     'keywords': ['绘本故事 儿童', '睡前故事 小朋友', '童话故事 动画']},
    {'name': '博物馆', 'icon': '🏛️', 'age': 6, 'max_dur': 600, 'quota': 10,
     'keywords': ['博物馆 讲解 少儿', '国博 文物 科普', '自然博物馆 恐龙']},
    {'name': '儿童手工', 'icon': '✂️', 'age': 5, 'max_dur': 600, 'quota': 12,
     'keywords': ['儿童手工 简单', '亲子手工 幼儿园', '手工DIY 小朋友']},
    {'name': '蛋糕烘焙', 'icon': '🎂', 'age': 5, 'max_dur': 600, 'quota': 12,
     'keywords': ['儿童蛋糕 制作', '亲子烘焙 蛋糕', '蛋糕DIY 小朋友']},
    {'name': '迷你厨房', 'icon': '🍳', 'age': 5, 'max_dur': 600, 'quota': 12,
     'keywords': ['开心迷你厨房', '迷你厨房 儿童', '迷你食玩 做饭']},
]

# 标题里出现这些词直接跳过（番剧版权/超纲/引流）
BLOCK_WORDS = ['番剧', '全集', '第1集', '付费', '课程', '网课', '高考', '考研',
               '公务员考试', '成人', '恐怖', '惊悚', '车祸', '打架', '鬼畜',
               'kol', '带货', '直播间', '录播', '演唱会', 'MV完整版',
               # 对 6 岁偏吓人/悲伤的童话
               '红舞鞋', '卖火柴', '小红帽', '大灰狼', '白雪公主', '灰姑娘',
               # 成人向/资讯向/才艺展演，不适合孩子
               '文创', '年货', '展演', '群舞', 'AI修', '参数', '营销号',
               '拓扑学', '天花板', '遇见博物馆', '读懂', '研学',
               # 烘焙/厨房类易混入的成人向内容
               '吃播', '大胃王', '探店', '测评', '配方', '商用', '摆摊',
               '烤箱推荐', '测评', '美食教程', '网红', 'asmr', 'ASMR',
               '卖的比较好', '出单', '爆单', '订单', '预约', '私房', '戚风蛋白',
               '蛋糕店', '看不见以后', 'Bank刚刚', '失败', '传世', '最小化电视机',
               '偷吃', '童年三色杯', '匕首', '隐藏式武器', '搬运 cc', '酱多多']

MIXIN_KEY = None
MIXIN_TS = 0
MIXIN_MAP = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,
             42,19,29,28,14,39,12,38,41,13,37,48,7,16,24,55,40,61,26,17,0,1,
             60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]


def log(*a):
    print('[%s]' % datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=H)
    return urllib.request.urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')


def get_json(url, timeout=15):
    return json.loads(http_get(url, timeout))


def refresh_mixin(force=False):
    """取 WBI 签名密钥，缓存 6 小时"""
    global MIXIN_KEY, MIXIN_TS
    if MIXIN_KEY and not force and time.time() - MIXIN_TS < 21600:
        return MIXIN_KEY
    nav = get_json('https://api.bilibili.com/x/web-interface/nav')
    w = nav['data']['wbi_img']
    raw = (w['img_url'].rsplit('/', 1)[-1].split('.')[0] +
           w['sub_url'].rsplit('/', 1)[-1].split('.')[0])
    MIXIN_KEY = ''.join(raw[i] for i in MIXIN_MAP)
    MIXIN_TS = time.time()
    log('WBI 密钥已更新')
    return MIXIN_KEY


def clean_param(v):
    """B站 WBI 要求过滤掉 !'()* """
    return re.sub(r"[!'()*]", '', str(v))


def wbi_sign(params):
    p = {k: clean_param(v) for k, v in params.items()}
    p['wts'] = int(time.time())
    query = urllib.parse.urlencode(sorted(p.items()), quote_via=urllib.parse.quote)
    p['w_rid'] = hashlib.md5((query + MIXIN_KEY).encode()).hexdigest()
    return urllib.parse.urlencode(sorted(p.items()), quote_via=urllib.parse.quote)


def api_call(path, params, retry=3):
    """带 WBI 签名 + 退避重试的接口调用"""
    for attempt in range(retry):
        try:
            refresh_mixin()
            url = 'https://api.bilibili.com' + path + '?' + wbi_sign(params)
            data = get_json(url)
            code = data.get('code')
            if code == 0:
                return data.get('data')
            log('  接口返回 code=%s %s，重试 %d/%d' % (code, data.get('message'), attempt + 1, retry))
        except Exception as e:
            log('  接口异常 %s，重试 %d/%d' % (type(e).__name__, attempt + 1, retry))
        time.sleep(4 + attempt * 5)
    return None


def parse_duration(s):
    """把 '3:45' / '12:03' 转成秒"""
    try:
        parts = [int(x) for x in str(s).split(':')]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 0


def strip_html(s):
    return re.sub(r'<[^>]+>', '', str(s or '')).replace('&quot;', '"').replace('&amp;', '&')


def search(keyword, page=1):
    data = api_call('/x/web-interface/search/type', {
        'search_type': 'video',
        'keyword': keyword,
        'page': page,
        'order': 'totalrank',
    })
    if not data:
        return []
    return data.get('result') or []


def verify(bvid):
    """用 view 接口确认：免费、能嵌入、非番剧"""
    try:
        d = get_json('https://api.bilibili.com/x/web-interface/view?bvid=' + bvid)
        if d.get('code') != 0:
            return None
        x = d['data']
        if x.get('rights', {}).get('pay', 0) or x.get('redirect_url'):
            return None
        if x.get('rights', {}).get('is_cooperation', 0) and x.get('stat', {}).get('view', 0) < 1000:
            return None
        return {
            'id': bvid,
            'title': x['title'],
            'channel': x['owner']['name'],
            'channelUrl': 'https://space.bilibili.com/%d' % x['owner']['mid'],
            'url': 'https://www.bilibili.com/video/' + bvid,
            'cover': x['pic'].replace('http://', 'https://') + '@448w_252h_1c.webp',
            'duration': x['duration'],
        }
    except Exception:
        return None


def main():
    log('开始拉取 B站视频')
    seen = set()
    result = {}
    for cat in CATEGORIES:
        log('分类: %s' % cat['name'])
        picked = []
        for kw in cat['keywords']:
            if len(picked) >= cat['quota']:
                break
            log('  搜索: %s' % kw)
            items = search(kw)
            log('  返回 %d 条' % len(items))
            for it in items:
                if len(picked) >= cat['quota']:
                    break
                bvid = it.get('bvid', '')
                if not bvid or bvid in seen:
                    continue
                title = strip_html(it.get('title', ''))
                dur = parse_duration(it.get('duration')) if isinstance(it.get('duration'), str) else int(it.get('duration') or 0)
                if dur <= 0 or dur > cat['max_dur']:
                    continue
                if any(w.lower() in title.lower() for w in BLOCK_WORDS):
                    continue
                seen.add(bvid)
                time.sleep(1.2)  # view 接口限速
                v = verify(bvid)
                if not v:
                    continue
                v['category'] = cat['name']
                v['minAge'] = cat['age']
                v['reason'] = '%s · %d 分钟，%s' % (cat['name'], round(dur / 60), it.get('author', ''))
                picked.append(v)
                log('    ✓ %s %s' % (bvid, v['title'][:26]))
            time.sleep(2)
        result[cat['name']] = picked
        log('  本类入库 %d 条' % len(picked))

    total = sum(len(v) for v in result.values())
    data = {
        'built': datetime.now(tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M'),
        'source': 'B站公开视频（关键词搜索 + 免费可嵌入过滤）',
        'categories': [{'name': c['name'], 'icon': c['icon'], 'age': c['age']} for c in CATEGORIES],
        'groups': result,
        'total': total,
    }
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log('完成，共 %d 条，已写入 %s' % (total, out))
    return data


if __name__ == '__main__':
    main()
