import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import json
import plotly.graph_objects as go
import plotly.express as px
from supabase import create_client, Client
import uuid

st.set_page_config(page_title="Debt Payoff Planner", layout="wide", initial_sidebar_state="expanded")

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
    st.error("⚠️ Database connection failed. Please check your Supabase credentials.")
    st.stop()

# -------------------------------------------------
# USER ID MANAGEMENT
# -------------------------------------------------
def get_user_id():
    """Get or create a persistent user ID"""
    try:
        query_params = st.query_params
        if "user_id" in query_params:
            user_id = query_params["user_id"]
            if isinstance(user_id, list):
                user_id = user_id[0]
            return user_id
    except Exception as e:
        pass
    
    if "user_id" not in st.session_state:
        st.session_state.user_id = f"user_{uuid.uuid4().hex[:12]}"
    
    return st.session_state.user_id

st.session_state.user_id = get_user_id()

# Show user ID only on first load
if "show_user_id_banner" not in st.session_state:
    st.session_state.show_user_id_banner = True

if st.session_state.show_user_id_banner:
    col1, col2 = st.columns([5, 1])
    with col1:
        st.info(f"🔑 **Your User ID:** `{st.session_state.user_id}` | 💾 **Bookmark this page to save your data!**")
    with col2:
        if st.button("✕ Dismiss", key="dismiss_banner"):
            st.session_state.show_user_id_banner = False
            st.rerun()

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

def load_payments_from_db():
    """Load payment history from Supabase"""
    try:
        response = supabase.table("payments").select("*").eq("user_id", st.session_state.user_id).execute()
        return response.data
    except Exception as e:
        return []

def save_payment_to_db(payment):
    """Save payment record to Supabase"""
    try:
        payment["user_id"] = st.session_state.user_id
        response = supabase.table("payments").insert(payment).execute()
        return True
    except Exception as e:
        st.error(f"Error saving payment: {e}")
        return False

# -------------------------------------------------
# LOAD DATA
# -------------------------------------------------
if "debts" not in st.session_state or st.session_state.get("reload_debts"):
    st.session_state.debts = load_debts_from_db()
    st.session_state.reload_debts = False

if "payments" not in st.session_state or st.session_state.get("reload_payments"):
    st.session_state.payments = load_payments_from_db()
    st.session_state.reload_payments = False

# -------------------------------------------------
# CALCULATION FUNCTIONS
# -------------------------------------------------
def calculate_payoff_schedule(debts_list, strategy, monthly_budget, extra_payment_amount=0):
    """Calculate detailed payoff schedule"""
    if not debts_list:
        return None, 0, 0, []
    
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
    
    while balances["Balance"].sum() > 0 and months < 600:
        remaining_budget = monthly_budget + extra_payment_amount
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

def get_upcoming_bills(debts_list, days_ahead=7):
    """Get bills due in the next X days"""
    today = datetime.today()
    current_day = today.day
    upcoming = []
    
    for debt in debts_list:
        due_day = debt["due_day"]
        
        # Calculate next due date
        if due_day >= current_day:
            next_due = datetime(today.year, today.month, due_day)
        else:
            next_month = today + relativedelta(months=1)
            next_due = datetime(next_month.year, next_month.month, due_day)
        
        days_until = (next_due - today).days
        
        if 0 <= days_until <= days_ahead:
            upcoming.append({
                "name": debt["name"],
                "amount": debt["min_payment"],
                "due_date": next_due,
                "days_until": days_until
            })
    
    return sorted(upcoming, key=lambda x: x["days_until"])

# -------------------------------------------------
# SIDEBAR NAVIGATION
# -------------------------------------------------
st.sidebar.title("💳 Debt Planner")

# Initialize page in session state
if "current_page" not in st.session_state:
    st.session_state.current_page = "📊 Dashboard"

pages = ["📊 Dashboard", "💳 My Credit Cards", "🏦 My Loans", "📄 Bills", "📈 Payoff Planner"]

st.sidebar.markdown("### Navigation")

