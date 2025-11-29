# app.py
"""
Smart Shopkeeper Assistant — Sidebar menu moved to top
Features:
- Prophet forecasting (trend-aware)
- Emoji product buttons (no prices)
- Gmail alerts only (sidebar)
- Inventory Dashboard (top/bottom sellers, stock health)
- Excel export & PDF quick report
- EOQ and DaysCovered removed
- Session-state bug fixed (stock keys initialized before widget)
- Menu placed at top of sidebar; other settings below
"""

import streamlit as st
import pandas as pd
import numpy as np
from prophet import Prophet
from datetime import datetime
from io import BytesIO
import matplotlib.pyplot as plt
import plotly.express as px
import smtplib
from email.message import EmailMessage

# Page config
st.set_page_config(page_title="📦 Smart Shopkeeper Assistant", layout="wide", page_icon="🛒")

# ----------------------------
# SESSION STATE INIT
# ----------------------------
if "sales_data" not in st.session_state:
    st.session_state.sales_data = pd.DataFrame(columns=["Date", "Product", "Quantity"])

if "selected_product" not in st.session_state:
    st.session_state.selected_product = ""

if "product_list" not in st.session_state:
    st.session_state.product_list = [
        "Milk", "Bread", "Biscuit", "Chocolate", "Juice",
        "Soap", "Oil", "Rice", "Salt", "Tissue"
    ]

if "alert_sent" not in st.session_state:
    st.session_state.alert_sent = {}

if "forced_page" not in st.session_state:
    st.session_state.forced_page = None

# ----------------------------
# Sidebar: MENU at top, other settings below
# ----------------------------
# Put menu at top
sidebar_page = st.sidebar.selectbox("📌 Menu", ["Sales Entry", "Forecasting", "Inventory Dashboard", "Reports", "Help"])

# Separator
st.sidebar.markdown("---")

# Other settings below menu
st.sidebar.subheader("⚙️ Settings")

st.sidebar.subheader("📈 Forecast Settings")
forecast_days = st.sidebar.number_input("Forecast Horizon (days)", min_value=3, max_value=60, value=7)
lead_time_days = st.sidebar.number_input("Lead Time (days)", min_value=1, max_value=14, value=3)

st.sidebar.subheader("📤 Export")
export_filename = st.sidebar.text_input("Export filename (Excel)", value="shop_report.xlsx")

st.sidebar.subheader("🔔 Gmail Alerts")
enable_email = st.sidebar.checkbox("Enable Gmail Alerts", value=False)
if enable_email:
    gmail_id = st.sidebar.text_input("Gmail (sender)", value="")
    gmail_pass = st.sidebar.text_input("Gmail App Password", type="password", value="")
    alert_recipient = st.sidebar.text_input("Recipient Email", value="")
else:
    gmail_id = gmail_pass = alert_recipient = ""

# No footer note — removed per request

# Use forced bottom nav override if set
page = st.session_state.forced_page if st.session_state.forced_page else sidebar_page

# ----------------------------
# Helper functions
# ----------------------------
def send_gmail_alert(product, current_stock, reorder_point, avg_demand):
    if not enable_email:
        return False, "Email alerts disabled"
    if not (gmail_id and gmail_pass and alert_recipient):
        return False, "SMTP fields missing"
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Low Stock Alert - {product}"
        msg["From"] = gmail_id
        msg["To"] = alert_recipient
        msg.set_content(
            f"⚠️ LOW STOCK ALERT\n\n"
            f"Product: {product}\n"
            f"Current stock: {current_stock}\n"
            f"Reorder point: {int(reorder_point)}\n"
            f"Avg daily demand (forecast): {avg_demand:.2f}\n\n"
            f"Sent by Smart Shopkeeper Assistant."
        )
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(gmail_id, gmail_pass)
        server.send_message(msg)
        server.quit()
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

