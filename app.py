import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
import matplotlib.pyplot as plt

st.set_page_config(page_title="📦 Smart Shopkeeper Assistant", layout="centered")

# Initialize session state
if 'sales_data' not in st.session_state:
    st.session_state.sales_data = pd.DataFrame(columns=["Date", "Product", "Quantity"])

if 'selected_product' not in st.session_state:
    st.session_state.selected_product = ""

# Navigation
page = st.sidebar.selectbox("📌 Choose Page", ["Sales Entry", "Forecast & Order Suggestion"])

# -----------------------------
# PAGE 1: Daily Sales Entry
# -----------------------------
if page == "Sales Entry":
    st.title("🛒 Daily Sales Entry")

    st.markdown("### 🛍️ Select a Product")

    # Product list with emojis
    product_list = [
        ("🥛 Milk", "Milk"),
        ("🍪 Biscuit", "Biscuit"),
        ("🍞 Bread", "Bread"),
        ("🧃 Juice", "Juice"),
        ("🍚 Rice", "Rice"),
        ("🛢️ Oil", "Oil"),
        ("🍫 Chocolate", "Chocolate"),
        ("🧂 Salt", "Salt"),
        ("🧼 Soap", "Soap"),
        ("🧻 Tissue", "Tissue")
    ]

    # Display in 5-column layout
    cols = st.columns(5)
    for idx, (emoji_name, value) in enumerate(product_list):
        with cols[idx % 5]:
            if st.button(emoji_name):
                st.session_state.selected_product = value

    # Auto-filled product field
    product = st.text_input("Selected Product", value=st.session_state.selected_product, disabled=True)
    quantity = st.number_input("Quantity Sold", min_value=1, step=1)
    date = st.date_input("Date", value=datetime.today())

    if st.button("➕ Add Sale"):
        if st.session_state.selected_product == "":
            st.warning("Please select a product.")
        else:
            new_entry = {"Date": date, "Product": st.session_state.selected_product, "Quantity": quantity}
            st.session_state.sales_data = pd.concat(
                [st.session_state.sales_data, pd.DataFrame([new_entry])],
                ignore_index=True
            )
            st.success(f"✅ Added: {quantity} x {st.session_state.selected_product} on {date}")

    st.subheader("📋 Sales History")
    st.dataframe(st.session_state.sales_data)

# -----------------------------
# PAGE 2: Forecast & Suggestion
# -----------------------------
if page == "Forecast & Order Suggestion":
    st.title("📈 Forecast & Order Recommendations")

    data = st.session_state.sales_data.copy()

    if data.empty:
        st.info("Please enter some sales data first.")
        st.stop()

    data['Date'] = pd.to_datetime(data['Date'])
    data = data.sort_values('Date')

    st.write("Enter your current stock for each product:")

    for product in data['Product'].unique():
        st.markdown(f"---\n### 📦 Product: **{product}**")

        df = data[data['Product'] == product]
        df = df.groupby("Date").agg({"Quantity": "sum"}).reset_index()
        df.rename(columns={"Quantity": "Sales"}, inplace=True)

        if len(df) < 2:
            st.warning(f"Not enough data to forecast **{product}** (need 2+ entries).")
            continue

        df['Day'] = df['Date'].dt.day
        df['Month'] = df['Date'].dt.month
        df['Weekday'] = df['Date'].dt.weekday
        df['Lag_1'] = df['Sales'].shift(1)
        df.dropna(inplace=True)

        if df.empty:
            st.warning(f"⚠️ Not enough lag data for **{product}**.")
            continue

        X = df[['Day', 'Month', 'Weekday', 'Lag_1']]
        y = df['Sales']

        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X, y)

        last_date = df['Date'].max()
        future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=7)

        recent_sales = list(df['Sales'].iloc[-1:])
        future_preds = []

        for date in future_dates:
            features = {
                'Day': date.day,
                'Month': date.month,
                'Weekday': date.weekday(),
                'Lag_1': recent_sales[-1],
            }
            pred = model.predict(pd.DataFrame([features]))[0]
            future_preds.append(pred)
            recent_sales.append(pred)

        forecast_df = pd.DataFrame({'Date': future_dates, 'Predicted Sales': np.round(future_preds)})
        st.dataframe(forecast_df)

        avg_demand = np.mean(future_preds)
        reorder_point = avg_demand * 3  # lead time = 3 days
        eoq = np.sqrt((2 * avg_demand * 365 * 50) / 1)  # ordering cost = 50, holding cost = 1

        current_stock = st.number_input(f"Current stock of {product}:", min_value=0, value=0, key=product)

        st.markdown(f"📌 **Reorder Point:** `{reorder_point:.0f}` units")
        st.markdown(f"📌 **EOQ (suggested order quantity):** `{eoq:.0f}` units")

        if current_stock < reorder_point:
            st.success(f"🛒 **Order Now!** Your stock ({current_stock}) is below the reorder point.")
        else:
            st.info(f"✅ **Stock OK.** You have enough stock for upcoming demand.")