# CSS to remove button styling and left-align
st.markdown("""
<style>
    [data-testid="stSidebar"] button {
        background: none !important;
        border: none !important;
        box-shadow: none !important;
        padding: 8px 0 !important;
        text-align: left !important;
        width: 100% !important;
        color: inherit !important;
    }
    [data-testid="stSidebar"] button:hover {
        background-color: rgba(255, 255, 255, 0.1) !important;
    }
    [data-testid="stSidebar"] button p {
        text-align: left !important;
    }
</style>
""", unsafe_allow_html=True)

for page_name in pages:
    if st.session_state.current_page == page_name:
        st.sidebar.markdown(f"<div style='padding: 8px 0; font-weight: bold; color: #1f77b4;'>{page_name}</div>", unsafe_allow_html=True)
    else:
        if st.sidebar.button(page_name, key=f"nav_{page_name}"):
            st.session_state.current_page = page_name
            st.rerun()

page = st.session_state.current_page

st.sidebar.divider()
st.sidebar.caption("💡 **Tip:** Bookmark this page to keep your data!")

# -------------------------------------------------
# PAGE: DASHBOARD
# -------------------------------------------------
if page == "📊 Dashboard":
    st.title("📊 Dashboard")
    
    if not st.session_state.debts:
        st.info("👋 Welcome! Add your debts using the navigation menu to get started.")
    else:
        debts_list = st.session_state.debts
        
        # Calculate totals
        total_debt = sum(d["balance"] for d in debts_list)
        total_min_payment = sum(d["min_payment"] for d in debts_list)
        
        # Metrics
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Debt", f"${total_debt:,.2f}")
        col2.metric("Total Min Payment", f"${total_min_payment:,.2f}/mo")
        col3.metric("Number of Debts", len(debts_list))
        
        st.divider()
        
        # Two columns: pie chart and debt list
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Debt by Type")
            
            # Group by type
            type_totals = {}
            for debt in debts_list:
                debt_type = debt["type"]
                if debt_type not in type_totals:
                    type_totals[debt_type] = 0
                type_totals[debt_type] += debt["balance"]
            
            fig = px.pie(
                values=list(type_totals.values()),
                names=list(type_totals.keys()),
                title="Total Balance by Debt Type",
                hole=0.4
            )
            fig.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("All Debts")
            
            debt_summary = []
            for debt in debts_list:
                debt_summary.append({
                    "Name": debt["name"],
                    "Type": debt["type"],
                    "Balance": f"${debt['balance']:,.2f}"
                })
            
            st.dataframe(
                pd.DataFrame(debt_summary),
                use_container_width=True,
                hide_index=True
            )
        
        st.divider()
        
        # Payment reminders
        st.subheader("📅 Upcoming Bills (Next 7 Days)")
        upcoming = get_upcoming_bills(debts_list, days_ahead=7)
        
        if upcoming:
            for bill in upcoming:
                if bill["days_until"] == 0:
                    st.warning(f"🔴 **{bill['name']}** - ${bill['amount']:,.2f} due **TODAY**")
                elif bill["days_until"] == 1:
                    st.info(f"🟡 **{bill['name']}** - ${bill['amount']:,.2f} due **tomorrow**")
                else:
                    st.info(f"🟢 **{bill['name']}** - ${bill['amount']:,.2f} due in **{bill['days_until']} days** ({bill['due_date'].strftime('%b %d')})")
        else:
            st.success("✅ No bills due in the next 7 days!")

