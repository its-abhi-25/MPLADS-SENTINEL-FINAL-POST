"""
MPLADS Sentinel - Realistic Dataset Generator
Generates a synthetic but realistic MPLADS dataset with embedded anomalies
for demonstration purposes.
"""
import csv
import random
import os
from datetime import datetime, timedelta

random.seed(42)

# Real Indian MP names and constituencies
MPS = [
    ("Rajesh Kumar Singh", "Azamgarh", "Uttar Pradesh"),
    ("Priya Sharma", "Lucknow", "Uttar Pradesh"),
    ("Amit Verma", "Kanpur", "Uttar Pradesh"),
    ("Sunita Devi", "Meerut", "Uttar Pradesh"),
    ("Vikram Patel", "Ghaziabad", "Uttar Pradesh"),
    ("Anita Kumari", "Agra", "Uttar Pradesh"),
    ("Suresh Yadav", "Varanasi", "Uttar Pradesh"),
    ("Meena Kumari", "Allahabad", "Uttar Pradesh"),
    ("Ravi Shankar Prasad", "Patna", "Bihar"),
    ("Kavita Singh", "Gaya", "Bihar"),
    ("Manoj Tiwari", "North East Delhi", "Delhi"),
    ("Sheila Dikshit", "New Delhi", "Delhi"),
    ("Arvind Kejriwal", "South Delhi", "Delhi"),
    ("Pankaj Gupta", "Central Delhi", "Delhi"),
    ("Ramesh Bidhuri", "South Delhi", "Delhi"),
    ("Mahesh Sharma", "Noida", "Uttar Pradesh"),
    ("Satyapal Singh", "Baghpat", "Uttar Pradesh"),
    ("Kanwar Singh Tanwar", "Amroha", "Uttar Pradesh"),
    ("Raj Babbar", "Firozabad", "Uttar Pradesh"),
    ("Dimple Yadav", "Mainpuri", "Uttar Pradesh"),
    ("Akhilesh Yadav", "Azamgarh", "Uttar Pradesh"),
    ("Mulayam Singh Yadav", "Mainpuri", "Uttar Pradesh"),
    ("Akhilesh Kumar", "Gorakhpur", "Uttar Pradesh"),
    ("Prahlad Singh Patel", "Narsinghpur", "Madhya Pradesh"),
    ("Narendra Singh Tomar", "Gwalior", "Madhya Pradesh"),
    ("Kailash Joshi", "Bhopal", "Madhya Pradesh"),
    (" Uma Bharti", "Jhansi", "Madhya Pradesh"),
    ("Babulal Gaur", "Bhopal", "Madhya Pradesh"),
    ("Narottam Mishra", "Datia", "Madhya Pradesh"),
    ("Sadhvi Niranjan Jyoti", "Fatehpur", "Uttar Pradesh"),
    ("Sakshi Maharaj", "Unnao", "Uttar Pradesh"),
    ("Rajyavardhan Singh Rathore", "Jaipur Rural", "Rajasthan"),
    ("Gajendra Singh Shekhawat", "Jodhpur", "Rajasthan"),
    ("Om Birla", "Kota", "Rajasthan"),
    ("Rao Rajendra Singh", "Karauli-Dholpur", "Rajasthan"),
    ("Col. Rajyavardhan Rathore", "Jaipur Rural", "Rajasthan"),
    ("Kirit Premjibhai Solanki", "Ahmedabad West", "Gujarat"),
    ("Paresh Rawal", "Ahmedabad East", "Gujarat"),
    ("Mohan Kundariya", "Rajkot", "Gujarat"),
    ("Devusinh Chauhan", "Kheda", "Gujarat"),
    ("Naranbhai Kachhadia", "Amreli", "Gujarat"),
    ("Ramesh Chandappa Jadhav", "Bharuch", "Gujarat"),
    ("Prabhavati Taviyad", "Bhavnagar", "Gujarat"),
    ("Dipsinh Rathod", "Sabarkantha", "Gujarat"),
    ("Jaswantsinh Sumanbhai Bhabhor", "Dahod", "Gujarat"),
    ("Ranjanben Dhananjay Bhatt", "Vadodara", "Gujarat"),
    ("Mansukhbhai Vasava", "Bharuch", "Gujarat"),
    ("Laxmi Rajput", "Surat", "Gujarat"),
    ("Narendra Modi", "Varanasi", "Uttar Pradesh"),
    ("Rahul Gandhi", "Wayanad", "Kerala"),
    ("Sonia Gandhi", "Rae Bareli", "Uttar Pradesh"),
    ("Mamata Banerjee", "Kolkata Dakshin", "West Bengal"),
    ("Sharad Pawar", "Maval", "Maharashtra"),
    ("Uddhav Thackeray", "Raigad", "Maharashtra"),
    ("Nitin Gadkari", "Nagpur", "Maharashtra"),
    ("Rajnath Singh", "Lucknow", "Uttar Pradesh"),
    ("Smriti Irani", "Amethi", "Uttar Pradesh"),
    ("Jyotiraditya Scindia", "Guna", "Madhya Pradesh"),
    ("Digvijaya Singh", "Rajgarh", "Madhya Pradesh"),
    ("Shashi Tharoor", "Thiruvananthapuram", "Kerala"),
]

