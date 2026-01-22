import os
import re
import json
import glob
from bs4 import BeautifulSoup
from datetime import datetime
import random
import copy
from urllib.parse import urlparse

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(BASE_DIR, 'index.html')
BLOG_DIR = os.path.join(BASE_DIR, 'blog')
BLOG_INDEX_PATH = os.path.join(BLOG_DIR, 'index.html')

def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

def clean_link(url, force_root=False):
    """
    Standardize links:
    1. Remove .html suffix for internal links.
    2. Ensure root-relative paths for assets where appropriate (force_root=True).
    3. Handle fragments and queries correctly.
    """
    if not url:
        return url
    
    # Skip external links, data URIs
    if url.startswith(('http://', 'https://', 'data:', 'mailto:', 'tel:')):
        return url
    
    # Handle pure anchors
    if url.startswith('#'):
        # If forcing root (e.g. for global nav), prepend /
        # e.g. #features -> /#features (so it works from subpages)
        if force_root:
            return '/' + url
        return url
        
    try:
        # Parse the URL
        parsed = urlparse(url)
        path = parsed.path
        
        # If path ends with .html, strip it
        if path.endswith('.html'):
            path = path[:-5]
        
        # Ensure root relative for internal paths if requested
        if force_root and path and not path.startswith('/'):
            path = '/' + path
            
        # Reassemble
        new_url = path
        if parsed.query:
            new_url += '?' + parsed.query
        if parsed.fragment:
            new_url += '#' + parsed.fragment
            
        return new_url
        
    except Exception:
        # Fallback
        if url.endswith('.html'):
            base = url[:-5]
        else:
            base = url
            
        if force_root and not base.startswith('/'):
            base = '/' + base
        return base

def clean_element_links(element, force_root=False):
    """Recursively clean links in an element."""
    if not element:
        return

    for tag in element.find_all(['a', 'link', 'img', 'script']):
        if tag.has_attr('href'):
            # Fix Twitter help links to X.com to avoid redirects/errors
            if 'help.twitter.com' in tag['href']:
                tag['href'] = tag['href'].replace('help.twitter.com', 'help.x.com')
                # Fix old appeal links
                if 'forms/general?subtopic=suspended' in tag['href']:
                     tag['href'] = 'https://help.x.com/en/forms/account-access/appeals'

            tag['href'] = clean_link(tag['href'], force_root)
            
            # Auto-add rel attributes for external links and soft routes
            if tag.name == 'a':
                href = tag['href']
                is_external = href.startswith(('http://', 'https://')) and 'x-mai.top' not in href
                is_soft_route = href.startswith('/go/')
                
                if is_external or is_soft_route:
                    # Get existing rel (ensure it's a list)
                    rel = tag.get('rel', [])
                    if isinstance(rel, str):
                        rel = rel.split()
                    
                    # Add required attributes
                    required = ['nofollow', 'noopener', 'noreferrer']
                    changed = False
                    for r in required:
                        if r not in rel:
                            rel.append(r)
                            changed = True
                            
                    if changed or not tag.get('rel'):
                        tag['rel'] = rel
                        
                    # Ensure target="_blank" for external links
                    if is_external and tag.get('target') != '_blank':
                        tag['target'] = '_blank'

        if tag.has_attr('src'):
            tag['src'] = clean_link(tag['src'], force_root)

def fix_breadcrumbs(soup):
    """Ensure breadcrumb nav has correct aria-label."""
    # 1. Fix existing with wrong case
    for nav in soup.find_all('nav', attrs={'aria-label': 'Breadcrumb'}):
        nav['aria-label'] = 'breadcrumb'
        
    # 2. Add to missing
    # Look for navs that contain "首页" and "Blog" but lack aria-label
    for nav in soup.find_all('nav'):
        if not nav.get('aria-label') and not nav.get('id') == 'navbar':
            text = nav.get_text()
            if '首页' in text and 'Blog' in text:
                nav['aria-label'] = 'breadcrumb'

def extract_assets(soup):
    """Extract layout components and brand assets."""
    # 1. Layout Components
    header = soup.find('header', id='navbar')
    if not header:
        header = soup.find('header')
    
    footer = soup.find('footer')
    
    # Clean links in header and footer
    # force_root=True because these come from index.html and should be valid globally
    if header:
        clean_element_links(header, force_root=True)
    if footer:
        clean_element_links(footer, force_root=True)

    # 2. Brand Assets (Favicons)
    favicons = []
    for rel in [['icon'], ['shortcut', 'icon'], ['apple-touch-icon']]:
        found = soup.find_all('link', rel=lambda x: x and set(x.split()) == set(rel))
        if not found and rel == ['icon']:
             found = soup.find_all('link', rel='icon')
        
        for link in found:
            href = link.get('href')
            if href:
                # Favicons must be root relative
                link['href'] = clean_link(href, force_root=True)
                favicons.append(str(link))
    
    seen = set()
    unique_favicons = []
    for f in favicons:
        if f not in seen:
            unique_favicons.append(f)
            seen.add(f)
            
    return header, footer, unique_favicons