# -------------------------------------------------
# PAGE: CREDIT CARDS
# -------------------------------------------------
elif page == "💳 My Credit Cards":
    st.title("💳 My Credit Card Debts")
    
    credit_cards = [d for d in st.session_state.debts if d["type"] == "Credit Card"]
    
    # Add credit card form
    with st.expander("➕ Add Credit Card", expanded=len(credit_cards) == 0):
        with st.form("add_credit_card"):
            name = st.text_input("Card Name (e.g., Chase Sapphire)")
            credit_limit = st.number_input("Credit Limit ($)", min_value=0.0, format="%.2f")
            balance = st.number_input("Current Balance ($)", min_value=0.0, format="%.2f")
            apr = st.number_input("APR (%)", min_value=0.0, format="%.2f")
            min_payment = st.number_input("Minimum Payment ($)", min_value=0.0, format="%.2f")
            due_day = st.slider("Due Day of Month", 1, 31, 1)
            status = st.selectbox("Status", ["Active", "Paid Off", "Closed"])
            
            submitted = st.form_submit_button("Add Credit Card")
            
            if submitted and name:
                new_debt = {
                    "name": name,
                    "type": "Credit Card",
                    "balance": balance,
                    "apr": apr / 100,
                    "min_payment": min_payment,
                    "due_day": due_day,
                    "status": status,
                    "original_balance": balance,
                    "credit_limit": credit_limit
                }
                if save_debt_to_db(new_debt):
                    st.success("✅ Credit card added!")
                    st.session_state.reload_debts = True
                    st.rerun()
    
    st.divider()
    
    # Display credit cards
    if credit_cards:
        st.subheader("Your Credit Cards")
        
        # Create table with utilization
        card_data = []
        for debt in credit_cards:
            credit_limit = debt.get('credit_limit', 0) or 0  # Handle None or missing
            balance = debt.get('balance', 0) or 0
            utilization = (balance / credit_limit * 100) if credit_limit > 0 else 0
            
            card_data.append({
                "Name": debt['name'],
                "Balance": f"${balance:,.2f}",
                "Credit Limit": f"${credit_limit:,.2f}" if credit_limit > 0 else "Not Set",
                "Utilization": f"{utilization:.1f}%" if credit_limit > 0 else "N/A",
                "APR": f"{debt['apr']*100:.1f}%",
                "Min Payment": f"${debt['min_payment']:,.2f}",
                "Status": debt.get("status", "Active"),
                "Due Day": f"Day {debt['due_day']}",
                "id": debt['id']
            })
        
        # Display table
        df_display = pd.DataFrame(card_data)
        st.dataframe(
            df_display.drop(columns=['id']),
            use_container_width=True,
            hide_index=True
        )
        
        st.divider()
        
        # Edit/Delete buttons
        st.subheader("Manage Cards")
        for i, debt in enumerate(credit_cards):
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{debt['name']}**")
            with col2:
                if st.button("✏️ Edit", key=f"edit_cc_{debt['id']}"):
                    st.session_state.editing_debt = debt
                    st.rerun()
            with col3:
                if st.button("🗑️ Delete", key=f"delete_cc_{debt['id']}"):
                    if delete_debt_from_db(debt['id']):
                        st.session_state.reload_debts = True
                        st.rerun()
        
        # Edit form
        if st.session_state.get("editing_debt") and st.session_state.editing_debt["type"] == "Credit Card":
            debt = st.session_state.editing_debt
            
            with st.expander("✏️ Edit Credit Card", expanded=True):
                with st.form("edit_credit_card"):
                    name = st.text_input("Card Name", value=debt["name"])
                    credit_limit = st.number_input("Credit Limit ($)", min_value=0.0, 
                                                  value=float(debt.get("credit_limit", 0)), format="%.2f")
                    balance = st.number_input("Current Balance ($)", min_value=0.0, value=float(debt["balance"]), format="%.2f")
                    apr = st.number_input("APR (%)", min_value=0.0, value=float(debt["apr"])*100, format="%.2f")
                    min_payment = st.number_input("Minimum Payment ($)", min_value=0.0, value=float(debt["min_payment"]), format="%.2f")
                    due_day = st.slider("Due Day of Month", 1, 31, int(debt["due_day"]))
                    status = st.selectbox("Status", ["Active", "Paid Off", "Closed"], 
                                        index=["Active", "Paid Off", "Closed"].index(debt.get("status", "Active")))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        save = st.form_submit_button("💾 Save Changes")
                    with col2:
                        cancel = st.form_submit_button("❌ Cancel")
                    
                    if save and name:
                        updated_debt = {
                            "name": name,
                            "type": "Credit Card",
                            "balance": balance,
                            "apr": apr / 100,
                            "min_payment": min_payment,
                            "due_day": due_day,
                            "status": status,
                            "original_balance": debt.get("original_balance", balance),
                            "credit_limit": credit_limit
                        }
                        if update_debt_in_db(debt['id'], updated_debt):
                            st.success("✅ Changes saved!")
                            st.session_state.editing_debt = None
                            st.session_state.reload_debts = True
                            st.rerun()
                    
                    if cancel:
                        st.session_state.editing_debt = None
                        st.rerun()
    else:
        st.info("No credit cards added yet. Use the form above to add one!")