# Work categories with typical cost ranges
CATEGORIES = {
    "Road Construction": (5, 80),
    "Drainage Construction": (3, 40),
    "Water Supply": (2, 35),
    "Street Lighting": (1, 15),
    "School Building": (3, 50),
    "Health Center": (5, 60),
    "Community Hall": (2, 25),
    "Park Development": (1, 20),
    "Bridge Construction": (10, 100),
    "Boundary Wall": (1, 15),
    "Toilet Construction": (0.5, 8),
    "Electricity Supply": (2, 30),
    "Flood Protection": (5, 70),
    "Skill Development Center": (3, 40),
    "Anganwadi Construction": (1, 12),
}

# Description templates
DESCRIPTIONS = {
    "Road Construction": [
        "Construction of road from {loc} to {loc2}",
        "Widening of road near {loc}",
        "Resurfacing of road in {loc}",
        "Construction of cement concrete road in {loc}",
        "Black topping of road from {loc} to {loc2}",
        "Repair and maintenance of road at {loc}",
        "Construction of road under PMGSY at {loc}",
        "Bituminous road construction at {loc}",
    ],
    "Drainage Construction": [
        "Construction of drain at {loc}",
        "Side drain construction in {loc}",
        "Covered drain at {loc}",
        "Drainage line at {loc}",
        "Nala improvement at {loc}",
        "Storm water drain at {loc}",
    ],
    "Water Supply": [
        "Construction of water tank at {loc}",
        "Hand pump installation at {loc}",
        "Water supply scheme at {loc}",
        "Bore well construction at {loc}",
        "Overhead water tank at {loc}",
        "Pipeline connection at {loc}",
    ],
    "Street Lighting": [
        "Solar street light at {loc}",
        "LED street light installation at {loc}",
        "Street light pole at {loc}",
        "Lighting arrangement at {loc}",
    ],
    "School Building": [
        "Construction of school building at {loc}",
        "Classroom construction at {loc}",
        "School boundary wall at {loc}",
        "Additional room for school at {loc}",
        "Toilet block for school at {loc}",
    ],
    "Health Center": [
        "PHC construction at {loc}",
        "Health center building at {loc}",
        "Medical facility center at {loc}",
        "Primary health sub-center at {loc}",
        "Dispensary construction at {loc}",
    ],
    "Community Hall": [
        "Community hall construction at {loc}",
        "Function hall at {loc}",
        "Sabha bhawan at {loc}",
        "Community center at {loc}",
    ],
    "Park Development": [
        "Park development at {loc}",
        "Garden construction at {loc}",
        "Children park at {loc}",
        "Public park at {loc}",
    ],
    "Bridge Construction": [
        "Bridge construction at {loc}",
        "Culvert construction at {loc}",
        "Minor bridge at {loc}",
        "RCC bridge at {loc}",
    ],
    "Boundary Wall": [
        "Boundary wall construction at {loc}",
        "Compound wall at {loc}",
        "Fencing work at {loc}",
    ],
    "Toilet Construction": [
        "Toilet construction at {loc}",
        "Community toilet at {loc}",
        "Individual toilet at {loc}",
        "Toilet block at {loc}",
    ],
    "Electricity Supply": [
        "Electricity connection at {loc}",
        "Transformer installation at {loc}",
        "Electric pole at {loc}",
        "HT/LT line at {loc}",
    ],
    "Flood Protection": [
        "Flood protection wall at {loc}",
        "Embankment at {loc}",
        "River bank protection at {loc}",
    ],
    "Skill Development Center": [
        "Skill development center at {loc}",
        "ITI construction at {loc}",
        "Training center at {loc}",
    ],
    "Anganwadi Construction": [
        "Anganwadi building at {loc}",
        "Anganwadi center at {loc}",
        "Pre-school construction at {loc}",
    ],
}