def excel_bytes_multi(all_data, summary_df):
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        all_data.to_excel(writer, index=False, sheet_name="SalesRaw")
        summary_df.to_excel(writer, index=False, sheet_name="Summary")
    buf.seek(0)
    return buf

def pdf_quick_report(history_df, forecast_df, product_name):
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(history_df["Date"], history_df["Quantity"], marker="o", label="Historical")
    ax.plot(forecast_df["Date"], forecast_df["Predicted Sales"], marker="o", linestyle="--", label="Forecast")
    ax.set_title(f"Sales Report: {product_name}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Units")
    ax.legend()
    ax.grid(True)
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="pdf")
    plt.close(fig)
    buf.seek(0)
    return buf

def colored_badge(text, color):
    html = f"""<span style="
        display:inline-block;
        padding:4px 8px;
        border-radius:8px;
        color:white;
        background:{color};
        font-weight:600;
        ">{text}</span>"""
    return html

# ----------------------------
# Product Emojis
# ----------------------------
product_emojis = {
    "Milk": "🥛",
    "Bread": "🍞",
    "Biscuit": "🍪",
    "Chocolate": "🍫",
    "Juice": "🧃",
    "Soap": "🧼",
    "Oil": "🛢️",
    "Rice": "🍚",
    "Salt": "🧂",
    "Tissue": "🧻",
}

# ----------------------------
# PAGE: Sales Entry
# ----------------------------
if page == "Sales Entry":
    st.title("🛒 Daily Sales Entry")

    with st.expander("➕ Add / edit product list"):
        new_prod = st.text_input("Product name to add (exact), leave blank to skip")
        if st.button("Add product"):
            if new_prod and new_prod.strip():
                p = new_prod.strip()
                if p not in st.session_state.product_list:
                    st.session_state.product_list.append(p)
                    st.success(f"Added product: {p}")
                else:
                    st.info("Product already exists.")
        st.write("Current products:", ", ".join(st.session_state.product_list))

    cols = st.columns(5)
    for idx, prod in enumerate(st.session_state.product_list):
        emoji = product_emojis.get(prod, "📦")
        with cols[idx % 5]:
            if st.button(f"{emoji} {prod}"):
                st.session_state.selected_product = prod

    product = st.text_input("Product", value=st.session_state.selected_product)
    qty = st.number_input("Quantity Sold", min_value=1, step=1, value=1)
    date = st.date_input("Date", datetime.today())

    if st.button("➕ Add Sale"):
        if not product or product.strip() == "":
            st.warning("Please enter a product name.")
        else:
            new_row = {"Date": pd.to_datetime(date), "Product": product.strip(), "Quantity": int(qty)}
            st.session_state.sales_data = pd.concat([st.session_state.sales_data, pd.DataFrame([new_row])], ignore_index=True)
            st.success(f"Added sale: {qty} × {product.strip()} on {date}")

    st.markdown("---")
    st.subheader("📋 Sales History (most recent first)")
    if st.session_state.sales_data.empty:
        st.info("No sales recorded yet.")
    else:
        st.dataframe(st.session_state.sales_data.sort_values("Date", ascending=False).reset_index(drop=True))