# -------------------------------------------------
# PAGE: LOANS
# -------------------------------------------------
elif page == "🏦 My Loans":
    st.title("🏦 My Loans")
    
    loans = [d for d in st.session_state.debts if d["type"] != "Credit Card"]
    
    # Add loan form
    with st.expander("➕ Add Loan", expanded=len(loans) == 0):
        with st.form("add_loan"):
            name = st.text_input("Loan Name (e.g., Auto Loan)")
            loan_type = st.selectbox("Loan Type", ["Student Loan", "Auto Loan", "Personal Loan", "Other"])
            original_balance = st.number_input("Original Loan Amount ($)", min_value=0.0, format="%.2f")
            current_balance = st.number_input("Current Balance ($)", min_value=0.0, format="%.2f")
            apr = st.number_input("APR (%)", min_value=0.0, format="%.2f")
            min_payment = st.number_input("Monthly Payment ($)", min_value=0.0, format="%.2f")
            due_day = st.slider("Due Day of Month", 1, 31, 1)
            status = st.selectbox("Status", ["Active", "Paid Off", "Closed"])
            
            submitted = st.form_submit_button("Add Loan")
            
            if submitted and name:
                new_debt = {
                    "name": name,
                    "type": loan_type,
                    "balance": current_balance,
                    "apr": apr / 100,
                    "min_payment": min_payment,
                    "due_day": due_day,
                    "status": status,
                    "original_balance": original_balance
                }
                if save_debt_to_db(new_debt):
                    st.success("✅ Loan added!")
                    st.session_state.reload_debts = True
                    st.rerun()
    
    st.divider()
    
    # Display loans
    if loans:
        st.subheader("Your Loans")
        
        for debt in loans:
            with st.container():
                col1, col2, col3, col4, col5, col6, col7, col8, col9 = st.columns([2, 1, 1.2, 1, 1, 1, 1, 0.6, 0.6])
                
                with col1:
                    st.write(f"**{debt['name']}**")
                with col2:
                    st.write(debt['type'])
                with col3:
                    orig = debt.get('original_balance', debt['balance'])
                    st.write(f"${orig:,.2f}")
                with col4:
                    st.write(f"${debt['balance']:,.2f}")
                with col5:
                    st.write(f"{debt['apr']*100:.1f}%")
                with col6:
                    st.write(f"${debt['min_payment']:,.2f}")
                with col7:
                    st.write(debt.get("status", "Active"))
                with col8:
                    if st.button("✏️", key=f"edit_loan_{debt['id']}"):
                        st.session_state.editing_debt = debt
                        st.rerun()
                with col9:
                    if st.button("🗑️", key=f"delete_loan_{debt['id']}"):
                        if delete_debt_from_db(debt['id']):
                            st.session_state.reload_debts = True
                            st.rerun()
                
                st.divider()
        
        # Edit form
        if st.session_state.get("editing_debt") and st.session_state.editing_debt["type"] != "Credit Card":
            debt = st.session_state.editing_debt
            
            with st.expander("✏️ Edit Loan", expanded=True):
                with st.form("edit_loan"):
                    name = st.text_input("Loan Name", value=debt["name"])
                    loan_type = st.selectbox("Loan Type", ["Student Loan", "Auto Loan", "Personal Loan", "Other"],
                                           index=["Student Loan", "Auto Loan", "Personal Loan", "Other"].index(debt["type"]))
                    original_balance = st.number_input("Original Loan Amount ($)", min_value=0.0, 
                                                      value=float(debt.get("original_balance", debt["balance"])), format="%.2f")
                    current_balance = st.number_input("Current Balance ($)", min_value=0.0, value=float(debt["balance"]), format="%.2f")
                    apr = st.number_input("APR (%)", min_value=0.0, value=float(debt["apr"])*100, format="%.2f")
                    min_payment = st.number_input("Monthly Payment ($)", min_value=0.0, value=float(debt["min_payment"]), format="%.2f")
                    due_day = st.slider("Due Day of Month", 1, 31, int(debt["due_day"]))
                    status = st.selectbox("Status", ["Active", "Paid Off", "Closed"],
                                        index=["Active", "Paid Off", "Closed"].index(debt.get("status", "Active")))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        save = st.form_submit_button("💾 Save Changes")
                    with col2:
                        cancel = st.form_submit_button("❌ Cancel")
                    
                    if save and name:
                        updated_debt = {
                            "name": name,
                            "type": loan_type,
                            "balance": current_balance,
                            "apr": apr / 100,
                            "min_payment": min_payment,
                            "due_day": due_day,
                            "status": status,
                            "original_balance": original_balance
                        }
                        if update_debt_in_db(debt['id'], updated_debt):
                            st.success("✅ Changes saved!")
                            st.session_state.editing_debt = None
                            st.session_state.reload_debts = True
                            st.rerun()
                    
                    if cancel:
                        st.session_state.editing_debt = None
                        st.rerun()
    else:
        st.info("No loans added yet. Use the form above to add one!")

