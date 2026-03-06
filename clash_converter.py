#!/usr/bin/env python3
"""
Clash 节点转换器
自动从 sharkDoor/vpn-free-nodes 获取最新节点，生成 Clash YAML 配置文件
"""

import json
import os
import re
from urllib.request import urlopen, Request
from urllib.parse import unquote
from datetime import datetime

GITHUB_API = "https://api.github.com/repos/sharkDoor/vpn-free-nodes/contents/node-list"
OUTPUT_FILE = "docs/clash_config.yaml"


def fetch_json(url):
    req = Request(url, headers={"User-Agent": "clash-converter/1.0"})
    with urlopen(req) as r:
        return json.loads(r.read())


from urllib.parse import quote

def fetch_text(url):
    # 对URL中的非ASCII字符进行编码
    encoded_url = quote(url, safe=':/?=&%#')
    req = Request(encoded_url, headers={"User-Agent": "clash-converter/1.0"})
    with urlopen(req) as r:
        return r.read().decode("utf-8")


def get_latest_file_url():
    print("📂 获取目录列表...")
    dirs = fetch_json(GITHUB_API)

    # 找最新月份文件夹
    month_dirs = sorted(
        [d for d in dirs if d["type"] == "dir"],
        key=lambda x: x["name"],
        reverse=True
    )
    if not month_dirs:
        raise RuntimeError("未找到月份目录")

    latest_month = month_dirs[0]
    print(f"📅 最新月份: {latest_month['name']}")

    # 找最新 md 文件
    files = fetch_json(latest_month["url"])
    md_files = sorted(
        [f for f in files if f["name"].endswith(".md")],
        key=lambda x: x["name"],
        reverse=True
    )
    if not md_files:
        raise RuntimeError("未找到节点文件")

    latest_file = md_files[0]
    print(f"📄 最新文件: {latest_file['name']}")
    return latest_file["download_url"], f"{latest_month['name']}/{latest_file['name']}"


def parse_nodes(text):
    nodes = []
    pattern = re.compile(
        r"trojan://([^@]+)@([^:]+):(\d+)\?([^#\s]+)#([^\s\n|]+)"
    )
    for m in pattern.finditer(text):
        password = m.group(1)
        server = m.group(2)
        port = int(m.group(3))
        params = dict(p.split("=", 1) for p in m.group(4).split("&") if "=" in p)
        raw_name = unquote(m.group(5).replace("+", " "))
        sni = params.get("peer", "download.windowsupdate.com")
        skip_cert = params.get("allowInsecure", "0") == "1"
        nodes.append({
            "name": raw_name,
            "server": server,
            "port": port,
            "password": password,
            "sni": sni,
            "skip_cert": skip_cert,
        })
    return nodes


def generate_yaml(nodes, source_file):
    def names_of(filter_fn):
        return [n["name"] for n in nodes if filter_fn(n["name"])]

    all_names = [n["name"] for n in nodes]
    jp_names = names_of(lambda n: "日本" in n or "JP" in n)
    us_names = names_of(lambda n: "美国" in n or "US" in n)
    netflix_names = names_of(lambda n: "Netflix" in n)
    chatgpt_names = names_of(lambda n: "ChatGPT" in n)

    def proxy_entry(n):
        return (
            f'  - name: "{n["name"]}"\n'
            f'    type: trojan\n'
            f'    server: {n["server"]}\n'
            f'    port: {n["port"]}\n'
            f'    password: {n["password"]}\n'
            f'    skip-cert-verify: {"true" if n["skip_cert"] else "false"}\n'
            f'    sni: {n["sni"]}'
        )

    def group_entry(name, gtype, proxies, extra=""):
        items = "\n".join(f'      - "{p}"' for p in proxies)
        return (
            f'  - name: "{name}"\n'
            f'    type: {gtype}\n'
            f'{extra}'
            f'    proxies:\n'
            f'{items}'
        )

    proxies_block = "\n\n".join(proxy_entry(n) for n in nodes)

    select_proxies = ['♻️ 自动选择', '🇯🇵 日本节点', '🇺🇸 美国节点'] + all_names
    auto_extra = '    url: http://www.gstatic.com/generate_204\n    interval: 300\n'

    groups_block = "\n\n".join([
        group_entry("🚀 节点选择", "select", select_proxies),
        group_entry("♻️ 自动选择", "url-test", all_names, auto_extra),
        group_entry("🇯🇵 日本节点", "select", jp_names or all_names),
        group_entry("🇺🇸 美国节点", "select", us_names or all_names),
        group_entry("🎬 Netflix", "select", netflix_names or all_names),
        group_entry("🤖 ChatGPT", "select", chatgpt_names or all_names),
        group_entry("🐟 漏网之鱼", "select", ["🚀 节点选择", "DIRECT"]),
    ])

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    return f"""\
# Clash 配置文件
# 生成时间: {now}
# 数据来源: {source_file}

mixed-port: 7890
allow-lan: false
mode: rule
log-level: info
external-controller: 127.0.0.1:9090

proxies:
{proxies_block}

proxy-groups:
{groups_block}

rules:
  - DOMAIN-SUFFIX,openai.com,🤖 ChatGPT
  - DOMAIN-SUFFIX,chatgpt.com,🤖 ChatGPT
  - DOMAIN-SUFFIX,netflix.com,🎬 Netflix
  - DOMAIN-SUFFIX,nflxvideo.net,🎬 Netflix
  - GEOIP,CN,DIRECT
  - MATCH,🐟 漏网之鱼
"""


def main():
    print("🚀 Clash 节点转换器启动\n")
    try:
        raw_url, source_file = get_latest_file_url()

        print("⬇️  下载节点数据...")
        text = fetch_text(raw_url)

        print("🔍 解析节点...")
        nodes = parse_nodes(text)
        if not nodes:
            raise RuntimeError("未找到有效节点")
        print(f"✅ 解析到 {len(nodes)} 个节点")

        yaml = generate_yaml(nodes, source_file)

        # 确保 docs 目录存在
        os.makedirs("docs", exist_ok=True)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(yaml)

        print(f"\n🎉 完成！已生成: {OUTPUT_FILE}")
        print(f"📋 节点列表:")
        for n in nodes:
            print(f"   - {n['name']}")

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        raise


if __name__ == "__main__":
    main()