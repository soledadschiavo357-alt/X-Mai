import csv
import os
import sys

# Configuration Files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BLACKLIST_FILE = os.path.join(BASE_DIR, 'blacklist.txt')
INPUT_FILE = os.path.join(BASE_DIR, 'raw_keywords.csv')
OUTPUT_FILE = os.path.join(BASE_DIR, 'final_tasks.csv')

# Intent Classification Dictionary
INTENT_RULES = {
    'Transactional': ['price', 'buy', 'cost', 'cheap', 'discount', 'deal', 'shop', 'store', '价格', '购买', '合租', '费用', '便宜', '优惠'],
    'Download': ['download', 'apk', 'install', 'setup', 'get', 'free', 'torrent', 'magnet', '下载', '安装', '获取', '免费'],
    'Issues': ['error', 'not working', 'fail', 'bug', 'fix', 'problem', 'issue', 'crash', 'slow', 'down', '报错', '失败', '崩溃', '问题', '慢'],
    'Guide': ['how to', 'tutorial', 'guide', 'steps', 'learn', 'course', 'example', 'tips', '教程', '怎么', '指南', '学习', '示例', '技巧', '方法']
}

def load_blacklist():
    """Reads blacklist words from blacklist.txt"""
    if not os.path.exists(BLACKLIST_FILE):
        print(f"Error: Configuration file '{BLACKLIST_FILE}' not found.")
        print("Please create blacklist.txt and add one filter word per line.")
        # Return empty list so process can continue if desired, or exit. 
        # User said "Script must read this file... do not hardcode". 
        # I'll return empty but print error.
        return []
    
    with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
        blacklist = [line.strip().lower() for line in f if line.strip()]
    
    return blacklist

def classify_intent(keyword):
    """Classifies keyword based on generic rules"""
    keyword_lower = keyword.lower()
    intents = []
    
    for intent, terms in INTENT_RULES.items():
        for term in terms:
            if term in keyword_lower:
                intents.append(intent)
                break # One match per category is enough
    
    if not intents:
        return 'Informational' # Default fallback
    
    return ', '.join(intents)

def is_blacklisted(keyword, blacklist):
    """Checks if keyword contains any blacklisted term"""
    keyword_lower = keyword.lower()
    for term in blacklist:
        if term in keyword_lower:
            return True
    return False

def main():
    print("Starting Cleaner...")
    
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file '{INPUT_FILE}' not found.")
        print("Please run miner.py first to generate raw keywords.")
        return

    blacklist = load_blacklist()
    if not blacklist and os.path.exists(BLACKLIST_FILE):
        print("Warning: Blacklist is empty.")

    processed_count = 0
    filtered_count = 0
    
    final_tasks = []

    try:
        with open(INPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            # Check if CSV has data
            if not reader.fieldnames:
                print("Error: Input CSV is empty or invalid.")
                return

            for row in reader:
                keyword = row.get('Keyword', '').strip()
                if not keyword:
                    continue
                
                processed_count += 1
                
                if is_blacklisted(keyword, blacklist):
                    filtered_count += 1
                    continue
                
                intent = classify_intent(keyword)
                
                # Create new row with classification
                new_row = {
                    'Keyword': keyword,
                    'Intent': intent,
                    'Source': row.get('Source', 'Unknown'),
                    'Seed': row.get('Seed', '')
                }
                final_tasks.append(new_row)
                
    except Exception as e:
        print(f"Error reading {INPUT_FILE}: {e}")
        return

    # Write results
    try:
        if final_tasks:
            fieldnames = ['Keyword', 'Intent', 'Source', 'Seed']
            with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(final_tasks)
            
            print(f"Processing complete.")
            print(f"Total processed: {processed_count}")
            print(f"Filtered (Blacklist): {filtered_count}")
            print(f"Saved to {OUTPUT_FILE}: {len(final_tasks)}")
        else:
            print("No valid keywords found after filtering.")
            
    except Exception as e:
        print(f"Error saving to {OUTPUT_FILE}: {e}")

if __name__ == "__main__":
    main()
