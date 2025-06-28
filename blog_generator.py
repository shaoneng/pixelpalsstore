import os
import datetime
import json
import re
import sys
import time
import google.generativeai as genai
from bs4 import BeautifulSoup

# --- 全域設定 (Global Settings) ---
# 從環境變數讀取您的 Gemini API 金鑰
# 這是為了安全性，避免將金鑰直接寫在程式碼中
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 檔案與路徑設定 (File and Path Settings) ---
KEYWORDS_FILE = "keywords.txt"
PROMPT_TEMPLATE_FILE = "prompt_template.txt"
BLOG_LIST_PAGE = "Blog-List-Page.html"
BLOG_POST_TEMPLATE = "blog_post_template.html"
BLOG_OUTPUT_DIR = "blog"

# --- 模組 1: Gemini API 呼叫 (Gemini API Call Module) ---

def _strip_keys(obj):
    """
    遞迴移除字典中所有鍵 (key) 的前後多餘空白。
    這是一個輔助函式，用來清理 AI 可能回傳的不標準 JSON 格式。
    """
    if isinstance(obj, dict):
        return {k.strip(): _strip_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_keys(i) for i in obj]
    return obj

def _extract_json(text: str) -> str | None:
    """
    從一段可能包含前後文的純文字中，提取出 JSON 字串。
    AI 的回覆有時會在 JSON 結構外層包上 markdown 標籤 (```json ... ```)，此函式可應對此情況。
    """
    # re.DOTALL (或 re.S) 讓 '.' 可以匹配包含換行符在內的任何字元
    match = re.search(r'\{[\s\S]*\}', text)
    return match.group(0) if match else None

def generate_blog_from_keyword(keyword: str, prompt_template: str) -> dict | None:
    """
    根據給定的關鍵詞和提示詞模板，呼叫 Gemini API 來生成部落格文章內容。

    Args:
        keyword: 要生成文章的主題關鍵詞。
        prompt_template: 包含指示和格式的提示詞模板。

    Returns:
        一個包含所有語言翻譯的字典，如果失敗則回傳 None。
    """
    max_retries, retry_delay = 3, 5  # 設定重試次數和延遲時間
    for attempt in range(1, max_retries + 1):
        print(f"🤖 正在呼叫 Gemini API... (第 {attempt}/{max_retries} 次嘗試)")
        raw_text = f"錯誤: 在第 {attempt} 次嘗試中，未能從 API 捕獲有效的回應文本。"
        try:
            # 步驟 1: 檢查並設定 API 金鑰
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY 環境變數未設定或為空。")
            
            genai.configure(api_key=GEMINI_API_KEY)
            
            # 步驟 2: 初始化模型
            # 使用 'gemini-2.5-flash' 模型，並關閉所有安全過濾以確保內容能順利生成
            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash", 
                safety_settings={c: "BLOCK_NONE" for c in (
                    "HARM_CATEGORY_HARASSMENT",
                    "HARM_CATEGORY_HATE_SPEECH",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "HARM_CATEGORY_DANGEROUS_CONTENT",
                )}
            )

            # 步驟 3: 生成並發送提示
            prompt = prompt_template.format(keyword=keyword)
            response = model.generate_content(prompt)

            # 步驟 4: 從回應中提取純文字
            raw_text = getattr(response, "text", None)
            if raw_text is None and response.candidates:
                # 兼容新版 SDK 的備用方案
                raw_text = response.candidates[0].content.parts[0].text

            if not raw_text:
                 raise ValueError("從 API 回應中無法提取任何文本內容。")

            # 步驟 5: 提取並解析 JSON
            json_str = _extract_json(raw_text)
            if not json_str:
                raise ValueError("API 回傳的內容中未檢測到有效的 JSON 結構。")

            article_data = _strip_keys(json.loads(json_str))

            # 步驟 6: 驗證 JSON 的基本結構
            if "en" not in article_data or "postTitle" not in article_data.get("en", {}):
                raise KeyError("JSON 缺少 'en.postTitle' 鍵，請檢查 prompt 或 API 回傳內容。")

            print("✅ Gemini 已成功生成所有語言版本的文章內容！")
            return article_data

        except Exception as e:
            print(f"🚨 嘗試 {attempt} 失敗：{repr(e)}")
            print("==== API 原始回應內容 (供除錯參考) ====")
            print(raw_text)
            print("====================================")
            if attempt < max_retries:
                print(f"將在 {retry_delay} 秒後重試…\n")
                time.sleep(retry_delay)
            else:
                print("❌ 已達最大重試次數，宣告失敗。")
                return None

# --- 模組 2: 檔案處理 (File Handling Module) ---

def slugify(text: str) -> str:
    """
    將字串轉換為適合用作 URL 或檔名的 "slug" 格式。
    例如："Hello World!" -> "hello-world"
    """
    text = text.lower()
    text = re.sub(r'\s+', '-', text)      # 將空白替換為連字號
    text = re.sub(r'[^\w-]', '', text)    # 移除所有非單詞、非連字號的字元
    return text

