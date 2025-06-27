import os
import datetime
import json
import re
import sys
import time
import google.generativeai as genai
from bs4 import BeautifulSoup

# --- 設定 ---
# 從環境變數讀取 API 金鑰
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 檔案與路徑設定 ---
KEYWORDS_FILE = "keywords.txt"
PROMPT_TEMPLATE_FILE = "prompt_template.txt"
BLOG_LIST_PAGE = "Blog-List-Page.html"
BLOG_POST_TEMPLATE = "blog_post_template.html"
BLOG_OUTPUT_DIR = "blog"

# --- 1. Gemini API 呼叫模組 (已根據您的建議修復並強化) ---

def _strip_keys(obj):
    """递归去掉 dict key 左右空白，解决 ' en' / '\nen ' 这类情况。"""
    if isinstance(obj, dict):
        return {k.strip(): _strip_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_keys(i) for i in obj]
    return obj

def _extract_json(text: str) -> str | None:
    """
    尝试在大段文本里抓第一段或唯一一段 JSON。
    允许 Gemini 在两边包围 markdown 文字。
    """
    # 使用 re.DOTALL (等同于 re.S) 来匹配包括换行符在内的任意字符
    match = re.search(r'\{[\s\S]*\}', text)
    return match.group(0) if match else None

def generate_blog_from_keyword(keyword: str, prompt_template: str) -> dict | None:
    max_retries, retry_delay = 3, 5
    for attempt in range(1, max_retries + 1):
        print(f"🤖 正在呼叫 Gemini API... (第 {attempt}/{max_retries} 次嘗試)")
        raw_text = f"Error: No valid response text was captured from the API on attempt {attempt}."
        try:
            # 確保 GEMINI_API_KEY 已載入
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY 環境變數未設定或為空。")
            
            genai.configure(api_key=GEMINI_API_KEY)
            
            # (修正) 模型名稱修正為有效的 'gemini-1.5-flash'
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash", 
                safety_settings={c: "BLOCK_NONE" for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )}
            )

            prompt = prompt_template.format(keyword=keyword)
            response = model.generate_content(prompt)

            # 1. 先拿到字符串（兼容不同 SDK 版本）
            raw_text = getattr(response, "text", None)
            if raw_text is None and response.candidates:
                # fallback, 新版 SDK: response.candidates[0].content.parts[0].text
                raw_text = response.candidates[0].content.parts[0].text

            if not raw_text:
                 raise ValueError("從 API 回應中無法提取任何文本內容。")

            # 2. 把真正的 JSON 摳出來
            json_str = _extract_json(raw_text)
            if not json_str:
                raise ValueError("API 回傳未檢測到 JSON 片段")

            # 3. 解析 + 清洗 key
            article_data = _strip_keys(json.loads(json_str))

            # 4. 基本結構校驗
            if "en" not in article_data or "postTitle" not in article_data.get("en", {}):
                raise KeyError("JSON 缺少 'en.postTitle'，請檢查 prompt 或 API 回傳")

            print("✅ Gemini 已成功生成所有語言版本的文章內容！")
            return article_data

        except Exception as e:
            print(f"🚨 嘗試 {attempt} 失敗：{repr(e)}")
            print("==== API 原始回應內容 (若有) ====")
            print(raw_text) # 打印捕獲到的原始文本以供調試
            print("==============================")
            if attempt < max_retries:
                print(f"將在 {retry_delay} 秒後重試…\n")
                time.sleep(retry_delay)
            else:
                print("❌ 已達最大重試次數，宣告失敗。")
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
        post_content = post_content.replace("{{POST_FILENAME}}", filename)
        post_content = post_content.replace("{{POST_DATE}}", datetime.date.today().strftime("%B %d, %Y"))
        post_content = post_content.replace("Post Title Placeholder", default_title)
        default_summary = translations_data.get('en', {}).get('postSummary', '')
        post_content = post_content.replace('<meta name="description" content="">', f'<meta name="description" content="{default_summary}">')
        
        output_path = os.path.join(BLOG_OUTPUT_DIR, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(post_content)
        
        print(f"✅ 新文章已儲存為: {output_path}")
        return filename
    except Exception as e:
        print(f"❌ 建立文章檔案時發生錯誤: {repr(e)}")
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
        print(f"❌ 更新列表頁面時發生錯誤: {repr(e)}")

# --- 3. 主執行流程 ---
def main():
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_PLACEHOLDER":
        print("🔥🔥🔥 錯誤: 找不到環境變數 `GEMINI_API_KEY` 或金鑰不正確。請在 GitHub Secrets 中設定它。")
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
            print(f"✅ 已成功處理并從 '{KEYWORDS_FILE}' 中移除關鍵詞 '{keyword_to_process}'。")
            print(f"\n🎉 恭喜！一個新的部落格文章已生成並更新！")
        else:
            print("❗ 因建立檔案失敗，流程已終止。關鍵詞未從佇列中移除。")
    else:
        print("❗ 因內容生成失敗，流程已終止。關鍵詞未從佇列中移除。")

if __name__ == "__main__":
    main()