LOCATIONS = [
    "Village Rampur", "Gram Panchayat Sonpur", "Ward No 5", "Ward No 12",
    "Block Haripur", "Tehsil Sitapur", "Mouza Khandwa", "Colony Rajiv Nagar",
    "Near Bus Stand", "Main Market Area", "School Road", "Hospital Road",
    "Temple Area", "Mosque Road", "Church Road", "Gurudwara Road",
    "Railway Crossing", "Canal Road", "River Bank", "Hill Side",
    "Industrial Area", "Agricultural Land", "Forest Border", "Lakeside",
    "Bridge End", "Dam Site", "Municipal Area", "Panchayat Bhawan",
    "Village Ghazipur", "Gram Panchayat Lucknow", "Ward No 3", "Ward No 8",
    "Block Muzaffarnagar", "Tehsil Aligarh", "Mouza Varanasi", "Colony Nehru Nagar",
    "Near Police Station", "Market Road", "College Road", "University Road",
    "Park Area", "Sports Complex", "Community Center", "Wedding Hall",
    "Gas Station", "Petrol Pump", "Shopping Complex", "Office Building",
]

def generate_dates(start_year=2019, end_year=2024):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31)
    delta = (end - start).days
    random_day = random.randint(0, delta)
    return start + timedelta(days=random_day)

def generate_amount(category):
    low, high = CATEGORIES[category]
    # Most amounts cluster toward lower end
    amount = random.triangular(low, high, low + (high - low) * 0.3)
    # Some round numbers
    if random.random() < 0.3:
        amount = round(amount)
    else:
        amount = round(amount, 2)
    return amount