# ----------------------------
# PAGE: Forecasting
# ----------------------------
if page == "Forecasting":
    st.title("📈 Forecasting & Alerts")

    data = st.session_state.sales_data.copy()
    if data.empty:
        st.info("No sales data. Add sales in Sales Entry.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    product_choices = sorted(data["Product"].unique())
    selected_product = st.selectbox("Select product", product_choices)

    prod_hist = data[data["Product"] == selected_product].groupby("Date").agg({"Quantity": "sum"}).reset_index().sort_values("Date")
    prod_hist = prod_hist.set_index("Date").asfreq("D").fillna(0).reset_index()

    st.subheader("Last 30 days (history)")
    st.dataframe(prod_hist.tail(30))

    dfp = prod_hist.rename(columns={"Date": "ds", "Quantity": "y"})
    model = Prophet(weekly_seasonality=True)
    model.fit(dfp)

    future = model.make_future_dataframe(periods=int(forecast_days))
    forecast = model.predict(future)

    forecast_display = forecast[forecast["ds"] > prod_hist["Date"].max()][["ds", "yhat"]].rename(columns={"ds": "Date", "yhat": "Predicted Sales"})
    forecast_display["Predicted Sales"] = forecast_display["Predicted Sales"].clip(lower=0).round().astype(int)

    st.subheader(f"{forecast_days}-day Forecast")
    st.dataframe(forecast_display)

    combined = pd.concat([
        prod_hist.rename(columns={"Date": "Date", "Quantity": "Sales"})[["Date", "Sales"]],
        forecast_display.rename(columns={"Date": "Date", "Predicted Sales": "Sales"})[["Date", "Sales"]],
    ], ignore_index=True)
    st.plotly_chart(px.line(combined, x="Date", y="Sales", title=f"History + Forecast: {selected_product}"), use_container_width=True)

    avg_demand = float(forecast_display["Predicted Sales"].mean()) if len(forecast_display) > 0 else 0.0
    reorder_point = avg_demand * lead_time_days

    st.markdown("### Inventory Suggestions")
    c1, c2 = st.columns(2)
    c1.metric("Avg daily demand", f"{avg_demand:.2f} units")
    c2.metric("Reorder point", f"{reorder_point:.0f} units")

    stock_key = f"stock_{selected_product}"
    if stock_key not in st.session_state:
        st.session_state[stock_key] = 0
    current_stock = st.number_input(f"Current stock for {selected_product}:", min_value=0, value=st.session_state[stock_key], key=stock_key)

    if current_stock < reorder_point:
        st.error(f"⚠️ LOW STOCK: {selected_product} — current {current_stock} < reorder {int(reorder_point)}")
        if enable_email:
            if st.button("📧 Send Gmail Alert"):
                success, msg = send_gmail_alert(selected_product, current_stock, reorder_point, avg_demand)
                if success:
                    st.success("📧 Gmail alert sent.")
                else:
                    st.error(f"Email failed: {msg}")
    else:
        st.success(f"✅ Stock OK for {selected_product}")

    st.markdown("---")
    excel_buf = excel_bytes_multi(all_data=data[data["Product"] == selected_product], summary_df=forecast_display)
    st.download_button("📥 Download Forecast Excel", data=excel_buf, file_name=f"{selected_product}_forecast.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    pdf_buf = pdf_quick_report(prod_hist.rename(columns={"Date":"Date","Quantity":"Quantity"}).tail(30), forecast_display, selected_product)
    st.download_button("📄 Download Quick PDF", data=pdf_buf, file_name=f"{selected_product}_report.pdf", mime="application/pdf")

# ----------------------------
# PAGE: Inventory Dashboard
# ----------------------------
if page == "Inventory Dashboard":
    st.title("📊 Inventory Dashboard")

    data = st.session_state.sales_data.copy()
    if data.empty:
        st.info("No sales data yet.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])

    window_days = st.number_input("Fast-mover window (days)", min_value=7, max_value=90, value=14)

    total_by_product = data.groupby("Product")["Quantity"].sum().reset_index().rename(columns={"Quantity": "TotalSold"})
    recent_from = pd.Timestamp(datetime.now().date()) - pd.Timedelta(days=int(window_days))
    recent = data[data["Date"] >= recent_from].groupby("Product")["Quantity"].sum().reset_index().rename(columns={"Quantity": "SoldRecent"})

    summary = pd.merge(total_by_product, recent, on="Product", how="left").fillna(0)
    summary["AvgDailyRecent"] = summary["SoldRecent"] / (window_days if window_days > 0 else 1)
    summary["CurrentStock"] = summary["Product"].apply(lambda p: st.session_state.get(f"stock_{p}", 0))
    summary["ReorderPoint"] = summary["AvgDailyRecent"] * lead_time_days

    def health_and_color(r):
        if r["CurrentStock"] <= 0:
            return "Critical", "#D7263D"
        if r["CurrentStock"] < r["ReorderPoint"]:
            return "Low", "#FF8C00"
        return "Healthy", "#2ECC71"

    summary[["Health", "BadgeColor"]] = summary.apply(lambda r: pd.Series(health_and_color(r)), axis=1)

    st.subheader("Product Summary")
    st.dataframe(summary.sort_values(["Health", "TotalSold"], ascending=[True, False]).reset_index(drop=True))

    st.subheader("Low Stock / Critical Items")
    low_items = summary[summary["Health"].isin(["Critical", "Low"])].sort_values("ReorderPoint")
    if low_items.empty:
        st.success("No low stock items.")
    else:
        for _, row in low_items.iterrows():
            prod = row["Product"]
            badge_html = colored_badge(row["Health"], row["BadgeColor"])
            st.markdown(f"**{prod}** — Current: `{int(row['CurrentStock'])}` | Reorder: `{int(row['ReorderPoint'])}` | Status: {badge_html}", unsafe_allow_html=True)

    st.subheader(f"Top movers (last {window_days} days)")
    movers = summary.sort_values("SoldRecent", ascending=False).head(10)
    if not movers.empty:
        fig = px.bar(movers, x="Product", y="SoldRecent", title="Top movers (recent)")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly Sales")
    monthly = data.copy()
    monthly["Month"] = monthly["Date"].dt.to_period("M").astype(str)
    monthly_agg = monthly.groupby(["Month", "Product"])["Quantity"].sum().reset_index()
    fig_month = px.bar(monthly_agg, x="Month", y="Quantity", color="Product", title="Monthly Sales", barmode="group")
    st.plotly_chart(fig_month, use_container_width=True)

    st.markdown("---")
    excel_buf = excel_bytes_multi(data, summary)
    st.download_button("📥 Download Inventory Excel", data=excel_buf, file_name=export_filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ----------------------------
# PAGE: Reports
# ----------------------------
if page == "Reports":
    st.title("📁 Raw Reports")
    data = st.session_state.sales_data.copy()
    if data.empty:
        st.info("No data.")
        st.stop()

    st.dataframe(data.sort_values("Date", ascending=False).reset_index(drop=True))
    excel_buf = excel_bytes_multi(data, data.groupby("Product")["Quantity"].sum().reset_index().rename(columns={"Quantity":"TotalSold"}))
    st.download_button("📥 Download Full Excel Report", data=excel_buf, file_name=export_filename, mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ----------------------------
# PAGE: Help
# ----------------------------
if page == "Help":
    st.title("ℹ️ Help")
    st.markdown("""
    • Use Sales Entry to add daily sales (emoji buttons available).  
    • Forecast demand in Forecasting and see reorder point.  
    • Inventory Dashboard shows low stock and top movers.  
    • Gmail alerts supported (enable and add App Password in sidebar).  
    """)

# ----------------------------
# Bottom navigation (mobile-friendly)
# ----------------------------
st.markdown("---")
c1, c2, c3, c4, c5 = st.columns(5)
if c1.button("🏠 Sales"):
    st.session_state.forced_page = "Sales Entry"
    st.experimental_rerun()
if c2.button("📈 Forecast"):
    st.session_state.forced_page = "Forecasting"
    st.experimental_rerun()
if c3.button("📊 Dashboard"):
    st.session_state.forced_page = "Inventory Dashboard"
    st.experimental_rerun()
if c4.button("📁 Reports"):
    st.session_state.forced_page = "Reports"
    st.experimental_rerun()
if c5.button("❓ Help"):
    st.session_state.forced_page = "Help"
    st.experimental_rerun()
