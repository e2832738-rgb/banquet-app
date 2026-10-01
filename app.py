import json
import os
import tempfile
import random
import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

@st.cache_resource
def load_menu_from_sheets():
    """從 Google Sheets 載入菜單資料庫 (透過單行 JSON 字串與暫存檔避開 TOML 解析缺陷)"""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    temp_file_path = None
    try:
        if "gcp_json_str" in st.secrets:
            # 1. 直接將 Secrets 裡的單行 JSON 字串還原為 Python 字典
            json_str = st.secrets["gcp_json_str"]
            sa_info = json.loads(json_str)
            
            # 2. 寫入暫存檔讓 Google 認證以實體檔案讀取
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as temp_file:
                json.dump(sa_info, temp_file)
                temp_file_path = temp_file.name
            
            creds = Credentials.from_service_account_file(temp_file_path, scopes=scopes)
        else:
            # 本機環境：讀取本機的 credentials.json 檔案
            creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
            
        client = gspread.authorize(creds)
        spreadsheet = client.open("banquet_db")
        sheet = spreadsheet.worksheet("dishes")
        
        all_dishes = sheet.get_all_records()
        active_dishes = []
        for dish in all_dishes:
            is_active = dish.get("active")
            if isinstance(is_active, str):
                is_active = is_active.strip().upper() == "TRUE"
            
            if is_active:
                taboos_raw = dish.get("taboos", "")
                if isinstance(taboos_raw, str) and taboos_raw.strip():
                    dish["taboos"] = [t.strip() for t in taboos_raw.split(",")]
                else:
                    dish["taboos"] = []
                active_dishes.append(dish)
        return active_dishes
    except Exception as e:
        st.error(f"載入 Google Sheets 失敗，請檢查憑證或連線：{e}")
        return []
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except:
                pass
def generate_banquet_menu(menu_db, target_price, total_dishes_count=10, user_taboos=None):
    if user_taboos is None:
        user_taboos = []
        
    base_categories = ["cold", "soup", "fish", "rice", "chicken", "veggie", "dessert", "fruit"]
    categories = []
    for i in range(total_dishes_count):
        cat = base_categories[i % len(base_categories)]
        categories.append(cat)
        
    best_menu = None
    min_price_diff = float('inf')
    
    for _ in range(5000):
        current_menu = []
        total_price = 0
        valid = True
        
        for cat in categories:
            options = [
                d for d in menu_db 
                if d["cat"] == cat and not any(t in d.get("taboos", []) for t in user_taboos)
            ]
            
            if not options:
                options = [d for d in menu_db if not any(t in d.get("taboos", []) for t in user_taboos)]
                if not options:
                    valid = False
                    break
            
            if target_price >= 8500:
                tier_options = [o for o in options if o.get("tier", 1) >= 2]
                chosen = random.choice(tier_options) if tier_options else random.choice(options)
            else:
                tier_options = [o for o in options if o.get("tier", 1) == 1]
                chosen = random.choice(tier_options) if tier_options else random.choice(options)
                
            current_menu.append(chosen)
            total_price += chosen["price"]
            
        if not valid:
            continue
            
        price_diff = abs(total_price - target_price)
        if price_diff < min_price_diff:
            min_price_diff = price_diff
            best_menu = current_menu
            
    if not best_menu:
        return None
        
    return {
        "menu": best_menu,
        "total_price": sum(d["price"] for d in best_menu),
        "total_cost": sum(d["cost"] for d in best_menu)
    }

# --- 網頁介面設計 ---
st.title("🍲 智慧辦桌菜單配置系統")
st.write("輸入客戶預算與忌口，系統自動從雲端資料庫配出最佳菜單！")

menu_database = load_menu_from_sheets()

if menu_database:
    with st.form("banquet_form"):
        customer_budget = st.number_input("客戶預算金額 (NT$)", min_value=3000, max_value=30000, value=8000, step=500)
        customer_dishes_count = st.slider("想要配置的菜色道數", min_value=6, max_value=12, value=10, step=2)
        taboo_input = st.text_input("客戶忌口標籤 (例如 shellfish，多個請用逗號隔開)", value="")
        
        submit_btn = st.form_submit_button("🚀 開始自動配菜")

    if submit_btn:
        customer_taboos = [t.strip() for t in taboo_input.split(",")] if taboo_input else []
        
        with st.spinner("正在計算最佳菜單組合中..."):
            result = generate_banquet_menu(
                menu_database, 
                target_price=customer_budget, 
                total_dishes_count=customer_dishes_count,
                user_taboos=customer_taboos
            )
            
        if result:
            st.success("✨ 菜單配置成功！")
            
            # 顯示總覽數據
            col1, col2, col3 = st.columns(3)
            col1.metric("總售價", f"NT$ {result['total_price']}")
            col2.metric("總成本", f"NT$ {result['total_cost']}")
            profit = result['total_price'] - result['total_cost']
            margin = (profit / result['total_price']) * 100 if result['total_price'] > 0 else 0
            col3.metric("預估毛利", f"NT$ {profit}", f"{margin:.1f}%")
            
            st.markdown("### 📋 推薦菜單明細")
            # 整理成表格呈現在手機上
            table_data = []
            for index, dish in enumerate(result["menu"], 1):
                table_data.append({
                    "道次": index,
                    "菜品名稱": dish['name'],
                    "分類": dish['cat'],
                    "售價": f"NT$ {dish['price']}",
                    "成本": f"NT$ {dish['cost']}"
                })
            st.table(table_data)
        else:
            st.error("很抱歉，找不到符合該預算與條件的菜單組合。")