# -------------------------------------------------
# PAGE: BILLS
# -------------------------------------------------
elif page == "📄 Bills":
    st.title("📄 Bills")
    
    bills = [d for d in st.session_state.debts if d.get("type") == "Bill"]
    
    st.markdown("Track recurring bills like utilities, subscriptions, insurance, and other monthly expenses.")
    
    # Add bill form
    with st.expander("➕ Add Bill", expanded=len(bills) == 0):
        with st.form("add_bill"):
            name = st.text_input("Bill Name (e.g., Electric, Netflix, Car Insurance)")
            amount = st.number_input("Monthly Amount ($)", min_value=0.0, format="%.2f")
            due_day = st.slider("Due Day of Month", 1, 31, 1)
            category = st.selectbox("Category", ["Utilities", "Subscription", "Insurance", "Phone/Internet", "Rent/Mortgage", "Other"])
            auto_pay = st.checkbox("Auto-pay enabled")
            status = st.selectbox("Status", ["Active", "Paused", "Cancelled"])
            notes = st.text_area("Notes (optional)", placeholder="Add any notes about this bill...")
            
            submitted = st.form_submit_button("Add Bill")
            
            if submitted and name:
                new_bill = {
                    "name": name,
                    "type": "Bill",
                    "balance": 0,  # Bills don't have balance
                    "apr": 0,  # Bills don't have APR
                    "min_payment": amount,
                    "due_day": due_day,
                    "status": status,
                    "category": category,
                    "auto_pay": auto_pay,
                    "notes": notes
                }
                if save_debt_to_db(new_bill):
                    st.success("✅ Bill added!")
                    st.session_state.reload_debts = True
                    st.rerun()
    
    st.divider()
    
    # Display bills
    if bills:
        st.subheader("Your Bills")
        
        # Calculate total monthly bills
        total_monthly = sum(b["min_payment"] for b in bills if b.get("status") == "Active")
        st.metric("Total Monthly Bills", f"${total_monthly:,.2f}")
        
        st.divider()
        
        for bill in bills:
            with st.container():
                col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([2, 1.5, 1, 1, 1, 1, 0.6, 0.6])
                
                with col1:
                    auto_icon = "🔄 " if bill.get("auto_pay") else ""
                    st.write(f"**{auto_icon}{bill['name']}**")
                with col2:
                    st.write(bill.get("category", "Other"))
                with col3:
                    st.write(f"${bill['min_payment']:,.2f}")
                with col4:
                    st.write(f"Day {bill['due_day']}")
                with col5:
                    status = bill.get("status", "Active")
                    if status == "Active":
                        st.write("🟢 Active")
                    elif status == "Paused":
                        st.write("🟡 Paused")
                    else:
                        st.write("🔴 Cancelled")
                with col6:
                    if bill.get("auto_pay"):
                        st.write("✓ Auto-pay")
                    else:
                        st.write("")
                with col7:
                    if st.button("✏️", key=f"edit_bill_{bill['id']}"):
                        st.session_state.editing_debt = bill
                        st.rerun()
                with col8:
                    if st.button("🗑️", key=f"delete_bill_{bill['id']}"):
                        if delete_debt_from_db(bill['id']):
                            st.session_state.reload_debts = True
                            st.rerun()
                
                # Show notes if any
                if bill.get("notes"):
                    st.caption(f"💬 {bill['notes']}")
                
                st.divider()
        
        # Edit form
        if st.session_state.get("editing_debt") and st.session_state.editing_debt.get("type") == "Bill":
            bill = st.session_state.editing_debt
            
            with st.expander("✏️ Edit Bill", expanded=True):
                with st.form("edit_bill"):
                    name = st.text_input("Bill Name", value=bill["name"])
                    amount = st.number_input("Monthly Amount ($)", min_value=0.0, value=float(bill["min_payment"]), format="%.2f")
                    due_day = st.slider("Due Day of Month", 1, 31, int(bill["due_day"]))
                    category = st.selectbox("Category", ["Utilities", "Subscription", "Insurance", "Phone/Internet", "Rent/Mortgage", "Other"],
                                          index=["Utilities", "Subscription", "Insurance", "Phone/Internet", "Rent/Mortgage", "Other"].index(bill.get("category", "Other")))
                    auto_pay = st.checkbox("Auto-pay enabled", value=bill.get("auto_pay", False))
                    status = st.selectbox("Status", ["Active", "Paused", "Cancelled"],
                                        index=["Active", "Paused", "Cancelled"].index(bill.get("status", "Active")))
                    notes = st.text_area("Notes (optional)", value=bill.get("notes", ""))
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        save = st.form_submit_button("💾 Save Changes")
                    with col2:
                        cancel = st.form_submit_button("❌ Cancel")
                    
                    if save and name:
                        updated_bill = {
                            "name": name,
                            "type": "Bill",
                            "balance": 0,
                            "apr": 0,
                            "min_payment": amount,
                            "due_day": due_day,
                            "status": status,
                            "category": category,
                            "auto_pay": auto_pay,
                            "notes": notes
                        }
                        if update_debt_in_db(bill['id'], updated_bill):
                            st.success("✅ Changes saved!")
                            st.session_state.editing_debt = None
                            st.session_state.reload_debts = True
                            st.rerun()
                    
                    if cancel:
                        st.session_state.editing_debt = None
                        st.rerun()
        
        # Summary by category
        st.divider()
        st.subheader("📊 Bills by Category")
        
        category_totals = {}
        for bill in bills:
            if bill.get("status") == "Active":
                cat = bill.get("category", "Other")
                if cat not in category_totals:
                    category_totals[cat] = 0
                category_totals[cat] += bill["min_payment"]
        
        if category_totals:
            fig = px.bar(
                x=list(category_totals.keys()),
                y=list(category_totals.values()),
                labels={'x': 'Category', 'y': 'Monthly Cost ($)'},
                title="Monthly Bills by Category"
            )
            st.plotly_chart(fig, use_container_width=True)
        
    else:
        st.info("No bills added yet. Use the form above to add one!")

