import os
from pathlib import Path

import pandas as pd
import streamlit as st

# Optional AI integrations
try:
    from hindsight_client import Hindsight
except Exception:
    Hindsight = None

try:
    from google import genai
except Exception:
    genai = None

BASE_DIR = Path(__file__).resolve().parent
SALES_CANDIDATES = [
    BASE_DIR / "restocking_sales_history.xlsx",
    BASE_DIR / "restocking_sales_history.csv",
]
INVENTORY_FILE = BASE_DIR / "inventory.csv"

st.set_page_config(
    page_title="Priya General Store AI",
    page_icon="🛒",
    layout="wide",
)

@st.cache_data
def load_sales():
    path = next((p for p in SALES_CANDIDATES if p.exists()), None)
    if path is None:
        raise FileNotFoundError(
            "Sales file not found. Put restocking_sales_history.xlsx or "
            "restocking_sales_history.csv beside app.py."
        )
    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data
def load_inventory():
    if not INVENTORY_FILE.exists():
        return None
    return pd.read_csv(INVENTORY_FILE)

def top_products():
    df = load_sales()
    return (
        df.groupby(["sku", "product_name"])["units_sold"]
        .sum()
        .sort_values(ascending=False)
    )

def monthly_sales():
    df = load_sales().copy()
    df["month"] = df["date"].dt.to_period("M").astype(str)
    return df.groupby("month")["units_sold"].sum()

def sales_velocity(days):
    df = load_sales()
    latest = df["date"].max()
    start = latest - pd.Timedelta(days=days - 1)
    recent = df[(df["date"] >= start) & (df["date"] <= latest)]
    result = (
        recent.groupby(["sku", "product_name"])["units_sold"]
        .sum()
        .to_frame("units_sold")
    )
    result["units_per_day"] = result["units_sold"] / days
    return result.sort_values("units_per_day", ascending=False)

def product_history(question):
    df = load_sales()
    products = df["product_name"].dropna().unique()
    q = question.lower()
    matches = [
        product for product in products
        if any(word in product.lower() for word in q.split() if len(word) > 3)
    ]
    if not matches:
        return None
    selected = matches[0]
    p = df[df["product_name"] == selected]
    monthly = (
        p.assign(month=p["date"].dt.to_period("M").astype(str))
        .groupby("month")["units_sold"]
        .sum()
    )
    return selected, int(p["units_sold"].sum()), monthly

def restocking_analysis():
    sales = load_sales()
    inventory = load_inventory()
    if inventory is None:
        raise FileNotFoundError(
            "inventory.csv is missing. Put it beside app.py to enable restocking analysis."
        )
    latest = sales["date"].max()
    start = latest - pd.Timedelta(days=29)
    recent = sales[(sales["date"] >= start) & (sales["date"] <= latest)]
    velocity = recent.groupby("sku")["units_sold"].sum().to_frame("units_sold_30_days")
    velocity["units_per_day"] = velocity["units_sold_30_days"] / 30
    result = inventory.merge(velocity, on="sku", how="left")
    result["units_per_day"] = result["units_per_day"].fillna(0)
    result["days_of_stock"] = result.apply(
        lambda row: row["current_stock"] / row["units_per_day"]
        if row["units_per_day"] > 0 else float("inf"),
        axis=1,
    )
    result["7_day_demand"] = result["units_per_day"] * 7
    result["14_day_demand"] = result["units_per_day"] * 14
    result["30_day_demand"] = result["units_per_day"] * 30
    result["suggested_reorder"] = (
        result["30_day_demand"] - result["current_stock"]
    ).clip(lower=0).round().astype(int)
    return result

def store_summary():
    df = load_sales()
    return (
        int(df["units_sold"].sum()),
        len(df),
        df["date"].min().date(),
        df["date"].max().date(),
    )

def hindsight_reflect(question):
    key = os.getenv("HINDSIGHT_API_KEY")
    if not key or Hindsight is None:
        return None
    try:
        client = Hindsight(
            base_url="https://api.hindsight.vectorize.io",
            api_key=key,
        )
        response = client.reflect(
            bank_id=os.getenv("HINDSIGHT_BANK_ID", "1"),
            query=question,
        )
        return response.text
    except Exception as exc:
        return f"Hindsight unavailable: {exc}"

def build_ai_context():
    sales = load_sales()
    inventory = load_inventory()
    latest = sales["date"].max()
    recent = sales[sales["date"] >= latest - pd.Timedelta(days=29)]
    velocity = (
        recent.groupby(["sku", "product_name"])["units_sold"]
        .sum()
        .to_frame("units_sold_30_days")
    )
    velocity["units_per_day"] = velocity["units_sold_30_days"] / 30

    parts = [
        "PRIYA GENERAL STORE SALES DATA",
        f"Data through: {latest.date()}",
        "",
        "TOP PRODUCTS:",
        top_products().head(10).to_string(),
        "",
        "RECENT SALES VELOCITY:",
        velocity.sort_values("units_per_day", ascending=False).to_string(),
    ]
    if inventory is not None:
        parts += ["", "CURRENT INVENTORY:", inventory.to_string(index=False)]
    return "\n".join(parts)

