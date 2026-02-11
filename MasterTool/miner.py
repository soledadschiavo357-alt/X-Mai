# Dependencies:
# pip install tqdm requests

import warnings
import os

# Suppress all warnings immediately
warnings.filterwarnings("ignore")
os.environ['PYTHONWARNINGS'] = 'ignore'

import csv
import sys
import time
import requests
import json
import random
import string
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from collections import defaultdict

# ==========================================
# 🔧 配置区域
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEDS_FILE = os.path.join(BASE_DIR, 'seeds.txt')
OUTPUT_FILE = os.path.join(BASE_DIR, 'raw_keywords.csv')

MAX_WORKERS = 8
DELAY_MIN = 0.5
DELAY_MAX = 1.0

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# ==========================================
# 🛠️ 核心功能
# ==========================================

def contains_chinese(text):
    """检查是否包含汉字"""
    return bool(re.search(r'[\u4e00-\u9fa5]', text))

def load_seeds():
    if not os.path.exists(SEEDS_FILE): return []
    with open(SEEDS_FILE, 'r', encoding='utf-8') as f:
        seeds = [line.strip() for line in f if line.strip()]
    return seeds

def get_suggestions(url, params, source_name):
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        response = requests.get(url, params=params, headers=headers, timeout=5)
        if response.status_code == 200:
            if source_name == 'Google':
                data = response.json()
                if len(data) > 1: return data[1]
            elif source_name == 'Bing':
                data = response.json()
                if isinstance(data, list) and len(data) > 1: return data[1]
                elif 'SearchSuggestions' in data: return [item['Query'] for item in data['SearchSuggestions']]
    except:
        pass
    return []

def mine_google(query):
    # 保持全球中文环境
    url = "http://suggestqueries.google.com/complete/search"
    params = {'client': 'chrome', 'q': query, 'hl': 'zh-CN', 'ds': ''}
    return get_suggestions(url, params, 'Google')

def mine_bing(query):
    url = "https://api.bing.com/osjson.aspx"
    params = {'query': query, 'mkt': 'zh-CN'}
    return get_suggestions(url, params, 'Bing')

def mine_single_task(task):
    """
    注意：这里不再做过滤，而是先把所有东西都挖回来。
    筛选逻辑放到最后统一处理，因为我们需要对比 Google 和 Bing 的结果。
    """
    query, seed = task
    results = []
    
    # 挖 Google
    g_results = mine_google(query)
    for kw in g_results:
        results.append({'kw': kw, 'source': 'Google', 'seed': seed})
        
    # 挖 Bing
    b_results = mine_bing(query)
    for kw in b_results:
        results.append({'kw': kw, 'source': 'Bing', 'seed': seed})
        
    return results

def get_suffixes():
    suffixes = list(string.ascii_lowercase)
    return suffixes

def main():
    print("🚀 启动【智能共识】挖掘模式 (Consensus Mode)...")
    print("🛡️  策略：保留中文 OR 保留(Google+Bing)共同推荐的英文热词")
    
    seeds = load_seeds()
    if not seeds:
        print("❌ seeds.txt 为空")
        return


    # 1. 生成任务
    suffixes = get_suffixes()
    tasks = []
    for seed in seeds:
        tasks.append((seed, seed))
        for suffix in suffixes:
            tasks.append((f"{seed} {suffix}", seed))
            
    print(f"📋 任务数: {len(tasks)}")
    
    # 2. 临时存储所有数据 (用于对比)
    # 格式: { "关键词": { "sources": {"Google", "Bing"}, "seed": "xxx" } }
    temp_storage = defaultdict(lambda: {'sources': set(), 'seed': ''})
    
    print("⏳ 正在全面挖掘 (先采集，后清洗)...")
    
    with tqdm(total=len(tasks), desc="Mining", unit="task", ncols=100) as pbar:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_task = {executor.submit(mine_single_task, task): task for task in tasks}
            
            for future in as_completed(future_to_task):
                try:
                    results = future.result()
                    if results:
                        for item in results:
                            kw = item['kw']
                            src = item['source']
                            # 记录数据
                            temp_storage[kw]['sources'].add(src)
                            # 记录来源种子 (保留第一个遇到的即可)
                            if not temp_storage[kw]['seed']:
                                temp_storage[kw]['seed'] = item['seed']
                    pbar.update(1)
                except:
                    pbar.update(1)

    # 3. 核心清洗逻辑 (Smart Filtering)
    print(f"\n🧹 正在清洗数据 (原始数据量: {len(temp_storage)})...")
    final_keywords = []
    
    for kw, data in temp_storage.items():
        sources = data['sources']
        seed = data['seed']
        
        # --- 你的核心策略 ---
        is_chinese = contains_chinese(kw)
        is_consensus = ('Google' in sources and 'Bing' in sources) # 两个都有
        
        should_keep = False
        
        if is_chinese:
            should_keep = True # 中文直接留
        elif is_consensus:
            should_keep = True # 英文如果双平台推荐，说明是热词，留！
        
        if should_keep:
            # 存入列表，展平来源 (如果两个都有，就存两条记录，方便 Analyzer 统计热度)
            for src in sources:
                final_keywords.append([kw, src, seed])

    print(f"✨ 清洗完成！保留了 {len(final_keywords)} 条【高价值】数据")
    print(f"🗑️  丢弃了 {len(temp_storage) - len(set(x[0] for x in final_keywords))} 条【单平台英文噪音】")

    # 4. 保存
    if final_keywords:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Keyword', 'Source', 'Seed'])
            writer.writerows(final_keywords)
        print(f"✅ 结果已保存至: {OUTPUT_FILE}")
    else:
        print("⚠️ 未保留任何数据")

if __name__ == "__main__":
    main()