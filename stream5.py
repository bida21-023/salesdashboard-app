import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import io
import tempfile
import os

# Set page configuration to wide layout
st.set_page_config(page_title="Sales Dashboard by Role", layout="wide")

# Data loading with enhanced validation
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("sales_data.csv", parse_dates=['sale_date', 'timestamp'], dayfirst=True)
        required_columns = ['sale_date', 'country', 'salesperson', 'total_price', 'category', 
                           'product_name', 'sales_channel', 'customer_age', 'customer_gender', 
                           'event_type', 'status_code', 'customer_id', 'customer_type', 'occupation',
                           'session_id', 'response_time_ms', 'url_requested']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            st.error(f"Missing required columns: {', '.join(missing_columns)}")
            st.stop()
        if (df['total_price'] < 0).any():
            st.error("Negative values found in 'total_price'.")
            st.stop()
        if (df['customer_age'] < 0).any() or (df['customer_age'] > 120).any():
            st.error("Invalid 'customer_age' values detected.")
            st.stop()
        if df['session_id'].duplicated().any():
            st.warning("Duplicate session IDs detected. Consider cleaning the dataset.")
        return df
    except FileNotFoundError:
        st.error("sales_data.csv not found. Please upload the file.")
        st.stop()
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        st.stop()

df = load_data()

# Handle dates
if 'sale_date' in df.columns:
    df['sale_date'] = pd.to_datetime(df['sale_date'], errors='coerce')
    if df['sale_date'].isna().all():
        st.warning("No valid dates found in 'sale_date'. Using default range.")
        min_date = datetime(2024, 1, 1).date()
        max_date = datetime(2024, 12, 31).date()
    else:
        min_date = df['sale_date'].min().date()
        max_date = min(df['sale_date'].max().date(), datetime.now().date())
else:
    st.error("'sale_date' column not found.")
    st.stop()

# Sidebar Filters
st.sidebar.header("Select Role")
role = st.sidebar.selectbox("Choose your role", ["Sales Manager", "Salesperson", "Sales Marketer"])

st.sidebar.header("Filters")
country_options = ['All'] + sorted(df['country'].dropna().unique().tolist())
selected_country = st.sidebar.selectbox("Select Country", country_options)

category_options = ['All'] + sorted(df['category'].dropna().unique().tolist())
selected_category = st.sidebar.selectbox("Select Category", category_options)

sales_channel_options = ['All'] + sorted(df['sales_channel'].dropna().unique().tolist())
selected_sales_channel = st.sidebar.selectbox("Select Sales Channel", sales_channel_options)

keyword = st.sidebar.text_input("Search by Product or URL")

if role == "Salesperson":
    salesperson_options = ['All'] + sorted(df['salesperson'].dropna().unique().tolist())
    selected_salesperson = st.sidebar.selectbox("Select Salesperson", salesperson_options)
    sales_target = st.sidebar.number_input("Sales Target ($)", min_value=0.0, value=1000.0, step=100.0)
else:
    selected_salesperson = None
    sales_target = None

if role == "Sales Manager":
    manager_sales_target = st.sidebar.number_input("Sales Target per Product ($)", min_value=0.0, value=1000.0, step=100.0)
else:
    manager_sales_target = None

if role == "Sales Marketer":
    marketer_url_target = st.sidebar.number_input("URL Visit Target", min_value=0.0, value=100.0, step=10.0)
else:
    marketer_url_target = None

start_date = st.sidebar.date_input("Start Date", value=min_date, min_value=min_date, max_value=max_date)
end_date = st.sidebar.date_input("End Date", value=max_date, min_value=min_date, max_value=max_date)

# Data refresh button
if st.sidebar.button("Refresh Data"):
    st.cache_data.clear()
    df = load_data()
    st.rerun()

# Filtering Data
@st.cache_data
def filter_data(df, country, category, sales_channel, keyword, salesperson, start_date, end_date):
    filtered_df = df.copy()
    if country != 'All':
        filtered_df = filtered_df[filtered_df['country'] == country]
    if category != 'All':
        filtered_df = filtered_df[filtered_df['category'] == category]
    if sales_channel != 'All':
        filtered_df = filtered_df[filtered_df['sales_channel'] == sales_channel]
    if keyword:
        filtered_df = filtered_df[
            filtered_df['product_name'].str.contains(keyword, case=False, na=False) |
            filtered_df['url_requested'].str.contains(keyword, case=False, na=False)
        ]
    if salesperson and salesperson != 'All':
        filtered_df = filtered_df[filtered_df['salesperson'] == salesperson]
    filtered_df = filtered_df[
        (filtered_df['sale_date'] >= pd.to_datetime(start_date)) & 
        (filtered_df['sale_date'] <= pd.to_datetime(end_date))
    ]
    return filtered_df

