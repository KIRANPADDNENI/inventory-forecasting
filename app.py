# app.py
"""
Smart Shopkeeper Assistant — with Gmail alerts (App Password)
Features:
- Prophet forecasting (optional)
- Fallback forecast if Prophet missing or insufficient data
- Plotly optional (falls back to Matplotlib)
- Gmail alerts using App Password (from st.secrets or sidebar)
- No DB, no signup — session-state only
"""

import streamlit as st
import pandas as pd
import numpy as np

# -----------------------
# Optional imports: Prophet, Plotly
# -----------------------
USE_PROPHET = True
try:
    from prophet import Prophet
except Exception:
    USE_PROPHET = False

px_available = True
try:
    import plotly.express as px
except Exception:
    px_available = False

from datetime import datetime
from io import BytesIO
import matplotlib.pyplot as plt
import smtplib
from email.message import EmailMessage
import traceback

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

if "forced_page" not in st.session_state:
    st.session_state.forced_page = None

# ----------------------------
# Sidebar MENU + settings + Gmail
# ----------------------------
sidebar_page = st.sidebar.selectbox("📌 Menu", ["Sales Entry", "Forecasting", "Inventory Dashboard", "Reports", "Help"])
st.sidebar.markdown("---")

st.sidebar.subheader("📈 Forecast Settings")
forecast_days = st.sidebar.number_input("Forecast Horizon (days)", min_value=3, max_value=60, value=7)
lead_time_days = st.sidebar.number_input("Lead Time (days)", min_value=1, max_value=14, value=3)

st.sidebar.subheader("📤 Export")
export_filename = st.sidebar.text_input("Export filename (Excel)", value="shop_report.xlsx")

st.sidebar.subheader("🔔 Gmail Alerts")
enable_email = st.sidebar.checkbox("Enable Gmail Alerts", value=False)

# First priority: secrets (recommended). Fall back to entering in sidebar fields if secrets absent.
secrets_gmail_id = st.secrets.get("gmail_id") if hasattr(st, "secrets") else None
secrets_gmail_pass = st.secrets.get("gmail_pass") if hasattr(st, "secrets") else None
secrets_alert_recipient = st.secrets.get("alert_recipient") if hasattr(st, "secrets") else None

if enable_email:
    # show fields but prefill with secrets if available (but do not expose secrets in logs)
    gmail_id_input = st.sidebar.text_input("Gmail (sender)", value=secrets_gmail_id or "")
    gmail_pass_input = st.sidebar.text_input("Gmail App Password", type="password", value=secrets_gmail_pass or "")
    alert_recipient_input = st.sidebar.text_input("Recipient Email", value=secrets_alert_recipient or "")
else:
    gmail_id_input = gmail_pass_input = alert_recipient_input = ""

page = st.session_state.forced_page if st.session_state.forced_page else sidebar_page

# ----------------------------
# Helper functions: email, export, pdf, charts
# ----------------------------
def send_gmail_alert(product, current_stock, reorder_point, avg_demand):
    """
    Sends a low-stock alert via Gmail SMTP.
    Uses st.secrets.gmail_id/gmail_pass/alert_recipient if present; else uses sidebar inputs.
    IMPORTANT: Use an App Password (16-char) for gmail_pass when 2FA is enabled.
    """
    if not enable_email:
        return False, "Email alerts disabled"

    # Resolve credentials: secrets preferred, then sidebar inputs
    gmail_id = secrets_gmail_id or gmail_id_input
    gmail_pass = secrets_gmail_pass or gmail_pass_input
    recipient = secrets_alert_recipient or alert_recipient_input

    if not (gmail_id and gmail_pass and recipient):
        return False, "SMTP fields missing (set secrets or enter in sidebar)"

    try:
        msg = EmailMessage()
        msg["Subject"] = f"Low Stock Alert - {product}"
        msg["From"] = gmail_id
        msg["To"] = recipient
        msg.set_content(
            f"⚠️ LOW STOCK ALERT\n\n"
            f"Product: {product}\n"
            f"Current stock: {current_stock}\n"
            f"Reorder point: {int(reorder_point)}\n"
            f"Avg daily demand (forecast): {avg_demand:.2f}\n\n"
            f"Sent by Smart Shopkeeper Assistant."
        )

        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.ehlo()
        server.starttls()
        server.login(gmail_id, gmail_pass)
        server.send_message(msg)
        server.quit()
        return True, "Email sent"
    except Exception as e:
        # return a readable error; in Streamlit logs full traceback is available if user expands
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

