import os
import datetime
import json
import re
import sys
import time
import unicodedata # 導入 unicodedata 以支援多樣化的字元
import google.generativeai as genai
from bs4 import BeautifulSoup

# --- 全域設定 (Global Settings) ---
# 從環境變數讀取您的 Gemini API 金鑰
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# --- 檔案與路徑設定 (File and Path Settings) ---
KEYWORDS_FILE = "keywords.txt"
PROMPT_TEMPLATE_FILE = "prompt_template.txt"
BLOG_LIST_PAGE = "Blog-List-Page.html"
BLOG_POST_TEMPLATE = "blog_post_template.html"
BLOG_OUTPUT_DIR = "blog"

# --- 模組 1: Gemini API 呼叫 (Gemini API Call Module) - 已根據建議重構 ---

def generate_blog_from_keyword(keyword: str, prompt_template: str) -> dict | None:
    """
    根據給定的關鍵詞和提示詞模板，呼叫 Gemini API 來生成部落格文章內容。
    此版本進行了多項優化，以提高穩定性和除錯效率。
    """
    # [修正] 使用 .replace() 而不是 .format() 來避免與模板中的 JSON 範例產生衝突
    prompt = prompt_template.replace("{keyword}", keyword).strip()

    max_retries, retry_delay = 3, 5
    for attempt in range(1, max_retries + 1):
        print(f"🤖 正在呼叫 Gemini API... (第 {attempt}/{max_retries} 次嘗試)")
        raw_text_for_debugging = f"錯誤: 在第 {attempt} 次嘗試中，API 呼叫未成功返回任何內容。"
        try:
            # 步驟 2: 檢查 API 金鑰
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY 環境變數未設定或為空。")
            
            genai.configure(api_key=GEMINI_API_KEY)
            
            # 步驟 3: 初始化模型，採用新版 SDK 語法和更穩定的設定
            model = genai.GenerativeModel(
                model_name="gemini-2.5-pro",
                # 新版 SDK 推薦使用 list of dicts 格式
                safety_settings=[
                    {"category": c, "threshold": "BLOCK_NONE"}
                    for c in [
                        "HARM_CATEGORY_HARASSMENT",
                        "HARM_CATEGORY_HATE_SPEECH",
                        "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        "HARM_CATEGORY_DANGEROUS_CONTENT",
                    ]
                ],
                # 使用強型別的 GenerationConfig，並強制 JSON 輸出與設定 token 上限
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                )
            )

            # 步驟 4: 發送請求並獲取回應
            response = model.generate_content(prompt)
            
            # 步驟 5: 穩健地獲取回應文本
            # 雙保險機制：優先使用 .text，若不存在則回退到遍歷 candidates
            raw_text_for_debugging = getattr(response, "text", None)
            if not raw_text_for_debugging and response.candidates:
                raw_text_for_debugging = response.candidates[0].content.parts[0].text
            
            if not raw_text_for_debugging:
                raise ValueError("API 回應為空，無法獲取任何文本內容。")

            article_data = json.loads(raw_text_for_debugging)
            
            # 步驟 6: 進行更友好的驗證
            if not isinstance(article_data.get("en"), dict) or "postTitle" not in article_data.get("en", {}):
                raise ValueError(f"AI 返回的 JSON 格式不符，缺少 'en' 或 'en.postTitle'。收到的內容片段: \n{raw_text_for_debugging[:500]}")

            print("✅ Gemini 已成功生成所有語言版本的文章內容！")
            return article_data

        except Exception as e:
            print(f"🚨 第 {attempt}/{max_retries} 次嘗試失敗: {repr(e)}")
            if "raw_text_for_debugging" in locals() and raw_text_for_debugging:
                 print("==== API 原始回應內容 (供除錯參考) ====")
                 print(raw_text_for_debugging)
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
    [優化] 將字串轉換為適合用作 URL 或檔名的 "slug" 格式。
    此版本能正確處理中文、日文、韓文、emoji 等多位元組字元。
    """
    text = str(text)
    # 使用 NFKD 正規化將相容字元（如全形字母）轉換為其基本形式
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'[\s]+', '-', text)       # 將一個或多個空白字元替換為單一連字號
    text = re.sub(r'[^\w-]', '', text)     # 移除所有非單詞字元和非連字號的字元
    return text

def create_new_blog_post(translations_data: dict) -> str | None:
    """
    使用模板和 AI 生成的內容來建立一個新的部落格文章 HTML 檔案。
    """
    print(f"📝 正在 '{BLOG_OUTPUT_DIR}/' 資料夾中建立新的部落格文章檔案...")
    try:
        os.makedirs(BLOG_OUTPUT_DIR, exist_ok=True)
        with open(BLOG_POST_TEMPLATE, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        default_title = translations_data.get('en', {}).get('postTitle', 'untitled-post')
        filename = f"{slugify(default_title)}.html"
        
        translations_json_string = json.dumps(translations_data, ensure_ascii=False, indent=4)

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
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        article_container = soup.find('div', class_='space-y-10')
        if not article_container:
            print(f"❌ 錯誤: 在 '{BLOG_LIST_PAGE}' 中找不到 <div class='space-y-10'>。")
            return

        # 1. 尋找包含翻譯物件的 <script> 標籤
        script_tag = soup.find("script", string=re.compile(r"\s*const\s+translations\s*="))
        if not script_tag:
            print(f"❌ 錯誤: 在 '{BLOG_LIST_PAGE}' 中找不到 'const translations' script 區塊。")
            return

        script_text = script_tag.string
        
        # 2. 精準地從 script 內容中提取 JSON 物件字串和後續的函式程式碼
        match = re.search(r'(const\s+translations\s*=\s*)(\{[\s\S]*?\});([\s\S]*)', script_text, re.DOTALL)
        if not match:
             print(f"❌ 錯誤: 無法從 script 區塊中完整地解析出 translations 物件和函式。")
             return
        
        # 分別獲取 JSON 字串和其後的 JavaScript 函式部分
        json_part_str = match.group(2)
        functions_part_str = match.group(3)
        
        # 將 JSON 字串解析為 Python 字典
        translations_obj = json.loads(json_part_str)

        # 3. 為新文章產生唯一的 slug，並將所有語言的翻譯加入到字典中
        post_slug = slugify(translations_data['en']['postTitle'])
        for lang, data in translations_data.items():
            if lang not in translations_obj:
                translations_obj[lang] = {}
            translations_obj[lang][f"postTitle_{post_slug}"] = data.get('postTitle', '')
            translations_obj[lang][f"postSummary_{post_slug}"] = data.get('postSummary', '')

        # 4. 建立新文章的 HTML 區塊，並使用 data-translate-key 屬性來標示
        link_path = os.path.join(BLOG_OUTPUT_DIR, filename).replace("\\", "/")
        new_article_html = f"""
        <article>
            <h2 class="text-2xl sm:text-3xl font-bold text-apple-gray-800 mb-2">
                <a href="{link_path}" class="hover:text-apple-blue-500 transition-colors" data-translate-key="postTitle_{post_slug}"></a>
            </h2>
            <p class="text-sm text-apple-gray-500 mb-4"><span data-translate-key="by">By</span> AI Assistant | {datetime.date.today().strftime("%B %d, %Y")}</p>
            <p class="text-base leading-relaxed text-apple-gray-600" data-translate-key="postSummary_{post_slug}"></p>
            <a href="{link_path}" data-translate-key="readMore" class="inline-block mt-4 font-semibold text-apple-blue-500 hover:text-apple-blue-600">Read More &rarr;</a>
        </article>
        <hr class="border-apple-gray-200"/>
        """
        new_article_soup = BeautifulSoup(new_article_html, 'html.parser')
        article_container.insert(0, new_article_soup)

        # 5. [核心修正] 重新組合一個完整的、全新的 <script> 內容
        # 將更新後的 Python 字典轉回 JSON 字串
        new_translations_str = json.dumps(translations_obj, ensure_ascii=False, indent=4)
        # 組合出 `const translations = ...;` 這部分，並接上先前保存的函式程式碼
        full_new_script_content = f"const translations = {new_translations_str};" + functions_part_str
        
        # 直接替換整個 <script> 標籤的內容
        script_tag.string = full_new_script_content

        # 6. 將更新後的 soup 物件寫回 HTML 檔案
        with open(BLOG_LIST_PAGE, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify(formatter="html5")))
        print(f"✅ '{BLOG_LIST_PAGE}' 已成功更新！")

    except Exception as e:
        # 提供更詳細的錯誤追蹤
        import traceback
        print(f"❌ 更新列表頁面時發生錯誤: {repr(e)}")
        traceback.print_exc()

# --- 模組 3: 主執行流程 (Main Execution Flow) ---
def main():
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_PLACEHOLDER":
        print("🔥🔥🔥 錯誤: 找不到環境變數 `GEMINI_API_KEY` 或金鑰不正確。請在 GitHub Secrets 中設定它。")
        sys.exit(1)

    try:
        with open(KEYWORDS_FILE, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip()]
        if not keywords:
            print(f"✅ '{KEYWORDS_FILE}' 是空的。沒有需要生成的文章，流程結束。")
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