filtered_df = filter_data(df, selected_country, selected_category, selected_sales_channel, keyword, selected_salesperson, start_date, end_date)
purchases_df = filtered_df[(filtered_df['total_price'] > 0) & (filtered_df['event_type'] == 'Purchase') & (filtered_df['status_code'] == 200)]

# PDF Generation Function
def generate_pdf(role, filtered_df, purchases_df, selected_salesperson, sales_target, manager_sales_target, marketer_url_target):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 50
    charts = []

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, f"{role} Dashboard Report")
    y -= 20
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    y -= 20
    c.drawString(50, y, f"Date Range: {start_date} to {end_date}")
    y -= 30

    color_sequence = px.colors.qualitative.Plotly

    if role == "Sales Manager":
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Key Performance Indicators")
        y -= 20
        c.setFont("Helvetica", 10)
        total_sales = purchases_df['total_price'].sum()
        top_products = purchases_df.groupby('product_name')['total_price'].sum().nlargest(5).reset_index()
        sales_by_person = purchases_df.groupby('salesperson')['total_price'].sum().reset_index()
        top_product = top_products.iloc[0]['product_name'] if not top_products.empty else "N/A"
        top_product_sales = top_products.iloc[0]['total_price'] if not top_products.empty else 0
        top_salesperson = sales_by_person.iloc[0]['salesperson'] if not sales_by_person.empty else "N/A"
        top_salesperson_sales = sales_by_person.iloc[0]['total_price'] if not sales_by_person.empty else 0
        demo_requests = len(filtered_df[filtered_df['event_type'] == 'Demo Request'])
        c.drawString(50, y, f"Total Revenue: ${total_sales:,.2f}")
        y -= 15
        c.drawString(50, y, f"Top Product: {top_product} (${top_product_sales:,.2f})")
        y -= 15
        c.drawString(50, y, f"Top Salesperson: {top_salesperson} (${top_salesperson_sales:,.2f})")
        y -= 15
        c.drawString(50, y, f"Demo Requests: {demo_requests}")
        y -= 30

        revenue_by_product = purchases_df.groupby('product_name')['total_price'].sum().reset_index()
        if not revenue_by_product.empty:
            fig = px.bar(revenue_by_product, x='product_name', y='total_price', title="Total Revenue by Product",
                         color='product_name', color_discrete_sequence=color_sequence)
            fig.add_trace(go.Scatter(x=revenue_by_product['product_name'], y=[manager_sales_target] * len(revenue_by_product), 
                                    mode='lines', name='Target', line=dict(color='black', dash='dash')))
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=True, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Total Revenue by Product"))

        sales_by_channel = purchases_df.groupby('sales_channel')['total_price'].sum().reset_index()
        if not sales_by_channel.empty:
            fig = px.bar(sales_by_channel, x='sales_channel', y='total_price', title="Sales by Channel",
                         color='sales_channel', color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=False, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Sales by Channel"))

        if not sales_by_person.empty:
            fig = px.pie(sales_by_person, names='salesperson', values='total_price', title="Sales Distribution by Salesperson",
                         color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Sales Distribution by Salesperson"))

        sales_by_product_time = purchases_df.groupby([purchases_df['sale_date'].dt.to_period('M'), 'product_name'])['total_price'].sum().reset_index()
        sales_by_product_time['sale_date'] = sales_by_product_time['sale_date'].astype(str)
        if not sales_by_product_time.empty:
            fig = px.line(sales_by_product_time, x='sale_date', y='total_price', color='product_name', title="Sales Trend Over Time by Product",
                          color_discrete_sequence=color_sequence)
            unique_dates = sales_by_product_time['sale_date'].unique()
            fig.add_trace(go.Scatter(x=unique_dates, y=[manager_sales_target] * len(unique_dates), mode='lines', name='Target',
                                    line=dict(color='black', dash='dash')))
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Sales Trend Over Time by Product"))

    elif role == "Salesperson":
        person_df = filtered_df[filtered_df['salesperson'] == selected_salesperson] if selected_salesperson and selected_salesperson != 'All' else filtered_df
        person_df = person_df[(person_df['sale_date'] >= pd.to_datetime(start_date)) & 
                              (person_df['sale_date'] <= pd.to_datetime(end_date))]
        purchases_df = person_df[(person_df['total_price'] > 0) & 
                                 (person_df['event_type'] == 'Purchase') & 
                                 (person_df['status_code'] == 200)]
        number_of_sales = len(purchases_df)
        revenue_achieved = purchases_df['total_price'].sum()
        top_products = purchases_df.groupby('product_name')['total_price'].sum().nlargest(1).reset_index()
        top_product = top_products.iloc[0]['product_name'] if not top_products.empty else "N/A"
        top_product_sales = top_products.iloc[0]['total_price'] if not top_products.empty else 0
        total_events = len(person_df)
        conversion_rate = (number_of_sales / total_events * 100) if total_events > 0 else 0
        # Determine gauge color based on target status
        if revenue_achieved >= sales_target:
            gauge_color = "green"
        elif revenue_achieved >= sales_target * 0.9:
            gauge_color = "magenta"
        else:
            gauge_color = "red"
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Key Performance Indicators")
        y -= 20
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Number of Sales: {number_of_sales}")
        y -= 15
        c.drawString(50, y, f"Revenue Achieved: ${revenue_achieved:,.2f}")
        y -= 15
        c.drawString(50, y, f"Top Product Sold: {top_product} (${top_product_sales:,.2f})")
        y -= 15
        c.drawString(50, y, f"Conversion Rate: {conversion_rate:.2f}%")
        y -= 30

        # Sales Gauge for PDF (smaller size for KPI style)
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=revenue_achieved,
            title={'text': "Sales Progress ($)"},
            gauge={
                'axis': {'range': [0, max(sales_target * 1.5, revenue_achieved * 1.2)]},
                'bar': {'color': gauge_color},
                'steps': [
                    {'range': [0, sales_target * 0.5], 'color': "lightgray"},
                    {'range': [sales_target * 0.5, sales_target], 'color': "gray"},
                    {'range': [sales_target, sales_target * 1.5], 'color': "darkgray"}
                ],
                'threshold': {
                    'line': {'color': "black", 'width': 4},
                    'thickness': 0.75,
                    'value': sales_target
                }
            }
        ))
        fig.update_layout(height=100, margin=dict(l=5, r=5, t=20, b=5), font=dict(size=6), template="plotly")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
            pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
            charts.append((tmpfile.name, "Sales Progress"))

        purchases_df = purchases_df.copy()
        purchases_df['period'] = purchases_df['sale_date'].dt.to_period('M').astype(str)
        sales_performance = purchases_df.groupby('period')['total_price'].sum().reset_index()
        if not sales_performance.empty:
            fig = px.line(sales_performance, x='period', y='total_price', markers=True, title="Individual Sales Performance",
                          color_discrete_sequence=[color_sequence[0]])
            fig.add_trace(go.Scatter(x=sales_performance['period'], y=[sales_target] * len(sales_performance), mode='lines', name='Target',
                                    line=dict(color='black', dash='dash')))
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=True, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Individual Sales Performance"))

        breakdown_df = purchases_df.groupby(['product_name', 'country'])['total_price'].sum().reset_index()
        if not breakdown_df.empty:
            fig = px.bar(breakdown_df, x='product_name', y='total_price', color='country', barmode='group', title="Performance Breakdown by Product and Region",
                         color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(title="Region", font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Performance Breakdown by Product and Region"))

        sales_by_product = purchases_df.groupby('product_name')['total_price'].sum().reset_index()
        if not sales_by_product.empty:
            fig = px.bar(sales_by_product, x='product_name', y='total_price', title="Sales by Product",
                         color='product_name', color_discrete_sequence=color_sequence)
            fig.add_trace(go.Scatter(x=sales_by_product['product_name'], y=[sales_target] * len(sales_by_product), 
                                    mode='lines', name='Target', line=dict(color='black', dash='dash')))
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=True, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Sales by Product"))

        top_customers = purchases_df.groupby(['customer_id', 'customer_type'])['total_price'].sum().nlargest(3).reset_index()
        if not top_customers.empty:
            top_customers['customer_label'] = top_customers['customer_id'] + ' (' + top_customers['customer_type'] + ')'
            fig = px.bar(top_customers, x='customer_label', y='total_price', title="Top 3 Customers",
                         color='customer_label', color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=False, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Top 3 Customers"))

    elif role == "Sales Marketer":
        total_visits = len(filtered_df['session_id'].unique())
        avg_session_length = filtered_df.groupby('session_id')['response_time_ms'].mean().mean() if not filtered_df.empty else 0
        filtered_df = filtered_df.copy()
        filtered_df['hour'] = pd.to_datetime(filtered_df['timestamp']).dt.hour
        most_active_hour = filtered_df['hour'].mode().iloc[0] if not filtered_df['hour'].empty else "N/A"
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Key Performance Indicators")
        y -= 20
        c.setFont("Helvetica", 10)
        c.drawString(50, y, f"Total Visits: {total_visits}")
        y -= 15
        c.drawString(50, y, f"Avg. Session Length (ms): {avg_session_length:,.2f}")
        y -= 15
        c.drawString(50, y, f"Most Active Hour: {most_active_hour}:00")
        y -= 15
        c.drawString(50, y, f"Total Log Requests: {len(filtered_df)}")
        y -= 30

        geo_df = purchases_df.groupby('country')['total_price'].sum().reset_index()
        if not geo_df.empty:
            fig = px.choropleth(geo_df, locations='country', locationmode='country names', color='total_price', title="Geographic Sales Distribution",
                                color_continuous_scale='Plasma')
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=False, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Geographic Sales Distribution"))

        age_bins = [0, 20, 30, 40, 50, 100]
        age_labels = ['0-20', '21-30', '31-40', '41-50', '51+']
        purchases_df = purchases_df.copy()
        purchases_df['age_group'] = pd.cut(purchases_df['customer_age'], bins=age_bins, labels=age_labels, include_lowest=True)
        sales_by_age_product = purchases_df.groupby(['age_group', 'product_name'])['total_price'].sum().reset_index()
        if not sales_by_age_product.empty:
            fig = px.bar(sales_by_age_product, x='age_group', y='total_price', color='product_name', barmode='group', title="Product Sales by Age",
                         color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Product Sales by Age"))

        sales_by_occupation_product = purchases_df.groupby(['occupation', 'product_name'])['total_price'].sum().reset_index()
        if not sales_by_occupation_product.empty:
            fig = px.bar(sales_by_occupation_product, x='occupation', y='total_price', color='product_name', barmode='group', title="Product Sales by Occupation",
                         color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Product Sales by Occupation"))

        top_customers = purchases_df.groupby(['customer_id', 'customer_type'])['total_price'].sum().nlargest(5).reset_index()
        if not top_customers.empty:
            top_customers['customer_label'] = top_customers['customer_id'] + ' (' + top_customers['customer_type'] + ')'
            fig = px.bar(top_customers, x='customer_label', y='total_price', title="Top 5 High-Value Clients",
                         color='customer_label', color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), showlegend=False, template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Top 5 High-Value Clients"))

        url_visits = filtered_df['url_requested'].value_counts().reset_index()
        url_visits.columns = ['url_requested', 'count']
        if not url_visits.empty:
            fig = px.pie(url_visits, names='url_requested', values='count', title="Most Visited URLs",
                         color_discrete_sequence=color_sequence)
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "Most Visited URLs"))

        url_trend = filtered_df.groupby([filtered_df['timestamp'].dt.to_period('M'), 'url_requested']).size().reset_index(name='count')
        url_trend['timestamp'] = url_trend['timestamp'].astype(str)
        if not url_trend.empty:
            fig = px.line(url_trend, x='timestamp', y='count', color='url_requested', title="URL Trend Over Time",
                          color_discrete_sequence=color_sequence)
            unique_timestamps = url_trend['timestamp'].unique()
            fig.add_trace(go.Scatter(x=unique_timestamps, y=[marketer_url_target] * len(unique_timestamps), mode='lines', name='Target',
                                    line=dict(color='black', dash='dash')))
            fig.update_layout(height=150, margin=dict(l=5, r=5, t=30, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmpfile:
                pio.write_image(fig, file=tmpfile.name, format="png", scale=2)
                charts.append((tmpfile.name, "URL Trend Over Time"))

    for chart_path, chart_title in charts:
        if y < 150:
            c.showPage()
            y = height - 50
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, chart_title)
        y -= 20
        img = ImageReader(chart_path)
        img_width, img_height = img.getSize()
        aspect = img_height / img_width
        target_width = 500
        target_height = target_width * aspect
        if y - target_height < 50:
            c.showPage()
            y = height - 50
        c.drawImage(chart_path, 50, y - target_height, width=target_width, height=target_height)
        y -= target_height + 20
        os.unlink(chart_path)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer

# Diagnostics before PDF generation
if filtered_df.empty:
    st.warning("Filtered data is empty. Adjust filters to include data.")
if purchases_df.empty:
    st.warning("No successful purchase data available. PDF may lack purchase-related charts.")

# Generate PDF
pdf = generate_pdf(role, filtered_df, purchases_df, selected_salesperson, sales_target, manager_sales_target, marketer_url_target)
if pdf is None:
    st.error("PDF generation failed. Check error messages above.")
    st.stop()

# Export Buttons in Sidebar
st.sidebar.header("Export Options")
csv = filtered_df.to_csv(index=False)
st.sidebar.download_button(
    label="Download Filtered Data (CSV)",
    data=csv,
    file_name=f"filtered_sales_data_{datetime.now().strftime('%Y%m%d')}.csv",
    mime="text/csv"
)
st.sidebar.download_button(
    label="Download PDF Report",
    data=pdf,
    file_name=f"{role.lower().replace(' ', '_')}_report_{datetime.now().strftime('%Y%m%d')}.pdf",
    mime="application/pdf"
)

# Salesperson Dashboard Function
def salesperson_dashboard(df, selected_salesperson, start_date, end_date, min_date, max_date, sales_target):
    with st.container():
        st.header("Salesperson Dashboard")

        if selected_salesperson and selected_salesperson != 'All':
            person_df = df[df['salesperson'] == selected_salesperson]
        else:
            person_df = df

        person_df = person_df[(person_df['sale_date'] >= pd.to_datetime(start_date)) & 
                              (person_df['sale_date'] <= pd.to_datetime(end_date))]
        
        purchases_df = person_df[(person_df['total_price'] > 0) & 
                                 (person_df['event_type'] == 'Purchase') & 
                                 (person_df['status_code'] == 200)]

        number_of_sales = len(purchases_df)
        revenue_achieved = purchases_df['total_price'].sum()
        top_products = purchases_df.groupby('product_name')['total_price'].sum().nlargest(1).reset_index()
        top_product = top_products.iloc[0]['product_name'] if not top_products.empty else "N/A"
        top_product_sales = top_products.iloc[0]['total_price'] if not top_products.empty else 0
        total_events = len(person_df)
        conversion_rate = (number_of_sales / total_events * 100) if total_events > 0 else 0

        # Determine gauge color based on target status
        if revenue_achieved >= sales_target:
            gauge_color = "green"
        elif revenue_achieved >= sales_target * 0.9:
            gauge_color = "magenta"
        else:
            gauge_color = "red"

        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        with kpi_col1:
            st.metric("Number of Sales", number_of_sales)
        with kpi_col2:
            st.metric("Revenue Achieved", f"${revenue_achieved:,.2f}")
        with kpi_col3:
            st.metric("Top Product Sold", top_product, f"${top_product_sales:,.2f}")
        with kpi_col4:
            st.metric("Sales Progress", f"${revenue_achieved:,.2f}", delta=f"Target: ${sales_target:,.2f}")
            fig = go.Figure(go.Indicator(
                mode="gauge",
                value=revenue_achieved,
                gauge={
                    'axis': {'range': [0, max(sales_target * 1.5, revenue_achieved * 1.2)], 'visible': False},
                    'bar': {'color': gauge_color},
                    'steps': [
                        {'range': [0, sales_target * 0.5], 'color': "lightgray"},
                        {'range': [sales_target * 0.5, sales_target], 'color': "gray"},
                        {'range': [sales_target, sales_target * 1.5], 'color': "darkgray"}
                    ],
                    'threshold': {
                        'line': {'color': "black", 'width': 4},
                        'thickness': 0.75,
                        'value': sales_target
                    }
                }
            ))
            fig.update_layout(height=100, margin=dict(l=0, r=0, t=0, b=0), font=dict(size=6), template="plotly")
            st.plotly_chart(fig, use_container_width=True)

        tab1, tab2 = st.tabs(["Performance", "Customer Insights"])
        color_sequence = px.colors.qualitative.Plotly

        with tab1:
            row1_col1, row1_col2 = st.columns(2)

            with row1_col1:
                st.subheader("Individual Sales Performance")
                granularity = st.selectbox("Granularity", ["Monthly", "Quarterly"], key="sales_granularity", label_visibility="collapsed")
                purchases_df = purchases_df.copy()
                if granularity == "Monthly":
                    purchases_df['period'] = purchases_df['sale_date'].dt.to_period('M').astype(str)
                    x_label = "Month"
                else:
                    purchases_df['period'] = purchases_df['sale_date'].dt.to_period('Q').astype(str)
                    x_label = "Quarter"
                sales_performance = purchases_df.groupby('period')['total_price'].sum().reset_index()
                if not sales_performance.empty:
                    fig = px.line(sales_performance, x='period', y='total_price', markers=True, title="",
                                  color_discrete_sequence=[color_sequence[0]])
                    fig.add_trace(go.Scatter(x=sales_performance['period'], y=[sales_target] * len(sales_performance), mode='lines', name='Target',
                                            line=dict(color='black', dash='dash')))
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=True, template="plotly")
                    fig.update_layout(xaxis_title=x_label, yaxis_title="Sales ($)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No sales data for the selected period.")

            with row1_col2:
                st.subheader("Performance Breakdown by Product and Region")
                breakdown_df = purchases_df.groupby(['product_name', 'country'])['total_price'].sum().reset_index()
                if not breakdown_df.empty:
                    fig = px.bar(breakdown_df, x='product_name', y='total_price', color='country', barmode='group', title="",
                                 color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), 
                                      legend=dict(title="Region", font=dict(size=6)), template="plotly")
                    fig.update_layout(xaxis_title="Product", yaxis_title="Sales ($)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No sales data for performance breakdown.")

        with tab2:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Sales by Product")
                sales_by_product = purchases_df.groupby('product_name')['total_price'].sum().reset_index()
                if not sales_by_product.empty:
                    fig = px.bar(sales_by_product, x='product_name', y='total_price', title="",
                                 color='product_name', color_discrete_sequence=color_sequence)
                    fig.add_trace(go.Scatter(x=sales_by_product['product_name'], y=[sales_target] * len(sales_by_product), 
                                            mode='lines', name='Target', line=dict(color='black', dash='dash')))
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=True, template="plotly")
                    fig.update_layout(xaxis_title="Product", yaxis_title="Sales ($)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No product sales data.")

            with col2:
                st.subheader("Top 3 Customers")
                top_customers = purchases_df.groupby(['customer_id', 'customer_type'])['total_price'].sum().nlargest(3).reset_index()
                if not top_customers.empty:
                    top_customers['customer_label'] = top_customers['customer_id'] + ' (' + top_customers['customer_type'] + ')'
                    fig = px.bar(top_customers, x='customer_label', y='total_price', title="",
                                 color='customer_label', color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=False, template="plotly")
                    fig.update_layout(xaxis_title="Customer", yaxis_title="Total Sales ($)")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No customer sales data.")

# Role-based Dashboard Logic
if role == "Sales Manager":
    with st.container():
        st.header("Sales Manager Dashboard")

        total_sales = purchases_df['total_price'].sum()
        top_products = purchases_df.groupby('product_name')['total_price'].sum().nlargest(5).reset_index()
        sales_by_person = purchases_df.groupby('salesperson')['total_price'].sum().reset_index()
        if not purchases_df.empty:
            top_product = top_products.iloc[0]['product_name'] if not top_products.empty else "N/A"
            top_product_sales = top_products.iloc[0]['total_price'] if not top_products.empty else 0
            top_salesperson = sales_by_person.iloc[0]['salesperson'] if not sales_by_person.empty else "N/A"
            top_salesperson_sales = sales_by_person.iloc[0]['total_price'] if not sales_by_person.empty else 0
        else:
            top_product, top_product_sales, top_salesperson, top_salesperson_sales = "N/A", 0, "N/A", 0
        demo_requests = len(filtered_df[filtered_df['event_type'] == 'Demo Request'])
        color_sequence = px.colors.qualitative.Plotly

        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        with kpi_col1:
            st.metric("Total Revenue", f"${total_sales:,.2f}")
        with kpi_col2:
            st.metric("Top Product", top_product, f"${top_product_sales:,.2f}")
        with kpi_col3:
            st.metric("Top Salesperson", top_salesperson, f"${top_salesperson_sales:,.2f}")
        with kpi_col4:
            st.metric("Demo Requests", demo_requests)

        row1_col1, row1_col2 = st.columns(2)
        row2_col1, row2_col2 = st.columns(2)

        with row1_col1:
            st.subheader("Total Revenue by Product")
            revenue_by_product = purchases_df.groupby('product_name')['total_price'].sum().reset_index()
            if not revenue_by_product.empty:
                fig = px.bar(revenue_by_product, x='product_name', y='total_price', title="",
                             color='product_name', color_discrete_sequence=color_sequence)
                fig.add_trace(go.Scatter(x=revenue_by_product['product_name'], y=[manager_sales_target] * len(revenue_by_product), 
                                        mode='lines', name='Target', line=dict(color='black', dash='dash')))
                fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=True, template="plotly")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No product data.")

        with row1_col2:
            st.subheader("Sales by Channel")
            sales_by_channel = purchases_df.groupby('sales_channel')['total_price'].sum().reset_index()
            if not sales_by_channel.empty:
                fig = px.bar(sales_by_channel, x='sales_channel', y='total_price', title="",
                             color='sales_channel', color_discrete_sequence=color_sequence)
                fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=False, template="plotly")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No channel data.")

        with row2_col1:
            st.subheader("Sales Distribution by Salesperson")
            if not sales_by_person.empty:
                fig = px.pie(sales_by_person, names='salesperson', values='total_price', title="",
                             color_discrete_sequence=color_sequence)
                fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No salesperson data.")

        with row2_col2:
            st.subheader("Sales Trend Over Time by Product")
            granularity = st.selectbox("Granularity", ["Daily", "Weekly", "Monthly", "Yearly"], key="trend_granularity", label_visibility="collapsed")
            if granularity == "Daily":
                sales_by_product_time = purchases_df.groupby([purchases_df['sale_date'].dt.date, 'product_name'])['total_price'].sum().reset_index()
                sales_by_product_time['sale_date'] = sales_by_product_time['sale_date'].astype(str)
                x_label = "Day"
            elif granularity == "Weekly":
                sales_by_product_time = purchases_df.groupby([purchases_df['sale_date'].dt.to_period('W'), 'product_name'])['total_price'].sum().reset_index()
                sales_by_product_time['sale_date'] = sales_by_product_time['sale_date'].astype(str)
                x_label = "Week"
            elif granularity == "Monthly":
                sales_by_product_time = purchases_df.groupby([purchases_df['sale_date'].dt.to_period('M'), 'product_name'])['total_price'].sum().reset_index()
                sales_by_product_time['sale_date'] = sales_by_product_time['sale_date'].astype(str)
                x_label = "Month"
            else:
                sales_by_product_time = purchases_df.groupby([purchases_df['sale_date'].dt.to_period('Y'), 'product_name'])['total_price'].sum().reset_index()
                sales_by_product_time['sale_date'] = sales_by_product_time['sale_date'].astype(str)
                x_label = "Year"
            if not sales_by_product_time.empty:
                fig = px.line(sales_by_product_time, x='sale_date', y='total_price', color='product_name', title="",
                              color_discrete_sequence=color_sequence)
                unique_dates = sales_by_product_time['sale_date'].unique()
                fig.add_trace(go.Scatter(x=unique_dates, y=[manager_sales_target] * len(unique_dates), mode='lines', name='Target',
                                        line=dict(color='black', dash='dash')))
                fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                fig.update_layout(xaxis_title=x_label, yaxis_title="Sales ($)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("No trend data.")

elif role == "Salesperson":
    salesperson_dashboard(filtered_df, selected_salesperson, start_date, end_date, min_date, max_date, sales_target)

elif role == "Sales Marketer":
    with st.container():
        st.header("Sales Marketer Dashboard")

        total_visits = len(filtered_df['session_id'].unique())
        avg_session_length = filtered_df.groupby('session_id')['response_time_ms'].mean().mean() if not filtered_df.empty else 0
        filtered_df = filtered_df.copy()
        filtered_df['hour'] = pd.to_datetime(filtered_df['timestamp']).dt.hour
        most_active_hour = filtered_df['hour'].mode().iloc[0] if not filtered_df['hour'].empty else "N/A"
        color_sequence = px.colors.qualitative.Plotly

        kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
        with kpi_col1:
            st.metric("Total Visits", total_visits)
        with kpi_col2:
            st.metric("Avg. Session Length (ms)", f"{avg_session_length:,.2f}")
        with kpi_col3:
            st.metric("Most Active Hour", f"{most_active_hour}:00")
        with kpi_col4:
            st.metric("Total Log Requests", len(filtered_df))

        tab1, tab2 = st.tabs(["Customer Insights", "Web Analysis"])

        with tab1:
            row1_col1, row1_col2 = st.columns(2)
            row2_col1, row2_col2 = st.columns(2)

            with row1_col1:
                st.subheader("Geographic Sales Distribution")
                geo_df = purchases_df.groupby('country')['total_price'].sum().reset_index()
                if not geo_df.empty:
                    fig = px.choropleth(geo_df, locations='country', locationmode='country names', color='total_price', title="",
                                        color_continuous_scale='Plasma')
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=False, template="plotly")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No geographic data.")

            with row1_col2:
                st.subheader("Product Sales by Age")
                age_bins = [0, 20, 30, 40, 50, 100]
                age_labels = ['0-20', '21-30', '31-40', '41-50', '51+']
                purchases_df = purchases_df.copy()
                purchases_df['age_group'] = pd.cut(purchases_df['customer_age'], bins=age_bins, labels=age_labels, include_lowest=True)
                sales_by_age_product = purchases_df.groupby(['age_group', 'product_name'])['total_price'].sum().reset_index()
                if not sales_by_age_product.empty:
                    fig = px.bar(sales_by_age_product, x='age_group', y='total_price', color='product_name', barmode='group', title="",
                                 color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No age data.")

            with row2_col1:
                st.subheader("Product Sales by Occupation")
                sales_by_occupation_product = purchases_df.groupby(['occupation', 'product_name'])['total_price'].sum().reset_index()
                if not sales_by_occupation_product.empty:
                    fig = px.bar(sales_by_occupation_product, x='occupation', y='total_price', color='product_name', barmode='group', title="",
                                 color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No occupation data.")

            with row2_col2:
                st.subheader("Top 5 High-Value Clients")
                top_customers = purchases_df.groupby(['customer_id', 'customer_type'])['total_price'].sum().nlargest(5).reset_index()
                if not top_customers.empty:
                    top_customers['customer_label'] = top_customers['customer_id'] + ' (' + top_customers['customer_type'] + ')'
                    fig = px.bar(top_customers, x='customer_label', y='total_price', title="",
                                 color='customer_label', color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), showlegend=False, template="plotly")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No client data.")

        with tab2:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Most Visited URLs")
                url_visits = filtered_df['url_requested'].value_counts().reset_index()
                url_visits.columns = ['url_requested', 'count']
                if not url_visits.empty:
                    fig = px.pie(url_visits, names='url_requested', values='count', title="",
                                 color_discrete_sequence=color_sequence)
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No URL data.")

            with col2:
                st.subheader("URL Trend Over Time")
                granularity = st.selectbox("Granularity", ["Daily", "Weekly", "Monthly"], key="url_trend_granularity", label_visibility="collapsed")
                if granularity == "Daily":
                    url_trend = filtered_df.groupby([filtered_df['timestamp'].dt.date, 'url_requested']).size().reset_index(name='count')
                    url_trend['timestamp'] = url_trend['timestamp'].astype(str)
                    x_label = "Day"
                elif granularity == "Weekly":
                    url_trend = filtered_df.groupby([filtered_df['timestamp'].dt.to_period('W'), 'url_requested']).size().reset_index(name='count')
                    url_trend['timestamp'] = url_trend['timestamp'].astype(str)
                    x_label = "Week"
                else:
                    url_trend = filtered_df.groupby([filtered_df['timestamp'].dt.to_period('M'), 'url_requested']).size().reset_index(name='count')
                    url_trend['timestamp'] = url_trend['timestamp'].astype(str)
                    x_label = "Month"
                if not url_trend.empty:
                    fig = px.line(url_trend, x='timestamp', y='count', color='url_requested', title="",
                                  color_discrete_sequence=color_sequence)
                    unique_timestamps = url_trend['timestamp'].unique()
                    fig.add_trace(go.Scatter(x=unique_timestamps, y=[marketer_url_target] * len(unique_timestamps), mode='lines', name='Target',
                                            line=dict(color='black', dash='dash')))
                    fig.update_layout(height=150, margin=dict(l=5, r=5, t=10, b=10), font=dict(size=7), legend=dict(font=dict(size=6)), template="plotly")
                    fig.update_layout(xaxis_title=x_label, yaxis_title="Visits")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("No URL trend data.")