def get_blog_metadata(file_path):
    """Extract metadata from a blog post."""
    content = read_file(file_path)
    soup = BeautifulSoup(content, 'html.parser')
    
    # Title
    title_tag = soup.find('title')
    title = title_tag.get_text().strip() if title_tag else "No Title"
    
    # Description
    desc_tag = soup.find('meta', attrs={'name': 'description'})
    description = desc_tag['content'].strip() if desc_tag else ""
    
    # Keywords
    kw_tag = soup.find('meta', attrs={'name': 'keywords'})
    keywords = kw_tag['content'].strip() if kw_tag else ""
    
    # Canonical
    can_tag = soup.find('link', rel='canonical')
    canonical = can_tag['href'].strip() if can_tag else ""
    if canonical.endswith('.html'):
        canonical = canonical[:-5]
        
    # Date
    date = "2026.01.01" 
    date_match = re.search(r'\d{4}\.\d{2}\.\d{2}', content)
    if date_match:
        date = date_match.group(0)
        
    # H1
    h1_tag = soup.find('h1')
    h1 = h1_tag.get_text().strip() if h1_tag else title
    
    # Image (og:image)
    img_tag = soup.find('meta', property='og:image')
    image = img_tag['content'].strip() if img_tag else "/og-cover.jpg"
    
    # URL (Relative)
    rel_url = "/blog/" + os.path.basename(file_path)
    if rel_url.endswith('.html'):
        rel_url = rel_url[:-5]
        
    return {
        'path': file_path,
        'title': title,
        'description': description,
        'keywords': keywords,
        'canonical': canonical,
        'date': date,
        'h1': h1,
        'image': image,
        'url': rel_url,
        'soup': soup 
    }

def reconstruct_head(soup, metadata, favicons):
    """Reconstruct the head section."""
    if not soup.head:
        head = soup.new_tag('head')
        soup.insert(0, head)
    else:
        soup.head.clear()
        
    head = soup.head
    
    def append_html(html_str):
        if html_str:
            tag = BeautifulSoup(html_str, 'html.parser')
            if tag:
                for child in list(tag.children):
                     head.append(child)

    # Group A: Basic Metadata
    head.append(soup.new_tag('meta', charset="utf-8"))
    head.append('\n    ')
    head.append(soup.new_tag('meta', attrs={"name": "viewport", "content": "width=device-width, initial-scale=1.0"}))
    head.append('\n    ')
    title_tag = soup.new_tag('title')
    title_tag.string = metadata['title']
    head.append(title_tag)
    head.append('\n\n    ')
    
    # Group B: SEO Core
    head.append(soup.new_tag('meta', attrs={"name": "description", "content": metadata['description']}))
    head.append('\n    ')
    if metadata['keywords']:
        head.append(soup.new_tag('meta', attrs={"name": "keywords", "content": metadata['keywords']}))
        head.append('\n    ')
    if metadata['canonical']:
        head.append(soup.new_tag('link', rel="canonical", href=metadata['canonical']))
    head.append('\n\n    ')
    
    # Group C: Indexing & Geo
    head.append(soup.new_tag('meta', attrs={"name": "robots", "content": "index, follow"}))
    head.append('\n    ')
    head.append(soup.new_tag('meta', attrs={"http-equiv": "content-language", "content": "zh-CN"}))
    head.append('\n    ')
    for lang, code in [('x-default', 'zh'), ('zh', 'zh'), ('zh-CN', 'zh-CN')]:
        head.append(soup.new_tag('link', rel="alternate", hreflang=lang, href=metadata['canonical']))
        head.append('\n    ')
    head.append('\n    ')

    # Group D: Branding & Resources
    for fav in favicons:
        append_html(fav)
        head.append('\n    ')
    
    resources = [
        '<link rel="preconnect" href="https://cdn.tailwindcss.com">',
        '<link rel="preconnect" href="https://fonts.googleapis.com">',
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">',
        '<script src="https://cdn.tailwindcss.com"></script>',
        '<script src="https://unpkg.com/lucide@latest"></script>'
    ]
    
    tailwind_config = """
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                fontFamily: {
                    sans: ['Inter', 'sans-serif'],
                },
                extend: {
                    colors: {
                        xblack: '#000000',
                        dark: '#050505',
                        card: '#111111',
                        twitter: '#1DA1F2',
                    }
                }
            }
        }
    </script>
    """
    
    for res in resources:
        append_html(res)
        head.append('\n    ')
    append_html(tailwind_config)
    head.append('\n\n    ')
    
    # Group E: Structured Data (Schema)
    schema_script = soup.new_tag('script', type="application/ld+json")
    schema_data = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": metadata['title'],
        "image": metadata['image'],
        "datePublished": metadata['date'],
        "author": {
            "@type": "Organization",
            "name": "X-Mai Team"
        },
        "description": metadata['description']
    }
    
    breadcrumb_data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [{
            "@type": "ListItem",
            "position": 1,
            "name": "首页",
            "item": "https://x-mai.top/"
        },{
            "@type": "ListItem",
            "position": 2,
            "name": "Blog",
            "item": "https://x-mai.top/blog/"
        },{
            "@type": "ListItem",
            "position": 3,
            "name": metadata['h1'],
            "item": metadata['canonical'] or metadata['url']
        }]
    }
    
    schema_script.string = json.dumps([schema_data, breadcrumb_data], ensure_ascii=False, indent=2)
    head.append(schema_script)
    head.append('\n')