# plotting helpers (Plotly optional)
def render_line_chart(df, x, y, title=None, use_container_width=True):
    if px_available:
        fig = px.line(df, x=x, y=y, title=title)
        st.plotly_chart(fig, use_container_width=use_container_width)
    else:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(df[x], df[y], marker="o")
        if title:
            ax.set_title(title)
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.grid(True)
        st.pyplot(fig)
        plt.close(fig)

def render_bar_chart(df, x, y, title=None, use_container_width=True):
    if px_available:
        fig = px.bar(df, x=x, y=y, title=title)
        st.plotly_chart(fig, use_container_width=use_container_width)
    else:
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(df[x].astype(str), df[y])
        if title:
            ax.set_title(title)
        ax.set_xlabel(x)
        ax.set_ylabel(y)
        ax.grid(True, axis='y')
        plt.xticks(rotation=45, ha='right')
        st.pyplot(fig)
        plt.close(fig)

def naive_forecast(history_df, days_ahead):
    """Fallback when Prophet isn't available or data is tiny."""
    h = history_df.copy()
    if h.empty:
        future_dates = pd.date_range(start=pd.Timestamp.today(), periods=days_ahead, freq='D')
        return pd.DataFrame({'Date': future_dates, 'Predicted Sales': [0]*days_ahead})
    h = h.set_index('Date').resample('D').sum().fillna(0)
    window = min(7, len(h))
    last_mean = 0 if window == 0 else h['Quantity'].tail(window).mean()
    future_dates = pd.date_range(start=h.index.max() + pd.Timedelta(days=1), periods=days_ahead, freq='D')
    preds = [int(round(last_mean)) for _ in range(days_ahead)]
    return pd.DataFrame({'Date': future_dates, 'Predicted Sales': preds})

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
    "Milk": "🥛", "Bread": "🍞", "Biscuit": "🍪", "Chocolate": "🍫", "Juice": "🧃",
    "Soap": "🧼", "Oil": "🛢️", "Rice": "🍚", "Salt": "🧂", "Tissue": "🧻",
}

# ----------------------------
# PAGE: Sales Entry
# ----------------------------
if page == "Sales Entry":
    st.title("🛒 Daily Sales Entry")

    with st.expander("➕ Add / edit product list"):
        new_prod = st.text_input("Product name to add")
        if st.button("Add product"):
            if new_prod.strip():
                p = new_prod.strip()
                if p not in st.session_state.product_list:
                    st.session_state.product_list.append(p)
                    st.success(f"Added product: {p}")
                else:
                    st.info("Product already exists.")

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
        if not product.strip():
            st.warning("Please enter a product name.")
        else:
            new_row = {"Date": pd.to_datetime(date), "Product": product.strip(), "Quantity": int(qty)}
            st.session_state.sales_data = pd.concat(
                [st.session_state.sales_data, pd.DataFrame([new_row])],
                ignore_index=True
            )
            st.success(f"Added sale: {qty} × {product}")

    st.markdown("---")
    st.subheader("📋 Sales History")
    if st.session_state.sales_data.empty:
        st.info("No sales yet.")
    else:
        st.dataframe(st.session_state.sales_data.sort_values("Date", ascending=False))