def ask_ai(question):
    key = os.getenv("GEMINI_API_KEY")
    if not key or genai is None:
        return (
            "Gemini is not configured. Add GEMINI_API_KEY to the environment "
            "where this app runs. The dashboard and non-AI analytics still work."
        )
    hindsight_context = hindsight_reflect(question) or "No Hindsight memory available."
    prompt = f"""
You are the AI business assistant for Priya General Store.

Answer the store owner's question using ONLY the store information provided below.
Be practical and concise. Do not invent sales, inventory, prices, suppliers,
weather information, or other facts. If the data is insufficient, say so.

STORE DATA
==========
{build_ai_context()}

HINDSIGHT HISTORICAL MEMORY
===========================
{hindsight_context}

STORE OWNER QUESTION
====================
{question}
"""
    try:
        client = genai.Client(api_key=key, vertexai=False)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        return response.text
    except Exception as exc:
        return f"Gemini error: {exc}"

def render_question(question):
    q = question.lower().strip()
    if any(x in q for x in ["top", "best selling", "highest selling", "most sold", "sell the most", "sold the most", "most popular"]):
        st.subheader("Top Products")
        st.dataframe(top_products().head(10).reset_index(), use_container_width=True)
        return
    if "60" in q:
        st.subheader("60-Day Sales Velocity")
        st.dataframe(sales_velocity(60).reset_index(), use_container_width=True)
        return
    if "90" in q:
        st.subheader("90-Day Sales Velocity")
        st.dataframe(sales_velocity(90).reset_index(), use_container_width=True)
        return
    if any(x in q for x in ["fast", "fastest", "recent", "moving", "velocity"]):
        st.subheader("30-Day Sales Velocity")
        st.dataframe(sales_velocity(30).reset_index(), use_container_width=True)
        return
    if any(x in q for x in ["monthly", "month by month", "by month"]):
        st.subheader("Monthly Sales")
        st.line_chart(monthly_sales())
        return
    if any(x in q for x in ["summary", "overall", "performance"]):
        total, records, first, last = store_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Units sold", f"{total:,}")
        c2.metric("Sales records", f"{records:,}")
        c3.metric("Data through", str(last))
        st.caption(f"Data starts {first}")
        return
    if any(x in q for x in ["restock", "reorder", "stockout", "stock out", "days of stock"]):
        st.subheader("Restocking Analysis")
        result = restocking_analysis()
        cols = [
            "sku", "product_name", "current_stock", "units_per_day",
            "days_of_stock", "7_day_demand", "14_day_demand",
            "30_day_demand", "suggested_reorder",
        ]
        display = result[cols].copy()
        display["units_per_day"] = display["units_per_day"].round(2)
        display["days_of_stock"] = display["days_of_stock"].replace(float("inf"), None).round(1)
        st.dataframe(display, use_container_width=True)
        st.caption("Suggested reorder is estimated 30-day demand minus current stock; it is not a final purchasing decision.")
        return
    product_result = product_history(question)
    if product_result:
        product, total, monthly = product_result
        st.subheader(product)
        st.metric("Total units sold", f"{total:,}")
        st.line_chart(monthly)
        return
    with st.spinner("Thinking..."):
        answer = ask_ai(question)
    st.markdown("### AI Store Assistant")
    st.write(answer)

# UI
st.title("🛒 Priya General Store — AI Assistant")
st.caption("Sales • Inventory • Restocking • Hindsight • Gemini")

try:
    sales = load_sales()
    inventory = load_inventory()
except Exception as exc:
    st.error(str(exc))
    st.stop()

with st.sidebar:
    st.header("Store Data")
    total, records, first, last = store_summary()
    st.metric("Units sold", f"{total:,}")
    st.metric("Sales records", f"{records:,}")
    st.write(f"Sales period: **{first} → {last}**")
    st.write(f"Inventory file: **{'Available' if inventory is not None else 'Missing'}**")
    st.divider()
    st.write("API keys are read from environment variables and are not stored in the app.")

tabs = st.tabs(["💬 AI Chat", "📊 Dashboard", "📦 Restocking"])

with tabs[0]:
    st.write("Ask a question about your store.")
    examples = [
        "Which products sell the most?",
        "What is selling fastest?",
        "Show me the last 60 days.",
        "Which products should I restock?",
        "What seasonal patterns do you see?",
        "What should I prepare for next month?",
    ]
    selected = st.selectbox("Example question", ["Custom"] + examples)
    question = st.text_input("Your question", value="" if selected == "Custom" else selected)
    if st.button("Ask AI", type="primary") and question.strip():
        render_question(question)

with tabs[1]:
    st.subheader("Top 10 Products")
    st.dataframe(top_products().head(10).reset_index(), use_container_width=True)
    st.subheader("Monthly Sales")
    st.line_chart(monthly_sales())
    st.subheader("30-Day Velocity")
    st.dataframe(sales_velocity(30).reset_index(), use_container_width=True)

with tabs[2]:
    if inventory is None:
        st.warning("Add inventory.csv beside app.py to enable restocking analysis.")
    else:
        result = restocking_analysis()
        st.dataframe(result, use_container_width=True)
