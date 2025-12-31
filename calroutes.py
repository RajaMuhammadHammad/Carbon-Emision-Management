from flask import Blueprint, render_template, request, redirect, url_for, session
import os, json
import google.generativeai as genai  
from google.generativeai import types  
import pyodbc
from db import get_db_connection






cal_bp = Blueprint("cal_bp", __name__, template_folder="templates", static_folder="static")



DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


with open(os.path.join(DATA_DIR, "scope2.json"), "r") as f:
    scope2_data = json.load(f)


with open(os.path.join(DATA_DIR, "scope1.json"), "r") as f:
    data = json.load(f)


with open(os.path.join(DATA_DIR, "scope3.json"), "r") as f:
    scope3_json = json.load(f)
    scope3_data = scope3_json["Scope3"]  

scope1_data = data["scope1"]  

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


# ----------------- ROUTES -----------------

@cal_bp.route("/skip_scope1")
def skip_scope1():
    session["scope1_total"] = 0.0
    session["scope1_results"] = []
    return redirect(url_for("cal_bp.scope2"))



@cal_bp.route("/skip_scope2")
def skip_scope2():
    session["scope2_total"] = 0.0
    session["scope2_results"] = []
    return redirect(url_for("cal_bp.scope3"))



# -------- SCOPE 1 --------
@cal_bp.route("/scope1", methods=["GET", "POST"])
def scope1():
    results = []
    total_emission = 0.0

    if request.method == "POST":
        # Loop through all categories at once
        for category in scope1_data:
            cat_name = category["category"]

            # -------- Stationary Combustion --------
            for fuel in category.get("fuels", []):
                name = fuel["name"]
                qty = request.form.get(f"qty_{name}")
                unit = request.form.get(f"unit_{name}")

                if qty and unit:
                    try:
                        qty_val = float(qty)
                        factor = fuel["units"].get(unit)
                        if factor and qty_val > 0:
                            emission = round(qty_val * factor, 2)
                            results.append({
                                "category": cat_name,
                                "item": name,
                                "unit": unit,
                                "qty": qty_val,
                                "factor": factor,
                                "emission": emission
                            })
                            total_emission += emission
                    except ValueError:
                        continue

            # -------- Mobile Emissions --------
            for vehicle, fuels_list in category.get("vehicles", {}).items():
                for fuel in fuels_list:
                    name = f"{vehicle} - {fuel['fuel']}"
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * fuel["emission_factor"], 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": fuel["unit"],
                                    "qty": qty_val,
                                    "factor": fuel["emission_factor"],
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue

            # -------- Fugitive Emissions --------
            for chem in category.get("chemicals", []):
                name = chem["name"]
                qty = request.form.get(f"qty_{name}")

                if qty:
                    try:
                        qty_val = float(qty)
                        if qty_val > 0:
                            emission = round(qty_val * chem["emission_factor"])
                            results.append({
                                "category": cat_name,
                                "item": name,
                                "unit": chem["unit"],
                                "qty": qty_val,
                                "factor": chem["emission_factor"],
                                "emission": emission
                            })
                            total_emission += emission
                    except ValueError:
                        continue

            # -------- Industrial Process Emissions --------
            for process in category.get("processes", []):
                name = process["name"]
                qty = request.form.get(f"qty_{name}")

                if qty:
                    try:
                        qty_val = float(qty)
                        if qty_val > 0:
                            emission = round(qty_val * process["emission_factor"])
                            results.append({
                                "category": cat_name,
                                "item": name,
                                "unit": process["unit"],
                                "qty": qty_val,
                                "factor": process["emission_factor"],
                                "emission": emission
                            })
                            total_emission += emission
                    except ValueError:
                        continue



        total_emission = round(total_emission, 2)
        # Save Scope 1 results to session for summary
        session["scope1_results"] = results
        session["scope1_total"] = total_emission

        return render_template(
            "scope1.html",
            categories=scope1_data,
            results=results,
            total=total_emission
        )

    # GET request
    return render_template("scope1.html", categories=scope1_data, results=None)

