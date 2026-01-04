import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import plotly.graph_objects as go
import plotly.express as px

st.set_page_config(page_title="Debt Payoff Planner", layout="wide")
st.title("💳 Debt Payoff Planner")

# -------------------------------------------------
# LOCAL STORAGE HELPERS (JS-based, Cloud-safe)
# -------------------------------------------------
def load_from_local_storage(key):
    result = st.components.v1.html(
        f"""
        <script>
        const data = localStorage.getItem("{key}");
        document.write(data ? data : "");
        </script>
        """,
        height=0,
    )
    return result

def save_to_local_storage(key, value):
    json_value = json.dumps(value)
    st.components.v1.html(
        f"""
        <script>
        localStorage.setItem("{key}", `{json_value}`);
        </script>
        """,
        height=0,
    )

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
if "debts" not in st.session_state:
    stored = load_from_local_storage("debts")
    if stored:
        try:
            st.session_state.debts = json.loads(stored)
        except:
            st.session_state.debts = []
    else:
        st.session_state.debts = []

if "editing_index" not in st.session_state:
    st.session_state.editing_index = None

# -------------------------------------------------
# CALCULATE PAYOFF SCHEDULE
# -------------------------------------------------
def calculate_payoff_schedule(debts_df, strategy, monthly_budget):
    """Calculate detailed payoff schedule with monthly snapshots"""
    if debts_df.empty:
        return None, 0, 0, []
    
    if strategy == "Snowball":
        df = debts_df.sort_values("Balance").copy()
    else:
        df = debts_df.sort_values("APR", ascending=False).copy()
    
    balances = df.copy()
    current_date = datetime.today()
    total_interest = 0
    months = 0
    schedule = []
    
    while balances["Balance"].sum() > 0 and months < 600:  # Safety limit
        remaining_budget = monthly_budget
        month_snapshot = {"Month": months + 1, "Date": current_date.strftime("%b %Y")}
        
        for i, row in balances.iterrows():
            if row["Balance"] <= 0:
                month_snapshot[row["Name"]] = 0
                continue
            
            interest = row["Balance"] * (row["APR"] / 12)
            total_interest += interest
            
            payment = min(
                row["Balance"] + interest,
                max(row["MinPayment"], remaining_budget)
            )
            
            balances.loc[i, "Balance"] = row["Balance"] + interest - payment
            month_snapshot[row["Name"]] = max(0, balances.loc[i, "Balance"])
            remaining_budget -= payment
            
            if remaining_budget <= 0:
                break
        
        schedule.append(month_snapshot)
        months += 1
        current_date += relativedelta(months=1)
    
    return balances, total_interest, months, schedule

# -------------------------------------------------
# ADD DEBT FORM
# -------------------------------------------------
with st.expander("➕ Add a Debt", expanded=len(st.session_state.debts) == 0):
    with st.form("add_debt"):
        name = st.text_input("Debt name")
        debt_type = st.selectbox(
            "Debt type",
            ["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"]
        )
        balance = st.number_input("Balance ($)", min_value=0.0, format="%.2f")
        apr = st.number_input("APR (%)", min_value=0.0, format="%.2f")
        min_payment = st.number_input("Minimum Payment ($)", min_value=0.0, format="%.2f")
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
            save_to_local_storage("debts", st.session_state.debts)
            st.success("✅ Debt added!")
            st.rerun()

