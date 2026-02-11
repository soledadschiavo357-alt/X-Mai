import csv
import os
import collections
import re
from datetime import datetime

# ==========================================
# 🔧 配置区域
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_FILE = os.path.join(BASE_DIR, 'raw_keywords.csv')
REPORT_FILE = os.path.join(BASE_DIR, 'SEO_Dashboard.html')

# 内置意图分类规则
INTENT_RULES = {
    '💰 搞钱 (Money)': ['price', 'buy', 'cost', 'cheap', 'discount', 'deal', 'shop', 'store', 'subscription', 'plan', '价格', '购买', '合租', '费用', '便宜', '优惠', '会员', '充值', '账号'],
    '🚦 引流 (Traffic)': ['download', 'apk', 'install', 'error', 'fix', 'bug', 'tutorial', 'guide', 'how to', '下载', '安装', '报错', '教程', '怎么', '指南', '解决', '办法'],
    '🆚 对比 (Competitor)': ['vs', 'alternative', 'better than', 'review', 'comparison', '对比', '替代', '好用', '评价']
}

# 停用词表 (用于生成右侧热词榜，不影响主表格显示)
STOP_WORDS = {
    'for', 'to', 'in', 'on', 'with', 'the', 'a', 'an', 'of', 'and', 'or', 'is', 'are', 
    'how', 'what', 'where', 'why', 'download', 'free', '2024', '2025', '2026',
    'mac', 'windows', 'linux', 'android', 'ios', 'vs', 'apk', 'mod',
    '教程', '下载', '怎么', '什么', '免费', '破解', '安装', '使用', 'cursor', 'grok', 'supergrok'
}

# ==========================================
# 🛠️ 核心功能函数
# ==========================================