# -------- Scope 2 --------
@cal_bp.route("/scope2", methods=["GET", "POST"])
def scope2():
    results = []
    total_emission = 0.0

    if request.method == "POST":
        selected_countries = request.form.getlist("countries")
        for country in selected_countries:
            qty = request.form.get(f"qty_{country}")
            if qty and qty.strip():
                try:
                    qty_val = float(qty)
                    factor = scope2_data[country]["factor"]
                    unit = scope2_data[country]["unit"]
                    emission = round(qty_val * factor, 2)
                    results.append({
                        "country": country,
                        "unit": unit,
                        "qty": qty_val,
                        "factor": factor,
                        "emission": emission
                    })
                    total_emission += emission
                except ValueError:
                    continue

         # Save Scope 2 to session for summary
        
        total_emission = round(total_emission, 2)
        session["scope2_results"] = results
        session["scope2_total"] = total_emission


        return render_template(
            "scope2.html",
            countries=scope2_data,
            selected=request.form.getlist("countries"),
            results=results,
            total=total_emission
        )

    return render_template("scope2.html", countries=scope2_data, selected=None)

# -------- SCOPE 3 ROUTE --------
@cal_bp.route("/scope3", methods=["GET", "POST"])
def scope3():
    results = []
    total_emission = 0.0

    if request.method == "POST":

   
        for category in scope3_data:
            if category["Category"] == "Purchased goods & services":
                cat_name = category["Category"]

                for sub in category.get("SubCategories", []):
                    sub_name = sub["name"]

                    for item in sub.get("items", []):
                        name = item.get("Product") or item.get("Product/Service")
                        unit = item.get("Unit")
                        factor = item.get("EmissionFactor")

                        # 🔥 FIX: Use the correct form field name
                        qty = request.form.get(f"qty_{name}")

                        if qty:
                            try:
                                qty_val = float(qty)
                                if qty_val > 0:
                                    emission = round(qty_val * factor, 2)

                                    
                                    results.append({
                                        "category": f"{cat_name} → {sub_name}",
                                        "item": name,
                                        "unit": unit,
                                        "qty": qty_val,
                                        "factor": factor,
                                        "emission": emission
                                    })
                                    total_emission += emission
                            except (ValueError, TypeError):
                                continue
                                
          
        for category in scope3_data:
            if category["Category"] == "Capital Goods":
                cat_name = category["Category"]

                for item in category.get("Capital Goods", []):
                    name = item["Product/Service"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": "USD",        # <-- Hardcoded here
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue

        for category in scope3_data:
            if category["Category"] == "Fuel- and energy-related activities":
                cat_name = category["Category"]

                for item in category.get("Fuel- and energy-related activities", []):
                    fuel_name = item["Fuel"]
                    factors = item["EmissionFactors"]

                    # User selects a unit (e.g., "litres", "tonnes", "kWh (Net CV)")
                    selected_unit = request.form.get(f"unit_{fuel_name}")
                    qty = request.form.get(f"qty_{fuel_name}")

                    if qty and selected_unit and selected_unit in factors:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                factor = float(factors[selected_unit])
                                emission = round(qty_val * factor, 2)

                                results.append({
                                    "category": cat_name,
                                    "item": fuel_name,
                                    "unit": selected_unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue

        # -------- Upstream transportation and distribution --------
        for category in scope3_data:
            if category["Category"] == "Upstream transportation and distribution":
                cat_name = category["Category"]
                for item in category.get("Upstream transportation and distribution", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue



        # --------Waste generated in operations--------
        for category in scope3_data:
            if category["Category"] == "Waste generated in operations":
                cat_name = category["Category"]
                for item in category.get("Waste generated in operations", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


        # -------- Business Travel and Employee Commuting --------
        for category in scope3_data:
            if category["Category"] == "Business Travel":
                cat_name = category["Category"]
                for item in category.get("Business Travel", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


        # -------- Business Travel and Employee Commuting --------
        for category in scope3_data:
            if category["Category"] == "Employee Commuting":
                cat_name = category["Category"]
                for item in category.get("Employee Commuting", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


        for category in scope3_data:
            if category["Category"] == "Upstream Leased Assets":
                cat_name = category["Category"]
                for item in category.get("Upstream Leased Assets", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue



        # -------- Downstream Transportation and Distribution --------
        for category in scope3_data:
            if category["Category"] == "Downstream Transportation and Distribution":
                cat_name = category["Category"]
                for item in category.get("Downstream Transportation and Distribution", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


        for category in scope3_data:
            if category["Category"] == "Processing of Sold Products":
                cat_name = category["Category"]
                for item in category.get("Processing of Sold Products", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


 # -------- USE OF SOLD PRODUCTS (NEW) --------
        for category in scope3_data:
            if category["Category"] == "Use of Sold Products":
                cat_name = category["Category"]
                for item in category.get("Use of Sold Products", []):
                    asset_type = item["Asset Type"]
                    factor = item["EmissionFactor"]
                    
                    # Get all three inputs
                    units_sold = request.form.get(f"units_sold_{asset_type}")
                    energy_per_unit = request.form.get(f"energy_per_unit_{asset_type}")
                    product_lifetime = request.form.get(f"product_lifetime_{asset_type}")

                    if units_sold and energy_per_unit and product_lifetime:
                        try:
                            units_val = float(units_sold)
                            energy_val = float(energy_per_unit)
                            lifetime_val = float(product_lifetime)
                            
                            if units_val > 0 and energy_val > 0 and lifetime_val > 0:
                                # Formula: Units Sold × Energy/Unit/Year × Lifetime × Emission Factor
                                total_energy = units_val * energy_val * lifetime_val
                                emission = round(total_energy * factor, 2)
                                
                                results.append({
                                    "category": cat_name,
                                    "item": f"{asset_type} ({units_val} units, {energy_val} kWh/yr, {lifetime_val} yrs)",
                                    "unit": item["Unit"],
                                    "qty": total_energy,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except (ValueError, TypeError):
                            continue

        # -------- Downstream Transportation and Distribution --------
        for category in scope3_data:
            if category["Category"] == "End-of-life Treatment of Sold Products":
                cat_name = category["Category"]
                for item in category.get("End-of-life Treatment of Sold Products", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue


      # -------- Downstream Transportation and Distribution --------
        for category in scope3_data:
            if category["Category"] == "Downstream Leased Assets":
                cat_name = category["Category"]
                for item in category.get("Downstream Leased Assets", []):
                    name = item["Product/Service"]
                    unit = item["Unit"]
                    factor = item["EmissionFactor"]
                    qty = request.form.get(f"qty_{name}")

                    if qty:
                        try:
                            qty_val = float(qty)
                            if qty_val > 0:
                                emission = round(qty_val * factor, 2)
                                results.append({
                                    "category": cat_name,
                                    "item": name,
                                    "unit": unit,
                                    "qty": qty_val,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except ValueError:
                            continue

# Add these sections to your existing scope3() route in the POST method handler

        # -------- FRANCHISES (Category 14) --------
        for category in scope3_data:
            if category["Category"] == "Franchises":
                cat_name = category["Category"]
                
                # Get all franchise entries (dynamic form submission)
                franchise_names = request.form.getlist("franchise_name[]")
                avg_emissions = request.form.getlist("avg_emissions_per_site[]")
                num_sites = request.form.getlist("number_of_sites[]")
                
                for i in range(len(franchise_names)):
                    if franchise_names[i] and avg_emissions[i] and num_sites[i]:
                        try:
                            avg_val = float(avg_emissions[i])
                            sites_val = float(num_sites[i])
                            
                            if avg_val > 0 and sites_val > 0:
                                # Formula: Total Emissions = Avg per Site × Number of Sites
                                emission = round(avg_val * sites_val, 2)
                                
                                results.append({
                                    "category": cat_name,
                                    "item": f"{franchise_names[i]} ({sites_val} sites)",
                                    "unit": "tCO₂e",
                                    "qty": sites_val,
                                    "factor": avg_val,
                                    "emission": emission
                                })
                                total_emission += emission
                        except (ValueError, TypeError):
                            continue


        # -------- INVESTMENTS (Category 15) --------
        for category in scope3_data:
            if category["Category"] == "Investments":
                cat_name = category["Category"]
                
                for item in category.get("Investments", []):
                    sector = item["Sector"]
                    factor = item["EmissionFactor"]  # tCO₂e per Million USD
                    
                    # Get form inputs
                    investment_value = request.form.get(f"investment_value_{sector}")
                    equity_share = request.form.get(f"equity_share_{sector}")
                    
                    if investment_value and equity_share:
                        try:
                            inv_val = float(investment_value)  # in USD
                            equity_pct = float(equity_share)  # percentage
                            
                            if inv_val > 0 and equity_pct > 0:
                                # Formula: (Investment in millions) × Sector Intensity × (Equity % / 100)
                                inv_millions = inv_val / 1_000_000
                                emission = round(inv_millions * factor * (equity_pct / 100), 2)
                                
                                results.append({
                                    "category": cat_name,
                                    "item": f"{sector} (${inv_val:,.0f}, {equity_pct}% equity)",
                                    "unit": "tCO₂e",
                                    "qty": inv_millions,
                                    "factor": factor,
                                    "emission": emission
                                })
                                total_emission += emission
                        except (ValueError, TypeError):
                            continue

                # -------- Store Results --------
        session["scope3_results"] = results
        session["scope3_total"] = round(total_emission,2)

        return render_template(
            "scope3.html",
            categories=scope3_data,
            results=results,
         total=round(total_emission, 2)   # 🔥 FIX

        )

    # GET request
    return render_template("scope3.html", categories=scope3_data, results=None)


@cal_bp.route("/scope3_summary")
def scope3_summary():
    results = session.get("scope3_results", [])
    
    # Only include items where qty > 0
    entered_results = [r for r in results if r.get("qty", 0) > 0]
    
    # Grand total
    total = round(sum(r.get("emission", 0.0) for r in entered_results), 2)

    
    return render_template("scope3_summary.html", results=entered_results, total=total)



# ----------------- Summary Input Form -----------------
@cal_bp.route("/summary", methods=["GET", "POST"])
def summary():
    if request.method == "POST":
        # Collect user inputs
        session["total_revenue"] = float(request.form.get("revenue") or 0)
        session["total_employees"] = int(request.form.get("employees") or 1)
        session["target_emission"] = float(request.form.get("target_emission") or 0)
        return redirect(url_for("cal_bp.dashboard"))


    return render_template("summary_input.html") 



def aggregate_top_sources():
    """
    Read session-stored results from scope1, scope2, scope3,
    flatten them, sum by “category/item”, and return top 5 sources.
    """
    all_items = []
    for key in ("scope1_results", "scope2_results", "scope3_results"):
        items = session.get(key, [])
        all_items.extend(items)

    agg = {}
    for it in all_items:
        key_name = f"{it.get('category','')} — {it.get('item','')}"
        val = it.get("emission", 0.0)
        agg[key_name] = agg.get(key_name, 0.0) + val

    sorted_items = sorted(agg.items(), key=lambda x: x[1], reverse=True)
    top5 = sorted_items[:5]
    return [{"source": name, "value": value} for name, value in top5]

# ---------------------------------------------------------------------
# ROUTE: Dashboard
# ---------------------------------------------------------------------


@cal_bp.route("/dashboard")
def dashboard():
    import pyodbc

    conn = get_db_connection()
    cursor = conn.cursor()


    # --- Read totals from session safely ---
    total_scope1 = float(session.get("scope1_total") or 0.0)
    total_scope2 = float(session.get("scope2_total") or 0.0)
    total_scope3 = float(session.get("scope3_total") or 0.0)

    if total_scope1 < 0:
        total_scope1 = 0.0

    overall_total = total_scope1 + total_scope2 + total_scope3

    # --- Other session data ---
    revenue = float(session.get("total_revenue") or 1)
    employees = int(session.get("total_employees") or 1)
    target_emission = float(session.get("target_emission") or 0)

    total_tonnes = overall_total / 1000  # kg → tonnes

    emission_per_revenue = total_tonnes / revenue if revenue > 0 else 0
    emission_per_employee = total_tonnes / employees if employees > 0 else 0

    chart_data = {
        "labels": ["Scope 1", "Scope 2", "Scope 3"],
        "values": [total_scope1, total_scope2, total_scope3],
    }
    top_sources = aggregate_top_sources()

    # --- Gemini AI analysis ---
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel("models/gemini-2.5-pro")

    prompt = f"""
    You are a sustainability and environmental impact expert.

    The company reports:
    - Total Emissions: {overall_total:.2f} kgCO₂e (≈ {total_tonnes:.2f} tonnes)
    - Target Emissions: {target_emission:.2f} kgCO₂e

    Please provide:
    1️⃣ A short summary comparing total vs target (percentage difference).
    2️⃣ Three clear, actionable recommendations to reduce carbon emissions.

    Respond STRICTLY in JSON format:
    {{
      "comparison_to_target": "text summary",
      "recommendations": [
        "recommendation 1",
        "recommendation 2",
        "recommendation 3"
      ]
    }}
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=types.GenerationConfig(
                temperature=0.3,
                top_p=0.9,
            ),
        )
        raw = response.text.strip()
        if "```" in raw:
            raw = raw.split("```")[1].replace("json", "").strip()
        ai_data = json.loads(raw)
    except Exception as e:
        print("⚠️ Gemini AI Error:", e)
        ai_data = {
            "comparison_to_target": f"Emissions {total_tonnes:.2f} tCO₂e vs Target {target_emission/1000:.2f} tCO₂e",
            "recommendations": [
                "Review energy consumption in key facilities.",
                "Switch to renewable power sources.",
                "Improve operational efficiency through audits."
            ]
        }
    company_id = int(session.get("company_id"))

    # --- Store totals in CarbonEmission table ---
    cursor.execute("""
    INSERT INTO CarbonEmission
    (company_id, scope1_total, scope2_total, scope3_total, overall_total, revenue, employees, target_emission)
    OUTPUT INSERTED.id
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""",
company_id,
total_scope1,
total_scope2,
total_scope3,
overall_total,
revenue,
employees,
target_emission
)


    emission_id = int(cursor.fetchone()[0])  # Get inserted ID
    conn.commit()  # Then commit

    # --- Store detailed items ---
    for scope_key, scope_name in [
    ("scope1_results", "Scope1"),
    ("scope2_results", "Scope2"),
    ("scope3_results", "Scope3")
]:
     for item in session.get(scope_key, []):
        if scope_name == "Scope2":
            # Use 'country' for item if item missing
            category_val = item.get("category", "Electricity") or "Electricity"
            item_val = item.get("item") or item.get("country") or "N/A"
        else:
            category_val = item.get("category", "N/A") or "N/A"
            item_val = item.get("item", "N/A") or "N/A"

        cursor.execute("""
            INSERT INTO CarbonEmissionDetails
            (emission_id, scope, category, item, qty, unit, factor, emission)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        emission_id,
        scope_name,
        category_val,
        item_val,
        float(item.get("qty") or 0),
        item.get("unit", "N/A") or "N/A",
        float(item.get("factor") or 0),
        float(item.get("emission") or 0)
        )

    conn.commit()
    conn.close()

    # --- Render dashboard ---
    return render_template(
        "dashboard.html",
        total_scope1=total_scope1,
        total_scope2=total_scope2,
        total_scope3=total_scope3,
        overall_total=overall_total,
        emission_per_revenue=emission_per_revenue,
        emission_per_employee=emission_per_employee,
        chart_data=chart_data,
        top_sources=top_sources,
        target_emission=target_emission,
        ai_comparison=ai_data,
    )



