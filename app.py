import streamlit as st
import pypdf
import requests
import json
from openai import OpenAI

# ----------------- 1. 工具函數：PDF/文字解析 -----------------
def extract_text_from_file(uploaded_file):
    """提取 TXT 或 PDF 文件的文字內容"""
    if uploaded_file.name.endswith(".txt"):
        return uploaded_file.read().decode("utf-8", errors="ignore")
    elif uploaded_file.name.endswith(".pdf"):
        reader = pypdf.PdfReader(uploaded_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text
    return ""

# ----------------- 2. 工具函數：即時天氣抓取 (Open-Meteo) -----------------
def fetch_weather(city_name):
    """免費即時取得指定城市明天的天氣與氣溫預報"""
    try:
        # 地理編碼取得經緯度
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city_name}&count=1&language=zh&format=json"
        geo_res = requests.get(geo_url, timeout=5).json()
        
        if not geo_res.get("results"):
            return f"{city_name} 天氣預報獲取失敗（可手動輸入）"
        
        lat = geo_res["results"][0]["latitude"]
        lon = geo_res["results"][0]["longitude"]
        
        # 查詢氣象
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            f"&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=auto"
        )
        w_res = requests.get(weather_url, timeout=5).json()
        daily = w_res.get("daily", {})
        
        # 取明天（index 1）
        t_max = daily["temperature_2m_max"][1]
        t_min = daily["temperature_2m_min"][1]
        code = daily["weathercode"][1]
        
        # WMO 天氣代碼簡易轉換
        weather_map = {
            0: "晴朗", 1: "大部晴朗", 2: "多雲", 3: "陰天",
            45: "有霧", 48: "凍霧", 51: "輕微細雨", 61: "小雨",
            63: "中雨", 65: "大雨", 71: "小雪", 75: "大雪", 95: "雷雨"
        }
        condition = weather_map.get(code, "晴時多雲")
        return f"{condition}，氣溫約 {t_min}°C ~ {t_max}°C"
    except Exception as e:
        return f"無法連線查詢天氣: {city_name}"

# ----------------- 3. 呼叫大模型生成提示詞 -----------------
def generate_tour_notices(api_key, itinerary_text, default_settings):
    client = OpenAI(api_key=api_key)

    prompt = f"""
你是一位專業、細心且富有同理心的資深華語隨團領隊。
請根據以下提供的「旅遊行程內容」，為每一天生成一份專屬的「領隊每日溫馨提示」。

【基礎共用資訊】：
- 領隊姓名：{default_settings['leader_name']}
- 預設房號：{default_settings['room_no']}
- 房間內線：{default_settings['phone_ext']}
- Wi-Fi 帳號預設：{default_settings['wifi_user']}
- Wi-Fi 密碼預設：{default_settings['wifi_pwd']}

【每則提示必須嚴格按照以下格式生成，每日一則】：

[日期，如：18/6]
[一句扣人心弦的主題標語] [入住酒店名稱]
領隊 {default_settings['leader_name']} 房號 [房號]（房間致電請打 [內線]）
wifi 帳號：[wifi帳號]
密碼：[wifi密碼]
早餐：[時間與地點，如：07:00-08:00 酒店一樓西餐廳]
明天行程提示行李安排：[需根據行程判定：原酒店連泊不需收拾 / 需收拾大行李放門口]
出發：[出發時間] (酒店大堂)
明天天氣：[目的地城市名稱]（例如：拉薩 / 林芝 / 日喀則）

明天行程：
[簡短回顧今天，接著介紹明天的具體重點行程、景點特色，以及當晚安排的餐食特色]
*** 天氣與穿著提醒：[針對明天目的地海拔、溫差、紫外線給出具體穿著指導，如洋蔥式穿法、防寒羽絨衣等]
*** 健康/安全提醒：[結合目的地特性，如高原反應、補水保濕、長途車程或健行注意事項]
*** 特別提示/證件預告：[提醒隔日需要的門票證件（回鄉證/護照）、行李清點、充電寶隨身帶等細節]

---
【行程內容】：
{itinerary_text}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "你是一個專業的旅遊行程分析助手。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content

# ----------------- 4. Streamlit 前端介面 -----------------
st.set_page_config(page_title="領隊每日行程提示生成器", layout="wide")
st.title("📋 領隊每日行程提示自動生成器")

# 側邊欄：設定
with st.sidebar:
    st.header("⚙️ 領隊預設設定")
    api_key = st.text_input("OpenAI API Key", type="password")
    leader_name = st.text_input("領隊名字", value="Yvonne")
    room_no = st.text_input("預設房號（可留空手填）", value="[請輸入]")
    phone_ext = st.text_input("房間內線（可留空手填）", value="[請輸入]")
    wifi_user = st.text_input("Wi-Fi 帳號（可留空手填）", value="[請輸入]")
    wifi_pwd = st.text_input("Wi-Fi 密碼（可留空手填）", value="[請輸入]")

# 主頁面：上傳行程
uploaded_file = st.file_uploader("請上傳行程檔案 (支援 PDF 或 TXT)", type=["pdf", "txt"])

if uploaded_file and api_key:
    if st.button("🚀 開始分析並生成每日提示"):
        with st.spinner("正在讀取文件並解析每日行程..."):
            raw_text = extract_text_from_file(uploaded_file)
            
            defaults = {
                "leader_name": leader_name,
                "room_no": room_no,
                "phone_ext": phone_ext,
                "wifi_user": wifi_user,
                "wifi_pwd": wifi_pwd
            }
            
            # 生成每日初稿
            generated_text = generate_tour_notices(api_key, raw_text, defaults)
            
            # 解析天數並查詢即時氣象
            daily_notices = generated_text.split("---")
            final_notices = []
            
            for notice in daily_notices:
                notice_clean = notice.strip()
                if not notice_clean:
                    continue
                
                # 自動搜尋「明天天氣：」行並連線抓取
                lines = notice_clean.split("\n")
                new_lines = []
                for line in lines:
                    if line.startswith("明天天氣："):
                        dest_city = line.replace("明天天氣：", "").strip().strip("[]")
                        # 擷取純城市名（排除括號說明）
                        city = dest_city.split("（")[0].replace("市", "").strip()
                        weather_info = fetch_weather(city)
                        new_lines.append(f"明天天氣：{city}（預報：{weather_info}）")
                    else:
                        new_lines.append(line)
                
                final_notices.append("\n".join(new_lines))
            
            st.session_state["result"] = "\n\n" + ("="*40 + "\n\n").join(final_notices)

# 顯示生成結果
if "result" in st.session_state:
    st.subheader("✅ 生成結果（可直接複製或編輯）")
    st.text_area("編輯區", value=st.session_state["result"], height=500)
    
    st.download_button(
        label="📥 下載為文字檔 (.txt)",
        data=st.session_state["result"],
        file_name="每日領隊行程提示.txt",
        mime="text/plain"
    )
elif not api_key:
    st.info("👈 請先在左側欄位輸入 OpenAI API Key 即可開始使用。")