def inject_layout(soup, header, footer):
    """Inject/Replace Header and Footer."""
    old_header = soup.find('header')
    if old_header:
        old_header.replace_with(header)
    else:
        if soup.body:
            soup.body.insert(0, header)
            
    old_footer = soup.find('footer')
    if old_footer:
        old_footer.replace_with(footer)
    else:
        if soup.body:
            soup.body.append(footer)

def generate_recommendations(articles, current_url):
    """Generate HTML for recommended reading."""
    candidates = [a for a in articles if a['url'] != current_url]
    if not candidates:
        return ""
    
    selected = random.sample(candidates, min(3, len(candidates)))
    
    html = '<div class="mt-12 pt-8 border-t border-white/10">\n'
    html += '    <h3 class="text-xl font-bold text-white mb-6">相关阅读</h3>\n'
    html += '    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">\n'
    
    for art in selected:
        html += f'''
        <a href="{art['url']}" class="block group bg-zinc-900/50 border border-white/5 rounded-xl overflow-hidden hover:border-blue-500/30 transition-all">
            <div class="h-32 bg-gray-800 relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-blue-900/20 to-purple-900/20"></div>
            </div>
            <div class="p-4">
                <div class="text-xs text-gray-500 mb-2">{art['date']}</div>
                <h4 class="font-bold text-white text-sm group-hover:text-blue-400 transition-colors line-clamp-2">{art['h1']}</h4>
            </div>
        </a>
        '''
    html += '    </div>\n</div>'
    return html

def inject_recommendations(soup, rec_html):
    """Inject recommendations at the bottom of article."""
    article = soup.find('article')
    if article:
        for div in article.find_all('div', recursive=False):
            # Safety check: Never delete the main content div (prose)
            if div.get('class') and any('prose' in c for c in div.get('class')):
                continue

            if div.find('h3', string=re.compile("推荐阅读|相关阅读|Related|Recommended")):
                div.decompose()
        
        rec_soup = BeautifulSoup(rec_html, 'html.parser')
        article.append(rec_soup)

def update_global_lists(index_soup, articles):
    """Update Latest News in index.html."""
    sorted_articles = sorted(articles, key=lambda x: x['date'], reverse=True)
    latest = sorted_articles[:3]
    
    target_section = None
    for section in index_soup.find_all('section'):
        if section.find('h2', string=re.compile("最新运营干货")):
            target_section = section
            break
            
    if target_section:
        grid = target_section.find('div', class_=lambda x: x and 'grid-cols-1' in x and 'md:grid-cols-3' in x)
        if grid:
            grid.clear()
            
            for art in latest:
                card_html = f'''
                <a href="{art['url']}" class="group block bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden hover:border-blue-500/50 transition-all duration-300 hover:-translate-y-1">
                    <div class="h-48 bg-gradient-to-br from-blue-900/20 to-purple-900/20 flex items-center justify-center relative overflow-hidden">
                        <div class="absolute inset-0 bg-blue-600/10 group-hover:bg-blue-600/20 transition-all"></div>
                        <i data-lucide="file-text" class="w-16 h-16 text-blue-500 group-hover:scale-110 transition-transform duration-500"></i>
                        <span class="absolute top-4 left-4 bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded shadow-lg">NEW</span>
                    </div>
                    <div class="p-6">
                        <div class="flex items-center gap-2 text-xs text-gray-500 mb-3">
                            <i data-lucide="clock" class="w-3 h-3"></i> {art['date']}
                        </div>
                        <h3 class="text-xl font-bold text-white mb-3 group-hover:text-blue-400 transition-colors">{art['h1']}</h3>
                        <p class="text-sm text-gray-400 line-clamp-2 leading-relaxed">
                            {art['description']}
                        </p>
                    </div>
                </a>
                '''
                grid.append(BeautifulSoup(card_html, 'html.parser'))

