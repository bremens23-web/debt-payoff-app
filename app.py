import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import json
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client
import uuid

st.set_page_config(page_title="Debt Payoff Planner", layout="wide")
st.title("💳 Debt Payoff Planner")

# -------------------------------------------------
# SUPABASE SETUP
# -------------------------------------------------
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_supabase()
except:
    st.error("⚠️ Database connection failed. Please check your Supabase credentials in secrets.")
    st.stop()

# -------------------------------------------------
# USER ID MANAGEMENT
# -------------------------------------------------
if "user_id" not in st.session_state:
    # Generate a unique user ID for this browser session
    st.session_state.user_id = f"user_{uuid.uuid4().hex[:12]}"
    
# Store user ID in browser for persistence across sessions
st.components.v1.html(
    f"""
    <script>
    localStorage.setItem("debt_tracker_user_id", "{st.session_state.user_id}");
    </script>
    """,
    height=0,
)

# -------------------------------------------------
# DATABASE FUNCTIONS
# -------------------------------------------------
def load_debts_from_db():
    """Load debts from Supabase for current user"""
    try:
        response = supabase.table("debts").select("*").eq("user_id", st.session_state.user_id).execute()
        return response.data
    except Exception as e:
        st.error(f"Error loading debts: {e}")
        return []

def save_debt_to_db(debt):
    """Save a new debt to Supabase"""
    try:
        debt["user_id"] = st.session_state.user_id
        response = supabase.table("debts").insert(debt).execute()
        return True
    except Exception as e:
        st.error(f"Error saving debt: {e}")
        return False

def update_debt_in_db(debt_id, debt):
    """Update existing debt in Supabase"""
    try:
        response = supabase.table("debts").update(debt).eq("id", debt_id).execute()
        return True
    except Exception as e:
        st.error(f"Error updating debt: {e}")
        return False