# -------------------------------------------------
# MAIN APP
# -------------------------------------------------
if st.session_state.debts:
    df = pd.DataFrame(st.session_state.debts)
    
    st.subheader("📋 Your Debts")
    
    # Display debts with edit/delete buttons
    for idx, debt in enumerate(st.session_state.debts):
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1.5, 1, 1, 1, 0.8, 0.8])
        
        with col1:
            st.write(f"**{debt['Name']}**")
        with col2:
            st.write(debt['Type'])
        with col3:
            st.write(f"${debt['Balance']:,.2f}")
        with col4:
            st.write(f"{debt['APR']*100:.2f}%")
        with col5:
            st.write(f"${debt['MinPayment']:,.2f}")
        with col6:
            if st.button("✏️", key=f"edit_{idx}"):
                st.session_state.editing_index = idx
                st.rerun()
        with col7:
            if st.button("🗑️", key=f"delete_{idx}"):
                st.session_state.debts.pop(idx)
                save_to_local_storage("debts", st.session_state.debts)
                st.rerun()
    
    st.divider()
    
    # Edit form
    if st.session_state.editing_index is not None:
        idx = st.session_state.editing_index
        debt = st.session_state.debts[idx]
        
        with st.expander("✏️ Edit Debt", expanded=True):
            with st.form("edit_debt"):
                name = st.text_input("Debt name", value=debt["Name"])
                debt_type = st.selectbox(
                    "Debt type",
                    ["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"],
                    index=["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"].index(debt["Type"])
                )
                balance = st.number_input("Balance ($)", min_value=0.0, value=debt["Balance"], format="%.2f")
                apr = st.number_input("APR (%)", min_value=0.0, value=debt["APR"]*100, format="%.2f")
                min_payment = st.number_input("Minimum Payment ($)", min_value=0.0, value=debt["MinPayment"], format="%.2f")
                due_day = st.slider("Due day of month", 1, 28, debt["DueDay"])
                
                col1, col2 = st.columns(2)
                with col1:
                    save = st.form_submit_button("💾 Save Changes")
                with col2:
                    cancel = st.form_submit_button("❌ Cancel")
                
                if save and name:
                    st.session_state.debts[idx] = {
                        "Name": name,
                        "Type": debt_type,
                        "Balance": balance,
                        "APR": apr / 100,
                        "MinPayment": min_payment,
                        "DueDay": due_day
                    }
                    save_to_local_storage("debts", st.session_state.debts)
                    st.session_state.editing_index = None
                    st.success("✅ Changes saved!")
                    st.rerun()
                
                if cancel:
                    st.session_state.editing_index = None
                    st.rerun()
    
    # -------------------------------------------------
    # PAYOFF SETTINGS
    # -------------------------------------------------
    st.subheader("⚙️ Payoff Settings")
    col1, col2 = st.columns(2)
    
    with col1:
        strategy = st.radio("Payoff Strategy", ["Snowball", "Avalanche"])
        st.caption("**Snowball**: Pay off smallest balance first  \n**Avalanche**: Pay off highest APR first")
    
    with col2:
        monthly_budget = st.number_input(
            "Total Monthly Debt Budget ($)",
            min_value=float(df["MinPayment"].sum()),
            value=float(df["MinPayment"].sum()),
            format="%.2f"
        )
        extra_payment = monthly_budget - df["MinPayment"].sum()
        st.caption(f"Extra payment: **${extra_payment:,.2f}** per month")
    
    # -------------------------------------------------
    # CALCULATIONS
    # -------------------------------------------------
    balances, total_interest, months, schedule = calculate_payoff_schedule(df, strategy, monthly_budget)
    
    if schedule:
        payoff_date = (datetime.today() + relativedelta(months=months)).strftime("%B %Y")
        
        st.subheader("📈 Payoff Results")
        col1, col2, col3 = st.columns(3)
        col1.metric("Payoff Date", payoff_date)
        col2.metric("Months to Payoff", months)
        col3.metric("Total Interest Paid", f"${total_interest:,.2f}")
        
        # -------------------------------------------------
        # CHARTS
        # -------------------------------------------------
        st.subheader("📊 Payoff Visualization")
        
        schedule_df = pd.DataFrame(schedule)
        
        # Balance over time chart
        fig = go.Figure()
        
        for debt_name in df["Name"]:
            if debt_name in schedule_df.columns:
                fig.add_trace(go.Scatter(
                    x=schedule_df["Date"],
                    y=schedule_df[debt_name],
                    name=debt_name,
                    mode='lines',
                    stackgroup='one',
                    fill='tonexty'
                ))
        
        fig.update_layout(
            title="Debt Balance Over Time",
            xaxis_title="Month",
            yaxis_title="Balance ($)",
            hovermode='x unified',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Debt breakdown pie chart
        fig2 = px.pie(
            df,
            values='Balance',
            names='Name',
            title='Current Debt Distribution',
            hole=0.3
        )
        fig2.update_traces(textposition='inside', textinfo='percent+label')
        
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(fig2, use_container_width=True)
        
        with col2:
            # Interest by debt
            interest_by_debt = []
            for _, row in df.iterrows():
                total_int = row['Balance'] * (row['APR'] / 12) * months
                interest_by_debt.append({
                    'Name': row['Name'],
                    'Interest': total_int
                })
            
            fig3 = px.bar(
                pd.DataFrame(interest_by_debt),
                x='Name',
                y='Interest',
                title='Estimated Interest by Debt',
                labels={'Interest': 'Interest ($)'}
            )
            st.plotly_chart(fig3, use_container_width=True)
    
    # -------------------------------------------------
    # CALENDAR
    # -------------------------------------------------
    st.subheader("📅 Monthly Bill Calendar")
    calendar = df[["Name", "Type", "MinPayment", "DueDay"]].copy()
    calendar = calendar.sort_values("DueDay")
    calendar["Due Date"] = calendar["DueDay"].apply(lambda x: f"{x}th of each month")
    calendar["Min Payment"] = calendar["MinPayment"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(
        calendar[["Name", "Type", "Min Payment", "Due Date"]], 
        use_container_width=True,
        hide_index=True
    )
    
    # -------------------------------------------------
    # EXPORT & CLEAR
    # -------------------------------------------------
    st.divider()
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Export to CSV
        csv = schedule_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Payment Schedule (CSV)",
            data=csv,
            file_name=f"debt_payoff_schedule_{datetime.today().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    with col3:
        if st.button("🗑️ Clear All Data", type="secondary"):
            if st.session_state.get("confirm_clear"):
                st.session_state.debts = []
                st.session_state.editing_index = None
                st.session_state.confirm_clear = False
                save_to_local_storage("debts", [])
                st.rerun()
            else:
                st.session_state.confirm_clear = True
                st.warning("⚠️ Click again to confirm deletion")

else:
    st.info("👆 Add at least one debt to get started using the form above!")
