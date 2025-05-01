from flask import Flask, render_template, redirect, request, url_for
import mysql.connector
import folium
import pickle
import os
from geopy.geocoders import Nominatim
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.preprocessing import MinMaxScaler



app = Flask(__name__)

mydb = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    port="3306",
    database='map'
)

mycursor = mydb.cursor()

def executionquery(query, values):
    mycursor.execute(query, values)
    mydb.commit()
    return

def retrivequery1(query, values):
    mycursor.execute(query, values)
    data = mycursor.fetchall()
    return data

def retrivequery2(query):
    mycursor.execute(query)
    data = mycursor.fetchall()
    return data


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        c_password = request.form['c_password']
        if password == c_password:
            query = "SELECT UPPER(email) FROM users"
            email_data = retrivequery2(query)
            email_data_list = []
            for i in email_data:
                email_data_list.append(i[0])
            if email.upper() not in email_data_list:
                query = "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)"
                values = (name, email, password)
                executionquery(query, values)
                return render_template('login.html', message="Successfully Registered! Please go to login section")
            return render_template('register.html', message="This email ID already exists!")
        return render_template('register.html', message="Confirm password does not match!")
    return render_template('register.html')


@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']
        
        query = "SELECT UPPER(email) FROM users"
        email_data = retrivequery2(query)
        email_data_list = []
        for i in email_data:
            email_data_list.append(i[0])

        if email.upper() in email_data_list:
            query = "SELECT UPPER(password) FROM users WHERE email = %s"
            values = (email,)
            password__data = retrivequery1(query, values)
            if password.upper() == password__data[0][0]:
                global user_email
                user_email = email
                return redirect("/home")
            return render_template('login.html', message="Invalid Password!!")
        return render_template('login.html', message="This email ID does not exist!")
    return render_template('login.html')


@app.route('/home')
def home():
    return render_template('home.html')

### Map Integration and House Price Prediction ###
geolocator = Nominatim(user_agent="mumbai_map")

# Load dataset
df = pd.read_excel(r'dataset/mumbai_dataset.xlsx')
df.drop(["Unnamed: 0"], axis=1, inplace=True)

# Handle missing values
numerical_cols = df.select_dtypes(include=['float64', 'int64']).columns
imputer = SimpleImputer(strategy='median')
df[numerical_cols] = imputer.fit_transform(df[numerical_cols])

# Normalize data
scaler = MinMaxScaler()
X_scaled = scaler.fit_transform(df[numerical_cols])

# Apply KMeans Clustering for House Prices
kmeans = KMeans(n_clusters=5, random_state=42)
df['Cluster'] = kmeans.fit_predict(X_scaled)
df['Price'] = df['Cluster'].map({0: 5000000, 1: 8000000, 2: 10000000, 3: 20000000, 4: 30000000})

# Mapping price to amenities based on your requirement
def map_amenities(price):
    if price == 5000000:
        return "Low"
    elif price == 8000000:
        return "Good"
    elif price in [10000000, 20000000, 30000000]:
        return "Best"
    return "N/A"  # Default if price doesn't match

# Apply the mapping function to create the amenities column
df['amenities'] = df['Price'].apply(map_amenities)

# Save Final Dataset
df.to_csv("dataset/Final_dataset.csv", index=False)

# Create Dictionary for Mapping Areas to Prices and Amenities
area_prices = dict(zip(df['Area'], df['Price']))
area_amenities = dict(zip(df['Area'], df['amenities']))

# Caching Geolocations
CACHE_FILE = "dataset/location_cache.pkl"

# Load cache if it exists
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "rb") as f:
        location_cache = pickle.load(f)
else:
    location_cache = {}

def get_location(area):
    """Retrieve location from cache or geocode if not available."""
    if area in location_cache:
        return location_cache[area]

    location = geolocator.geocode(area + ", Mumbai, India", timeout=10)
    if location:
        location_cache[area] = (location.latitude, location.longitude)

        # Save to cache
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(location_cache, f)

        return location.latitude, location.longitude
    return None


### Route to Generate Prediction Map ###
@app.route('/prediction', methods=["GET", "POST"])
def prediction():
    """Generate a map with area-wise house prices and amenities."""
    mumbai_map = folium.Map(location=[19.0760, 72.8777], zoom_start=12)
    # Define colors for different price clusters
    cluster_colors = {
        0: 'red', 1: 'blue', 2: 'green', 3: 'purple', 4: 'orange'
    }
    for area, price in area_prices.items():
        try:
            cluster = df[df['Area'] == area]['Cluster'].values[0]
            color = cluster_colors.get(cluster, 'gray')
            location = get_location(area)
            if location:
                folium.Marker(
                    location=location,
                    popup=f"{area}: ₹{price:,} ({area_amenities[area]})",
                    icon=folium.Icon(color=color, icon='info-sign')
                ).add_to(mumbai_map)
        except Exception as e:
            print(f"Error fetching location for {area}: {e}")
    mumbai_map.save('templates/mumbai_map.html')
    return render_template('mumbai_map.html')


### Route for Search Page ###
@app.route('/search', methods=["GET", "POST"])
def search():
    if request.method == "POST":
        selected_area = request.form['area']
        selected_amenities = request.form.getlist('amenities')

        price = area_prices.get(selected_area, "Price data not available")
        amenities_level = area_amenities.get(selected_area, "Amenities data not available")

        dataframe = pd.read_csv(r'dataset/Final_dataset.csv')
        filtered_df = dataframe[dataframe['Area'] == selected_area]

        # Get actual column names based on selected amenities
        if selected_amenities:
            # User selected specific amenities
            columns_to_display = ['Area'] + selected_amenities
        else:
            # No amenities selected → Show all amenities
            # Get all amenity columns except 'Area'
            amenity_columns = [col for col in filtered_df.columns if col != 'Area']
            columns_to_display = ['Area'] + amenity_columns

        # Filter dataframe
        filtered_df = filtered_df[columns_to_display]

        # Clean up numeric formatting (optional)
        filtered_df = filtered_df.apply(lambda x: pd.to_numeric(x, errors='ignore').astype('Int64') if x.dtype == 'float64' else x)

        # Convert to HTML table
        table_html = filtered_df.to_html(classes='table table-bordered', index=False)

        return render_template('search_result.html',
                               area=selected_area,
                               price=price,
                               amenities_level=amenities_level,
                               selected_area=selected_area,
                               table_html=table_html)

    return render_template('search.html', areas=df['Area'].tolist())



@app.route('/view_area_on_map/<area>', methods=["GET"])
def view_area_on_map(area):
    """Display a map centered on the selected area with house price and amenities details."""
    location = get_location(area)

    if not location:
        return render_template('view_area_on_map.html', error=f"Location for {area} not found!")

    # Create a folium map centered on the area
    area_map = folium.Map(location=location, zoom_start=15)

    # Fetch price and amenities details
    price = area_prices.get(area, "Price data not available")
    amenities_level = area_amenities.get(area, "Amenities data not available")

    # Add a marker with a popup
    folium.Marker(
        location=location,
        popup=f"<b>{area}</b><br>Price: ₹{price:,}<br>Amenities: {amenities_level}",
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(area_map)

    # Save map as HTML
    map_file = f"static/maps/{area.replace(' ', '_')}.html"
    area_map.save(map_file)

    return render_template('view_area_on_map.html', area=area, map_file=map_file, price=price, amenities_level=amenities_level)

if __name__ == '__main__':
    app.run(debug=True)
