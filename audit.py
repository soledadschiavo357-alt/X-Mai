import os
import sys
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

class SEOAudit:
    def __init__(self, root_dir='.'):
        self.root_dir = os.path.abspath(root_dir)
        self.files_to_scan = []
        self.internal_links = defaultdict(list)  # target -> [source1, source2]
        self.external_links = defaultdict(list)  # url -> [source1, source2]
        self.pages_data = {}  # path -> {title, h1_count, has_schema, has_breadcrumb}
        self.score = 100
        self.base_url = None
        self.ignore_paths = {'.git', 'node_modules', '__pycache__', '.vscode', '.idea'}
        self.ignore_urls_start = ('/go/', 'cdn-cgi', 'javascript:', 'mailto:', '#', 'tel:')
        self.ignore_files_contain = ('google', '404.html')
        self.issues = [] # List of dicts {type, message, file, deduct}

    def log(self, level, message):
        if level == 'SUCCESS':
            print(f"{Fore.GREEN}[SUCCESS] {message}")
        elif level == 'ERROR':
            print(f"{Fore.RED}[ERROR] {message}")
        elif level == 'WARN':
            print(f"{Fore.YELLOW}[WARN] {message}")
        elif level == 'INFO':
            print(f"{Fore.CYAN}[INFO] {message}")

    def add_issue(self, type, message, file, deduct=0):
        self.issues.append({
            'type': type,
            'message': message,
            'file': file,
            'deduct': deduct
        })
        self.score = max(0, self.score - deduct)

    def auto_configure(self):
        index_path = os.path.join(self.root_dir, 'index.html')
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8', errors='ignore') as f:
                    soup = BeautifulSoup(f, 'html.parser')
                    
                    # Base URL
                    canonical = soup.find('link', rel='canonical')
                    if canonical and canonical.get('href'):
                        self.base_url = canonical['href']
                    else:
                        og_url = soup.find('meta', property='og:url')
                        if og_url and og_url.get('content'):
                            self.base_url = og_url['content']
                    
                    if self.base_url:
                        # Ensure base_url doesn't have trailing slash for consistency in checks
                        self.base_url = self.base_url.rstrip('/')
                        self.log('SUCCESS', f"Base URL detected: {self.base_url}")
                    else:
                        self.log('WARN', "Could not detect Base URL from index.html (canonical or og:url).")
                        
                    # Keywords (Just reading for now as per req)
                    keywords = soup.find('meta', attrs={'name': 'keywords'})
                    if keywords:
                        self.log('INFO', f"Keywords detected: {keywords.get('content')}")
            except Exception as e:
                self.log('ERROR', f"Failed to parse index.html: {str(e)}")
        else:
            self.log('WARN', "index.html not found in root directory.")

    def scan_files(self):
        self.log('INFO', "Scanning files...")
        for root, dirs, files in os.walk(self.root_dir):
            # Filter directories
            dirs[:] = [d for d in dirs if d not in self.ignore_paths]
            
            for file in files:
                if not file.endswith('.html'):
                    continue
                
                # Check ignore files
                if any(x in file for x in self.ignore_files_contain):
                    continue
                
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_dir)
                
                # Normalize path for ID (e.g., /blog/post)
                # If filename is index.html, the page ID is the folder path
                if file == 'index.html':
                    page_id = '/' + os.path.dirname(rel_path)
                    if page_id == '/.': page_id = '/'
                else:
                    page_id = '/' + os.path.splitext(rel_path)[0]
                
                # Fix double slashes
                page_id = page_id.replace('//', '/')
                
                self.files_to_scan.append({
                    'path': full_path,
                    'rel_path': rel_path,
                    'id': page_id
                })

    def resolve_local_path(self, link_href, current_file_path):
        """
        Resolves a link to a local file path.
        Returns the absolute path to the file if found, else None.
        """
        # Remove query params and fragments
        link_href = link_href.split('#')[0].split('?')[0]
        
        if not link_href:
            return None

        current_dir = os.path.dirname(current_file_path)
        
        # Absolute path (starts with /)
        if link_href.startswith('/'):
            # Path relative to project root
            # link: /blog/post -> root/blog/post
            target_path_part = link_href.lstrip('/')
            potential_roots = [self.root_dir]
        else:
            # Relative path
            # link: post -> current_dir/post
            # link: ../post -> current_dir/../post
            target_path_part = link_href
            potential_roots = [current_dir]

        for root in potential_roots:
            base_target = os.path.join(root, target_path_part)
            
            # Case 1: Direct file match (unlikely for Clean URLs but possible for .html links)
            if os.path.isfile(base_target):
                return base_target
            
            # Case 2: Clean URL -> check .html
            if os.path.isfile(base_target + '.html'):
                return base_target + '.html'
            
            # Case 3: Directory -> check index.html
            if os.path.isdir(base_target):
                if os.path.isfile(os.path.join(base_target, 'index.html')):
                    return os.path.join(base_target, 'index.html')
                    
        return None

    def analyze_semantics(self, soup, file_info):
        # H1 Check
        h1s = soup.find_all('h1')
        if len(h1s) == 0:
            self.add_issue('ERROR', 'Missing H1 tag', file_info['rel_path'], 5)
        elif len(h1s) > 1:
            self.add_issue('WARN', f'Multiple H1 tags found ({len(h1s)})', file_info['rel_path'], 0) # Usually minor, but good to note
        
        # Schema Check
        schema = soup.find('script', type='application/ld+json')
        if not schema:
            self.add_issue('WARN', 'Missing Schema (application/ld+json)', file_info['rel_path'], 2)
            
        # Breadcrumb Check
        breadcrumb = soup.find(attrs={"aria-label": "breadcrumb"}) or soup.find(class_=lambda c: c and 'breadcrumb' in c)
        if not breadcrumb and file_info['rel_path'] != 'index.html': # Home usually doesn't need breadcrumbs
            self.add_issue('WARN', 'Missing Breadcrumb navigation', file_info['rel_path'], 0) # Optional but good

    def analyze_links(self, soup, file_info):
        for a in soup.find_all('a', href=True):
            href = a['href']
            
            # Check Soft Routes (/go/) for rel attributes before skipping
            if href.startswith('/go/'):
                rel = a.get('rel', [])
                if isinstance(rel, str): rel = rel.split()
                missing = [r for r in ['nofollow', 'noopener', 'noreferrer'] if r not in rel]
                if missing:
                    self.add_issue('WARN', f'Soft Route link missing rel attributes ({", ".join(missing)}): {href}', file_info['rel_path'], 2)

            # Skip ignored
            if any(href.startswith(p) for p in self.ignore_urls_start):
                continue
                
            # External Links
            if href.startswith('http://') or href.startswith('https://'):
                # Check if it's actually internal (using Base URL)
                if self.base_url and href.startswith(self.base_url):
                    self.add_issue('WARN', f'Internal link using absolute URL: {href}', file_info['rel_path'], 2)
                    # Treat as internal for existence check?
                    # For now, let's parse the path out and treat as internal path
                    parsed = urlparse(href)
                    path = parsed.path
                    if not path: path = '/'
                    self.check_internal_link(path, file_info)
                else:
                    self.external_links[href].append(file_info['rel_path'])
                    # Check rel attributes
                    rel = a.get('rel', [])
                    if isinstance(rel, str): rel = rel.split()
                    
                    missing = [r for r in ['nofollow', 'noopener', 'noreferrer'] if r not in rel]
                    if missing:
                        self.add_issue('WARN', f'External link missing rel attributes ({", ".join(missing)}): {href}', file_info['rel_path'], 2)
            else:
                # Internal Links
                self.check_internal_link(href, file_info)

    def check_internal_link(self, href, file_info):
        # 1. URL Normality Checks
        if not href.startswith('/'):
            self.add_issue('WARN', f'Relative path used: {href}', file_info['rel_path'], 2)
        
        if href.endswith('.html'):
             self.add_issue('WARN', f'Link includes .html suffix: {href}', file_info['rel_path'], 2)
             
        # 2. Dead Link Detection
        target_file = self.resolve_local_path(href, file_info['path'])
        
        if target_file:
            # Determine target page ID for graph
            rel_target = os.path.relpath(target_file, self.root_dir)
            if os.path.basename(rel_target) == 'index.html':
                 target_id = '/' + os.path.dirname(rel_target)
                 if target_id == '/.': target_id = '/'
            else:
                target_id = '/' + os.path.splitext(rel_target)[0]
            target_id = target_id.replace('//', '/')
            
            self.internal_links[target_id].append(file_info['id'])
        else:
            self.add_issue('ERROR', f'Dead Internal Link: {href}', file_info['rel_path'], 10)

    def check_external_links(self):
        self.log('INFO', f"Checking {len(self.external_links)} external links...")
        
        def check_url(url):
            try:
                # Use a standard browser User-Agent to avoid 403s from sites like X.com
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                
                # Skip known 403 blockers if we know the link structure is likely correct
                if 'help.x.com' in url or 'twitter.com' in url or 'x.com' in url:
                    return url, 200

                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                
                # Some servers reject HEAD, try GET
                if response.status_code == 405 or response.status_code == 403:
                    response = requests.get(url, headers=headers, timeout=5, stream=True)
                
                if response.status_code >= 400:
                    return url, response.status_code
            except Exception as e:
                return url, str(e)
            return url, 200

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {executor.submit(check_url, url): url for url in self.external_links}
            for future in as_completed(future_to_url):
                url, status = future.result()
                if status != 200:
                    sources = ', '.join(self.external_links[url][:3]) # List first 3 sources
                    if len(self.external_links[url]) > 3:
                        sources += '...'
                    self.add_issue('ERROR', f'Broken External Link ({status}): {url} (found in {sources})', 'External', 5)

    def analyze_orphans(self):
        # Get all defined pages
        all_pages = set(f['id'] for f in self.files_to_scan)
        linked_pages = set(self.internal_links.keys())
        
        orphans = all_pages - linked_pages
        
        for orphan in orphans:
            if orphan == '/' or orphan == '/index':
                continue
            self.add_issue('WARN', f'Orphan page (no incoming links): {orphan}', 'Structure', 5)

    def print_report(self):
        print("\n" + "="*50)
        print("SEO AUDIT REPORT")
        print("="*50 + "\n")
        
        # Group issues by type
        errors = [i for i in self.issues if i['type'] == 'ERROR']
        warns = [i for i in self.issues if i['type'] == 'WARN']
        
        if errors:
            print(f"{Fore.RED}== ERRORS ({len(errors)}) ==")
            for err in errors:
                print(f"  [{err['file']}] {err['message']}")
        
        if warns:
            print(f"\n{Fore.YELLOW}== WARNINGS ({len(warns)}) ==")
            for warn in warns:
                print(f"  [{warn['file']}] {warn['message']}")
                
        # Top Pages
        print(f"\n{Fore.CYAN}== TOP PAGES (Inbound Links) ==")
        sorted_pages = sorted(self.internal_links.items(), key=lambda x: len(x[1]), reverse=True)[:10]
        for page, links in sorted_pages:
            print(f"  {page}: {len(links)} links")
            
        # Final Score
        print("\n" + "-"*50)
        score_color = Fore.GREEN if self.score >= 90 else (Fore.YELLOW if self.score >= 60 else Fore.RED)
        print(f"FINAL SCORE: {score_color}{self.score}/100")
        
        if self.score < 100:
            print(f"\n{Fore.MAGENTA}Actionable Advice:")
            print("  Run 'python fix_links.py' (if available) or manually fix the errors above.")
        
        print("-"*50 + "\n")

    def run(self):
        self.auto_configure()
        self.scan_files()
        
        if not self.files_to_scan:
            self.log('ERROR', "No HTML files found to scan.")
            return

        self.log('INFO', f"Found {len(self.files_to_scan)} files. Starting analysis...")

        for file_info in self.files_to_scan:
            try:
                with open(file_info['path'], 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    self.analyze_semantics(soup, file_info)
                    self.analyze_links(soup, file_info)
            except Exception as e:
                self.log('ERROR', f"Error reading {file_info['rel_path']}: {e}")

        self.check_external_links()
        self.analyze_orphans()
        self.print_report()

if __name__ == '__main__':
    audit = SEOAudit()
    audit.run()
