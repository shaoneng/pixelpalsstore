import os
import datetime
import json
import re
import google.generativeai as genai
from bs4 import BeautifulSoup

# --- 設定 ---
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"

# --- 檔案與路徑設定 ---
BLOG_LIST_PAGE = "Blog-List-Page.html"
BLOG_POST_TEMPLATE = "blog_post_template.html"
BLOG_OUTPUT_DIR = "blog"

# --- 1. Gemini API 呼叫模組 (更新) ---

def generate_blog_from_keyword(keyword: str) -> dict:
    """
    (更新) 使用指定的關鍵詞呼叫 Gemini API，生成包含多語言翻譯的部落格文章。
    """
    print(f"🤖 正在使用關鍵詞 '{keyword}' 呼叫 Gemini API (請求多語言版本)...")
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # (更新) 全新的 Prompt，要求巢狀 JSON 格式的多語言輸出
        prompt = f"""
        您是一位專業的健康與健身領域的內容創作者與翻譯專家，擅長撰寫符合 SEO 策略的部落格文章。
        請根據以下關鍵詞生成一篇引人入勝且資訊豐富的部落格文章，並將其翻譯成所有指定語言。

        主要關鍵詞: "{keyword}"

        請嚴格按照以下巢狀 JSON 格式輸出，不要添加任何 JSON 格式以外的文字或說明。
        所有欄位都必須有內容，特別是 `postContent` 必須是完整的 HTML 格式文章。

        {{
          "en": {{
            "navBlog": "Blog",
            "by": "By",
            "backToBlog": "&larr; Back to Blog",
            "footer": "&copy; 2025 Your Website Name. All Rights Reserved.",
            "postTitle": "An engaging, keyword-rich title in English",
            "postSummary": "A brief summary of about 150 characters in English, for SEO and list pages.",
            "postContent": "The full article content in HTML format. Use <h3> for subheadings and <p> for paragraphs. Should be detailed, well-structured, and naturally incorporate the keyword."
          }},
          "zh-TW": {{
            "navBlog": "部落格",
            "by": "作者：",
            "backToBlog": "&larr; 返回部落格",
            "footer": "&copy; 2025 您的網站名稱. 版權所有.",
            "postTitle": "一個吸引人且包含關鍵詞的繁體中文標題",
            "postSummary": "一段約 150 字元的繁體中文簡短摘要。",
            "postContent": "完整的繁體中文文章內容，HTML 格式。"
          }},
          "es": {{
            "navBlog": "Blog",
            "by": "Por",
            "backToBlog": "&larr; Volver al Blog",
            "footer": "&copy; 2025 Su Nombre de Sitio Web. Todos los derechos reservados.",
            "postTitle": "Un título atractivo y rico en palabras clave en español",
            "postSummary": "Un breve resumen de unos 150 caracteres en español.",
            "postContent": "El contenido completo del artículo en español, en formato HTML."
          }},
          "fr": {{
            "navBlog": "Blog",
            "by": "Par",
            "backToBlog": "&larr; Retour au Blog",
            "footer": "&copy; 2025 Votre Nom de Site Web. Tous droits réservés.",
            "postTitle": "Un titre engageant et riche en mots-clés en français",
            "postSummary": "Un bref résumé d'environ 150 caractères en français.",
            "postContent": "Le contenu complet de l'article en français, au format HTML."
          }},
          "ru": {{
            "navBlog": "Блог",
            "by": "Автор:",
            "backToBlog": "&larr; Назад в блог",
            "footer": "&copy; 2025 Название Вашего Сайта. Все права защищены.",
            "postTitle": "Привлекательный, насыщенный ключевыми словами заголовок на русском языке",
            "postSummary": "Краткое резюме около 150 символов на русском языке.",
            "postContent": "Полное содержание статьи на русском языке в формате HTML."
          }}
        }}
        """

        response = model.generate_content(prompt)
        cleaned_response = re.sub(r'```json\s*|\s*```', '', response.text.strip())
        article_data = json.loads(cleaned_response)
        print("✅ Gemini 已成功生成所有語言版本的文章內容！")
        return article_data

    except Exception as e:
        print(f"❌ 呼叫 Gemini API 時發生錯誤: {e}")
        return None

# --- 2. 檔案處理模組 (更新) ---

def slugify(text: str) -> str:
    """將文字轉換為 URL 安全的檔名格式 (slug)。"""
    text = text.lower()
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'[^\w-]', '', text)
    return text

def create_new_blog_post(translations_data: dict):
    """
    (更新) 使用包含所有語言翻譯的資料，建立一個自給自足的多語言 HTML 檔案。
    """
    print(f"📝 正在 '{BLOG_OUTPUT_DIR}/' 資料夾中建立新的多語言部落格文章檔案...")
    
    try:
        os.makedirs(BLOG_OUTPUT_DIR, exist_ok=True)

        with open(BLOG_POST_TEMPLATE, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # 使用英文標題來命名檔案
        default_title = translations_data.get('en', {}).get('postTitle', 'untitled')
        filename = f"{slugify(default_title)}.html"
        
        # (更新) 將整個翻譯物件轉換為 JSON 字串
        translations_json_string = json.dumps(translations_data, ensure_ascii=False, indent=8)

        # 替換模板中的佔位符
        post_content = template_content.replace("'{{TRANSLATIONS_JSON}}'", translations_json_string) # 注意這裡的單引號
        post_content = template_content.replace("{{TRANSLATIONS_JSON}}", translations_json_string)
        post_content = post_content.replace("{{POST_FILENAME}}", filename)
        post_content = post_content.replace("{{POST_DATE}}", datetime.date.today().strftime("%B %d, %Y"))

        # 使用預設語言(英文)的內容來填充初始的 title 和 meta description
        post_content = post_content.replace("Post Title Placeholder", default_title)
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
    """
    更新部落格列表頁面，使用預設語言(英文)的標題和摘要。
    """
    print(f"🔄 正在更新 '{BLOG_LIST_PAGE}'...")
    
    try:
        with open(BLOG_LIST_PAGE, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        article_container = soup.find('div', class_='space-y-10')
        if not article_container:
            print(f"❌ 錯誤: 在 '{BLOG_LIST_PAGE}' 中找不到 <div class='space-y-10'>。")
            return
            
        link_path = os.path.join(BLOG_OUTPUT_DIR, filename).replace("\\", "/")
        
        # 從翻譯資料中獲取英文的標題和摘要
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


# --- 3. 主執行流程 (無變動) ---

if __name__ == "__main__":
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("🔥🔥🔥 請先在 `blog_generator.py` 檔案中設定您的 GEMINI_API_KEY！")
    else:
        keyword_input = input("👉 請輸入您想生成文章的 SEO 關鍵詞 (例如: 'benefits of strength training'): ")
        
        if keyword_input:
            generated_translations = generate_blog_from_keyword(keyword_input)
            if generated_translations:
                new_filename = create_new_blog_post(generated_translations)
                if new_filename:
                    update_blog_list(generated_translations, new_filename)
                    print("\n🎉 恭喜！多語言部落格文章生成與更新流程已全部完成！")
        else:
            print("❗ 沒有輸入關鍵詞，程式已結束。")
