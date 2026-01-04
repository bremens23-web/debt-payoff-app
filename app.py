import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from streamlit_local_storage import LocalStorage

st.set_page_config(page_title="Debt Payoff Planner", layout="wide")

st.title("💳 Debt Payoff Planner")

local_storage = LocalStorage()

# -------------------------
# LOAD FROM LOCAL STORAGE
# -------------------------
stored_debts = local_storage.getItem("debts")

if stored_debts and "debts" not in st.session_state:
    st.session_state.debts = stored_debts
elif "debts" not in st.session_state:
    st.session_state.debts = []

# -------------------------
# ADD DEBT FORM
# -------------------------
with st.expander("➕ Add a Debt", expanded=True):
    with st.form("add_debt"):
        name = st.text_input("Debt name")
        debt_type = st.selectbox(
            "Debt type",
            ["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"]
        )
        balance = st.number_input("Balance ($)", min_value=0.0)
        apr = st.number_input("APR (%)", min_value=0.0)
        min_payment = st.number_input("Minimum Payment ($)", min_value=0.0)
        due_day = st.slider("Due day of month", 1, 28, 1)

        submitted = st.form_submit_button("Add Debt")

        if submitted and name:
            st.session_state.debts.append({
                "Name": name,
                "Type": debt_type,
                "Balance": balance,
                "APR": apr / 100,
                "MinPayment": min_payment,
                "DueDay": due_day
            })
            local_storage.setItem("debts", st.session_state.debts)
            st.success("Debt added!")

# -------------------------
# SHOW DEBTS
# -------------------------
if st.session_state.debts:
    df = pd.DataFrame(st.session_state.debts)

    st.subheader("📋 Your Debts")
    st.dataframe(df, use_container_width=True)

    st.subheader("⚙️ Payoff Settings")
    strategy = st.radio("Payoff Strategy", ["Snowball", "Avalanche"])
    monthly_budget = st.number_input(
        "Total Monthly Debt Budget ($)",
        min_value=float(df["MinPayment"].sum()),
        value=float(df["MinPayment"].sum())
    )

    if strategy == "Snowball":
        df = df.sort_values("Balance")
    else:
        df = df.sort_values("APR", ascending=False)

    balances = df.copy()
    current_date = datetime.today()
    total_interest = 0
    months = 0

    while balances["Balance"].sum() > 0:
        remaining_budget = monthly_budget

        for i, row in balances.iterrows():
            if row["Balance"] <= 0:
                continue

            interest = row["Balance"] * (row["APR"] / 12)
            total_interest += interest

            payment = min(
                row["Balance"] + interest,
                max(row["MinPayment"], remaining_budget)
            )

            balances.loc[i, "Balance"] = row["Balance"] + interest - payment
            remaining_budget -= payment

            if remaining_budget <= 0:
                break

        months += 1
        current_date += relativedelta(months=1)

    st.subheader("📈 Payoff Results")
    col1, col2, col3 = st.columns(3)
    col1.metric("Payoff Date", current_date.strftime("%B %Y"))
    col2.metric("Months to Payoff", months)
    col3.metric("Total Interest Paid", f"${total_interest:,.2f}")

    st.subheader("📅 Monthly Bill Calendar")
    calendar = df[["Name", "Type", "MinPayment", "DueDay"]].copy()
    calendar["Due"] = calendar["DueDay"].apply(lambda x: f"Every month on the {x}th")
    st.dataframe(calendar, use_container_width=True)

    # -------------------------
    # CLEAR DATA BUTTON
    # -------------------------
    if st.button("🗑️ Clear All Data"):
        local_storage.deleteItem("debts")
        st.session_state.debts = []
        st.experimental_rerun()

else:
    st.info("Add at least one debt to get started.")