def load_raw_data():
    """读取 Raw CSV 文件"""
    data = []
    if os.path.exists(RAW_FILE):
        try:
            with open(RAW_FILE, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    data.append(row)
        except Exception as e:
            print(f"Error reading {RAW_FILE}: {e}")
    return data

def classify_keyword(keyword):
    """对原始关键词进行实时分类"""
    kw_lower = keyword.lower()
    intents = []
    for intent_name, keywords in INTENT_RULES.items():
        if any(k in kw_lower for k in keywords):
            intents.append(intent_name)
    return intents if intents else ['ℹ️ 其他 (Info)']

def calculate_heat(keyword, raw_data_list):
    """计算热度分数 (1-5)"""
    mentions = [r for r in raw_data_list if r['Keyword'] == keyword]
    sources = set(r.get('Source', '') for r in mentions)
    count = len(mentions)
    
    score = 1
    if 'Google' in sources and 'Bing' in sources: score += 2
    if count > 1: score += 1
    if len(keyword) < 15: score += 1
    return min(score, 5)

def get_heat_icon(score):
    return "🔥" * score

def analyze_raw_data(data):
    """全量分析原始数据"""
    
    # 1. 基础统计
    total_raw = len(data)
    sources_count = collections.Counter(r.get('Source', 'Unknown') for r in data)
    
    # 2. 关键词聚合与热度计算
    unique_keywords = {}
    intent_stats = collections.Counter()
    
    for row in data:
        kw = row['Keyword']
        if kw not in unique_keywords:
            unique_keywords[kw] = {
                'Keyword': kw,
                'Sources': set(),
                'Count': 0,
                'Intent': classify_keyword(kw)
            }
        unique_keywords[kw]['Sources'].add(row.get('Source', 'Unknown'))
        unique_keywords[kw]['Count'] += 1

    # 3. 处理列表
    processed_list = []
    for kw, info in unique_keywords.items():
        score = calculate_heat(kw, data)
        info['HeatScore'] = score
        info['HeatIcon'] = get_heat_icon(score)
        info['SourceDisplay'] = " + ".join(info['Sources'])
        processed_list.append(info)
        
        # 统计意图（用于图表）
        for intent in info['Intent']:
            intent_stats[intent] += 1

    # 4. 排序 (按热度降序)
    processed_list.sort(key=lambda x: x['HeatScore'], reverse=True)

    # 5. 词频统计
    all_text = " ".join([d['Keyword'].lower() for d in data])
    words = re.findall(r'[\w]+', all_text)
    clean_words = [w for w in words if w not in STOP_WORDS and len(w) > 1 and not w.isdigit()]
    word_freq = collections.Counter(clean_words).most_common(20)
    
    # 6. 打包数据
    analysis = {
        'total_raw': total_raw,
        'unique_total': len(processed_list),
        'high_heat_count': sum(1 for x in processed_list if x['HeatScore'] >= 4),
        'sources_stats': dict(sources_count),
        'intent_stats': dict(intent_stats),
        'word_freq': word_freq,
        'money_keywords': [x for x in processed_list if any('搞钱' in i for i in x['Intent'])],
        'traffic_keywords': [x for x in processed_list if any('引流' in i for i in x['Intent'])],
        'all_keywords': processed_list # 这里保留全量数据
    }
    
    return analysis

def generate_html(analysis):
    """生成全能版仪表盘 (无限制版)"""
    
    # 准备图表数据
    freq_labels = [x[0] for x in analysis['word_freq']]
    freq_values = [x[1] for x in analysis['word_freq']]
    
    intent_labels = list(analysis['intent_stats'].keys())
    intent_values = list(analysis['intent_stats'].values())
    
    source_labels = list(analysis['sources_stats'].keys())
    source_values = list(analysis['sources_stats'].values())

    # 热词列表HTML
    top_roots_html = ""
    for word, count in analysis['word_freq']:
        top_roots_html += f"""
        <button class="list-group-item list-group-item-action d-flex justify-content-between align-items-center" 
                onclick="filterTable('{word}')">
            <span class="fw-bold">{word}</span>
            <span class="badge bg-light text-dark">{count}</span>
        </button>
        """
        
    # 设置显示限制：虽然我们解除了限制，但为了防止浏览器崩溃，设置一个极高的安全上限 (比如 5000)
    # 如果你的数据少于 5000，就会全部显示。
    SHOW_LIMIT = 5000 
    display_keywords = analysis['all_keywords'][:SHOW_LIMIT]

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>SEO Master Dashboard (Full View)</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body {{ background-color: #f0f2f5; font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
        .kpi-card {{ border: none; border-radius: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); transition: transform 0.2s; }}
        .kpi-card:hover {{ transform: translateY(-3px); }}
        .kpi-icon {{ font-size: 2.5rem; opacity: 0.2; position: absolute; right: 20px; bottom: 10px; }}
        .card {{ border: none; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.03); margin-bottom: 20px; }}
        .section-header {{ font-weight: 700; color: #1a202c; margin: 30px 0 15px 0; border-left: 4px solid #3182ce; padding-left: 12px; }}
        .heat-icon {{ color: #e53e3e; letter-spacing: -2px; }}
        .search-btn {{ color: #718096; margin-left: 8px; transition: 0.2s; }}
        .search-btn:hover {{ opacity: 1; transform: scale(1.1); }}
        .xhs-color {{ color: #ff2442; }}
        .zhihu-color {{ color: #0084ff; }}
        .table-hover tbody tr:hover {{ background-color: #f7fafc; }}
        .chart-container {{ position: relative; height: 200px; width: 100%; }}
        .badge-source {{ font-size: 0.7em; opacity: 0.8; }}
    </style>
</head>
<body>

<div class="container py-4">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h2 class="fw-bold text-dark"><i class="fas fa-chart-line text-primary"></i> SEO 全景战情室</h2>
            <p class="text-muted mb-0">Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | <span class="badge bg-success">Full Data View</span></p>
        </div>
        <button onclick="window.print()" class="btn btn-outline-secondary btn-sm"><i class="fas fa-print"></i> 打印报告</button>
    </div>

    <div class="row g-3 mb-4">
        <div class="col-md-3">
            <div class="card kpi-card bg-primary text-white h-100 p-3">
                <h6 class="text-uppercase mb-2" style="opacity:0.9">挖掘总数 (Raw)</h6>
                <h2 class="display-6 fw-bold mb-0">{analysis['total_raw']}</h2>
                <i class="fas fa-database kpi-icon text-white"></i>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card bg-danger text-white h-100 p-3">
                <h6 class="text-uppercase mb-2" style="opacity:0.9">去重后总数 (Unique)</h6>
                <h2 class="display-6 fw-bold mb-0">{analysis['unique_total']}</h2>
                <i class="fas fa-fire kpi-icon text-white"></i>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card bg-success text-white h-100 p-3">
                <h6 class="text-uppercase mb-2" style="opacity:0.9">搞钱机会 (Money)</h6>
                <h2 class="display-6 fw-bold mb-0">{len(analysis['money_keywords'])}</h2>
                <i class="fas fa-coins kpi-icon text-white"></i>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card kpi-card bg-info text-white h-100 p-3">
                <h6 class="text-uppercase mb-2" style="opacity:0.9">引流机会 (Traffic)</h6>
                <h2 class="display-6 fw-bold mb-0">{len(analysis['traffic_keywords'])}</h2>
                <i class="fas fa-users kpi-icon text-white"></i>
            </div>
        </div>
    </div>

    <h5 class="section-header">📊 数据可视化透视</h5>
    <div class="row g-3">
        <div class="col-md-5">
            <div class="card h-100">
                <div class="card-body">
                    <h6 class="card-title text-muted mb-3"><i class="fas fa-poll"></i> 市场热点雷达 (Top 20)</h6>
                    <div class="chart-container"><canvas id="freqChart"></canvas></div>
                </div>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card h-100">
                <div class="card-body">
                    <h6 class="card-title text-muted mb-3"><i class="fas fa-pie-chart"></i> 搜索意图分布</h6>
                    <div class="chart-container"><canvas id="intentChart"></canvas></div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card h-100">
                <div class="card-body">
                    <h6 class="card-title text-muted mb-3"><i class="fas fa-server"></i> 渠道贡献</h6>
                    <div class="chart-container"><canvas id="sourceChart"></canvas></div>
                </div>
            </div>
        </div>
    </div>

    <h5 class="section-header">🚀 每日速赢行动 (Top 10)</h5>
    <div class="row g-3">
        <div class="col-md-6">
            <div class="card h-100 border-success border-top border-3">
                <div class="card-header bg-white border-0 fw-bold text-success"><span><i class="fas fa-money-bill-wave"></i> 搞钱词 Top 10</span></div>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0 text-nowrap">
                        <thead class="table-light"><tr><th>热度</th><th>关键词</th><th class="text-end">调研</th></tr></thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td class="heat-icon">{r['HeatIcon']}</td>
                                <td class="fw-bold">{r['Keyword']}</td>
                                <td class="text-end">
                                    <a href="https://www.xiaohongshu.com/search_result?keyword={r['Keyword']}" target="_blank" class="search-btn xhs-color"><i class="fas fa-book"></i></a>
                                    <a href="https://www.zhihu.com/search?type=content&q={r['Keyword']}" target="_blank" class="search-btn zhihu-color"><i class="fas fa-brain"></i></a>
                                </td>
                            </tr>
                            ''' for r in analysis['money_keywords'][:10]])}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card h-100 border-primary border-top border-3">
                <div class="card-header bg-white border-0 fw-bold text-primary"><span><i class="fas fa-users"></i> 引流词 Top 10</span></div>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0 text-nowrap">
                        <thead class="table-light"><tr><th>热度</th><th>关键词</th><th class="text-end">调研</th></tr></thead>
                        <tbody>
                            {"".join([f'''
                            <tr>
                                <td class="heat-icon">{r['HeatIcon']}</td>
                                <td>{r['Keyword']}</td>
                                <td class="text-end">
                                    <a href="https://www.xiaohongshu.com/search_result?keyword={r['Keyword']}" target="_blank" class="search-btn xhs-color"><i class="fas fa-book"></i></a>
                                    <a href="https://www.zhihu.com/search?type=content&q={r['Keyword']}" target="_blank" class="search-btn zhihu-color"><i class="fas fa-brain"></i></a>
                                </td>
                            </tr>
                            ''' for r in analysis['traffic_keywords'][:10]])}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <h5 class="section-header">🔍 全量数据库 (Deep Dive)</h5>
    <div class="row g-3">
        <div class="col-md-9">
            <div class="card h-100">
                <div class="card-header bg-white d-flex justify-content-between align-items-center">
                    <span class="fw-bold small">关键词总表 (按热度排序)</span>
                    <input type="text" id="tableSearch" class="form-control form-control-sm w-25" placeholder="🔍 搜索...">
                </div>
                <div class="card-body p-0">
                    <div class="table-responsive" style="max-height: 800px; overflow-y: auto;">
                        <table class="table table-sm table-hover align-middle mb-0" id="mainTable">
                            <thead class="table-light sticky-top">
                                <tr>
                                    <th width="80">热度</th>
                                    <th>关键词</th>
                                    <th>来源</th>
                                    <th>分类</th>
                                    <th class="text-end">调研</th>
                                </tr>
                            </thead>
                            <tbody>
                                {"".join([f'''
                                <tr>
                                    <td class="heat-icon">{r['HeatIcon']}</td>
                                    <td>{r['Keyword']}</td>
                                    <td><span class="badge bg-light text-dark border badge-source">{r['SourceDisplay']}</span></td>
                                    <td><span class="badge bg-secondary badge-source">{r['Intent'][0]}</span></td>
                                    <td class="text-end">
                                        <a href="https://www.xiaohongshu.com/search_result?keyword={r['Keyword']}" target="_blank" class="search-btn xhs-color"><i class="fas fa-book"></i></a>
                                    </td>
                                </tr>
                                ''' for r in display_keywords])} 
                            </tbody>
                        </table>
                        <div class="p-2 text-center text-muted small">
                            当前展示了 {len(display_keywords)} 条数据 (Total Available: {analysis['unique_total']})
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-md-3">
            <div class="card h-100">
                <div class="card-header bg-white border-0 fw-bold small">📌 点击筛选热词</div>
                <div class="card-body p-0" style="max-height: 800px; overflow-y: auto;">
                    <div class="list-group list-group-flush small">
                        {top_roots_html}
                    </div>
                </div>
            </div>
        </div>
    </div>

</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    // Charts Config
    new Chart(document.getElementById('freqChart'), {{
        type: 'bar',
        data: {{ labels: {freq_labels}, datasets: [{{ label: '提及频次', data: {freq_values}, backgroundColor: '#6c5ce7', borderRadius: 4 }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
    }});

    new Chart(document.getElementById('intentChart'), {{
        type: 'doughnut',
        data: {{ labels: {intent_labels}, datasets: [{{ data: {intent_values}, backgroundColor: ['#00b894', '#0984e3', '#636e72', '#fdcb6e'] }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, cutout: '65%', plugins: {{ legend: {{ position: 'right' }} }} }}
    }});

    new Chart(document.getElementById('sourceChart'), {{
        type: 'pie',
        data: {{ labels: {source_labels}, datasets: [{{ data: {source_values}, backgroundColor: ['#4285F4', '#00a4ef', '#EA4335'] }}] }},
        options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'bottom' }} }} }}
    }});

    // Filter Logic
    const searchInput = document.getElementById('tableSearch');
    const table = document.getElementById('mainTable');
    const trs = table.getElementsByTagName('tr');

    function filterTable(query) {{
        searchInput.value = query;
        const filter = query.toLowerCase();
        for (let i = 1; i < trs.length; i++) {{
            const td = trs[i].getElementsByTagName('td')[1];
            if (td) {{
                const txtValue = td.textContent || td.innerText;
                trs[i].style.display = txtValue.toLowerCase().indexOf(filter) > -1 ? "" : "none";
            }}
        }}
        table.scrollIntoView({{behavior: "smooth"}});
    }}
    searchInput.addEventListener('keyup', function() {{ filterTable(this.value); }});
</script>
</body>
</html>
    """
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✅ Dashboard generated successfully: {REPORT_FILE}")

def main():
    raw_data = load_raw_data()
    if not raw_data:
        print("❌ No raw_keywords.csv found!")
        return
    analysis = analyze_raw_data(raw_data)
    generate_html(analysis)

if __name__ == "__main__":
    main()