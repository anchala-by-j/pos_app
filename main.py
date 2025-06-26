import streamlit as st
import pandas as pd
import os
from datetime import datetime
from sqlalchemy import create_engine, text
import tempfile
from fpdf import FPDF
import streamlit.components.v1 as components

st.image("logo.png", use_container_width=True)

# Load credentials from environment variables
DB_USERNAME = st.secrets["connections.postgres"]["DB_USERNAME"]
DB_PASSWORD = st.secrets["connections.postgres"]["DB_PASSWORD"]
DB_HOST = st.secrets["connections.postgres"]["DB_HOST"]
DB_NAME = st.secrets["connections.postgres"]["DB_NAME"]
DB_PORT = st.secrets["connections.postgres"]["DB_PORT"]

# Create database engine
@st.cache_resource
def get_engine():
    cert_path = os.path.join(os.path.dirname(__file__), "prod-ca-2021.crt")
    return create_engine(
        f"postgresql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        connect_args={
            "sslmode": "verify-full",
            "sslrootcert": cert_path
        }
    )

engine = get_engine()

# Load data functions
@st.cache_data(ttl=600)
def load_inventory():
    df = pd.read_sql('SELECT * FROM "mainDB".purchase_audit', con=engine)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    return df

def load_sales():
    return pd.read_sql('SELECT * FROM "mainDB".sales', con=engine)

def load_billbook():
    return pd.read_sql('SELECT * FROM "mainDB".billbook', con=engine)

def save_sales(df):
    df.to_sql("sales", con=engine, if_exists="append", index=False, schema="mainDB")

def save_billbook(df):
    df.to_sql("billbook", con=engine, if_exists="append", index=False, schema="mainDB")

def save_return(df):
    df.to_sql("returns", con=engine, if_exists="append", index=False, schema="mainDB")

def save_balance_payment(df):
    df.to_sql("balance_payments", con=engine, if_exists="append", index=False, schema="mainDB")

def update_balance(bill_no, amount):
    with engine.begin() as conn:
        conn.execute(text('''
            UPDATE "mainDB".sales
            SET paid = paid + :amount,
                balance = GREATEST(balance - :amount, 0)
            WHERE bill_no = :bill_no
        '''), {'amount': amount, 'bill_no': bill_no})