def create_new_blog_post(translations_data: dict) -> str | None:
    """
    使用模板和 AI 生成的內容來建立一個新的部落格文章 HTML 檔案。

    Args:
        translations_data: 包含所有翻譯內容的字典。

    Returns:
        成功建立的檔案名稱，如果失敗則回傳 None。
    """
    print(f"📝 正在 '{BLOG_OUTPUT_DIR}/' 資料夾中建立新的部落格文章檔案...")
    try:
        os.makedirs(BLOG_OUTPUT_DIR, exist_ok=True) # 確保輸出目錄存在
        with open(BLOG_POST_TEMPLATE, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 使用英文標題來生成檔名
        default_title = translations_data.get('en', {}).get('postTitle', 'untitled-post')
        filename = f"{slugify(default_title)}.html"
        
        # 將翻譯字典轉換為格式化的 JSON 字串，以便嵌入 HTML
        translations_json_string = json.dumps(translations_data, ensure_ascii=False, indent=4)

        # 替換模板中的佔位符
        post_content = template_content.replace("{{TRANSLATIONS_JSON}}", translations_json_string)
        post_content = post_content.replace("{{POST_FILENAME}}", filename)
        post_content = post_content.replace("{{POST_DATE}}", datetime.date.today().strftime("%B %d, %Y"))
        post_content = post_content.replace("Post Title Placeholder", default_title)
        
        # 替換 meta description
        default_summary = translations_data.get('en', {}).get('postSummary', '')
        post_content = post_content.replace('<meta name="description" content="">', f'<meta name="description" content="{default_summary}">')
        
        # 寫入新檔案
        output_path = os.path.join(BLOG_OUTPUT_DIR, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(post_content)
        
        print(f"✅ 新文章已儲存為: {output_path}")
        return filename
    except Exception as e:
        print(f"❌ 建立文章檔案時發生錯誤: {repr(e)}")
        return None

def update_blog_list(translations_data: dict, filename: str):
    """
    在部落格列表頁面 (Blog-List-Page.html) 的最頂部插入新文章的連結和摘要。

    Args:
        translations_data: 包含文章標題和摘要的字典。
        filename: 新文章的檔名。
    """
    print(f"🔄 正在更新 '{BLOG_LIST_PAGE}'...")
    try:
        with open(BLOG_LIST_PAGE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # 找到要插入新文章的容器 div
        article_container = soup.find('div', class_='space-y-10')
        if not article_container:
            print(f"❌ 錯誤: 在 '{BLOG_LIST_PAGE}' 中找不到 <div class='space-y-10'>。")
            return
            
        # 組合新文章的 HTML 結構
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
        
        # 使用 BeautifulSoup 解析新 HTML 並插入到列表的最前面
        new_article_soup = BeautifulSoup(new_article_html, 'html.parser')
        article_container.insert(0, new_article_soup)

        # 寫回更新後的 HTML 檔案
        with open(BLOG_LIST_PAGE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        print(f"✅ '{BLOG_LIST_PAGE}' 已成功更新！")
    except Exception as e:
        print(f"❌ 更新列表頁面時發生錯誤: {repr(e)}")

# --- 模組 3: 主執行流程 (Main Execution Flow) ---
def main():
    # 檢查 API 金鑰是否存在
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_PLACEHOLDER":
        print("🔥🔥 錯誤: 找不到環境變數 `GEMINI_API_KEY` 或金鑰不正確。請在 GitHub Secrets 中設定它。")
        sys.exit(1)

    # 讀取關鍵詞檔案
    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip()]
        if not keywords:
            print(f"✅ '{KEYWORDS_FILE}' 是空的。沒有需要生成的文章，流程結束。")
            return
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到關鍵詞檔案 '{KEYWORDS_FILE}'。")
        sys.exit(1)

    # 讀取提示詞模板檔案
    try:
        with open(PROMPT_TEMPLATE_FILE, 'r', encoding='utf-8') as f:
            prompt_template = f.read()
    except FileNotFoundError:
        print(f"❌ 錯誤: 找不到 Prompt 模板檔案 '{PROMPT_TEMPLATE_FILE}'。")
        sys.exit(1)
        
    # 處理佇列中的第一個關鍵詞
    keyword_to_process = keywords[0]
    print(f"--- 開始處理關鍵詞: '{keyword_to_process}' ---")
    
    # 呼叫 AI 生成內容
    generated_translations = generate_blog_from_keyword(keyword_to_process, prompt_template)
    
    if generated_translations:
        # 如果內容生成成功，則建立文章檔案
        new_filename = create_new_blog_post(generated_translations)
        if new_filename:
            # 如果檔案建立成功，則更新部落格列表
            update_blog_list(generated_translations, new_filename)
            
            # 從關鍵詞列表中移除已處理的關鍵詞
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