def delete_debt_from_db(debt_id):
    """Delete debt from Supabase"""
    try:
        response = supabase.table("debts").delete().eq("id", debt_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting debt: {e}")
        return False

def clear_all_debts_from_db():
    """Delete all debts for current user"""
    try:
        response = supabase.table("debts").delete().eq("user_id", st.session_state.user_id).execute()
        return True
    except Exception as e:
        st.error(f"Error clearing debts: {e}")
        return False

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
if "debts" not in st.session_state or st.session_state.get("reload_debts"):
    st.session_state.debts = load_debts_from_db()
    st.session_state.reload_debts = False

if "editing_index" not in st.session_state:
    st.session_state.editing_index = None

# -------------------------------------------------
# CALCULATE PAYOFF SCHEDULE
# -------------------------------------------------
def calculate_payoff_schedule(debts_list, strategy, monthly_budget):
    """Calculate detailed payoff schedule with monthly snapshots"""
    if not debts_list:
        return None, 0, 0, []
    
    # Convert to DataFrame
    df = pd.DataFrame([{
        "Name": d["name"],
        "Type": d["type"],
        "Balance": d["balance"],
        "APR": d["apr"],
        "MinPayment": d["min_payment"],
        "DueDay": d["due_day"]
    } for d in debts_list])
    
    if strategy == "Snowball":
        df = df.sort_values("Balance").copy()
    else:
        df = df.sort_values("APR", ascending=False).copy()
    
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
            new_debt = {
                "name": name,
                "type": debt_type,
                "balance": balance,
                "apr": apr / 100,
                "min_payment": min_payment,
                "due_day": due_day
            }
            if save_debt_to_db(new_debt):
                st.success("✅ Debt added!")
                st.session_state.reload_debts = True
                st.rerun()

# -------------------------------------------------
# MAIN APP
# -------------------------------------------------
if st.session_state.debts:
    debts_list = st.session_state.debts
    
    st.subheader("📋 Your Debts")
    
    # Display debts with edit/delete buttons
    for debt in debts_list:
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1.5, 1, 1, 1, 0.8, 0.8])
        
        with col1:
            st.write(f"**{debt['name']}**")
        with col2:
            st.write(debt['type'])
        with col3:
            st.write(f"${debt['balance']:,.2f}")
        with col4:
            st.write(f"{debt['apr']*100:.2f}%")
        with col5:
            st.write(f"${debt['min_payment']:,.2f}")
        with col6:
            if st.button("✏️", key=f"edit_{debt['id']}"):
                st.session_state.editing_debt = debt
                st.rerun()
        with col7:
            if st.button("🗑️", key=f"delete_{debt['id']}"):
                if delete_debt_from_db(debt['id']):
                    st.session_state.reload_debts = True
                    st.rerun()
    
    st.divider()
    
    # Edit form
    if st.session_state.get("editing_debt"):
        debt = st.session_state.editing_debt
        
        with st.expander("✏️ Edit Debt", expanded=True):
            with st.form("edit_debt"):
                name = st.text_input("Debt name", value=debt["name"])
                debt_type = st.selectbox(
                    "Debt type",
                    ["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"],
                    index=["Credit Card", "Student Loan", "Auto Loan", "Personal Loan", "Other"].index(debt["type"])
                )
                balance = st.number_input("Balance ($)", min_value=0.0, value=float(debt["balance"]), format="%.2f")
                apr = st.number_input("APR (%)", min_value=0.0, value=float(debt["apr"])*100, format="%.2f")
                min_payment = st.number_input("Minimum Payment ($)", min_value=0.0, value=float(debt["min_payment"]), format="%.2f")
                due_day = st.slider("Due day of month", 1, 28, int(debt["due_day"]))
                
                col1, col2 = st.columns(2)
                with col1:
                    save = st.form_submit_button("💾 Save Changes")
                with col2:
                    cancel = st.form_submit_button("❌ Cancel")
                
                if save and name:
                    updated_debt = {
                        "name": name,
                        "type": debt_type,
                        "balance": balance,
                        "apr": apr / 100,
                        "min_payment": min_payment,
                        "due_day": due_day
                    }
                    if update_debt_in_db(debt['id'], updated_debt):
                        st.success("✅ Changes saved!")
                        st.session_state.editing_debt = None
                        st.session_state.reload_debts = True
                        st.rerun()
                
                if cancel:
                    st.session_state.editing_debt = None
                    st.rerun()
    
    # -------------------------------------------------
    # PAYOFF SETTINGS
    # -------------------------------------------------
    st.subheader("⚙️ Payoff Settings")
    col1, col2 = st.columns(2)
    
    # Calculate total minimum payment
    total_min = sum(d["min_payment"] for d in debts_list)
    
    with col1:
        strategy = st.radio("Payoff Strategy", ["Snowball", "Avalanche"])
        st.caption("**Snowball**: Pay off smallest balance first  \n**Avalanche**: Pay off highest APR first")
    
    with col2:
        monthly_budget = st.number_input(
            "Total Monthly Debt Budget ($)",
            min_value=float(total_min),
            value=float(total_min),
            format="%.2f"
        )
        extra_payment = monthly_budget - total_min
        st.caption(f"Extra payment: **${extra_payment:,.2f}** per month")
    
    # -------------------------------------------------
    # CALCULATIONS
    # -------------------------------------------------
    balances, total_interest, months, schedule = calculate_payoff_schedule(debts_list, strategy, monthly_budget)
    
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
        
        for debt in debts_list:
            debt_name = debt["name"]
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
        
        # Create DataFrames for charts
        chart_df = pd.DataFrame([{
            'Name': d['name'],
            'Balance': d['balance']
        } for d in debts_list])
        
        # Debt breakdown pie chart
        fig2 = px.pie(
            chart_df,
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
            for debt in debts_list:
                total_int = debt['balance'] * (debt['apr'] / 12) * months
                interest_by_debt.append({
                    'Name': debt['name'],
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
    calendar_data = [{
        'Name': d['name'],
        'Type': d['type'],
        'Min Payment': f"${d['min_payment']:,.2f}",
        'Due Date': f"{d['due_day']}th of each month"
    } for d in sorted(debts_list, key=lambda x: x['due_day'])]
    
    st.dataframe(
        pd.DataFrame(calendar_data), 
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
        if schedule:
            csv = pd.DataFrame(schedule).to_csv(index=False)
            st.download_button(
                label="📥 Download Payment Schedule (CSV)",
                data=csv,
                file_name=f"debt_payoff_schedule_{datetime.today().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    with col3:
        if st.button("🗑️ Clear All Data", type="secondary"):
            if st.session_state.get("confirm_clear"):
                if clear_all_debts_from_db():
                    st.session_state.debts = []
                    st.session_state.editing_debt = None
                    st.session_state.confirm_clear = False
                    st.success("✅ All data cleared!")
                    st.rerun()
            else:
                st.session_state.confirm_clear = True
                st.warning("⚠️ Click again to confirm deletion")

else:
    st.info("👆 Add at least one debt to get started using the form above!")