# ----------------------------
# PAGE: Forecasting
# ----------------------------
if page == "Forecasting":
    st.title("📈 Forecasting")

    data = st.session_state.sales_data.copy()
    if data.empty:
        st.info("No sales data. Please add sales first.")
        st.stop()

    data["Date"] = pd.to_datetime(data["Date"])
    product_list = sorted(data["Product"].unique())
    selected_product = st.selectbox("Select product", product_list)

    prod_hist = (
        data[data["Product"] == selected_product]
        .groupby("Date")["Quantity"]
        .sum()
        .reset_index()
        .sort_values("Date")
    )
    prod_hist = prod_hist.set_index("Date").asfreq("D").fillna(0).reset_index()

    st.subheader("Last 30 days")
    st.dataframe(prod_hist.tail(30))

    dfp = prod_hist.rename(columns={"Date": "ds", "Quantity": "y"}).copy()
    dfp["ds"] = pd.to_datetime(dfp["ds"])
    dfp["y"] = pd.to_numeric(dfp["y"], errors="coerce").fillna(0)

    # Decide: Prophet or fallback?
    if USE_PROPHET and dfp["y"].count() >= 2:
        try:
            model = Prophet(weekly_seasonality=True)
            model.fit(dfp)
            future = model.make_future_dataframe(periods=int(forecast_days))
            forecast = model.predict(future)
            forecast_display = (
                forecast[forecast["ds"] > prod_hist["Date"].max()]
                [["ds", "yhat"]]
                .rename(columns={"ds": "Date", "yhat": "Predicted Sales"})
            )
            forecast_display["Predicted Sales"] = (
                forecast_display["Predicted Sales"].clip(lower=0).round().astype(int)
            )
        except Exception as e:
            st.warning("Prophet failed — using fallback forecast instead.")
            with st.expander("Prophet error (traceback)"):
                st.text(traceback.format_exc())
            forecast_display = naive_forecast(prod_hist, int(forecast_days))
    else:
        if not USE_PROPHET:
            st.info("Prophet not available. Using fallback forecast.")
        else:
            st.info("Insufficient data for Prophet. Using fallback forecast.")
        forecast_display = naive_forecast(prod_hist, int(forecast_days))

    st.subheader(f"{forecast_days}-day Forecast")
    st.dataframe(forecast_display)

    # Chart
    combined = pd.concat([
        prod_hist.rename(columns={"Date": "Date", "Quantity": "Sales"})[["Date", "Sales"]],
        forecast_display.rename(columns={"Date": "Date", "Predicted Sales": "Sales"})[["Date", "Sales"]],
    ])
    render_line_chart(combined, x="Date", y="Sales", title=f"History + Forecast: {selected_product}")

    # Inventory suggestion
    avg_demand = float(forecast_display["Predicted Sales"].mean()) if len(forecast_display) > 0 else 0.0
    reorder_point = avg_demand * lead_time_days

    c1, c2 = st.columns(2)
    c1.metric("Avg daily demand", f"{avg_demand:.2f}")
    c2.metric("Reorder point", f"{int(reorder_point)} units")

    stock_key = f"stock_{selected_product}"
    if stock_key not in st.session_state:
        st.session_state[stock_key] = 0

    current_stock = st.number_input(
        f"Current stock for {selected_product}",
        min_value=0,
        value=st.session_state[stock_key],
        key=stock_key
    )

    if current_stock < reorder_point:
        st.error(f"⚠️ LOW STOCK: {current_stock} < {int(reorder_point)}")
        # Offer to send Gmail alert if enabled
        if enable_email:
            if st.button("📧 Send Gmail Alert"):
                success, msg = send_gmail_alert(selected_product, current_stock, reorder_point, avg_demand)
                if success:
                    st.success("📧 Gmail alert sent.")
                else:
                    st.error(f"Email failed: {msg}")
    else:
        st.success("Stock is OK ✔")

    # Downloads
    st.markdown("---")
    excel_data = excel_bytes_multi(
        data[data["Product"] == selected_product],
        forecast_display
    )
    st.download_button("📥 Download Forecast Excel", data=excel_data, file_name=f"{selected_product}_forecast.xlsx")
    pdf_data = pdf_quick_report(
        prod_hist.rename(columns={"Date": "Date", "Quantity": "Quantity"}).tail(30),
        forecast_display,
        selected_product
    )
    st.download_button("📄 Download PDF Report", data=pdf_data, file_name=f"{selected_product}_report.pdf")

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

    total_by_product = data.groupby("Product")["Quantity"].sum().reset_index()
    recent_from = pd.Timestamp.today() - pd.Timedelta(days=window_days)
    recent = (
        data[data["Date"] >= recent_from]
        .groupby("Product")["Quantity"]
        .sum()
        .reset_index()
    )

    summary = pd.merge(total_by_product, recent, on="Product", how="left").fillna(0)
    # normalize columns
    if "Quantity_y" in summary.columns:
        summary = summary.rename(columns={"Quantity_x": "TotalSold", "Quantity_y": "SoldRecent"})
    else:
        summary = summary.rename(columns={"Quantity": "TotalSold"})
        if "SoldRecent" not in summary.columns:
            recent_map = recent.set_index("Product")["Quantity"].to_dict()
            summary["SoldRecent"] = summary["Product"].map(recent_map).fillna(0)

    summary["SoldRecent"] = pd.to_numeric(summary["SoldRecent"], errors="coerce").fillna(0)
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
        render_bar_chart(movers, x="Product", y="SoldRecent", title="Top movers (recent)")

    st.subheader("Monthly Sales")
    monthly = data.copy()
    monthly["Month"] = monthly["Date"].dt.to_period("M").astype(str)
    monthly_agg = monthly.groupby(["Month", "Product"])["Quantity"].sum().reset_index()
    if px_available:
        fig_month = px.bar(monthly_agg, x="Month", y="Quantity", color="Product", title="Monthly Sales", barmode="group")
        st.plotly_chart(fig_month, use_container_width=True)
    else:
        try:
            pivot = monthly_agg.pivot(index="Month", columns="Product", values="Quantity").fillna(0)
            fig, ax = plt.subplots(figsize=(10, 5))
            pivot.plot(kind="bar", ax=ax)
            ax.set_title("Monthly Sales")
            ax.set_xlabel("Month")
            ax.set_ylabel("Quantity")
            plt.xticks(rotation=45, ha='right')
            st.pyplot(fig)
            plt.close(fig)
        except Exception:
            st.write("Plotly not available and Matplotlib grouped bar failed to render.")

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
    else:
        st.dataframe(data.sort_values("Date"))

# ----------------------------
# PAGE: Help
# ----------------------------
if page == "Help":
    st.title("ℹ️ Help")
    st.markdown("""
    • Add daily sales in **Sales Entry**  
    • Get demand forecast in **Forecasting**  
    • View stock health in **Inventory Dashboard**  
    • To enable Gmail alerts: set `gmail_id`, `gmail_pass` (App Password), and `alert_recipient` in Streamlit Secrets or enter them in the sidebar.
    """)

# ----------------------------
# Bottom navigation
# ----------------------------
st.markdown("---")
cols = st.columns(5)
if cols[0].button("🏠 Sales"): st.session_state.forced_page = "Sales Entry"; st.experimental_rerun()
if cols[1].button("📈 Forecast"): st.session_state.forced_page = "Forecasting"; st.experimental_rerun()
if cols[2].button("📊 Dashboard"): st.session_state.forced_page = "Inventory Dashboard"; st.experimental_rerun()
if cols[3].button("📁 Reports"): st.session_state.forced_page = "Reports"; st.experimental_rerun()
if cols[4].button("❓ Help"): st.session_state.forced_page = "Help"; st.experimental_rerun()
