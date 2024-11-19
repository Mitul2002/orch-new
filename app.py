from fastapi import FastAPI, HTTPException, UploadFile, Form
from pydantic import BaseModel
import pandas as pd
import os
from typing import Dict
from statistics import mean

app = FastAPI()

# Set base path as constant
BASE_PATH = "/home/miso/Documents/new2/xlsx/clean"

class SearchRequest(BaseModel):
    carrier: str
    tolerance: float
    top_n: int

def normalize_discount(discount: float) -> float:
    """Normalize discount value by dividing by 100 if it's greater than 100"""
    if discount > 100:
        return discount / 100
    return discount

def extract_target_spend(file: UploadFile) -> float:
    """Extract target spend by summing the 'total_charge' column from an Excel file."""
    try:
        df = pd.read_excel(file.file)
        if "total_charge" not in df.columns:
            raise ValueError("The Excel file must contain a 'total_charge' column.")
        return df["total_charge"].sum()
    except Exception as e:
        raise ValueError(f"Error processing the file: {e}")

def analyze_contracts(
    target_spend: float,
    carrier: str,
    tolerance: float,
    top_n: int
) -> Dict:
    """
    Analyze contracts to get statistics for each service level.
    
    Args:
        target_spend: Target spend amount as float (e.g., 670000)
        carrier: Carrier name (e.g., 'UPS', 'FedEx')
        tolerance: Tolerance range as decimal (e.g., 0.2 for 20%)
        top_n: Number of top service levels to return
        
    Returns:
        Dictionary containing service level statistics
    """
    lower_spend = target_spend * (1 - tolerance)
    upper_spend = target_spend * (1 + tolerance)
    carrier_path = os.path.join(BASE_PATH, carrier)
    
    # Dictionary to store discounts by service level
    service_discounts = {}
    
    # Read all contract files in the carrier directory
    for filename in os.listdir(carrier_path):
        if filename.endswith('.xlsx'):
            contract_spend = float(filename.split('_')[1].replace('.xlsx', ''))
                
            # Check if contract is within spend range
            if lower_spend <= contract_spend <= upper_spend:
                df = pd.read_excel(os.path.join(carrier_path, filename))
                current_col = f'CURRENT {carrier.upper()}'
                
                for _, row in df.iterrows():
                    service = row['DOMESTIC AIR SERVICE LEVEL']
                    try:
                        discount = normalize_discount(float(row[current_col]))
                        
                        if service not in service_discounts:
                            service_discounts[service] = []
                        service_discounts[service].append(discount)
                    except (ValueError, TypeError):
                        continue  # Skip invalid values
    
    # Calculate statistics for each service level
    service_stats = {}
    for service, discounts in service_discounts.items():
        if discounts:  # Only process if we have valid discounts
            service_stats[service] = {
                'avg_discount': mean(discounts),
                'min_discount': min(discounts),
                'max_discount': max(discounts),
                'contract_count': len(discounts),
                'discount_values': sorted(discounts)
            }
    
    # Sort by average discount and get top N
    sorted_services = dict(sorted(
        service_stats.items(),
        key=lambda x: x[1]['avg_discount'],
        reverse=True
    )[:top_n])
    
    return sorted_services

@app.post("/analyze_contracts/")
async def analyze_contracts_endpoint(request: SearchRequest, file: UploadFile):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")
    
    try:
        target_spend = extract_target_spend(file)
        results = analyze_contracts(
            target_spend,
            request.carrier,
            request.tolerance,
            request.top_n
        )
        return format_results(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def format_results(stats: Dict) -> str:
    """Format results dictionary into the requested output string"""
    output = []
    
    for service, data in stats.items():
        # Multiply percentage values by 100 for display
        avg_discount = data['avg_discount'] * 100
        min_discount = data['min_discount'] * 100
        max_discount = data['max_discount'] * 100
        discount_values = [d * 100 for d in data['discount_values']]
        
        service_output = [
            f"\nService Level: {service}",
            f"Average Discount: {avg_discount:.2f}",
            f"Min Discount: {min_discount:.2f}",
            f"Max Discount: {max_discount:.2f}",
            f"Contract Count: {data['contract_count']}",
            f"Discount Values: {', '.join(f'{d:.2f}' for d in discount_values)}"
        ]
        output.extend(service_output)
    
    return "\n".join(output)