def generate_invoice_pdf(bill_no, customer, bill_items, total_amount, paid, balance):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=80, y=10, w=50)
        pdf.ln(30)
    else:
        pdf.ln(10)

    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Anchala Sarees - Invoice", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Arial", size=12)
    pdf.cell(100, 10, txt=f"Bill No: {bill_no}", ln=True)
    pdf.cell(100, 10, txt=f"Customer: {customer}", ln=True)
    pdf.cell(100, 10, txt=f"Date: {datetime.today().strftime('%d-%m-%Y')}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(80, 10, "Product", border=1, fill=True)
    pdf.cell(30, 10, "Qty", border=1, fill=True, align="C")
    pdf.cell(40, 10, "Price", border=1, fill=True, align="C")
    pdf.cell(40, 10, "Total", border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Arial", size=12)
    for item in bill_items:
        pdf.cell(80, 10, str(item.get('product_name', '')), border=1)
        pdf.cell(30, 10, str(item.get('qty', 0)), border=1, align="C")
        pdf.cell(40, 10, f"Rs.{item.get('price', 0.0):.2f}", border=1, align="R")
        pdf.cell(40, 10, f"Rs.{item.get('total_price', 0.0):.2f}", border=1, align="R")
        pdf.ln()

    pdf.ln(5)
    pdf.cell(150, 10, "Total Amount", border=1)
    pdf.cell(40, 10, f"Rs.{total_amount:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(150, 10, "Paid", border=1)
    pdf.cell(40, 10, f"Rs.{paid:.2f}", border=1, align="R")
    pdf.ln()
    pdf.cell(150, 10, "Balance", border=1)
    pdf.cell(40, 10, f"Rs.{balance:.2f}", border=1, align="R")

    pdf.ln(15)
    pdf.set_font("Arial", 'I', 10)
    pdf.cell(200, 10, txt="Thank you for shopping at Anchala Sarees!", ln=True, align="C")

    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(tmp_file.name)
    return tmp_file.name

if 'bill_items' not in st.session_state:
    st.session_state.bill_items = []

page = st.sidebar.radio("Select Module", ["POS", "Returns", "Balances"])

if page == "POS":
    st.title("Anchala POS")
    st.markdown("""
        <style>
            .stApp {
                background-color: #fabec0;
            }
        </style>
    """, unsafe_allow_html=True)
    st.markdown("Scan or enter the barcode below to add items to a bill.")

    st.markdown("### 📸 Scan Barcode")
    scanner_with_buttons = """
    <audio id="beepSound" src="https://www.soundjay.com/button/beep-07.wav" preload="auto"></audio>
<div style="margin-bottom:10px;">
  <button onclick="startScanner()">📷 Start Scanning</button>
  <button onclick="stopScanner()">🛑 Stop Scanning</button>
</div>
<div id="reader" style="width:300px;"></div>
<script src="https://unpkg.com/html5-qrcode"></script>
<script>
let html5QrcodeScanner;
let beepPlayed = false;

function startScanner() {
    if (!html5QrcodeScanner) {
        html5QrcodeScanner = new Html5Qrcode("reader");
    }

    html5QrcodeScanner.start(
        { facingMode: "environment" },
        {
            fps: 10,
            qrbox: 250
        },
        (decodedText, decodedResult) => {
            if (!beepPlayed) {
                document.getElementById("beepSound").play();
                beepPlayed = true;
            }
            const inputBoxes = window.parent.document.querySelectorAll('input');
            for (const box of inputBoxes) {
                if (box.placeholder === "Or enter barcode manually") {
                    box.value = decodedText;
                    box.dispatchEvent(new Event("input", { bubbles: true }));
                    break;
                }
            }
            html5QrcodeScanner.stop().then(() => {
                beepPlayed = false;
                console.log("Scanner stopped");
            }).catch(err => console.error("Stop error:", err));
        },
        (errorMessage) => {
            // Optional debug
        }
    ).catch(err => {
        console.error("Start error:", err);
    });
}

function stopScanner() {
    if (html5QrcodeScanner) {
        html5QrcodeScanner.stop().then(() => {
            html5QrcodeScanner.clear();
            beepPlayed = false;
            console.log("Scanner manually stopped");
        }).catch(err => console.error("Stop error:", err));
    }
}
</script>
    """

    components.html(
        """
        <audio id="beepSound" src="https://www.soundjay.com/button/beep-07.wav" preload="auto"></audio>
        <div style="margin-bottom:10px;">
          <button onclick="startScanner()">📷 Start Scanning</button>
          <button onclick="stopScanner()">🛑 Stop Scanning</button>
        </div>
        <div id="reader" style="width:300px;"></div>
        <script src="https://unpkg.com/html5-qrcode"></script>
        <script>
        let html5QrcodeScanner;
        let beepPlayed = false;

        function startScanner() {
            if (!html5QrcodeScanner) {
                html5QrcodeScanner = new Html5Qrcode("reader");
            }

            html5QrcodeScanner.start(
                { facingMode: "environment" },
                { fps: 10, qrbox: 250 },
                (decodedText) => {
                    if (!beepPlayed) {
                        document.getElementById("beepSound").play();
                        beepPlayed = true;
                    }

                    // Send message to Streamlit
                    const message = { type: "barcode", data: decodedText };
                    window.parent.postMessage(message, "*");

                    html5QrcodeScanner.stop().then(() => {
                        beepPlayed = false;
                        html5QrcodeScanner.clear();
                    });
                },
                (error) => {}
            );
        }

        function stopScanner() {
            if (html5QrcodeScanner) {
                html5QrcodeScanner.stop().then(() => {
                    html5QrcodeScanner.clear();
                    beepPlayed = false;
                });
            }
        }
        </script>
        """,
        height=500
    )
    components.html(
        """
        <script>
        window.addEventListener("message", (event) => {
            if (event.data && event.data.type === "barcode") {
                const input = window.parent.document.querySelector('input[data-testid="stTextInput"][placeholder="Or enter barcode manually"]');
                if (input) {
                    input.value = event.data.data;
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                }
            }
        });
        </script>
        """,
        height=0
    )
    barcode = st.text_input("Or enter barcode manually", key="manual_barcode", placeholder="Or enter barcode manually")

    if barcode:
        inventory_df = load_inventory()
        barcode_cleaned = str(barcode).strip().lower()
        inventory_df['product_code'] = inventory_df['product_code'].astype(str).str.strip().str.lower()

        product = inventory_df[inventory_df['product_code'] == barcode_cleaned]

        if not product.empty:
            item = product.iloc[0]
            st.success(f" {item['product_name']}")
            st.write(f"Price: ₹{item['price']}")

            quantity = st.number_input("Enter Quantity", min_value=1, value=1)
            selling_price = st.number_input("Selling Price", min_value=0.0, value=float(item['price']))

            if st.button("Add to Bill", key=f"add_{barcode}"):
                st.session_state.bill_items.append({
                    'product_code': barcode,
                    'product_name': item['product_name'],
                    'qty': quantity,
                    'cost': item['cost'],
                    'price': selling_price,
                    'total_price': selling_price * quantity,
                    'margin': (selling_price - item['cost']) * quantity
                })
                st.success("Item added to bill.")
        else:
            st.error("Product not found in inventory.")

    if st.session_state.bill_items:
        st.subheader("Current Bill Items")

        display_df = pd.DataFrame(st.session_state.bill_items).drop(columns=["cost", "margin"])

        total_row = pd.DataFrame([{
            'product_code': '',
            'product_name': 'Total',
            'qty': '',
            'price': '',
            'total_price': display_df['total_price'].sum()
        }])

        display_df_with_total = pd.concat([display_df, total_row], ignore_index=True)
        st.dataframe(display_df_with_total)

        def get_next_bill_no():
            try:
                result = pd.read_sql('SELECT MAX(bill_no) AS max_bill FROM "mainDB".sales', con=engine)
                max_bill = result['max_bill'].iloc[0]
                return int(max_bill) + 1 if pd.notna(max_bill) else 1
            except Exception as e:
                st.error(f"Error fetching last bill number: {e}")
                return 1

        bill_no = str(get_next_bill_no())
        st.markdown(f"### 🧾 Bill Number: `{bill_no}`")
        customer = st.text_input("Customer Name")
        paid = st.number_input("Paid Amount", min_value=0.0, value=0.0)
        returns = st.number_input("Returns", min_value=0.0, value=0.0)

        if st.button("Confirm Sale", disabled=not st.session_state.bill_items):
            if bill_no.strip() and customer.strip():
                total_amount = sum([item['total_price'] for item in st.session_state.bill_items])

                sales_df = pd.DataFrame([{
                    'bill_no': bill_no,
                    'date': datetime.today().date(),
                    'customer': customer,
                    'items': len(st.session_state.bill_items),
                    'amount': total_amount,
                    'paid': paid,
                    'bal_paid': 0,
                    'balance': total_amount - paid
                }])
                save_sales(sales_df)

                billbook_df = pd.DataFrame(st.session_state.bill_items)
                billbook_df['bill_no'] = bill_no
                save_billbook(billbook_df)

                invoice_path = generate_invoice_pdf(bill_no, customer, st.session_state.bill_items, total_amount, paid,
                                                    total_amount - paid)
                st.success("Sale recorded and bill updated.")
                st.download_button("📄 Download Invoice", open(invoice_path, "rb"), file_name=f"Invoice_{bill_no}.pdf",
                                   mime="application/pdf")
                st.session_state.bill_items.clear()
            else:
                st.warning("Fill Customer Name and Paid Amount before confirming.")