# -------------------------------------------------
# PAGE: PAYOFF PLANNER
# -------------------------------------------------
elif page == "📈 Payoff Planner":
    st.title("📈 Payoff Planner")
    
    if not st.session_state.debts:
        st.info("Add some debts first to use the payoff planner!")
    else:
        debts_list = [d for d in st.session_state.debts if d.get("status", "Active") == "Active"]
        
        if not debts_list:
            st.warning("All your debts are marked as Paid Off or Closed. Update their status to plan payoffs.")
        else:
            total_min = sum(d["min_payment"] for d in debts_list)
            
            # Settings
            st.subheader("⚙️ Payoff Strategy")
            
            col1, col2 = st.columns(2)
            
            with col1:
                strategy = st.radio(
                    "Choose Strategy",
                    ["Snowball", "Avalanche"],
                    help="**Snowball**: Pay smallest balance first (psychological wins)\n\n**Avalanche**: Pay highest APR first (save more money)"
                )
            
            with col2:
                monthly_budget = st.number_input(
                    "Monthly Debt Budget ($)",
                    min_value=float(total_min),
                    value=float(total_min),
                    format="%.2f"
                )
            
            st.divider()
            
            # What-if scenarios
            st.subheader("🔮 What-If Scenarios")
            
            scenarios = {
                "Current Plan": 0,
                "+$50/month": 50,
                "+$100/month": 100,
                "+$200/month": 200,
                "+$500/month": 500
            }
            
            comparison_data = []
            
            for scenario_name, extra in scenarios.items():
                _, interest, months, _ = calculate_payoff_schedule(debts_list, strategy, monthly_budget, extra)
                payoff_date = (datetime.today() + relativedelta(months=months)).strftime("%b %Y")
                
                comparison_data.append({
                    "Scenario": scenario_name,
                    "Extra Payment": f"${extra:,.0f}",
                    "Months": months,
                    "Payoff Date": payoff_date,
                    "Total Interest": f"${interest:,.2f}",
                    "Interest Saved": f"${comparison_data[0]['Interest'] - interest:,.2f}" if comparison_data else "$0"
                })
            
            st.dataframe(pd.DataFrame(comparison_data), use_container_width=True, hide_index=True)
            
            st.divider()
            
            # Snowball vs Avalanche comparison
            st.subheader("⚖️ Strategy Comparison")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("**Snowball Method**")
                _, snow_interest, snow_months, snow_schedule = calculate_payoff_schedule(debts_list, "Snowball", monthly_budget)
                snow_payoff = (datetime.today() + relativedelta(months=snow_months)).strftime("%B %Y")
                
                st.metric("Payoff Date", snow_payoff)
                st.metric("Months", snow_months)
                st.metric("Total Interest", f"${snow_interest:,.2f}")
            
            with col2:
                st.markdown("**Avalanche Method**")
                _, aval_interest, aval_months, aval_schedule = calculate_payoff_schedule(debts_list, "Avalanche", monthly_budget)
                aval_payoff = (datetime.today() + relativedelta(months=aval_months)).strftime("%B %Y")
                
                st.metric("Payoff Date", aval_payoff)
                st.metric("Months", aval_months)
                st.metric("Total Interest", f"${aval_interest:,.2f}")
            
            # Show savings
            if snow_interest > aval_interest:
                st.success(f"💰 Avalanche saves **${snow_interest - aval_interest:,.2f}** in interest!")
            elif aval_interest > snow_interest:
                st.success(f"💰 Snowball saves **${aval_interest - snow_interest:,.2f}** in interest!")
            else:
                st.info("Both strategies result in the same interest paid.")
            
            st.divider()
            
            # Visualization
            st.subheader("📊 Payoff Timeline")
            
            schedule = snow_schedule if strategy == "Snowball" else aval_schedule
            schedule_df = pd.DataFrame(schedule)
            
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
                title=f"{strategy} Method - Debt Balance Over Time",
                xaxis_title="Month",
                yaxis_title="Balance ($)",
                hovermode='x unified',
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Export
            st.divider()
            csv = schedule_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Payment Schedule (CSV)",
                data=csv,
                file_name=f"payoff_schedule_{strategy.lower()}_{datetime.today().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