def inject_blog_index_schema(soup):
    """Inject Schema for Blog Index."""
    schema_script = soup.find('script', type="application/ld+json")
    if schema_script:
        schema_script.decompose()
        
    schema_data = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "X-Mai Blog",
        "description": "X (Twitter) 运营干货与教程",
        "url": "https://x-mai.top/blog/",
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [{
                "@type": "ListItem",
                "position": 1,
                "name": "首页",
                "item": "https://x-mai.top/"
            },{
                "@type": "ListItem",
                "position": 2,
                "name": "Blog",
                "item": "https://x-mai.top/blog/"
            }]
        }
    }
    
    new_script = soup.new_tag('script', type="application/ld+json")
    new_script.string = json.dumps(schema_data, ensure_ascii=False, indent=2)
    
    if soup.head:
        soup.head.append(new_script)

def update_blog_index(articles, header, footer, favicons):
    """Update blog/index.html."""
    if not os.path.exists(BLOG_INDEX_PATH):
        return

    content = read_file(BLOG_INDEX_PATH)
    soup = BeautifulSoup(content, 'html.parser')
    
    if soup.head:
        for link in soup.head.find_all('link', rel=re.compile('icon')):
            link.decompose()
        for fav in favicons:
            soup.head.append(BeautifulSoup(fav, 'html.parser'))
            
    inject_layout(soup, header, footer)
    
    # Also clean links in blog/index.html body!
    clean_element_links(soup, force_root=False)
    
    # Fix breadcrumbs & Add Schema
    fix_breadcrumbs(soup)
    inject_blog_index_schema(soup)

    container = soup.find('div', class_=lambda x: x and 'grid-cols-1' in x and 'md:grid-cols-3' in x)
    if container:
        container.clear()
        sorted_articles = sorted(articles, key=lambda x: x['date'], reverse=True)
        
        for art in sorted_articles:
             card_html = f'''
                <a href="{art['url']}" class="group block bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden hover:border-blue-500/50 transition-all duration-300 hover:-translate-y-1 shadow-lg">
                    <div class="h-56 bg-gradient-to-br from-gray-800 to-black flex items-center justify-center relative">
                        <i data-lucide="file-text" class="w-16 h-16 text-blue-500 group-hover:scale-110 transition-transform"></i>
                        <span class="absolute top-4 left-4 bg-blue-600 text-white text-[10px] font-bold px-2 py-1 rounded">ARTICLE</span>
                    </div>
                    <div class="p-6">
                        <div class="flex items-center gap-2 text-xs text-gray-500 mb-3">
                            <span>{art['date']}</span>
                            <span class="w-1 h-1 rounded-full bg-gray-600"></span>
                            <span>Blog</span>
                        </div>
                        <h2 class="text-xl font-bold text-white mb-3 group-hover:text-blue-400 transition-colors">{art['h1']}</h2>
                        <p class="text-sm text-gray-400 line-clamp-3 leading-relaxed">
                            {art['description']}
                        </p>
                    </div>
                </a>
             '''
             container.append(BeautifulSoup(card_html, 'html.parser'))

    write_file(BLOG_INDEX_PATH, str(soup))

def main():
    print("Phase 1: Smart Extraction from index.html...")
    index_content = read_file(INDEX_PATH)
    index_soup = BeautifulSoup(index_content, 'html.parser')
    header, footer, favicons = extract_assets(index_soup)
    
    print(f"Extracted {len(favicons)} favicons.")
    
    print("Phase 2: Processing Blog Posts...")
    articles = []
    blog_files = glob.glob(os.path.join(BLOG_DIR, '*.html'))
    
    for file_path in blog_files:
        if os.path.basename(file_path) == 'index.html':
            continue
            
        print(f"Analyzing {os.path.basename(file_path)}...")
        meta = get_blog_metadata(file_path)
        articles.append(meta)
        
    for meta in articles:
        print(f"Updating {os.path.basename(meta['path'])}...")
        soup = meta['soup']
        
        reconstruct_head(soup, meta, favicons)
        inject_layout(soup, copy.copy(header), copy.copy(footer))
        
        rec_html = generate_recommendations(articles, meta['url'])
        inject_recommendations(soup, rec_html)
        
        # Clean links in the article body! (force_root=False to preserve relative context, but strip .html)
        clean_element_links(soup, force_root=False)
        
        # Fix breadcrumbs
        fix_breadcrumbs(soup)
        
        write_file(meta['path'], str(soup))
        
    print("Phase 3: Global Updates...")
    update_global_lists(index_soup, articles)
    write_file(INDEX_PATH, str(index_soup))
    
    update_blog_index(articles, copy.copy(header), copy.copy(footer), favicons)
    
    print("Build Complete!")

if __name__ == "__main__":
    main()
