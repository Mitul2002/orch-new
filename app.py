from fastapi import FastAPI, HTTPException, UploadFile, Form
from pydantic import BaseModel
import pandas as pd
import os
from typing import Dict, List
from statistics import mean

app = FastAPI()

# Set base path as constant
BASE_PATH = "/home/miso/Documents/new2/xlsx/clean"


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
    target_spend: float, carrier: str, tolerance: float, top_n: int
) -> Dict:
    lower_spend = target_spend * (1 - tolerance)
    upper_spend = target_spend * (1 + tolerance)
    carrier_path = os.path.join(BASE_PATH, carrier)

    service_discounts = {}

    for filename in os.listdir(carrier_path):
        if filename.endswith(".xlsx"):
            contract_spend = float(filename.split("_")[1].replace(".xlsx", ""))

            if lower_spend <= contract_spend <= upper_spend:
                df = pd.read_excel(os.path.join(carrier_path, filename))
                current_col = f"CURRENT {carrier.upper()}"

                for _, row in df.iterrows():
                    service = row["DOMESTIC AIR SERVICE LEVEL"]
                    try:
                        discount = normalize_discount(float(row[current_col]))

                        if service not in service_discounts:
                            service_discounts[service] = []
                        service_discounts[service].append(discount)
                    except (ValueError, TypeError):
                        continue

    service_stats = {}
    for service, discounts in service_discounts.items():
        if discounts:
            service_stats[service] = {
                "avg_discount": mean(discounts),
                "min_discount": min(discounts),
                "max_discount": max(discounts),
                "contract_count": len(discounts),
                "discount_values": sorted(discounts),
            }

    sorted_services = dict(
        sorted(
            service_stats.items(),
            key=lambda x: x[1]["avg_discount"],
            reverse=True,
        )[:top_n]
    )

    return sorted_services


@app.post("/analyze_contracts/")
async def analyze_contracts_endpoint(
    carrier: str = Form(...),
    tolerance: float = Form(...),
    top_n: int = Form(...),
    file: UploadFile = Form(...),
):
    if not file or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported.")

    try:
        target_spend = extract_target_spend(file)
        results = analyze_contracts(
            target_spend,
            carrier,
            tolerance,
            top_n,
        )
        return format_results(results)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def format_results(stats: Dict) -> Dict:
    formatted = []
    for service, data in stats.items():
        formatted.append(
            {
                "service_level": service,
                "average_discount": round(data["avg_discount"] * 100, 2),
                "min_discount": round(data["min_discount"] * 100, 2),
                "max_discount": round(data["max_discount"] * 100, 2),
                "contract_count": data["contract_count"],
                "discount_values": [round(d * 100, 2) for d in data["discount_values"]],
            }
        )
    return {"results": formatted}
