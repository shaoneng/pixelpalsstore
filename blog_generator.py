import os
import datetime
import json
import re
import sys
import google.generativeai as genai
from bs4 import BeautifulSoup

# --- 設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# --- 檔案與路徑設定 ---
KEYWORDS_FILE = "keywords.txt"
PROMPT_TEMPLATE_FILE = "prompt_template.txt"
BLOG_LIST_PAGE = "Blog-List-Page.html"
BLOG_POST_TEMPLATE = "blog_post_template.html"
BLOG_OUTPUT_DIR = "blog"

# --- 1. Gemini API 呼叫模組 (最終修復版) ---

def generate_blog_from_keyword(keyword: str, prompt_template: str) -> dict:
    """
    (最終修復) 使用正規表示式強力提取 JSON，並增加詳細的錯誤日誌。
    """
    print(f"🤖 正在使用關鍵詞 '{keyword}' 呼叫 Gemini API...")
    raw_response_text = "" # 用於在出錯時顯示原始回傳
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = prompt_template.format(keyword=keyword)
        
        response = model.generate_content(prompt)
        raw_response_text = response.text

        # --- 全新的、基於正規表示式的 JSON 提取邏輯 ---
        # 這個正規表示式會尋找一個以 '{' 開始，以 '}' 結束，且中間包含任何字元（包括換行）的最長區塊。
        json_match = re.search(r'\{.*\}', raw_response_text, re.DOTALL)
        
        if not json_match:
            print("❌ Gemini API 的回應中找不到有效的 JSON 區塊。")
            print("==== API 原始回應內容 ====")
            print(raw_response_text)
            print("==========================")
            return None

        json_string = json_match.group(0)
        article_data = json.loads(json_string)
        # --- 提取邏輯結束 ---

        print("✅ Gemini 已成功生成所有語言版本的文章內容！")
        return article_data

    except json.JSONDecodeError as e:
        print(f"❌ 解析 JSON 時發生嚴重錯誤: {e}")
        print("提取出的 JSON 字串似乎已損毀。")
        print("==== 提取出的字串 ====")
        print(json_string)
        print("======================")
        return None
    except Exception as e:
        print(f"❌ 呼叫 Gemini API 或處理過程中發生未知錯誤: {e}")
        if raw_response_text:
            print("==== API 原始回應內容 (可能導致錯誤) ====")
            print(raw_response_text)
            print("==========================================")
        return None


# --- 2. 檔案處理模組 (無變動) ---

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^\w-]', '', text)
    return text

def create_new_blog_post(translations_data: dict):
    print(f"📝 正在 '{BLOG_OUTPUT_DIR}/' 資料夾中建立新的多語言部落格文章檔案...")
    try:
        os.makedirs(BLOG_OUTPUT_DIR, exist_ok=True)
        with open(BLOG_POST_TEMPLATE, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        default_title = translations_data.get('en', {}).get('postTitle', 'untitled')
        filename = f"{slugify(default_title)}.html"
        translations_json_string = json.dumps(translations_data, ensure_ascii=False, indent=8)

        post_content = template_content.replace("{{TRANSLATIONS_JSON}}", translations_json_string)
        post_content = template_content.replace("{{POST_FILENAME}}", filename)
        post_content = template_content.replace("{{POST_DATE}}", datetime.date.today().strftime("%B %d, %Y"))
        post_content = template_content.replace("Post Title Placeholder", default_title)
        default_summary = translations_data.get('en', {}).get('postSummary', '')
        post_content = post_content.replace('<meta name="description" content="">', f'<meta name="description" content="{default_summary}">')
        
        output_path = os.path.join(BLOG_OUTPUT_DIR, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(post_content)
        
        print(f"✅ 新文章已儲存為: {output_path}")
        return filename
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到模板檔案 '{BLOG_POST_TEMPLATE}'。")
        return None
    except Exception as e:
        print(f"❌ 建立文章檔案時發生錯誤: {e}")
        return None

def update_blog_list(translations_data: dict, filename: str):
    print(f"🔄 正在更新 '{BLOG_LIST_PAGE}'...")
    try:
        with open(BLOG_LIST_PAGE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        article_container = soup.find('div', class_='space-y-10')
        if not article_container:
            print(f"❌ 錯誤: 在 '{BLOG_LIST_PAGE}' 中找不到 <div class='space-y-10'>。")
            return
            
        link_path = os.path.join(BLOG_OUTPUT_DIR, filename).replace("\\", "/")
        title = translations_data.get('en', {}).get('postTitle', 'Untitled')
        summary = translations_data.get('en', {}).get('postSummary', 'No summary available.')
        
        new_article_html = f"""
        <article>
            <h2 class="text-2xl sm:text-3xl font-bold text-apple-gray-800 mb-2">
                <a href="{link_path}" class="hover:text-apple-blue-500 transition-colors">{title}</a>
            </h2>
            <p class="text-sm text-apple-gray-500 mb-4">By AI Assistant | {datetime.date.today().strftime("%B %d, %Y")}</p>
            <p class="text-base leading-relaxed text-apple-gray-600">{summary}</p>
            <a href="{link_path}" class="inline-block mt-4 font-semibold text-apple-blue-500 hover:text-apple-blue-600">Read More &rarr;</a>
        </article>
        <hr class="border-apple-gray-200">
        """
        
        new_article_soup = BeautifulSoup(new_article_html, 'html.parser')
        article_container.insert(0, new_article_soup)

        with open(BLOG_LIST_PAGE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        print(f"✅ '{BLOG_LIST_PAGE}' 已成功更新！")
    except Exception as e:
        print(f"❌ 更新列表頁面時發生錯誤: {e}")


# --- 3. 主執行流程 ---
def main():
    if not GEMINI_API_KEY:
        print("🔥🔥🔥 錯誤: 找不到環境變數 `GEMINI_API_KEY`。請在 GitHub Secrets 中設定它。")
        sys.exit(1)

    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip()]
        if not keywords:
            print(f"✅ '{KEYWORDS_FILE}' 是空的。沒有需要生成的文章。")
            return
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到關鍵詞檔案 '{KEYWORDS_FILE}'。")
        sys.exit(1)

    try:
        with open(PROMPT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到 Prompt 模板檔案 '{PROMPT_TEMPLATE_FILE}'。")
        sys.exit(1)
        
    keyword_to_process = keywords[0]
    print(f"--- 開始處理關鍵詞: '{keyword_to_process}' ---")
    
    generated_translations = generate_blog_from_keyword(keyword_to_process, prompt_template)
    
    if generated_translations:
        new_filename = create_new_blog_post(generated_translations)
        if new_filename:
            update_blog_list(generated_translations, new_filename)
            remaining_keywords = keywords[1:]
            with open(KEYWORDS_FILE, 'w', encoding='utf-8') as f:
                for kw in remaining_keywords:
                    f.write(kw + '\n')
            print(f"✅ 已成功處理並從 '{KEYWORDS_FILE}' 中移除關鍵詞 '{keyword_to_process}'。")
            print(f"\n🎉 恭喜！一個新的部落格文章已生成並更新！")
        else:
            print("❗ 因建立檔案失敗，流程已終止。關鍵詞未從佇列中移除。")
    else:
        print("❗ 因內容生成失敗，流程已終止。關鍵詞未從佇列中移除。")

if __name__ == "__main__":
    main()