def add_anomalies(records):
    """Inject realistic anomalies into the dataset"""
    anomalous_indices = []
    
    # 1. COST ANOMALIES: Very high amounts for category
    for i in range(15):
        idx = random.randint(0, len(records) - 1)
        cat = records[idx]['Work Category']
        low, high = CATEGORIES[cat]
        records[idx]['Amount (Rs. Lakhs)'] = str(round(random.uniform(high * 1.5, high * 3), 2))
        records[idx]['Work Description'] = records[idx]['Work Description'] + " (URGENT)"
        anomalous_indices.append(('cost_anomaly', idx))
    
    # 2. DUPLICATE-ISH records (very similar descriptions, same MP)
    for i in range(10):
        base_idx = random.randint(0, len(records) - 1)
        dup_idx = random.randint(0, len(records) - 1)
        if base_idx != dup_idx:
            records[dup_idx]['Work Description'] = records[base_idx]['Work Description']
            records[dup_idx]['MP Name'] = records[base_idx]['MP Name']
            records[dup_idx]['Amount (Rs. Lakhs)'] = str(float(records[base_idx]['Amount (Rs. Lakhs)']) * random.uniform(0.95, 1.05))
            records[dup_idx]['Work Category'] = records[base_idx]['Work Category']
            anomalous_indices.append(('duplicate', dup_idx))
    
    # 3. CONCENTRATION: Many records same MP, same category, same area
    concentration_mp = MPS[0]  # First MP
    for i in range(20):
        idx = random.randint(0, len(records) - 1)
        records[idx]['MP Name'] = concentration_mp[0]
        records[idx]['Constituency'] = concentration_mp[1]
        records[idx]['State'] = concentration_mp[2]
        records[idx]['Work Category'] = "Road Construction"
        records[idx]['Amount (Rs. Lakhs)'] = str(round(random.uniform(10, 25), 2))
        anomalous_indices.append(('concentration', idx))
    
    # 4. TEMPORAL CLUSTER: Many records same date
    cluster_date = "15/03/2022"
    for i in range(12):
        idx = random.randint(0, len(records) - 1)
        records[idx]['Sanction Date'] = cluster_date
        anomalous_indices.append(('temporal', idx))
    
    # 5. ROUND AMOUNT anomalies
    for i in range(8):
        idx = random.randint(0, len(records) - 1)
        records[idx]['Amount (Rs. Lakhs)'] = str(float(records[idx]['Amount (Rs. Lakhs)']) * 10)
        anomalous_indices.append(('round_amount', idx))
    
    # 6. Missing/empty values
    for i in range(25):
        idx = random.randint(0, len(records) - 1)
        field = random.choice(['Work Description', 'Amount (Rs. Lakhs)', 'Sanction Date'])
        records[idx][field] = ""
        anomalous_indices.append(('missing', idx))
    
    # 7. Malformed values
    for i in range(10):
        idx = random.randint(0, len(records) - 1)
        records[idx]['Amount (Rs. Lakhs)'] = random.choice([
            "N/A", "Rs. 5.00", "5 lakhs", "5,00,000", "pending", "TBD", "---"
        ])
        anomalous_indices.append(('malformed', idx))
    
    return records, anomalous_indices

def main():
    records = []
    record_id = 1
    
    for mp_name, constituency, state in MPS:
        # Each MP has 20-40 records
        num_records = random.randint(20, 40)
        for _ in range(num_records):
            category = random.choice(list(CATEGORIES.keys()))
            desc_template = random.choice(DESCRIPTIONS[category])
            loc1 = random.choice(LOCATIONS)
            loc2 = random.choice(LOCATIONS)
            description = desc_template.format(loc=loc1, loc2=loc2)
            
            amount = generate_amount(category)
            date = generate_dates()
            
            record = {
                'Record ID': f"MPL-{record_id:05d}",
                'MP Name': mp_name,
                'Work Description': description,
                'Work Category': category,
                'Amount (Rs. Lakhs)': str(amount),
                'Constituency': constituency,
                'State': state,
                'Sanction Date': date.strftime('%d/%m/%Y'),
            }
            records.append(record)
            record_id += 1
    
    # Add anomalies
    records, anomaly_indices = add_anomalies(records)
    
    # Shuffle
    random.shuffle(records)
    
    # Write CSV
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'raw')
    os.makedirs(output_dir, exist_ok=True)
    
    filepath = os.path.join(output_dir, 'mplads_works.csv')
    fieldnames = ['Record ID', 'MP Name', 'Work Description', 'Work Category', 
                  'Amount (Rs. Lakhs)', 'Constituency', 'State', 'Sanction Date']
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    
    print(f"Generated {len(records)} records")
    print(f"Anomalies injected: {len(anomaly_indices)}")
    print(f"Saved to: {filepath}")
    
    # Print summary
    print(f"\nDataset Summary:")
    print(f"  Total records: {len(records)}")
    print(f"  Unique MPs: {len(set(r['MP Name'] for r in records))}")
    print(f"  Categories: {len(set(r['Work Category'] for r in records))}")
    print(f"  States: {len(set(r['State'] for r in records))}")

if __name__ == "__main__":
    main()
