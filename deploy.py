#!/usr/bin/env python3
"""一键部署到 GitHub Pages。token 从环境变量 GH_TOKEN 读取，不落盘。"""
import os, sys, json, subprocess, urllib.request, urllib.error

TOKEN = os.environ.get('GH_TOKEN', '').strip()
if not TOKEN:
    print('ERROR: 请先设置环境变量 GH_TOKEN'); sys.exit(1)

OWNER = 'liuhei276'
REPO = 'family-tv'
API = 'https://api.github.com'
H = {'User-Agent': 'Mozilla/5.0', 'Authorization': 'Bearer ' + TOKEN,
     'Accept': 'application/vnd.github+json'}


def api(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=H, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        raw = r.read().decode()
        return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


import re
def _mask(c):
    # 脱敏 URL 里嵌的 token，以及任何 ghp_/github_pat_ 开头的字符串
    c = re.sub(r'https://[^/@\s]+@', 'https://***@', c)
    c = re.sub(r'(ghp_|github_pat_)[A-Za-z0-9_]+', r'\1***', c)
    return c

def run(cmd, check=True):
    print('>', ' '.join(_mask(c) for c in cmd))
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.stdout: print(_mask(p.stdout.rstrip()))
    if check and p.returncode != 0:
        print(_mask(p.stderr.rstrip())); sys.exit(p.returncode)
    return p


print('=== 1. 确认账号 ===')
code, me = api('GET', '/user')
if code != 200:
    print('token 无效:', me); sys.exit(1)
OWNER = me.get('login', OWNER)
print('登录成功:', OWNER)

print('=== 2. 创建仓库（已存在则跳过）===')
code, info = api('GET', '/repos/%s/%s' % (OWNER, REPO))
if code == 404:
    code, info = api('POST', '/user/repos', {
        'name': REPO, 'private': False,
        'description': '家庭儿童电视 - B站精选视频聚合, 每日自动更新',
        'auto_init': False})
    if code not in (200, 201):
        print('创建仓库失败:', info); sys.exit(1)
    print('仓库已创建')
elif code == 200:
    print('仓库已存在，复用')
else:
    print('检查仓库失败:', info); sys.exit(1)

print('=== 3. 初始化并推送 ===')
here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
if not os.path.exists('.git'):
    run(['git', 'init', '-b', 'main'])
run(['git', 'config', 'user.name', 'family-tv-bot'])
run(['git', 'config', 'user.email', 'bot@users.noreply.github.com'])
run(['git', 'add', '-A'])
p = run(['git', 'diff', '--cached', '--quiet'], check=False)
if p.returncode == 0:
    print('没有新改动，跳过提交')
else:
    run(['git', 'commit', '-m', '初始部署：儿童电视视频聚合系统'])
remote = 'https://%s:%s@github.com/%s/%s.git' % (OWNER, TOKEN, OWNER, REPO)
run(['git', 'push', '--force', remote, 'main'])
# 清掉可能残留的带 token remote
run(['git', 'remote', 'remove', 'origin'], check=False)
run(['git', 'remote', 'add', 'origin', 'https://github.com/%s/%s.git' % (OWNER, REPO)])

print('=== 4. 开启 GitHub Pages ===')
code, pages = api('GET', '/repos/%s/%s/pages' % (OWNER, REPO))
if code == 404:
    code, pages = api('POST', '/repos/%s/%s/pages' % (OWNER, REPO), {
        'source': {'branch': 'main', 'path': '/root'}})
    if code not in (200, 201):
        print('开启 Pages 失败（可能需要手动）:', pages)
    else:
        print('Pages 已开启')
elif code == 200:
    print('Pages 已存在，状态:', pages.get('status'))
else:
    print('检查 Pages 失败:', pages)

print()
print('=== 完成 ===')
print('电视访问地址：https://%s.github.io/%s/tv.html' % (OWNER, REPO))
print('诊断页：      https://%s.github.io/%s/diag.html' % (OWNER, REPO))
