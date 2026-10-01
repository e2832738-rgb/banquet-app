import random
import pandas as pd
import streamlit as st

# === 1. 背景安靜載入雲端 Google 試算表資料 ===
@st.cache_resource
def load_menu_from_sheets():
    try:
        sheet_id = "11DIvmuntVIaYWLtZcRPl8DZGVLGviwiWJgioxmK0r7A"
        sheet_name = "dishes"  
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
        
        df = pd.read_csv(url)
        all_dishes = df.to_dict(orient="records")
        
        active_dishes = []
        for dish in all_dishes:
            is_active = dish.get("active")
            if isinstance(is_active, str):
                is_active = is_active.strip().upper() == "TRUE"
            elif isinstance(is_active, bool):
                pass
            else:
                is_active = False
            
            if is_active:
                taboos_raw = dish.get("taboos", "")
                if isinstance(taboos_raw, str) and taboos_raw.strip():
                    dish["taboos"] = [t.strip() for t in taboos_raw.split(",")]
                else:
                    dish["taboos"] = []
                active_dishes.append(dish)
        return active_dishes
    except Exception as e:
        st.error(f"載入 Google Sheets 失敗：{e}")
        return []

# === 2. 智慧彈性配菜演算法 (強化預算容忍度) ===
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
    
    # 進行 8000 次模擬抽樣，尋找最貼近預算的組合
    for _ in range(8000):
        current_menu = []
        total_price = 0
        valid = True
        
        for cat in categories:
            # 篩選符合分類且沒有違反忌口標籤的菜色
            options = [
                d for d in menu_db 
                if d["cat"] == cat and not any(t in d.get("taboos", []) for t in user_taboos)
            ]
            
            # 如果該分類剛好被忌口擋光，退而求其次抓任意未違規菜色
            if not options:
                options = [d for d in menu_db if not any(t in d.get("taboos", []) for t in user_taboos)]
                if not options:
                    valid = False
                    break
            
            # 依照預算高低自動偏好高階或平價菜色
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
            
    # 🛡️ 彈性防禦機制：如果跑完幾千次還是找不到完美貼近的，自動放寬標準回傳最接近的菜單
    if not best_menu and menu_db:
        # 取任意符合忌口的菜色湊滿道數
        fallback_options = [d for d in menu_db if not any(t in d.get("taboos", []) for t in user_taboos)]
        if len(fallback_options) >= total_dishes_count:
            best_menu = random.sample(fallback_options, total_dishes_count)
        else:
            best_menu = fallback_options  # 盡量給出有的
            
    if not best_menu:
        return None
        
    return {
        "menu": best_menu,
        "total_price": sum(d["price"] for d in best_menu),
        "total_cost": sum(d["cost"] for d in best_menu)
    }

# === 3. 網頁前端介面設計 ===
st.title("🍲 黃家外燴菜色配置系統")
st.write("輸入客戶預算與忌口，系統自動從雲端資料庫配出最佳菜單！")

# 載入資料庫
menu_database = load_menu_from_sheets()

if menu_database:
    with st.form("banquet_form"):
        customer_budget = st.number_input("客戶預算金額 (NT$)", min_value=3000, max_value=50000, value=8000, step=500)
        customer_dishes_count = st.slider("想要配置的菜色道數", min_value=6, max_value=12, value=10, step=2)
        taboo_input = st.text_input("客戶忌口標籤 (例如 shellfish，多個請用逗號隔開)", value="")
        
        submit_btn = st.form_submit_button("🚀 開始自動配菜")

    if submit_btn:
        customer_taboos = [t.strip() for t in taboo_input.split(",")] if taboo_input else []
        
        with st.spinner("正在彈性計算最佳菜單組合中..."):
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
            table_data = []
            for index, dish in enumerate(result["menu"], 1):
                table_data.append({
                    "道次": index,
                    "菜品名稱": dish.get('name', '未命名'),
                    "分類": dish.get('cat', ''),
                    "售價": f"NT$ {dish.get('price', 0)}",
                    "成本": f"NT$ {dish.get('cost', 0)}"
                })
            st.table(table_data)
        else:
            st.error("很抱歉，資料庫中沒有足夠的菜色可供配置，請檢查 Google 試算表內容。")
else:
    st.warning("目前無法載入雲端菜單資料，請確認網絡或試算表共用設定。")